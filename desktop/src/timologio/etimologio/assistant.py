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

import difflib
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


#: Ό,τι ακούγεται **ίδιο** στα ελληνικά αλλά γράφεται αλλιώς. Το whisper τα
#: μπερδεύει σταθερά, και ο χρήστης δεν φταίει σε τίποτα: «εταιρεία» και
#: «ετερεία» είναι ο ίδιος ήχος.
#:
#: Η σειρά μετράει — οι δίφθογγοι πρώτα, αλλιώς το «ει» θα είχε ήδη γίνει «ι».
#: Δεν είναι φωνητική μεταγραφή και δεν προσπαθεί να είναι: αρκεί να εφαρμόζεται
#: **το ίδιο** και στην είσοδο και στις λέξεις-κλειδιά.
_FOLD: tuple[tuple[str, str], ...] = (
    ("αι", "ε"), ("ει", "ι"), ("οι", "ι"), ("υι", "ι"),
    ("η", "ι"), ("υ", "ι"), ("ω", "ο"),
)


def fold(text: str) -> str:
    """Ηχητική «ισοπέδωση»: ό,τι ακούγεται ίδιο, γράφεται ίδιο.

    Χρησιμοποιείται **μόνο ως δεύτερο πέρασμα**, αφού αποτύχει το κανονικό
    ταίριασμα. Έτσι δεν μπορεί να χαλάσει καμία σωστή απάντηση — το χειρότερο
    που κάνει είναι να μετατρέψει ένα «δεν το κατάλαβα» σε σωστή ενέργεια.
    """
    out = text
    for old, new in _FOLD:
        out = out.replace(old, new)
    return out


def normalize(text: str) -> str:
    """Πεζά, χωρίς τόνους, με τελικό σίγμα ίδιο με το μεσαίο."""
    return (text or "").lower().translate(_TRANS)


# --- πλοήγηση -----------------------------------------------------------------
#: Ενότητα → λέξεις-κλειδιά (κανονικοποιημένες). Η σειρά μετράει: το πρώτο
#: ταίριασμα κερδίζει, όπως στο web.
#: Η σειρά μετράει και μέσα στη γραμμή: η **Καρτέλα** πρέπει να κριθεί πριν από
#: τους Πελάτες, γιατί το «καρτέλα πελάτη» περιέχει και τα δύο.
NAV: list[tuple[str, tuple[str, ...]]] = [
    # Η **μαζική** πριν από την Έκδοση: το «μαζική έκδοση» περιέχει «έκδοση»,
    # και με την αντίστροφη σειρά κατέληγε πάντα στη μονή φόρμα.
    ("bulk",          ("μαζικη εκδοση", "μαζικ",
                       "bulk", "mass issue", "issue many")),
    ("issue",         ("εκδοση παραστατικου", "νεο παραστατικο", "εκδοση",
                       "new invoice", "create an invoice", "issue a document",
                       "issue an invoice")),
    # Στο web τα εκδοθέντα ζουν μέσα στην Καρτέλα· η εφαρμογή υπολογιστή έχει
    # ξεχωριστή σελίδα «Παραστατικά».
    ("documents",     ("παραστατικα", "τιμολογια μου", "λιστα παραστατικων",
                       "αναζητηση παραστατικ",
                       "documents", "invoices list", "my invoices", "invoice list")),
    ("card",          ("καρτελα πελατη", "καρτελα του πελατη",
                       "customer card", "client card", "ledger")),
    ("customers",     ("πελατ", "καρτελ",
                       "customers", "customer", "client list", "clients")),
    ("payments",      ("τραπεζ", "extrait", "εξτρε", "εισαγωγη πληρωμ", "πληρωμ", "ταμει",
                       "payments", "bank import", "import payments")),
    ("products",      ("ειδη", "ειδοσ", "προιοντ", "καταλογο",
                       "products", "items", "product list", "item list")),
    ("series",        ("σειρ", "αριθμηση", "series", "numbering")),
    ("drafts",        ("προχειρ", "προσχεδι", "drafts", "saved drafts")),
    ("credit",        ("ακυρωσ", "πιστωτικ",
                       "credit note", "cancel an invoice", "cancellation")),
    ("schedule",      ("προγραμματισμ", "χρονοπρογραμμ",
                       "schedule", "scheduler", "scheduled invoice")),
    ("stats",         ("στατιστικ", "γραφημ", "statistics", "stats", "charts")),
    ("notifications", ("ειδοποιησ", "αδιαβαστ", "notification")),
    ("settings",      ("ρυθμισ", "2fa", "κωδικο", "authenticator",
                       "settings", "preferences")),
    # Οι Εταιρείες είναι δική τους ενότητα από την 0.4.1 — το «εταιρεία» έστελνε
    # ως τότε στη Διαχείριση, που δείχνει χρήστες και ρόλους, όχι εταιρείες.
    ("companies",     ("εταιρει", "επιχειρησ", "αλλαγη εταιρει",
                       "companies", "my companies", "switch company")),
    ("admin",         ("διαχειρισ", "χρηστ", "ρολο", "προσκλησ",
                       "administration", "users and roles", "manage users",
                       "user management")),
]

#: Ρήματα που δηλώνουν ρητή πλοήγηση. Χωρίς αυτά το «πήγαινε στα παραστατικά»
#: θα περνούσε για εντολή έκδοσης, γιατί περιέχει «παραστατ».
_NAV_VERB = re.compile(
    r"πηγαινε|ανοιξε|δειξε|εμφανισε|παμε|βγαλε μου|φερε μου|βρεσ? μου"
    r"|go to|open|show|list|take me"
)

#: Ρήματα δημιουργίας. Ξεχωρίζουν το «φτιάξε καρτέλα για τον 802576637»
#: (νέος πελάτης) από το «άνοιξε την καρτέλα του 802576637» (υπάρχων).
_MAKES_NEW = re.compile(r"\bνεοσ?\b|\bνεα\b|\bνεο\b|φτιαξε|δημιουργησε|καταχωρησε|προσθεσε"
                        r"|\bnew\b|\badd\b|\bcreate\b")

#: (μοτίβο, ενότητα, τι λέει) για λειτουργίες που **δεν έχουν εντολή** στο
#: συμβόλαιο του :class:`Reply` — π.χ. το ✕ της ειδοποίησης ή η επιλογή στηλών
#: είναι κουμπιά μέσα στη σελίδα, όχι ενέργειες του κελύφους.
#:
#: Η ειλικρινής απάντηση είναι «σε πάω στη σωστή οθόνη και σου λέω τι να
#: πατήσεις» — καλύτερη και από «δεν κατάλαβα», και από μια εντολή που ο
#: επικυρωτής θα πετούσε.
#:
#: ⚠️ Κρίνονται **πριν** από το :data:`COMMANDS`, γι' αυτό τα μοτίβα είναι
#: στενά: το «ανανέωσε τα παραστατικά» πρέπει να πάει στα Παραστατικά, αλλά το
#: σκέτο «ανανέωση» να μείνει εντολή ανανέωσης σελίδας.
TIPS: tuple[tuple[str, str, str], ...] = (
    (r"(?:σβην|σβησ|διαγραφ|διαγραψ|καθαρι)\S*\s+\S*\s?ειδοποιησ"
     r"|φυγουν οι ειδοποιησ|delete a notification|clear the notification",
     "notifications",
     "Κάθε ειδοποίηση έχει ένα ✕ πάνω δεξιά που τη σβήνει οριστικά. Το κλικ στη "
     "γραμμή σημαίνει μόνο «διαβασμένη» — είναι άλλο πράγμα."),
    (r"ανανεωσ\S*\s+(τα\s+)?παραστατ|τσεκαρε τον φακελο|ελεγξε τον φακελο"
     r"|ελεγξε αν κατεβηκαν|λεει αναμονη|δεν το δειχνει|ενω κατεβηκε"
     r"|δεν βλεπω το pdf"
     r"|refresh the document|check the folder|say pending|says pending",
     "documents",
     "Πάτα «Ανανέωση»: ελέγχει τον φάκελο του πελάτη και ό,τι βρει εκεί το "
     "σημειώνει ως «Ελήφθη»."),
    (r"επαναφορα|να επαναφερω|γυρνα πισω τα δεδομεν|restore"
     r"|φερω πισω \S*\s?\S*\s?αντιγραφο|παλιο αντιγραφο",
     "settings",
     "Η «Επαναφορά από αντίγραφο» είναι στις Ρυθμίσεις. Ζητά να γράψεις τη λέξη "
     "ΕΠΑΝΑΦΟΡΑ πριν αγγίξει οτιδήποτε."),
    (r"δοκιμασε τα κλειδι|ελεγξε αν δουλευει το api|τεστ κωδικ"
     r"|test the api|check the credential",
     "customers",
     "Στην καρτέλα του πελάτη, δίπλα στο κλειδί, υπάρχει κουμπί «Δοκιμή» που "
     "ρωτά την ΑΑΔΕ επιτόπου."),
    (r"διαλεξε στηλ|κρυψε (μια )?στηλ|θελω αλλεσ στηλ|choose column|hide a column",
     "",
     "Πάνω από κάθε πίνακα υπάρχει το κουμπί «Στήλες»: διαλέγεις τι φαίνεται."),
    (r"κλεισε τι?σ? ?λεπτομερει|ανοιξε το πλαινο|πλαινο panel"
     r"|να δω τον πινακα ολοκληρο",
     "",
     "Το κουμπί «Λεπτομέρειες» ανοιγοκλείνει το πλαϊνό panel, και το χώρισμα "
     "σέρνεται για να του δώσεις όποιο πλάτος θέλεις."),
    (r"αλλαξε θεμα|φωτεινο θεμα|σκουρο θεμα|change the theme|dark mode|light mode",
     "settings",
     "Ο διακόπτης «Φωτεινό θέμα» είναι κάτω αριστερά."),
    (r"ελεγξε για ενημερωσ|υπαρχει νεα εκδοση|τι εκδοση εχω"
     r"|check for update|new version",
     "",
     "Ο «Έλεγχος για ενημερώσεις» είναι στο μενού — ή κάνε κλικ στον αριθμό "
     "έκδοσης, κάτω αριστερά."),
    (r"τι σημαινει ο τυπο|τι ειναι το \d\.\d|τι τυποσ παραστατικου"
     r"|τιμολογια παροχησ υπηρεσι|μονο τα \d\.\d|ψαξε τυπο παραστατικου",
     "documents",
     "Η στήλη «Τύπος» δείχνει κωδικό και ονομασία — π.χ. «2.1 Τιμολόγιο "
     "Παροχής Υπηρεσιών». Η αναζήτηση δέχεται και τα δύο: «2.1» ή «υπηρεσι»."),
)

def _hits(pattern: str, speech: str, heard: str) -> bool:
    """Ταιριάζει το μοτίβο — είτε όπως γράφτηκε, είτε όπως ακούγεται.

    Δύο περάσματα και όχι ένα «χαλαρό» μοτίβο: το κανονικό κείμενο κρίνεται
    πρώτο και κερδίζει πάντα, οπότε το ακουστικό πέρασμα δεν μπορεί να κλέψει
    ένα σωστό ταίριασμα — μόνο να σώσει ένα χαμένο.
    """
    return bool(re.search(pattern, speech) or re.search(fold(pattern), heard))


def _nav_match(speech: str, heard: str) -> str:
    """Η ενότητα που ζητά η φράση, ή «» — με το ίδιο διπλό πέρασμα."""
    for view, keys in NAV:
        if any(key in speech for key in keys):
            return view
    # Μόνο κλειδιά με σώμα: το folded «είδη» είναι «ιδι», τρία γράμματα
    # που υπάρχουν μέσα στο «εγχειρίδιο» — και η ξενάγηση κατέληγε στα
    # Είδη. Τα κοντά κλειδιά τα πιάνει ήδη το ακριβές πέρασμα.
    for view, keys in NAV:
        if any(len(fold(key)) >= 5 and fold(key) in heard for key in keys):
            return view
    return ""


#: «Τον Ιανουάριο» είναι μήνας, το ίδιο με το «αυτόν τον μήνα». Χωρίς αυτό
#: κάθε ερώτηση με όνομα μήνα απαντιόταν με στοιχεία **έτους**.
_MONTHS = (r"μηνα|μηνασ|this month|per month"
           r"|ιανουαρ|φεβρουαρ|μαρτ|απριλ|μαι[οω]|ιουν|ιουλ|αυγουστ"
           r"|σεπτεμβρ|οκτωβρ|νοεμβρ|δεκεμβρ"
           r"|january|february|march|april|june|july|august"
           r"|september|october|november|december")

#: Ό,τι ζητά **οριστική** έκδοση. Δεν είναι σχόλιο: είναι ο μόνος κανόνας που
#: δεν διαπραγματεύεται, και πρέπει να απαντηθεί με άρνηση — όχι με «δεν
#: κατάλαβα», που αφήνει τον χρήστη να νομίζει ότι απλώς δεν ακούστηκε.
_WANTS_FINAL = re.compile(
    r"οριστικ|στειλ\S* το στην ααδε|παρε μαρκ|υποβαλ\S*|κανε το οριστικο"
    r"|issue it for real|submit it to the tax|officially|for real|επισημα"
)
_REFUSAL = (
    "Ετοιμάζω μόνο ΠΡΟΧΕΙΡΟ. Το ΜΑΡΚ το δίνει η ΑΑΔΕ όταν πατήσεις εσύ το "
    "κόκκινο «Οριστική Έκδοση»."
)

# --- εντολές προς το κέλυφος ---------------------------------------------------
#: (εντολή, μοτίβο, τι λέει ο βοηθός). Ό,τι δεν είναι ούτε πλοήγηση ούτε έκδοση
#: αλλά **ενέργεια** της εφαρμογής. Ο βοηθός τη *ονομάζει*· την εκτελεί το
#: κέλυφος (`shell._assistant_command`), γιατί μόνο εκείνο ξέρει από σελίδες,
#: αρχεία και σύνδεση.
#:
#: Η σειρά μετράει όπως στο NAV: το «backup» πρέπει να κριθεί ΠΡΙΝ το «back»,
#: αλλιώς το «κράτα backup» θα γύριζε σελίδα πίσω.
COMMANDS: tuple[tuple[str, str, str], ...] = (
    ("backup",  r"αντιγραφο ασφαλει|backup|back up|κρατα \S*\s?αντιγραφο"
                r"|σωσ\S* τα δεδομεν|save my data",
     "Ετοιμάζω αντίγραφο ασφαλείας — θα σου πω μόλις τελειώσει."),
    ("manual",  r"εγχειριδι|manual|οδηγιεσ χρησ|user guide|documentation",
     "Ανοίγω το εγχειρίδιο."),
    ("tour",    r"ξεναγ\S*|\btour\b|show me around|walk me through"
                r"|πωσ δουλευει η εφαρμογη|how the app works",
     "Ξεκινώ την ξενάγηση — ακολούθησε τα βήματα."),
    ("logout",  r"αποσυνδεσ|logout|log out|sign out"
                r"|εξοδοσ απο τον λογαριασμο|να βγω απο τον λογαριασμο"
                r"|βγαλε με εξω|sign me out|log me out",
     "Σε αποσυνδέω."),
    ("palette", r"παλετα εντολ|command palette|\bpalette\b",
     "Άνοιξα την παλέτα εντολών."),
    ("refresh", r"ανανεωσ|ξαναφορτωσ|refresh|reload|φρεσκαρε",
     "Ανανεώνω τη σελίδα."),
    ("home",    r"αρχικη|^home$|go home",
     "Πάμε στην αρχική."),
    # ΟΧΙ «επιστροφή»: στη λογιστική είναι το πιστωτικό, όχι το κουμπί «πίσω».
    ("back",    r"^πισω\b|γυρνα πισω|\bback\b|go back",
     "Γυρίζω πίσω."),
    # Η φωνή είναι του panel, όχι του κελύφους — αλλά περνά από τον ίδιο δρόμο,
    # ώστε να υπάρχει ΕΝΑ σημείο που ξέρει τι εντολές δέχεται ο βοηθός.
    ("speak:off", r"σωπα|μη \S*\s?μιλα|σταματα να μιλα|\bmute\b"
                  r"|be quiet|stop talking",
     "Εντάξει, απαντώ μόνο γραπτά."),
    ("speak:on",  r"μιλα μου|ξαναμιλα|ενεργοποιησε τη φωνη|ανοιξε τη φωνη"
                  r"|\bunmute\b"
                  r"|talk to me|turn the voice on",
     "Εντάξει, ξαναμιλάω."),
)

HELP_TEXT = (
    "Μπορώ (πάντα ως ΠΡΟΧΕΙΡΟ — καμία οριστική έκδοση χωρίς εσένα):\n"
    "📄 Έκδοση: «έκδοση τιμολογίου στον 802576637 καθαρή αξία 100 "
    "με παρακράτηση 20% είδος συντήρηση»\n"
    "👥 Δεδομένα: «νέος πελάτης <ΑΦΜ>» · «νέο είδος <περιγραφή> <τιμή> ευρώ» · «νέα σειρά»\n"
    "🖨️ Εκτυπώσεις: «μαζική εκτύπωση» · «ZIP παραστατικών»\n"
    "💶 Ταμείο: «πληρωμές» · «εισαγωγή από τράπεζα»\n"
    "⏰ Αυτοματισμοί: «προγραμματισμός» · «πόσες αδιάβαστες ειδοποιήσεις»\n"
    "⚙️ Λογαριασμός: «ρυθμίσεις» · «2FA» · «διαχείριση»\n"
    "🛠️ Εφαρμογή: «εγχειρίδιο» · «ξενάγηση» · «αντίγραφο ασφαλείας» · "
    "«άλλαξε εταιρεία» · «ανανέωσε» · «πίσω» · «σώπα» · «αποσύνδεση»\n"
    "📊 Ερωτήσεις: «πόσα τιμολόγια φέτος» · «τζίρος μήνα» · «πόσους πελάτες έχω»\n"
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
    #: Ενέργεια της εφαρμογής που εκτελεί το κέλυφος: «manual», «backup»,
    #: «company:094019245», «card:802576637», … (δες :data:`COMMANDS`).
    command: str = ""
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
        # Το «για 500» και το «200 ευρώ» ΔΕΝ είναι μέρος της επωνυμίας.
        # Χωρίς αυτά, το «κόψε τιμολόγιο στην ΑΛΦΑ ΟΕ για 500» έψαχνε
        # πελάτη με όνομα «ΑΛΦΑ ΟΕ για 500» — και δεν τον έβρισκε ποτέ.
        spec.name = re.sub(
            r"\s+(καθαρ\S*|ποσ[όο]|αξ[ίι]α|με|ε[ίι]δος|παρακρ\S*"
            r"|για\s+\d|\d|ευρ[ώω]|€|eur|,).*$",
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
        # Τελευταία ευκαιρία: το whisper ακούει «Παπαδόποιλος» και
        # «Γεοργίου». Ένα γράμμα διαφορά δεν είναι άλλος πελάτης — είναι
        # ο ίδιος, γραμμένος όπως ακούστηκε.
        #
        # Το κατώφλι είναι σκόπιμα ψηλό και το όνομα θέλει τουλάχιστον
        # τέσσερα γράμματα: προτιμάμε να ρωτήσουμε «ποιον εννοείς» παρά
        # να διαλέξουμε λάθος πελάτη. Και ό,τι βγει είναι ΠΡΟΧΕΙΡΟ, που
        # το βλέπει ο χρήστης πριν εκδοθεί.
        if len(needle) >= 4:
            names = {normalize(_text(r, "name", "customer_name")): r
                     for r in rows if _text(r, "name", "customer_name")}
            close = difflib.get_close_matches(needle, list(names), n=1, cutoff=0.82)
            if close:
                return names[close[0]]
    return None


def find_product(rows: Sequence[dict[str, Any]], description: str) -> str:
    """Ο κωδικός του είδους που ταιριάζει καλύτερα στην περιγραφή («» αν κανένα).

    Ίδια βαθμολόγηση με το web: πλήρης εμφωλευμός μετράει 5, κάθε κοινή λέξη
    ≥4 γραμμάτων μετράει 1, και κάτω από 2 δεν το θεωρούμε εύρημα — αλλιώς μια
    τυχαία λέξη θα διάλεγε λάθος είδος και θα έφευγε λάθος κωδικός στην ΑΑΔΕ.
    """
    if not description:
        return ""
    # Ηχητική ισοπέδωση και στα δύο: η «εκπαίδευση προσοπικού» που άκουσε
    # το whisper πρέπει να βρει την «εκπαίδευση προσωπικού» του καταλόγου.
    needle = fold(normalize(description))
    best, best_score = "", 0
    for row in rows:
        code = _text(row, "code", "product_code")
        desc = fold(normalize(_text(row, "description", "product_description")))
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
        # Η «ακουστική» εκδοχή της ίδιας φράσης, για δεύτερο πέρασμα όταν το
        # whisper έγραψε «ετερεία» αντί για «εταιρεία». Δες :func:`fold`.
        heard = fold(speech)

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

        # Στοχευμένες εντολές με ΑΦΜ. Κρίνονται ΠΡΙΝ την πλοήγηση: αλλιώς το
        # «καρτέλα» και το «εταιρεία» ανοίγουν απλώς τη λίστα και ο αριθμός —
        # δηλαδή όλη η εντολή — πάει χαμένος.
        vat_said = re.search(r"\b(\d{9})\b", speech)
        # «φτιάξε καρτέλα για τον Χ» είναι ΝΕΟΣ πελάτης, όχι άνοιγμα καρτέλας —
        # η ίδια λέξη, αντίθετη ενέργεια. Το ρήμα αποφασίζει.
        if vat_said and not _MAKES_NEW.search(speech) and (
            "καρτελ" in heard or _hits(r"χρωσταει|υπολοιπο|\bcard\b|ledger", speech, heard)
        ):
            return Reply(
                "Ανοίγω την καρτέλα του πελάτη.",
                command=f"card:{vat_said.group(1)}",
            )
        if vat_said and _hits(r"εταιρει|επιχειρησ|\bcompany\b|switch to", speech, heard):
            return Reply(
                "Αλλάζω ενεργή εταιρεία.",
                command=f"company:{vat_said.group(1)}",
            )

        # Ρητή πλοήγηση ΠΡΩΤΑ.
        if _NAV_VERB.search(speech) or _NAV_VERB.search(heard):
            view = _nav_match(speech, heard)
            if view:
                return Reply("Άνοιξα την ενότητα.", navigate=view)

        # Η άρνηση οριστικής έκδοσης κρίνεται ΠΡΩΤΗ από τις ενέργειες: το
        # «στείλ' το στην ΑΑΔΕ» δεν επιτρέπεται να καταλήξει πουθενά αλλού.
        if _hits(_WANTS_FINAL.pattern, speech, heard):
            return Reply(_REFUSAL, navigate="issue")

        # Λειτουργίες που ζουν ΜΕΣΑ στη σελίδα (το ✕ της ειδοποίησης, οι
        # «Στήλες», η «Επαναφορά»). Πριν από το COMMANDS επίτηδες — δες TIPS.
        for pattern, view, said in TIPS:
            if _hits(pattern, speech, heard):
                return Reply(said, navigate=view) if view else Reply(said)

        # Ενέργειες της εφαρμογής (εγχειρίδιο, αντίγραφο, αποσύνδεση…). Μετά την
        # πλοήγηση, ώστε το «πήγαινε στα πρόχειρα» να μένει πλοήγηση, και πριν τη
        # βοήθεια, ώστε το «οδηγίες χρήσης» να ανοίγει το εγχειρίδιο αντί να
        # τυπώνει τη λίστα παραδειγμάτων.
        for command, pattern, said in COMMANDS:
            if _hits(pattern, speech, heard):
                return Reply(said, command=command)

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

        # ΕΡΩΤΗΣΗ για ειδοποιήσεις, όχι σκέτη λέξη: το «ειδοποιήσεις» μόνο του
        # σημαίνει «άνοιξέ τες» (πέφτει στην πλοήγηση παρακάτω), ενώ το «πόσες
        # αδιάβαστες έχω» θέλει αριθμό από τον server.
        if _hits(r"ποσ\S*\s+\S*\s*(ειδοποιησ|αδιαβαστ)|εχω ειδοποιησ"
                 r"|τι νεο υπαρχει|any unread|how many unread"
                 r"|unread notification", speech, heard):
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
        # Πλήθη που ξέρουμε ήδη: πελατολόγιο και κατάλογος είναι φορτωμένα στη
        # μνήμη της Έκδοσης. Απαντιούνται εδώ, χωρίς γύρο στο backend — και
        # ΠΡΙΝ το `is_question`, που θα τα έστελνε στα στατιστικά παραστατικών.
        if re.search(r"ποσ\S*\s+(?:\w+\s+){0,2}πελατ"
                     r"|how many (?:\w+\s+){0,2}(?:customers|clients)"
                     r"|customer count|client count", speech):
            count = len(self._customers() or ())
            return Reply(f"Έχεις {count} πελάτες στο πελατολόγιο.")
        if re.search(r"ποσ\S*\s+(?:ειδ|προιοντ)|how many items|how many products"
                     r"|product count|item count", speech):
            count = len(self._products() or ())
            return Reply(f"Έχεις {count} είδη στον κατάλογο.")

        # «τα στατιστικά» είναι ΠΛΟΗΓΗΣΗ· «στατιστικά μήνα» είναι ερώτηση. Η
        # διαφορά είναι ο χρονικός προσδιορισμός, όχι η λέξη «στατιστικά».
        is_question = bool(
            re.search(r"^ποσ[αο]\b|ποσα τιμολ|ποσα παραστατ|τζιρο"
                      r"|how many|how much|turnover", speech)
            or re.search(r"(στατιστικ|statistic|stats)\S*\s*(ετουσ|μηνα|φετοσ"
                         r"|this year|this month|\byear\b|\bmonth\b)", speech)
        )
        if is_question:
            period = ("month" if re.search(_MONTHS, speech) else "year")
            return Reply("Φέρνω στατιστικά…", fetch=f"stats:{period}")

        wants_issue = bool(
            re.search(r"εκδοσ|τιμολογ|αποδειξ|παραστατ|issue|invoice", speech)
            and not re.search(r"λιστα|αναζητησ|ολα τα", speech)
        )

        if _hits(r"νε[οα]\S* (?:\w+\s+){0,2}πελατ|δημιουργησε (?:\w+\s+){0,2}πελατ"
                 r"|φτιαξε (?:\w+\s+){0,2}πελατ|καταχωρησε (?:\w+\s+){0,2}πελατ"
                 r"|προσθεσε (?:\w+\s+){0,2}πελατ|φτιαξε (?:\w+\s+){0,2}καρτελα"
                 r"|νεα καρτελα"
                 r"|new customer|create customer|create a client|add a customer"
                 r"|add a client|new client", speech, heard):
            afm = re.search(r"\b(\d{9})\b", raw)
            return Reply(
                "Ανοίγω φόρμα νέου πελάτη"
                + (f" για ΑΦΜ {afm.group(1)}" if afm else "")
                + ". Έλεγξε τα στοιχεία και πάτα Αποθήκευση.",
                dialog="customer",
                prefill={"vat": afm.group(1) if afm else ""},
            )

        if _hits(r"νεο (?:\w+\s+){0,2}ειδ|νεο (?:\w+\s+){0,2}προι"
                 r"|δημιουργησε (?:\w+\s+){0,2}ειδ|φτιαξε (?:\w+\s+){0,2}ειδ"
                 r"|καταχωρησε (?:\w+\s+){0,2}ειδ|καταχωρησε (?:\w+\s+){0,2}προι"
                 r"|προσθεσε (?:\w+\s+){0,2}ειδ|προσθεσε (?:\w+\s+){0,2}προι"
                 r"|new item|new product|add a product|add an item"
                 r"|create a product", speech, heard):
            price = _number(r"(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)", raw)
            desc = re.sub(
                r"^.*?(νέο είδ\S*|νεο ειδ\S*|νέο προϊ\S*|νεο προι\S*|new (?:item|product)|"
                r"καταχώρησε είδ\S*|καταχώρησε προϊ\S*|πρόσθεσε είδ\S*|πρόσθεσε προϊ\S*|"
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
            spec = parse_issue(raw)
            # «τα παραστατικά», «cancel an invoice», «μαζική έκδοση»:
            # περιέχουν λέξη τιμολόγησης, αλλά ΔΕΝ κουβαλούν τίποτα να
            # εκδοθεί — ούτε πελάτη, ούτε ποσό, ούτε είδος. Είναι ονόματα
            # οθονών, και εκεί πρέπει να πάνε. Η Έκδοση κρατά μόνο ό,τι
            # δείχνει πραγματικά σε αυτήν.
            if not any((spec.vat, spec.name, spec.item, spec.price)):
                view = _nav_match(speech, heard)
                if view and view != "issue":
                    return Reply("Άνοιξα την ενότητα.", navigate=view)
            return self._start_issue(spec)

        # Σιωπηλή πλοήγηση: «πελάτες» σκέτο, χωρίς ρήμα.
        view = _nav_match(speech, heard)
        if view:
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
