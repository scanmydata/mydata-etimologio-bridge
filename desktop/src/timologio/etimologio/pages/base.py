"""Shared plumbing for the native e-Τιμολόγιο pages."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal

from ...gui.widgets import resort as _resort
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: Injected worker: ``run(fn, on_ok, on_err)`` runs ``fn`` off the UI thread and
#: delivers the result on the main thread. The shell passes its ``QThreadPool``
#: helper; tests pass a synchronous stub.
RunFn = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[str], None]], None]

#: Zero-arg accessor for the live client (may be ``None`` before login).
ClientFn = Callable[[], Any]

_MONEY_RE = re.compile(r"[^0-9,.\-]")

#: Ο ρόλος όπου κάθε γραμμή κρατά τη θέση της στα δεδομένα. Μόλις ο πίνακας
#: ταξινομηθεί, η οπτική σειρά παύει να συμπίπτει με τη σειρά φόρτωσης — χωρίς
#: αυτόν τον δείκτη, το «επιλεγμένο» θα ήταν άλλη εγγραφή από αυτή που βλέπει
#: ο χρήστης, και οι διαγραφές θα έσβηναν λάθος πράγματα.
ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 7


def parse_money(value: Any) -> float:
    """Parse a Greek-formatted money string (``1.234,56 €``) to a float.

    Returns ``0.0`` for blanks or garbage — totals must never raise while a
    table is being filled from whatever the AADE HTML scrape produced.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = _MONEY_RE.sub("", str(value or "")).strip()
    if not text:
        return 0.0
    # Greek grouping: dot = thousands, comma = decimals. Drop dots, comma→dot.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def date_key(value: Any) -> tuple[int, int, int]:
    """(έτος, μήνας, ημέρα) από «dd/MM/yyyy» **ή** «yyyy-mm-dd».

    Οι δύο μορφές συνυπάρχουν επίτηδες: η ΑΑΔΕ δίνει ελληνική μορφή, η τοπική
    βάση κρατά ISO (γιατί εκεί η ημερομηνία συγκρίνεται ως κείμενο). Ό,τι τις
    ανακατεύει — η ενιαία κίνηση της καρτέλας — περνά από εδώ.
    """
    text = str(value or "").strip()[:10]
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return (int(parts[2]), int(parts[1]), int(parts[0]))
    if "-" in text:
        parts = text.split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return (int(parts[0]), int(parts[1]), int(parts[2]))
    return (0, 0, 0)


def fmt_date(value: Any) -> str:
    """Ημερομηνία για ανθρώπους: «dd/MM/yyyy», από οποιαδήποτε από τις δύο μορφές."""
    year, month, day = date_key(value)
    if not year:
        return str(value or "")
    return f"{day:02d}/{month:02d}/{year}"


def fmt_money(value: float) -> str:
    """Format a float as ``1.234,56`` (Greek grouping) for display."""
    return f"{value:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def cached_then_live(
    run: RunFn,
    client: Any,
    kind: str,
    live: Callable[[], Any],
    on_rows: Callable[[list[dict[str, Any]], bool], None],
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Δείχνει αμέσως την τοπική cache, και ανανεώνει από την ΑΑΔΕ από πίσω.

    Το web το κάνει έτσι (``cachedThenSync``) και γι' αυτό ανοίγει ακαριαία. Η
    εφαρμογή υπολογιστή ρωτούσε κάθε φορά την ΑΑΔΕ: μετρημένα **4,3 δευτερόλεπτα
    για το πελατολόγιο** και ~5 συνολικά, με τον επιλογέα πελάτη άδειο σε όλο
    αυτό το διάστημα — που μοιάζει με «το dropdown δεν έχει τίποτα».

    Το ``on_rows(rows, from_cache)`` καλείται μία ή δύο φορές: πρώτα με τα
    caches (αν υπάρχουν) και μετά με τα ζωντανά.

    **Το ζωντανό βήμα πρέπει να είναι το ``sync``**: μόνο αυτό γράφει το
    snapshot στη βάση (``cache_set``). Καλώντας το απλό ``list_*`` η cache δεν
    γεμίζει ποτέ και η επόμενη φόρτωση ξαναπερίμενε την ΑΑΔΕ.
    """
    #: Έδειξε η cache κάτι; Μόνο τότε αξίζει να προστατευτεί από ένα άδειο sync.
    showed_cache = False

    def live_ok(data: dict[str, Any]) -> None:
        rows = rows_of(data)
        # Ένα άδειο sync δεν σβήνει ό,τι έδειξε η cache. Αν όμως η cache δεν
        # έδειξε τίποτα, το «άδειο» ΕΙΝΑΙ η απάντηση και πρέπει να φτάσει: μια
        # καινούργια εταιρεία χωρίς σειρές έμενε με τελείως άδειο dropdown —
        # ούτε «➕ Νέα σειρά…», ούτε προειδοποίηση.
        if rows or not showed_cache:
            on_rows(rows, False)

    def start_live(*_args: Any) -> None:
        run(live, live_ok, on_error or (lambda _m: None))

    def cache_ok(data: dict[str, Any]) -> None:
        nonlocal showed_cache
        rows = data.get("rows") or []
        if rows:
            showed_cache = True
            on_rows(list(rows), True)
        # Το ζωντανό ξεκινά ΜΕΤΑ την ανάγνωση της cache, όχι παράλληλα: ο
        # ενσωματωμένος server της PHP εξυπηρετεί **σειριακά**, οπότε μια
        # παράλληλη γρήγορη ανάγνωση περίμενε πίσω από ένα sync 4 δευτερολέπτων
        # και η cache δεν πρόφταινε να ωφελήσει κανέναν.
        start_live()

    run(lambda: client.cached(kind), cache_ok, start_live)


def rows_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Οι γραμμές μιας απάντησης, όποιο κι αν είναι το κλειδί τους."""
    if not isinstance(data, dict):
        return []
    # Η σειρά μετράει μόνο για απαντήσεις με πολλά κλειδιά· το «rows» μένει
    # τελευταίο γιατί είναι το γενικό κλειδί των snapshot.
    for key in ("customers", "products", "series", "categories",
                "product_categories", "temp_invoices", "invoices",
                "deductions", "items", "rows"):
        value = data.get(key)
        if isinstance(value, list):
            return list(value)
    return []


class EtimPage(QWidget):
    """Base for a native page: gives access to the client and the worker."""

    def __init__(
        self,
        get_client: ClientFn,
        run: RunFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_client = get_client
        self._run = run

    def client(self) -> Any:
        return self._get_client()


class ListPage(EtimPage):
    """A back-bar + toolbar + table + status list page.

    Subclasses set ``columns``/``rows_key``, implement :meth:`fetch`, and add
    their own buttons to ``self.toolbar`` (a ``QHBoxLayout``). The table, refresh,
    row access and status line are handled here.
    """

    go_back = Signal()

    def __init__(
        self,
        get_client: ClientFn,
        run: RunFn,
        *,
        title: str,
        columns: list[tuple[str, str]],
        rows_key: str,
        subtitle: str = "",
        stretch_col: int = -1,
        newest_first: int | None = None,
        cache_kind: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(get_client, run, parent)
        self._columns = columns
        self._rows_key = rows_key
        #: Το είδος snapshot που ξέρει το backend (`?sync=`/`?cached=`). Όταν
        #: δίνεται, η σελίδα ανοίγει από την τοπική cache και ανανεώνεται από
        #: πίσω, αντί να περιμένει την ΑΑΔΕ με άδειο πίνακα.
        self._cache_kind = cache_kind
        self._rows: list[dict[str, Any]] = []

        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)
        # Το ← ζει στη μόνιμη μπάρα του κελύφους — ένα για όλη την εφαρμογή.
        self.toolbar = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-size:16px;font-weight:600;")
        self.toolbar.addWidget(label)
        self.toolbar.addStretch(1)
        refresh = QPushButton("Ανανέωση")
        refresh.clicked.connect(self.refresh)
        self.toolbar.addWidget(refresh)
        box.addLayout(self.toolbar)
        if subtitle:
            from . import ui as _ui

            box.addWidget(_ui.page_hint(subtitle))

        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([h for h, _ in columns])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        if stretch_col >= 0:
            self.table.horizontalHeader().setSectionResizeMode(
                stretch_col, QHeaderView.ResizeMode.Stretch
            )
        box.addWidget(self.table, 1)
        # Ταξινόμηση + φίλτρα στήλης, όπως στους πίνακες του Downloader.
        from . import ui as _ui

        # `newest_first`: η στήλη ημερομηνίας μιας ροής (ειδοποιήσεις,
        # παραστατικά, πρόχειρα). Χωρίς αυτό η λίστα ανοίγει αύξουσα και το πιο
        # πρόσφατο — αυτό που ψάχνει κανείς — κρύβεται στο τέλος.
        self._filter = _ui.make_sortable(
            self.table, f"list/{rows_key}",
            default_column=newest_first,
            filter_columns=[c for c in range(len(columns)) if columns[c][1] != "_check"],
        )

        self.status = QLabel("")
        self.status.setObjectName("muted")
        box.addWidget(self.status)
        self._box = box

    # subclasses override -------------------------------------------------
    def fetch(self, client: Any) -> dict[str, Any]:
        raise NotImplementedError

    # shared --------------------------------------------------------------
    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        self.status.setText("Φόρτωση…")
        if not self._cache_kind:
            self._run(lambda: self.fetch(client), self._fill, self._failed)
            return
        kind = self._cache_kind
        # Το αποτέλεσμα ξαναγίνεται απάντηση backend ώστε να περάσει από το
        # ΙΔΙΟ `_fill` — οι υποκλάσεις το επεκτείνουν (π.χ. στήλη επιλογής στα
        # Πρόχειρα) και δεν πρέπει να υπάρχει δεύτερος δρόμος γεμίσματος.
        cached_then_live(
            self._run, client, kind, lambda: client.sync(kind),
            lambda rows, from_cache: self._fill(
                {self._rows_key: rows, "_from_cache": from_cache}
            ),
            self._failed,
        )

    def _fill(self, data: dict[str, Any]) -> None:
        from . import ui as _ui

        self._rows = list(data.get(self._rows_key, []))
        # Η ταξινόμηση κλείνει όσο γεμίζει ο πίνακας: αλλιώς κάθε setItem
        # ξαναταξινομεί και οι γραμμές μπερδεύονται με τα _rows.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, (header, key) in enumerate(self._columns):
                text = str(row.get(key, ""))
                if "Ημ/νία" in header:
                    item = _ui.date_cell(text)
                elif any(word in header for word in ("Τιμή", "Ποσό", "Αξία", "Α/Α")):
                    item = _ui.money_cell(text)
                else:
                    item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(ROW_ROLE, r)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        _resort(self.table)
        note = "   ·   τοπικά, ανανέωση από ΑΑΔΕ…" if data.get("_from_cache") else ""
        self.status.setText(f"{len(self._rows)} εγγραφές{note}")

    def _failed(self, msg: str) -> None:
        self.status.setText(f"Σφάλμα: {msg}")

    def row_at(self, table_row: int) -> dict[str, Any] | None:
        """Η εγγραφή που αντιστοιχεί σε μια ΟΠΤΙΚΗ γραμμή του πίνακα."""
        item = self.table.item(table_row, 0)
        index = item.data(ROW_ROLE) if item is not None else None
        if index is None:
            index = table_row          # πίνακας χωρίς δείκτη (π.χ. άδειος)
        index = int(index)
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def selected_row(self) -> dict[str, Any] | None:
        return self.row_at(self.table.currentRow())
