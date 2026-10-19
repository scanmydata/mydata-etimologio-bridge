"""HTTP client για τα myDATA REST endpoints.

Αμετάβλητος κανόνας: αυτό το module είναι το **μόνο** σημείο όπου στέλνονται
τα διαπιστευτήρια ΑΑΔΕ, και μόνο προς config.AADE_HOST. Το download/provider.py
έχει δικό του Session χωρίς auth headers, ώστε η διαρροή κλειδιού σε πάροχο να
είναι δομικά αδύνατη.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import requests

from ..config import (
    AADE_HOST,
    URL_REQUEST_DOCS,
    URL_REQUEST_E3_INFO,
    URL_REQUEST_MY_EXPENSES,
    URL_REQUEST_TRANSMITTED_DOCS,
    Settings,
)
from collections.abc import Callable

from ..models import Classification, Direction, Document, OperationCancelled
from .e3 import parse_e3
from .errors import AuthError, MydataError, RateLimitError, TransientError
from .parse import extract_cursors, parse_documents

log = logging.getLogger(__name__)

#: Αναμονές (δευτερόλεπτα) πριν από κάθε νέα προσπάθεια όταν η ΑΑΔΕ απαντά
#: «πολλά αιτήματα» (HTTP 429). Μέχρι την 0.4.39 ΔΕΝ υπήρχε καμία επανάληψη:
#: ένα 429 σε οποιαδήποτε σελίδα έριχνε ολόκληρη τη λήψη του πελάτη — και με
#: την ανακάλυψη όλης της χρήσης οι σελίδες ενός πελάτη με μεγάλη κίνηση είναι
#: δεκάδες. Μετρημένο σε πελάτη με ~18.000 εγγραφές: ~3–4 σελίδες περνούν, και
#: μετά η ΑΑΔΕ ζητά 10″ και αμέσως ~4½′ (Retry-After) — μία σελίδα μπορεί να
#: χρειαστεί 2–3 αναμονές, γι' αυτό το περιθώριο είναι γενναίο.
RATE_LIMIT_DELAYS: tuple[float, ...] = (10, 30, 60, 120, 300, 300, 300, 300)
#: Το ίδιο για 5xx / timeout: συνήθως περνούν σε λίγα δευτερόλεπτα.
TRANSIENT_DELAYS: tuple[float, ...] = (5, 15, 30)
#: Ανώτατο όριο σε ό,τι ζητήσει το Retry-After.
MAX_WAIT = 300.0


class MydataClient:
    def __init__(
        self,
        user: str,
        key: str,
        settings: Settings,
        *,
        retry: bool = True,
        on_wait: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        if not user or not key:
            from .errors import MissingKeyError

            raise MissingKeyError("λείπουν διαπιστευτήρια")
        self._headers = {"aade-user-id": user, "Ocp-Apim-Subscription-Key": key}
        self._settings = settings
        self._session = requests.Session()
        #: Ο έλεγχος κωδικών (διάλογος) δεν περιμένει λεπτά — απαντά αμέσως.
        self._retry = retry
        self._on_wait = on_wait
        self._should_cancel = should_cancel
        #: Πόσες φορές χρειάστηκε αναμονή — για την αναφορά στο τέλος.
        self.waits = 0

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> MydataClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self, seconds: float, why: str) -> None:
        """Αναμονή που ακούει την «Ακύρωση» και λέει στον χρήστη τι γίνεται."""
        self.waits += 1
        if self._on_wait:
            self._on_wait(f"{why} — νέα προσπάθεια σε {_clock(seconds)}")
        log.warning("%s — αναμονή %.0fs", why, seconds)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._should_cancel and self._should_cancel():
                raise OperationCancelled()
            time.sleep(min(0.25, max(0.0, end - time.monotonic())))

    def _get(self, url: str, params: dict[str, str]) -> bytes:
        """Ένα αίτημα, με επανάληψη σε «πολλά αιτήματα» (429) και 5xx/timeout."""
        rate_left = list(RATE_LIMIT_DELAYS) if self._retry else []
        transient_left = list(TRANSIENT_DELAYS) if self._retry else []
        while True:
            try:
                return self._get_once(url, params)
            except RateLimitError as exc:
                if not rate_left:
                    raise
                delay = rate_left.pop(0)
                if exc.retry_after:
                    delay = min(max(delay, exc.retry_after), MAX_WAIT)
                self._wait(delay, "Η ΑΑΔΕ έβαλε προσωρινό περιορισμό αιτημάτων")
            except TransientError:
                if not transient_left:
                    raise
                self._wait(transient_left.pop(0), "Η ΑΑΔΕ δεν απάντησε σωστά")

    def _get_once(self, url: str, params: dict[str, str]) -> bytes:
        if urlsplit(url).netloc != AADE_HOST:
            raise ValueError(f"Τα διαπιστευτήρια ΑΑΔΕ δεν στέλνονται στο {url!r}")
        try:
            resp = self._session.get(
                url, params=params, headers=self._headers, timeout=self._settings.aade_timeout
            )
        except requests.Timeout as exc:
            raise TransientError("timeout") from exc
        except requests.RequestException as exc:
            raise TransientError(str(exc)) from exc

        if resp.status_code == 403:
            # Μετρημένο: κενό body. Μην προσπαθήσεις να παρσάρεις XML.
            raise AuthError(resp.text[:200] if resp.content else "403 χωρίς σώμα απάντησης")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise RateLimitError(float(retry_after) if retry_after else None)
        if resp.status_code >= 500:
            raise TransientError(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise TransientError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def fetch(
        self,
        direction: Direction,
        *,
        mark: str = "0",
        date_from: str | None = None,
        date_to: str | None = None,
        entity_vat: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[Document]:
        """Κατεβάζει όλα τα παραστατικά μιας κατεύθυνσης, με pagination.

        Το RequestTransmittedDocs παίρνει τον **ίδιο** βρόχο pagination με το
        RequestDocs. Το fetch.py:275-286 κάνει ένα μόνο GET χωρίς cursors, που
        σιωπηλά κόβει αποτελέσματα σε μεγάλα διαστήματα.
        """
        url = (
            URL_REQUEST_DOCS
            if direction is Direction.INCOMING
            else URL_REQUEST_TRANSMITTED_DOCS
        )
        current_mark = (mark or "0").strip() or "0"
        params: dict[str, str] = {"mark": current_mark}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if entity_vat:
            params["entityVatNumber"] = entity_vat

        collected: dict[str, Document] = {}
        resume_guard: set[str] = set()
        try:
            self._fetch_pages(url, params, current_mark, date_from, date_to,
                              entity_vat, collected, resume_guard, should_cancel,
                              direction)
        except MydataError as exc:
            # Ό,τι πρόλαβε να έρθει δεν πετιέται: ο καλών το κρατά, χωρίς να
            # προχωρήσει cursor ή κάλυψη (η ουρά θα ξαναζητηθεί).
            exc.partial = list(collected.values())  # type: ignore[attr-defined]
            raise
        return list(collected.values())

    def _fetch_pages(
        self, url, params, current_mark, date_from, date_to, entity_vat,
        collected, resume_guard, should_cancel, direction,
    ) -> None:
        while True:
            # Ακύρωση ανάμεσα στις σελίδες: ένα μεγάλο διάστημα μπορεί να έχει
            # δεκάδες σελίδες — χωρίς αυτό η ακύρωση δεν «πιανόταν» μέχρι το τέλος.
            if should_cancel and should_cancel():
                raise OperationCancelled()
            payload = self._get(url, params)
            docs, cursors = parse_documents(payload, direction)

            page_max = current_mark
            for doc in docs:
                if doc.mark and doc.mark not in collected:
                    collected[doc.mark] = doc
                if doc.mark.isdigit() and int(doc.mark) > int(page_max or 0):
                    page_max = doc.mark

            npk, nrk = cursors["nextPartitionKey"], cursors["nextRowKey"]
            token = cursors["nextPartitionToken"]

            if npk or nrk:
                params.pop("nextPartitionToken", None)
                params["nextPartitionKey"] = npk
                params["nextRowKey"] = nrk
                continue

            if token:
                params.pop("nextPartitionKey", None)
                params.pop("nextRowKey", None)
                params["nextPartitionToken"] = token
                continue

            # Fallback (fetch.py:242-258): κατά καιρούς η ΑΑΔΕ παραλείπει τα
            # cursors ενώ υπάρχουν κι άλλες εγγραφές. Ξαναρωτάμε με το
            # μεγαλύτερο MARK της σελίδας ως νέο κατώφλι. Το resume_guard
            # αποτρέπει ατέρμονο βρόχο αν το ίδιο MARK ξαναγυρίσει.
            if docs and page_max and page_max != current_mark and page_max not in resume_guard:
                resume_guard.add(page_max)
                current_mark = page_max
                params = {"mark": current_mark}
                if date_from:
                    params["dateFrom"] = date_from
                if date_to:
                    params["dateTo"] = date_to
                if entity_vat:
                    params["entityVatNumber"] = entity_vat
                log.debug("Resume από MARK %s", current_mark)
                continue

            break

    def fetch_e3(
        self,
        *,
        mark: str = "0",
        date_from: str | None = None,
        date_to: str | None = None,
        entity_vat: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Classification]:
        """MARK -> κατάσταση χαρακτηρισμού.

        Επιστρέφει μόνο όσα MARK έχουν εγγραφή E3· τα υπόλοιπα μένουν UNKNOWN
        (δεν υπόκεινται σε χαρακτηρισμό εξόδων).

        Το fetch.py:299-302 διευρύνει το dateTo κατά 3 μήνες. Δεν χρειάζεται
        εδώ: το IssueDate της εγγραφής E3 είναι η ημερομηνία έκδοσης του
        παραστατικού, οπότε το ίδιο παράθυρο επιστρέφει τα ίδια MARK
        (επιβεβαιωμένο: 29 εγγραφές E3 για 34 παραστατικά Ιουλίου).
        """
        params: dict[str, str] = {"mark": (mark or "0").strip() or "0"}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if entity_vat:
            params["entityVatNumber"] = entity_vat

        result: dict[str, Classification] = {}
        seen_tokens: set[str] = set()

        while True:
            if should_cancel and should_cancel():
                raise OperationCancelled()
            payload = self._get(URL_REQUEST_E3_INFO, params)
            result.update(parse_e3(payload))

            from xml.etree import ElementTree as ET

            cursors = extract_cursors(ET.fromstring(payload))
            npk, nrk = cursors["nextPartitionKey"], cursors["nextRowKey"]
            token = cursors["nextPartitionToken"]

            if npk or nrk:
                signature = f"{npk}|{nrk}"
                if signature in seen_tokens:
                    break
                seen_tokens.add(signature)
                params.pop("nextPartitionToken", None)
                params["nextPartitionKey"] = npk
                params["nextRowKey"] = nrk
                continue
            if token:
                if token in seen_tokens:
                    break
                seen_tokens.add(token)
                params.pop("nextPartitionKey", None)
                params.pop("nextRowKey", None)
                params["nextPartitionToken"] = token
                continue
            break

        return result

    # --- έλεγχος διαπιστευτηρίων -------------------------------------------
    def check_credentials(
        self, *, date_from: str, date_to: str, entity_vat: str | None = None
    ) -> int:
        """Ρωτά το ``RequestMyExpenses`` και επιστρέφει πόσες γραμμές γύρισαν.

        ΓΙΑΤΙ ΑΥΤΟ ΤΟ ENDPOINT και όχι το `RequestDocs`: ο έλεγχος τρέχει τη
        στιγμή που καταχωρείται ο πελάτης, μέσα σε ένα παράθυρο διαλόγου. Το
        `RequestDocs` θα κατέβαζε ολόκληρα παραστατικά — δεκάδες MB XML για μια
        ερώτηση ναι/όχι. Τα «σύνολα εξόδων» της §4.2.9 απαντούν το ίδιο πράγμα
        με μία μικρή σελίδα, χωρίς pagination.

        **Μηδέν γραμμές ΔΕΝ σημαίνει αποτυχία**: ένας πελάτης μπορεί κάλλιστα να
        μην έχει έξοδα τον τρέχοντα μήνα. Η απάντηση HTTP 200 είναι από μόνη της
        η απόδειξη ότι τα διαπιστευτήρια έγιναν δεκτά — το λάθος κλειδί γυρίζει
        403 (`AuthError`) με κενό σώμα.
        """
        params: dict[str, str] = {"dateFrom": date_from, "dateTo": date_to}
        if entity_vat:
            params["entityVatNumber"] = entity_vat
        payload = self._get(URL_REQUEST_MY_EXPENSES, params)
        return _count_elements(payload)


def _clock(seconds: float) -> str:
    """272 -> «4:32 λεπτά», 30 -> «30 δευτ.» (χωρίς σύμβολα ′″, που δεν
    υπάρχουν σε κάθε κωδικοσελίδα κονσόλας/αρχείου καταγραφής)."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} δευτ."
    return f"{seconds // 60}:{seconds % 60:02d} λεπτά"


def _count_elements(payload: bytes) -> int:
    """Πόσα «παιδιά» έχει η ρίζα της απάντησης.

    Δεν παρσάρουμε το σχήμα των συνόλων: ο έλεγχος ενδιαφέρεται για το αν
    απάντησε η ΑΑΔΕ, όχι για το τι είπε. Ένα XML που δεν διαβάζεται μετρά ως
    μηδέν αντί να ρίξει τον διάλογο.
    """
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return 0
    return sum(1 for _ in root)
