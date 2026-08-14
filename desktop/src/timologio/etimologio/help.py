"""Ξενάγηση και εγχειρίδιο του e-Τιμολόγιο Pro.

Ο μηχανισμός είναι του Downloader (``gui/tour.py``, ``gui/manual.py``)· εδώ
ζει μόνο το **περιεχόμενο**, μεταφερμένο από τους πίνακες ``TOUR`` και
``MANUAL`` του ``app.php``. Το εγχειρίδιο γράφεται σε δικό του αρχείο με δική
του υπογραφή — αλλιώς τα δύο PDF θα χτυπιόνταν στο ίδιο cache και ο χρήστης θα
έπαιρνε το λάθος.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sys
from pathlib import Path

from ..gui.tour import Step

log = logging.getLogger(__name__)

#: Το όνομα του PDF. Διαφορετικό από του Downloader, επίτηδες.
MANUAL_FILENAME = "Εγχειρίδιο χρήσης — e-Τιμολόγιο Pro.pdf"

#: Το ίδιο αρχείο **μέσα** στο bundle, χτισμένο από το build.ps1. Ξεχωριστό
#: όνομα από το ``manual.pdf`` του Downloader — μοιράζονται τον ίδιο φάκελο.
BUNDLED_NAME = "etim-manual.pdf"

#: (κείμενο, είδος) — ``h1``/``h2``/``p``/``li``, όπως ο πίνακας του web.
MANUAL: list[tuple[str, str]] = [
    ("e-Τιμολόγιο Pro — Εγχειρίδιο χρήσης", "h1"),
    ("Η εφαρμογή εκδίδει παραστατικά στο e-timologio της ΑΑΔΕ. Ό,τι εκδίδεται "
     "λαμβάνει ΜΑΡΚ και δεν διαγράφεται — ακυρώνεται με πιστωτικό.", "p"),

    ("1. Πριν από την πρώτη έκδοση", "h2"),
    ("Πρόσθεσε την εταιρεία σου: το «＋» δίπλα στον επιλογέα εταιρείας, με ΑΦΜ, "
     "username και subscription key του e-timologio.", "li"),
    ("Δημιούργησε τουλάχιστον μία σειρά ανά τύπο παραστατικού που θα εκδίδεις. "
     "Χωρίς σειρά, ο τύπος δεν εμφανίζεται καν στην Έκδοση.", "li"),
    ("Όρισε κατηγορίες ειδών με χαρακτηρισμούς: η ΑΑΔΕ απορρίπτει είδος χωρίς "
     "κατηγορία.", "li"),

    ("2. Έκδοση παραστατικού", "h2"),
    ("Διάλεξε τύπο και σειρά. Η λίστα σειρών δείχνει μόνο όσες ανήκουν στον "
     "συγκεκριμένο τύπο.", "li"),
    ("Πελάτης: κάνε κλικ στο πεδίο για να ανοίξει η λίστα. Με 9ψήφιο ΑΦΜ τα "
     "στοιχεία αντλούνται από το Taxisnet. Η πρώτη γραμμή φτιάχνει νέο πελάτη.", "li"),
    ("Γραμμές: το πεδίο περιγραφής είναι επιλογέας ειδών — συμπληρώνει τιμή και "
     "ΦΠΑ από τον κατάλογο.", "li"),
    ("Φόροι και κρατήσεις: το κουμπί «💶 Φόρος / Κράτηση». Παρακρατήσεις και "
     "κρατήσεις ΑΦΑΙΡΟΥΝΤΑΙ από το πληρωτέο, τέλη προστίθενται.", "li"),
    ("Τρία κουμπιά: πρόχειρο (τίποτα δεν φεύγει στην ΑΑΔΕ), προεπισκόπηση "
     "(αποθηκεύει πρόχειρο και δείχνει το πραγματικό PDF), και Έκδοση (ΜΑΡΚ).", "li"),

    ("3. Μαζική έκδοση", "h2"),
    ("Κοινός τύπος, σειρά και τρόπος πληρωμής για όλη την παρτίδα· μία γραμμή "
     "ανά πελάτη. Δοκίμασε πρώτα με «Αποθήκευση πρόχειρων».", "li"),

    ("4. Πελάτες και Καρτέλα", "h2"),
    ("Ο πελάτης με ΑΦΜ και ο ιδιώτης είναι διαφορετικές εγγραφές στην ΑΑΔΕ — ο "
     "διάλογος έχει ξεχωριστή καρτέλα για καθέναν.", "li"),
    ("Η Καρτέλα δείχνει τζίρο, πληρωμές και υπόλοιπο, και εξάγει PDF κίνησης.", "li"),

    ("5. Ακύρωση και πιστωτικό", "h2"),
    ("Διάλεξε το παραστατικό από τη λίστα — το ΜΑΡΚ δεν πληκτρολογείται. Πλήρης "
     "αξία = ακύρωση, μικρότερη = μερική πίστωση.", "li"),

    ("6. Πρόχειρα", "h2"),
    ("Προεπισκόπηση PDF, μαζική εκτύπωση και ZIP, και «Άνοιγμα σε Έκδοση» που "
     "συνεχίζει το ίδιο πρόχειρο αντί να φτιάξει δεύτερο.", "li"),

    ("7. Πληρωμές", "h2"),
    ("Χειροκίνητη καταχώρηση ή εισαγωγή από extrait τράπεζας. Οι πληρωμές είναι "
     "τοπικές — η ΑΑΔΕ δεν τις γνωρίζει.", "li"),

    ("8. Προγραμματισμός", "h2"),
    ("Το «⏰ Προγραμματισμός» στην Έκδοση βάζει το παραστατικό σε ουρά για "
     "μελλοντική ώρα, με επανάληψη αν χρειάζεται.", "li"),

    ("9. Ψηφιακός βοηθός", "h2"),
    ("Το «🤖 Βοηθός» (ή Ctrl+B) δέχεται εντολές με κείμενο ή φωνή: «έκδοση "
     "τιμολογίου στον <ΑΦΜ> καθαρή αξία 100 με παρακράτηση 20%», «νέος πελάτης», "
     "«πήγαινε στα πρόχειρα».", "li"),
    ("Ο βοηθός αποθηκεύει ΠΑΝΤΑ πρόχειρο — ΜΑΡΚ παίρνει το παραστατικό μόνο "
     "όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση».", "li"),
    ("Η φωνή δουλεύει εκτός δικτύου με το ελληνικό μοντέλο Vosk. Δεν "
     "πακετάρεται (~1.1 GB): το κουμπί του μικροφώνου λέει τι λείπει και πού "
     "μπαίνει.", "li"),

    ("10. Ασφάλεια", "h2"),
    ("Τα κλειδιά της ΑΑΔΕ αποθηκεύονται κρυπτογραφημένα, τοπικά. Στις Ρυθμίσεις "
     "ενεργοποιείς 2FA.", "li"),
]


def manual_signature() -> str:
    """Υπογραφή περιεχομένου — αλλάζει μόνο όταν αλλάξει το κείμενο."""
    joined = "\n".join(f"{kind}:{text}" for text, kind in MANUAL)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def manual_html() -> str:
    """Το εγχειρίδιο ως HTML, για απόδοση σε PDF."""
    parts = [
        "<html><head><meta charset='utf-8'><style>"
        "body{font-family:Segoe UI,Arial,sans-serif;color:#12202b;line-height:1.5}"
        "h1{font-size:24px;border-bottom:3px solid #0ea5e9;padding-bottom:6px}"
        "h2{font-size:16px;color:#0369a1;margin-top:22px}"
        "li{margin:4px 0}"
        "</style></head><body>"
    ]
    open_list = False
    for text, kind in MANUAL:
        if kind == "li" and not open_list:
            parts.append("<ul>")
            open_list = True
        elif kind != "li" and open_list:
            parts.append("</ul>")
            open_list = False
        tag = {"h1": "h1", "h2": "h2", "li": "li"}.get(kind, "p")
        parts.append(f"<{tag}>{text}</{tag}>")
    if open_list:
        parts.append("</ul>")
    parts.append("</body></html>")
    return "".join(parts)


def build_manual(target: Path) -> Path:
    """Γράφει το PDF. Απαιτεί ενεργό QGuiApplication (offscreen αρκεί)."""
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    target.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(target))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(16, 14, 16, 14), QPageLayout.Unit.Millimeter)
    writer.setTitle("e-Τιμολόγιο Pro — Εγχειρίδιο χρήσης")
    writer.setCreator("e-Τιμολόγιο Pro")
    # Η ανάλυση και το μέγεθος σελίδας ΔΕΝ είναι λεπτομέρειες: χωρίς αυτά ο
    # QPdfWriter δουλεύει στα 1200dpi ενώ το QTextDocument στοιχειοθετεί σε
    # πλάτος οθόνης, και το κείμενο πέφτει έξω από το χαρτί. Το εγκατεστημένο
    # εγχειρίδιο ήταν έτσι **3 KB χωρίς ούτε ένα γράμμα** — δύο κενές σελίδες.
    # Το gui/manual.py το είχε ήδη μάθει· εδώ είχε ξαναγραφτεί από την αρχή.
    writer.setResolution(96)
    document = QTextDocument()
    document.setHtml(manual_html())
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    document.setPageSize(QSizeF(rect.size()))
    document.print_(writer)
    return target


#: Το πραγματικό εγχειρίδιο είναι ~39 KB· ένα κενό PDF είναι λίγα KB. Το παλιό
#: κατώφλι ήταν 1.000 bytes, οπότε το κενό των 3 KB περνούσε για έγκυρο και δεν
#: ξαναχτιζόταν ποτέ — ούτε καν μετά τη διόρθωση.
_MIN_PDF_BYTES = 20_000


def _looks_built(path: Path) -> bool:
    try:
        if path.stat().st_size < _MIN_PDF_BYTES:
            return False
        with open(path, "rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def _bundled_manual() -> Path | None:
    """Το έτοιμο PDF μέσα στο bundle (μόνο σε πακεταρισμένη εκτέλεση)."""
    base = getattr(sys, "_MEIPASS", "")
    if base:
        candidate = Path(base) / BUNDLED_NAME
        if _looks_built(candidate):
            return candidate
    return None


def ensure_manual(data_dir: Path) -> Path:
    """Η διαδρομή του PDF, χτίζοντάς το αν λείπει, αν χάλασε ή αν άλλαξε το κείμενο."""
    target = data_dir / MANUAL_FILENAME
    stamp = data_dir / ".etim-manual.hash"
    signature = manual_signature()
    if _looks_built(target) and stamp.exists():
        try:
            if stamp.read_text(encoding="utf-8").strip() == signature:
                return target
        except OSError:
            pass

    data_dir.mkdir(parents=True, exist_ok=True)
    bundled = _bundled_manual()
    if bundled is not None:
        try:
            shutil.copyfile(bundled, target)
        except OSError as exc:
            log.warning("Δεν αντιγράφηκε το έτοιμο εγχειρίδιο: %s", exc)
    if not _looks_built(target):
        build_manual(target)
    if not _looks_built(target):
        # Χωρίς σφραγίδα, ώστε να ξαναδοκιμαστεί την επόμενη φορά αντί να
        # κλειδώσει ένα κενό PDF για πάντα.
        log.warning("Το εγχειρίδιο του e-Τιμολόγιο δεν στοιχειοθετήθηκε σωστά.")
        return target
    try:
        stamp.write_text(signature, encoding="utf-8")
    except OSError:
        pass
    return target


def tour_steps(shell) -> list[Step]:
    """Τα βήματα της ξενάγησης, μεταφερμένα από τον πίνακα ``TOUR`` του web.

    Ο ``target`` αποτιμάται τη στιγμή που δείχνεται το βήμα, οπότε μπορεί να
    δείξει σε widget που δημιουργείται από το ``before``.
    """
    def section(key: str):
        return lambda: shell.open_section(key)

    return [
        Step("Έκδοση παραστατικού",
             "Από εδώ εκδίδεις τιμολόγια και αποδείξεις. Δοκίμασε πρώτα "
             "«Αποθήκευση πρόχειρου» — τίποτα δεν φεύγει στην ΑΑΔΕ.",
             lambda: shell.page("issue"), section("issue")),
        Step("Πελάτης με ένα κλικ",
             "Κάνε κλικ στο πεδίο πελάτη και η λίστα ανοίγει. Η πρώτη γραμμή "
             "φτιάχνει νέο πελάτη χωρίς να φύγεις από τη σελίδα.",
             lambda: getattr(shell.page("issue"), "_picker", None)),
        Step("Φόροι και κρατήσεις",
             "Παρακρατήσεις, τέλη και κρατήσεις. Το ποσό υπολογίζεται μόνο του "
             "από το ποσοστό της κατηγορίας.",
             lambda: shell.page("issue")),
        Step("Μαζική έκδοση",
             "Μία γραμμή ανά πελάτη, κοινός τύπος και σειρά για όλη την παρτίδα.",
             lambda: shell.page("bulk"), section("bulk")),
        Step("Παραστατικά",
             "Αναζήτηση, διπλό κλικ για το PDF, και μαζική εκτύπωση ή ZIP για "
             "όσα σημειώσεις.",
             lambda: shell.page("documents"), section("documents")),
        Step("Πελάτες και καρτέλες",
             "Λίστα πελατών· διπλό κλικ ανοίγει την καρτέλα με τζίρο, πληρωμές "
             "και υπόλοιπο.",
             lambda: shell.page("customers"), section("customers")),
        Step("Ακύρωση και πιστωτικό",
             "Διάλεξε το παραστατικό από τη λίστα — το ΜΑΡΚ δεν πληκτρολογείται.",
             lambda: shell.page("credit"), section("credit")),
        Step("Πρόχειρα",
             "Προεπισκόπηση, μαζική εκτύπωση και συνέχεια στην Έκδοση.",
             lambda: shell.page("drafts"), section("drafts")),
        Step("Σειρές",
             "Κάθε τύπος παραστατικού χρειάζεται δική του σειρά. Η διαγραφή "
             "εμποδίζεται αν έχουν εκδοθεί παραστατικά.",
             lambda: shell.page("series"), section("series")),
        Step("Είδη και χαρακτηρισμοί",
             "Ο κατάλογος ειδών και οι κατηγορίες με τους χαρακτηρισμούς myDATA.",
             lambda: shell.page("products"), section("products")),
        Step("Προγραμματισμός",
             "Εκδόσεις που τρέχουν μόνες τους σε μελλοντική ώρα.",
             lambda: shell.page("schedule"), section("schedule")),
        Step("Επιλογή εταιρείας",
             "Πάνω δεξιά διαλέγεις εταιρεία — και με το «＋» προσθέτεις νέα.",
             lambda: getattr(shell, "_accounts", None), lambda: shell.open_section("home")),
        Step("Ρυθμίσεις",
             "Κωδικός, 2FA και ειδοποιήσεις email.",
             lambda: shell.page("settings"), section("settings")),
        Step("Ψηφιακός βοηθός",
             "Με Ctrl+B δίνεις εντολές γραπτά ή με φωνή: «έκδοση τιμολογίου "
             "στον 802576637 καθαρή αξία 100». Ετοιμάζει πάντα πρόχειρο.",
             lambda: getattr(shell, "_assistant", None)),
    ]
