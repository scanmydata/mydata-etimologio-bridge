"""Ο ψηφιακός βοηθός — ο δρομολογητής προθέσεων, χωρίς Qt.

Μεταφορά του `cbHandle` του `app.php` σε Python. Κρατά τη λογική **καθαρή**:
δέχεται κείμενο, επιστρέφει μια :class:`Reply` που περιγράφει *τι να γίνει*, και
δεν αγγίζει ούτε widget ούτε δίκτυο. Έτσι ολόκληρος ο βοηθός δοκιμάζεται χωρίς
παράθυρο και χωρίς ΑΑΔΕ.

Γιατί όχι έτοιμη βιβλιοθήκη NLU: το λεξιλόγιο είναι μικρό και σταθερό (ρήματα
τιμολόγησης), ενώ ένα μοντέλο θα πρόσθετε megabytes και εξάρτηση από CDN —
ασύμβατο με offline εγκατάσταση.

**Αμετάβλητος κανόνας, ίδιος με το web: ο βοηθός φτιάχνει μόνο ΠΡΟΧΕΙΡΟ.** Δεν
υπάρχει πεδίο ή διαδρομή εδώ που να ζητά οριστική έκδοση· το ΜΑΡΚ βγαίνει μόνο
από το κόκκινο κουμπί της Έκδοσης, με τη δική του επιβεβαίωση.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

# --- κανονικοποίηση -----------------------------------------------------------
# Πεζά + αφαίρεση τόνων/διαλυτικών, ώστε «καρτέλα», «ΚΑΡΤΕΛΑ» και «καρτελα» να
# είναι το ίδιο πράγμα — αλλιώς κάθε λέξη θα έμπαινε δύο φορές στους πίνακες.
_ACCENTS = {
    "ά": "α", "ὰ": "α", "ᾶ": "α",
    "έ": "ε", "ὲ": "ε",
    "ή": "η", "ὴ": "η", "ῆ": "η",
    "ί": "ι", "ὶ": "ι", "ῖ": "ι", "ϊ": "ι", "ΐ": "ι",
    "ό": "ο", "ὸ": "ο",
    "ύ": "υ", "ὺ": "υ", "ῦ": "υ", "ϋ": "υ", "ΰ": "υ",
    "ώ": "ω", "ὼ": "ω", "ῶ": "ω",
    "ς": "σ",
}
_TRANS = str.maketrans(_ACCENTS)


def normalize(text: str) -> str:
    """Πεζά, χωρίς τόνους, με τελικό σίγμα ίδιο με το μεσαίο."""
    return (text or "").lower().translate(_TRANS)


# --- πλοήγηση -----------------------------------------------------------------
#: Ενότητα → λέξεις-κλειδιά (κανονικοποιημένες). Η σειρά μετράει: το πρώτο
#: ταίριασμα κερδίζει, όπως στο web.
NAV: list[tuple[str, tuple[str, ...]]] = [
    ("issue",         ("εκδοση παραστατικου", "νεο παραστατικο", "εκδοση")),
    # Στο web τα εκδοθέντα ζουν μέσα στην Καρτέλα· η εφαρμογή υπολογιστή έχει
    # ξεχωριστή σελίδα «Παραστατικά».
    ("documents",     ("παραστατικα", "τιμολογια μου", "λιστα παραστατικων",
                       "αναζητηση παραστατικ")),
    ("bulk",          ("μαζικη εκδοση", "μαζικ")),
    ("customers",     ("πελατ", "καρτελ")),
    ("payments",      ("τραπεζ", "extrait", "εξτρε", "εισαγωγη πληρωμ", "πληρωμ", "ταμει")),
    ("products",      ("ειδη", "ειδοσ", "προιοντ", "καταλογο")),
    ("series",        ("σειρ", "αριθμηση")),
    ("drafts",        ("προχειρ", "προσχεδι")),
    ("credit",        ("ακυρωσ", "πιστωτικ")),
    ("schedule",      ("προγραμματισμ", "χρονοπρογραμμ")),
    ("stats",         ("στατιστικ", "γραφημ")),
    ("notifications", ("ειδοποιησ", "αδιαβαστ")),
    ("settings",      ("ρυθμισ", "2fa", "κωδικο", "authenticator")),
    ("admin",         ("διαχειρισ", "χρηστ", "ρολο", "προσκλησ", "εταιρει")),
]

#: Ρήματα που δηλώνουν ρητή πλοήγηση. Χωρίς αυτά το «πήγαινε στα παραστατικά»
#: θα περνούσε για εντολή έκδοσης, γιατί περιέχει «παραστατ».
_NAV_VERB = re.compile(r"πηγαινε|ανοιξε|go to|open|δειξε|εμφανισε|παμε|βγαλε μου")

HELP_TEXT = (
    "Μπορώ (πάντα ως ΠΡΟΧΕΙΡΟ — καμία οριστική έκδοση χωρίς εσένα):\n"
    "📄 Έκδοση: «έκδοση τιμολογίου στον 802576637 καθαρή αξία 100 "
    "με παρακράτηση 20% είδος συντήρηση»\n"
    "👥 Δεδομένα: «νέος πελάτης <ΑΦΜ>» · «νέο είδος <περιγραφή> <τιμή> ευρώ» · «νέα σειρά»\n"
    "🖨️ Εκτυπώσεις: «μαζική εκτύπωση» · «ZIP παραστατικών»\n"
    "💶 Ταμείο: «πληρωμές» · «εισαγωγή από τράπεζα»\n"
    "⏰ Αυτοματισμοί: «προγραμματισμός» · «πόσες αδιάβαστες ειδοποιήσεις»\n"
    "⚙️ Λογαριασμός: «ρυθμίσεις» · «2FA» · «διαχείριση»\n"
    "📊 Ερωτήσεις: «πόσα τιμολόγια φέτος» · «τζίρος μήνα»\n"
    "🧭 Πλοήγηση: «πήγαινε στους πελάτες / στα είδη / στις σειρές / στα πρόχειρα…»\n\n"
    "ℹ️ ΜΑΡΚ παίρνει το παραστατικό μόνο όταν πατήσεις εσύ το κόκκινο "
    "«Οριστική Έκδοση»."
)


@dataclass
class DraftSpec:
    """Ό,τι χρειάζεται η Έκδοση για να ετοιμάσει ένα πρόχειρο."""

    vat: str = ""
    name: str = ""
    #: Κωδικός είδους από τον κατάλογο (αυτό φεύγει στην ΑΑΔΕ).
    code: str = ""
    #: Η περιγραφή όπως την είπε ο χρήστης, όταν δεν βρέθηκε κωδικός.
    item: str = ""
    qty: float = 1.0
    price: float | None = None
    withholding_pct: float | None = None
    retail: bool = False


@dataclass
class Reply:
    """Τι απαντά ο βοηθός και τι ζητά από το κέλυφος να κάνει.

    Κάθε πεδίο είναι προαιρετικό: ο host εκτελεί όσα βρει γεμάτα.
    """

    say: str
    #: Κλειδί ενότητας για πλοήγηση («issue», «drafts», …).
    navigate: str = ""
    #: Ασύγχρονο ερώτημα που πρέπει να κάνει ο host: «stats:year|month» ή
    #: «notifications». Η απάντηση γυρίζει με :meth:`Assistant.report`.
    fetch: str = ""
    #: Διάλογος προς άνοιγμα: «customer» ή «product».
    dialog: str = ""
    prefill: dict[str, Any] = field(default_factory=dict)
    #: Όταν είναι γεμάτο, ο host ετοιμάζει ΠΡΟΧΕΙΡΟ με αυτά τα στοιχεία.
    draft: DraftSpec | None = None
    #: Κουμπιά συντόμευσης: (ετικέτα, κείμενο που στέλνεται με το πάτημα).
    choices: tuple[tuple[str, str], ...] = ()


#: Πηγή δεδομένων: δύο callables που δίνουν τα *ήδη φορτωμένα* πελατολόγιο και
#: κατάλογο ειδών. Ο βοηθός δεν κάνει δίκτυο μόνος του.
Rows = Callable[[], Sequence[dict[str, Any]]]


# --- βοηθητικά ----------------------------------------------------------------
def _number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_issue(text: str) -> DraftSpec:
    """Ελεύθερο κείμενο → δομημένη εντολή έκδοσης."""
    spec = DraftSpec()
    afm = re.search(r"\b(\d{9})\b", text)
    if afm:
        spec.vat = afm.group(1)

    ref = re.search(
        r"(?:στην|στον|στη|στο|πελατ\S*|πελάτ\S*|για\s+τον?ν?)\s+"
        r"([\w&.\-]+(?:\s+[\w&.\-]+){0,3})",
        text,
        re.IGNORECASE | re.UNICODE,
    )
    if ref:
        spec.name = re.sub(
            r"\s+(καθαρ\S*|ποσ[όο]|αξ[ίι]α|με|ε[ίι]δος|παρακρ\S*|,).*$",
            "",
            ref.group(1),
            flags=re.IGNORECASE,
        ).strip()
        if spec.name.isdigit():
            spec.name = ""

    price = _number(r"καθαρ\S*\s*αξ\S*\s*(\d+(?:[.,]\d+)?)", text)
    if price is None:
        price = _number(r"(?:ποσ[όο]|αξ[ίι]α)\s*(\d+(?:[.,]\d+)?)", text)
    if price is None:
        price = _number(r"(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)", text)
    spec.price = price

    spec.withholding_pct = _number(
        r"παρακρ\S*\s*(?:φ[όο]ρου)?\s*(\d+(?:[.,]\d+)?)\s*%", text
    )

    item = re.search(r"ε[ίι]δος\s*[:\-]?\s*(.+)$", text, re.IGNORECASE)
    if item:
        spec.item = re.sub(
            r"\s*(με\s+παρακρ\S*.*|καθαρ\S*\s*αξ\S*.*)$",
            "",
            item.group(1),
            flags=re.IGNORECASE,
        ).strip()

    qty = _number(r"(\d+(?:[.,]\d+)?)\s*(?:τεμ|τεμάχ|τεμαχ|\bx\b|\bχ\b)", text)
    spec.qty = qty or 1.0
    return spec


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def resolve_customer(rows: Sequence[dict[str, Any]], name: str, vat: str) -> dict | None:
    """Ο πελάτης που ταιριάζει σε ΑΦΜ ή επωνυμία — ή ``None``."""
    if vat:
        for row in rows:
            if _text(row, "vat", "afm") == vat:
                return row
    if name:
        needle = normalize(name)
        exact = [r for r in rows if normalize(_text(r, "name", "customer_name")) == needle]
        if exact:
            return exact[0]
        partial = [r for r in rows if needle in normalize(_text(r, "name", "customer_name"))]
        if partial:
            return partial[0]
    return None


def find_product(rows: Sequence[dict[str, Any]], description: str) -> str:
    """Ο κωδικός του είδους που ταιριάζει καλύτερα στην περιγραφή («» αν κανένα).

    Ίδια βαθμολόγηση με το web: πλήρης εμφωλευμός μετράει 5, κάθε κοινή λέξη
    ≥4 γραμμάτων μετράει 1, και κάτω από 2 δεν το θεωρούμε εύρημα — αλλιώς μια
    τυχαία λέξη θα διάλεγε λάθος είδος και θα έφευγε λάθος κωδικός στην ΑΑΔΕ.
    """
    if not description:
        return ""
    needle = normalize(description)
    best, best_score = "", 0
    for row in rows:
        code = _text(row, "code", "product_code")
        desc = normalize(_text(row, "description", "product_description"))
        if not code or len(desc) < 3:
            continue
        score = 0
        if needle in desc or desc in needle:
            score += 5
        score += sum(1 for word in desc.split() if len(word) >= 4 and word in needle)
        if score > best_score:
            best, best_score = code, score
    return best if best_score >= 2 else ""


class Assistant:
    """Ο δρομολογητής προθέσεων, με μνήμη για ημιτελείς ροές."""

    def __init__(self, customers: Rows, products: Rows) -> None:
        self._customers = customers
        self._products = products
        #: (στάδιο, εντολή) όσο εκκρεμεί ερώτηση· ``None`` όταν δεν εκκρεμεί.
        self._pending: tuple[str, DraftSpec] | None = None

    # --- κατάσταση ---------------------------------------------------------
    @property
    def pending(self) -> str:
        return self._pending[0] if self._pending else ""

    def reset(self) -> None:
        self._pending = None

    # --- είσοδος -----------------------------------------------------------
    def handle(self, text: str) -> Reply:
        raw = (text or "").strip()
        speech = normalize(raw)
        if not speech:
            return Reply("Δεν άκουσα κάτι.")

        # Πάντα διαθέσιμη έξοδος: χωρίς αυτό μια ημιτελής ροή «κρατούσε» τον
        # βοηθό και κάθε επόμενη εντολή καταναλωνόταν ως απάντηση σε παλιά
        # ερώτηση.
        if re.fullmatch(r"(ακυρο|ακυρωση|σταματα|ξεχνα το|cancel|stop)", speech.strip()):
            if self._pending:
                self._pending = None
                return Reply("Εντάξει, το ακύρωσα.")
            return Reply("Δεν εκκρεμεί κάτι.")

        if self._pending:
            return self._continue(raw, speech)

        # Ρητή πλοήγηση ΠΡΩΤΑ.
        if _NAV_VERB.search(speech):
            for view, keys in NAV:
                if any(key in speech for key in keys):
                    return Reply("Άνοιξα την ενότητα.", navigate=view)

        if re.search(r"βοηθεια|help|τι μπορεισ|τι κανεισ|οδηγιεσ", speech):
            return Reply(HELP_TEXT)

        if re.search(r"νεα σειρα|new series|δημιουργησε σειρα|φτιαξε σειρα", speech):
            return Reply(
                "Άνοιξα τις Σειρές. Διάλεξε τύπο παραστατικού, δώσε κωδικό σειράς "
                "(π.χ. Α, ΤΠΥ, ΔΑ) και πάτα «Νέα σειρά».",
                navigate="series",
            )

        if re.search(r"μαζικη εκτυπωσ|εκτυπωσε ολα|τυπωσε τα παραστατικ|print all", speech):
            return Reply(
                "Άνοιξα τα Παραστατικά. Σημείωσε όσα θέλεις και πάτα «Εκτύπωση επιλεγμένων».",
                navigate="documents",
            )

        if re.search(r"\bzip\b|συμπιεσ|πακετ|κατεβασε ολα", speech):
            return Reply(
                "Άνοιξα τα Παραστατικά. Σημείωσε όσα θέλεις και πάτα «Εξαγωγή ZIP».",
                navigate="documents",
            )

        if re.search(r"ειδοποιησ|αδιαβαστ|notification", speech):
            return Reply("Κοιτάζω τις ειδοποιήσεις…", fetch="notifications")

        if re.search(r"2fa|διπλη πιστοποιησ|authenticator|αλλαγη κωδικ|αλλαξε κωδικ", speech):
            return Reply(
                "Άνοιξα τις Ρυθμίσεις — εκεί αλλάζεις κωδικό και ενεργοποιείς το 2FA "
                "σαρώνοντας το QR.",
                navigate="settings",
            )

        if re.search(r"προγραμματισμ|χρονοπρογραμμ|αυτοματη εκδοσ", speech):
            return Reply(
                "Άνοιξα τον Προγραμματισμό — από εδώ βλέπεις και ακυρώνεις τις "
                "προγραμματισμένες εκδόσεις.",
                navigate="schedule",
            )

        # Η ερώτηση κρίνεται ΠΡΙΝ την πρόθεση έκδοσης: το «πόσα τιμολόγια φέτος»
        # περιέχει «τιμολογ» και στο web κατέληγε — λάθος — σε ροή έκδοσης, παρότι
        # το ίδιο το κείμενο βοήθειας το διαφημίζει ως ερώτηση.
        # Προσοχή στο «ποσό»: χωρίς τόνους είναι ίδιο με το «πόσο». Ερώτηση το
        # θεωρούμε μόνο στην αρχή της φράσης ή μπροστά από «τιμολόγια», αλλιώς
        # το «…ποσό 100» θα διαβαζόταν ως ερώτηση αντί για εντολή έκδοσης.
        is_question = bool(
            re.search(r"^ποσ[αο]\b|ποσα τιμολ|ποσα παραστατ|τζιρο|στατιστικ|how many", speech)
        )
        if is_question:
            period = "month" if re.search(r"μηνα|μηνασ", speech) else "year"
            return Reply("Φέρνω στατιστικά…", fetch=f"stats:{period}")

        wants_issue = bool(
            re.search(r"εκδοσ|τιμολογ|αποδειξ|παραστατ|issue|invoice", speech)
            and not re.search(r"λιστα|αναζητησ|ολα τα", speech)
        )

        if re.search(r"νεοσ? πελατ|new customer|create customer|δημιουργησε πελατ|φτιαξε πελατ", speech):
            afm = re.search(r"\b(\d{9})\b", raw)
            return Reply(
                "Ανοίγω φόρμα νέου πελάτη"
                + (f" για ΑΦΜ {afm.group(1)}" if afm else "")
                + ". Έλεγξε τα στοιχεία και πάτα Αποθήκευση.",
                dialog="customer",
                prefill={"vat": afm.group(1) if afm else ""},
            )

        if re.search(r"νεο ειδ|νεο προι|new item|new product|δημιουργησε ειδ|φτιαξε ειδ", speech):
            price = _number(r"(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)", raw)
            desc = re.sub(
                r"^.*?(νέο είδ\S*|νεο ειδ\S*|νέο προϊ\S*|νεο προι\S*|new (?:item|product)|"
                r"δημιούργησε είδ\S*|φτιάξε είδ\S*)",
                "",
                raw,
                flags=re.IGNORECASE,
            )
            desc = re.sub(
                r"(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur).*", "", desc, flags=re.IGNORECASE
            )
            desc = re.sub(r"\bτιμ[ήη]\b", "", desc, flags=re.IGNORECASE).strip()
            return Reply(
                "Ανοίγω φόρμα νέου είδους"
                + (f" «{desc}»" if desc else "")
                + (f" τιμή {price:g}€" if price else "")
                + ". Έλεγξε κατηγορία και ΦΠΑ και πάτα Αποθήκευση.",
                dialog="product",
                prefill={"description": desc, "price": price or ""},
            )

        if wants_issue:
            return self._start_issue(parse_issue(raw))

        # Σιωπηλή πλοήγηση: «πελάτες» σκέτο, χωρίς ρήμα.
        for view, keys in NAV:
            if any(key in speech for key in keys):
                return Reply("Άνοιξα την ενότητα.", navigate=view)

        return Reply("Δεν το κατάλαβα. Πες «βοήθεια» για παραδείγματα.")

    # --- ροή έκδοσης -------------------------------------------------------
    def _start_issue(self, spec: DraftSpec) -> Reply:
        # Σκέτο «έκδοση», χωρίς κανένα στοιχείο: άνοιγμα της φόρμας. Το να
        # ρωτήσουμε «επαγγελματίας ή ιδιώτης;» σε κάποιον που απλώς ζήτησε τη
        # σελίδα είναι ανάκριση, όχι βοήθεια.
        if not any((spec.vat, spec.name, spec.item, spec.price)):
            return Reply("Άνοιξα την Έκδοση.", navigate="issue")
        match = resolve_customer(self._customers(), spec.name, spec.vat)
        if match is not None:
            spec.vat = _text(match, "vat", "afm")
            spec.name = _text(match, "name", "customer_name")
            return self._resolve_product(spec)
        if spec.vat:
            # 9ψήφιο ΑΦΜ που δεν είναι στο πελατολόγιο: η ΑΑΔΕ το αναγνωρίζει
            # και το καταχωρεί μόνη της κατά την άντληση.
            return self._resolve_product(spec)
        self._pending = ("who", spec)
        return Reply(
            f"Δεν βρήκα πελάτη «{spec.name or '—'}». Είναι επαγγελματίας ή ιδιώτης;",
            choices=(("🏢 Επαγγελματίας", "επαγγελματίας"), ("👤 Ιδιώτης", "ιδιώτης")),
        )

    def _continue(self, raw: str, speech: str) -> Reply:
        stage, spec = self._pending or ("", DraftSpec())
        if stage == "who":
            if re.search(r"επαγγελ|επιχειρ|εταιρ|professional", speech):
                self._pending = ("afm", spec)
                return Reply(
                    f"Δώσε το ΑΦΜ της επιχείρησης «{spec.name}» για να τον καταχωρήσω."
                )
            if re.search(r"ιδιωτ|φυσικ|individual|λιανικ", speech):
                self._pending = None
                spec.retail = True
                return Reply(
                    "Άνοιξα φόρμα νέου ιδιώτη — συμπλήρωσε ονοματεπώνυμο και στοιχεία, "
                    "και μετά ζήτησέ μου ξανά την έκδοση.",
                    dialog="customer",
                    prefill={"name": spec.name.upper(), "personal": True},
                )
            return Reply("Πες «επαγγελματίας» ή «ιδιώτης».")

        if stage == "afm":
            afm = re.search(r"\b(\d{9})\b", raw)
            if not afm:
                return Reply("Δώσε ένα έγκυρο 9ψήφιο ΑΦΜ (ή «άκυρο»).")
            self._pending = None
            spec.vat = afm.group(1)
            return self._resolve_product(spec)

        if stage == "confirm":
            if re.search(r"^(ναι|οκ|ok|εντ[αά]ξει|ετοιμασε|προχωρα|yes)", speech):
                self._pending = None
                return Reply("Ετοιμάζω το πρόχειρο…", draft=spec)
            if re.search(r"φορμα|ανοιξε", speech):
                self._pending = None
                return Reply("Άνοιξα τη φόρμα Έκδοσης.", navigate="issue")
            return Reply("Πες «ναι» για να ετοιμάσω το πρόχειρο, ή «άκυρο».")

        self._pending = None
        return Reply("Εντάξει, ακυρώθηκε.")

    def _resolve_product(self, spec: DraftSpec) -> Reply:
        if not spec.code and spec.item:
            spec.code = find_product(self._products(), spec.item)
        if not spec.code and spec.item:
            return Reply(
                f"Το είδος «{spec.item}» δεν υπάρχει στον κατάλογο — το ανοίγω για "
                "δημιουργία. Έλεγξε κατηγορία και ΦΠΑ, και μετά ζήτησέ μου ξανά την έκδοση.",
                dialog="product",
                prefill={"description": spec.item, "price": spec.price or ""},
            )
        return self._confirm(spec)

    def _confirm(self, spec: DraftSpec) -> Reply:
        self._pending = ("confirm", spec)
        lines = [
            "Θα ετοιμάσω ΠΡΟΧΕΙΡΟ:",
            f"• Πελάτης: {spec.name or spec.vat or '—'}",
            f"• Είδος: {spec.code or spec.item or '(στη φόρμα)'}",
            f"• Ποσότητα: {spec.qty:g}",
        ]
        if spec.price is not None:
            lines.append(f"• Τιμή μονάδας: {spec.price:g} €")
        if spec.withholding_pct:
            lines.append(f"• Παρακράτηση φόρου: {spec.withholding_pct:g}%")
        return Reply(
            "\n".join(lines),
            choices=(("✔ Ετοίμασε πρόχειρο", "ναι"), ("Άνοιξε φόρμα", "άνοιξε τη φόρμα")),
        )

    # --- απαντήσεις σε ασύγχρονα ερωτήματα ---------------------------------
    def report(self, kind: str, data: Any) -> Reply:
        """Το αποτέλεσμα ενός ``fetch``, διατυπωμένο για τον χρήστη."""
        if kind == "notifications":
            # ΔΕΝ πλοηγούμαστε μόνοι μας: η απάντηση μπορεί να αργήσει και να
            # φτάσει ενώ ο χρήστης συμπληρώνει ήδη άλλη σελίδα — στο ζωντανό
            # τεστ ακριβώς αυτό τον πέταξε έξω από τη φόρμα Έκδοσης. Δίνουμε
            # κουμπί και αποφασίζει εκείνος.
            return Reply(
                f"Έχεις {int(data or 0)} αδιάβαστες ειδοποιήσεις.",
                choices=(("Άνοιξε τις ειδοποιήσεις", "πήγαινε στις ειδοποιήσεις"),),
            )
        if kind.startswith("stats"):
            period = kind.partition(":")[2] or "year"
            payload = data if isinstance(data, dict) else {}
            when = "Φέτος" if period == "year" else "Αυτόν τον μήνα"
            return Reply(
                f"{when}: {payload.get('total_count', '—')} παραστατικά, "
                f"καθαρή αξία {payload.get('total_value', '—')} €."
            )
        return Reply(str(data))
