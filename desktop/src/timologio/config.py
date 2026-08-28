"""Ρυθμίσεις εφαρμογής.

Ο φάκελος δεδομένων κρατιέται εκτός του πακέτου ώστε το PyInstaller bundle να
μένει read-only και το .enckey να επιβιώνει σε αναβαθμίσεις.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# --- myDATA endpoints -------------------------------------------------------
MYDATA_BASE = "https://mydatapi.aade.gr/myDATA"
URL_REQUEST_DOCS = f"{MYDATA_BASE}/RequestDocs"
URL_REQUEST_TRANSMITTED_DOCS = f"{MYDATA_BASE}/RequestTransmittedDocs"
URL_REQUEST_E3_INFO = f"{MYDATA_BASE}/RequestE3Info"
#: Έλεγχος διαπιστευτηρίων. Το `RequestMyExpenses` επιστρέφει τα **σύνολα** των
#: εξόδων μιας περιόδου (myDATA REST API v2.0.1, §4.2.9) — μια απάντηση μικρή
#: όσο μια σελίδα, σε αντίθεση με το `RequestDocs` που κατεβάζει ολόκληρα
#: παραστατικά. Ό,τι χρειάζεται για να απαντηθεί «περνούν αυτά τα κλειδιά;»
#: χωρίς να φορτωθεί η ΑΑΔΕ με πραγματική λήψη.
URL_REQUEST_MY_EXPENSES = f"{MYDATA_BASE}/RequestMyExpenses"

#: Ο μόνος host στον οποίο επιτρέπεται να σταλούν τα διαπιστευτήρια ΑΑΔΕ.
AADE_HOST = "mydatapi.aade.gr"

#: XML namespace όλων των απαντήσεων myDATA.
NS = {"ns": "http://www.aade.gr/myDATA/invoice/v1.0"}

# --- Πάροχοι ----------------------------------------------------------------
#: Το επίσημο PDF της ΑΑΔΕ (σελ. 31) λέει ότι το σκέτο downloadingInvoiceUrl
#: επιστρέφει PDF by default. ΔΕΝ ισχύει: μετρημένα, Epsilon και Impact
#: επιστρέφουν HTML σελίδα προβολής. Το suffix είναι υποχρεωτικό.
PDF_SUFFIX = "/pdf"


#: Κλειδί registry όπου ο installer γράφει τον φάκελο δεδομένων που επέλεξε ο
#: χρήστης. HKCU (όχι HKLM) ώστε να μη χρειάζεται δικαιώματα διαχειριστή.
_REG_PATH = r"Software\scanmydata\TimologioDownloader"
_REG_VALUE = "DataDir"

#: Οι τρεις ρόλοι που δίνει ο installer. Ο ρόλος δεν αλλάζει τι *μπορεί* να κάνει
#: η εφαρμογή — αλλάζει τι της ταιριάζει: ο server ξεκινά στο tray και μένει
#: ανοιχτός, το τερματικό ελέγχει τη σύνδεση πριν από οτιδήποτε άλλο.
ROLES = ("standalone", "server", "terminal")

#: Η έκδοση που δηλώνει το κάθε instance στους υπόλοιπους του δικτύου. Κρατιέται
#: εδώ ώστε να υπάρχει μία πηγή: το pyproject δεν διαβάζεται μέσα από το bundle
#: του PyInstaller.
APP_VERSION = "0.4.22"

ROLE_LABELS_EL = {
    "standalone": "Αυτόνομος υπολογιστής",
    "server": "Server (κρατά τα δεδομένα)",
    "terminal": "Τερματικό (συνδέεται στον server)",
}


def _registry_value(name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return str(value) if value else None
    except OSError:
        return None


def _data_dir_from_registry() -> Path | None:
    value = _registry_value(_REG_VALUE)
    return Path(value) if value else None


def load_role() -> str:
    """Ο ρόλος του υπολογιστή, όπως τον όρισε ο installer."""
    value = (os.environ.get("TIMOLOGIO_ROLE") or _registry_value("Role") or "").lower()
    return value if value in ROLES else "standalone"


def load_start_minimized() -> bool:
    """Ξεκινά μαζεμένο στο tray;

    Ο installer γράφει την αρχική τιμή· η εφαρμογή τη γράφει ξανά όταν την
    αλλάξει ο χρήστης από τον πίνακα ελέγχου, ώστε να υπάρχει μία πηγή αλήθειας
    ανεξάρτητα από το ποιος την όρισε τελευταίος.
    """
    return (_registry_value("StartMinimized") or "0") == "1"


def save_start_minimized(value: bool) -> None:
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            winreg.SetValueEx(key, "StartMinimized", 0, winreg.REG_SZ, "1" if value else "0")
    except OSError:
        pass


def consume_show_once() -> bool:
    """Μία-φορά σημαία «δείξε κανονικά το παράθυρο» που γράφει ο installer σε
    ΚΑΘΕ εγκατάσταση/ενημέρωση.

    Επιστρέφει ``True`` αν ήταν αναμμένη και τη σβήνει. Έτσι η **πρώτη** εκκίνηση
    μετά την εγκατάσταση ανοίγει κανονικά το παράθυρο, ακόμη κι αν έχει επιλεγεί
    «εκκίνηση στο tray» — ανεξάρτητα από ποιο μονοπάτι ξεκίνησε την εφαρμογή
    (κουμπί «Εκκίνηση» του installer, αυτόματη εκκίνηση, ή relaunch της
    ενημέρωσης). Πιο αξιόπιστο από το ``--show``, που εξαρτάται από το αν το
    σωστό όρισμα έφτασε στη σωστή διεργασία."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ShowWindowOnce")
            if str(value) == "1":
                try:
                    winreg.DeleteValue(key, "ShowWindowOnce")
                except OSError:
                    pass
                return True
    except OSError:
        pass
    return False


#: Υποφάκελος για τα κατεβασμένα PDF/ZIP, μέσα στον φάκελο δεδομένων που
#: επέλεξε ο χρήστης στην εγκατάσταση. Δίπλα στα παραστατικά της Λήψης, όχι
#: χαμένος στα «Λήψεις» των Windows.
DOWNLOADS_DIRNAME = "Λήψεις e-Τιμολόγιο"


def load_download_dir() -> Path | None:
    """Ο φάκελος λήψεων **που όρισε ρητά ο χρήστης** (αλλιώς ``None``)."""
    raw = os.environ.get("TIMOLOGIO_DOWNLOAD_DIR") or _registry_value("DownloadDir")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if str(path).strip() else None


def default_download_dir(data_dir: Path | str) -> Path:
    """Πού πέφτουν τα αρχεία όταν δεν έχει επιλέξει κάτι ο χρήστης."""
    return Path(data_dir) / DOWNLOADS_DIRNAME


def resolve_download_dir(data_dir: Path | str) -> Path:
    """Ο φάκελος λήψεων που ισχύει τώρα — ΠΑΝΤΑ κάποιος.

    Χωρίς προεπιλογή, κάθε «PDF καρτέλας» ή «ZIP παραστατικών» άνοιγε διάλογο
    «πού να το βάλω;». Χειρότερα: αν ο χρήστης τον έκλεινε, η λήψη ακυρωνόταν
    και **δεν άνοιγε τίποτα** — έμοιαζε με χαλασμένο κουμπί, όχι με ακύρωση.
    """
    return load_download_dir() or default_download_dir(data_dir)


def save_download_dir(path: Path | str | None) -> None:
    """Θυμάται τον φάκελο λήψεων (κενό = «ρώτα με κάθε φορά»)."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            winreg.SetValueEx(key, "DownloadDir", 0, winreg.REG_SZ, str(path or ""))
    except OSError:
        pass


def _documents_dir() -> Path:
    """Ο φάκελος «Έγγραφα», ακόμη κι αν έχει μετακινηθεί (π.χ. OneDrive)."""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
            return Path(os.path.expandvars(value))
        except OSError:
            pass
    return Path.home() / "Documents"


def _default_data_dir() -> Path:
    return _documents_dir() / "Παραστατικά myDATA"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    """Ρίζα για βάση, .enckey και κατεβασμένα αρχεία."""

    max_workers: int = 8
    """Συνολικά ταυτόχρονα downloads."""

    max_per_host: int = 2
    """Ταυτόχρονα ανά πάροχο. Impact+Epsilon = ~88% του όγκου· χωρίς αυτό
    τους σφυροκοπάμε."""

    aade_timeout: int = 120
    """Το RequestDocs επιστρέφει μεγάλα XML — θέλει γενναίο timeout."""

    provider_timeout: int = 60
    max_retries: int = 4
    retry_cap_seconds: int = 300

    @property
    def db_path(self) -> Path:
        return self.data_dir / "timologio.db"

    @property
    def enckey_path(self) -> Path:
        return self.data_dir / ".enckey"

    @property
    def storage_root(self) -> Path:
        return self.data_dir / "data"

    @property
    def role(self) -> str:
        return load_role()


def _has_clients(db_path: Path) -> bool:
    """Έχει ΔΕΔΟΜΕΝΑ αυτή η βάση; (όχι απλώς «υπάρχει το αρχείο»)

    Ανοίγει read-only: ένας φάκελος που ελέγχεται δεν πρέπει να αποκτήσει βάση
    επειδή τον κοιτάξαμε.
    """
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT 1 FROM clients LIMIT 1").fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _save_data_dir(path: Path) -> None:
    """Γράφει τον φάκελο δεδομένων στο μητρώο (ό,τι γράφει και ο installer)."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            winreg.SetValueEx(key, _REG_VALUE, 0, winreg.REG_SZ, str(path))
    except OSError:
        pass


def recover_data_dir(configured: Path) -> Path:
    """Ο φάκελος που ΟΝΤΩΣ κρατά τα δεδομένα, όταν ο ρυθμισμένος είναι άδειος.

    ⚠️ ΓΙΑΤΙ ΥΠΑΡΧΕΙ — μετρημένο σε πραγματική εγκατάσταση. Ο installer παίρνει
    τον φάκελο από τη γραμμή εντολών της αυτόματης ενημέρωσης με το
    ``{param:DATADIR|}`` του Inno, **που κόβει την τιμή στο πρώτο κενό**. Το
    ``C:\\…\\Παραστατικά myDATA`` γινόταν ``C:\\…\\Παραστατικά``: ο installer
    έγραφε ΑΥΤΟ στο μητρώο, η επόμενη εκκίνηση άνοιγε καινούρια άδεια βάση, και
    ο χρήστης έβλεπε την εφαρμογή «να έχασε τα πάντα» ενώ τα δεδομένα κάθονταν
    άθικτα δύο εκατοστά πιο δίπλα. Το ίδιο έπαιρνε μαζί του και το e-Τιμολόγιο,
    που ζει σε υποφάκελο του ίδιου φακέλου.

    Η αιτία διορθώθηκε στον installer (δες ``CmdLineParam`` στο timologio.iss),
    αλλά το χαλασμένο μητρώο ΜΕΝΕΙ σε όποιον ενημερώθηκε ήδη. Εδώ το βρίσκουμε
    και το επισκευάζουμε: το κόψιμο γίνεται πάντα σε κενό, άρα ο πραγματικός
    φάκελος είναι αδελφός που **ξεκινά με το ίδιο όνομα**.

    Δεν μετακινεί και δεν σβήνει τίποτα — μόνο δείχνει αλλού.
    """
    if _has_clients(configured / "timologio.db"):
        return configured

    candidates: list[Path] = []
    try:
        prefix = configured.name + " "
        candidates += sorted(
            p for p in configured.parent.iterdir()
            if p.is_dir() and p.name.startswith(prefix)
        )
    except OSError:
        pass
    default = _default_data_dir()
    if default != configured:
        candidates.append(default)

    for candidate in candidates:
        if _has_clients(candidate / "timologio.db"):
            log.warning(
                "Ο ρυθμισμένος φάκελος δεδομένων (%s) είναι άδειος — τα δεδομένα "
                "βρέθηκαν στο %s. Διορθώνεται το μητρώο.", configured, candidate,
            )
            _save_data_dir(candidate)
            return candidate
    return configured


def load_settings() -> Settings:
    """Ο φάκελος δεδομένων, κατά σειρά προτεραιότητας:

    1. TIMOLOGIO_DATA_DIR (για δοκιμές / φορητή χρήση)
    2. ό,τι επέλεξε ο χρήστης στην εγκατάσταση (registry)
    3. Έγγραφα\\Παραστατικά myDATA

    Το (2) περνά από ``recover_data_dir``: μια ρύθμιση που δείχνει σε άδειο
    φάκελο δεν είναι λόγος να ανοίξει η εφαρμογή χωρίς τα δεδομένα του χρήστη.
    """
    raw = os.environ.get("TIMOLOGIO_DATA_DIR")
    if raw:
        return Settings(data_dir=Path(raw).expanduser())
    from_registry = _data_dir_from_registry()
    if from_registry is not None:
        return Settings(data_dir=recover_data_dir(from_registry))
    return Settings(data_dir=_default_data_dir())
