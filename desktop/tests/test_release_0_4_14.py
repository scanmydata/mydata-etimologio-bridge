"""Φύλακες για τις αλλαγές της 0.4.14.

Όπως και στις προηγούμενες: κάθε test αντιστοιχεί σε κάτι που **έσπασε
σιωπηλά** — ο χρήστης πατούσε και δεν συνέβαινε τίποτα, ή συνέβαινε λάθος
πράγμα χωρίς κανένα μήνυμα πουθενά.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
LOCALDB = REPO / "localdb.php"
SERVERBACKUP = REPO / "serverbackup.php"
GUI = REPO / "desktop" / "src" / "timologio" / "gui"
VENDOR = REPO / "assets" / "vendor"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


# --- 1. «Η βιβλιοθήκη PDF δεν φόρτωσε» -------------------------------------
def test_pdf_libraries_are_served_by_us_not_by_a_cdn(page: str) -> None:
    """Ο server στέλνει `Content-Security-Policy: script-src 'self'`.

    Το jsdelivr δεν είναι 'self', άρα το <script> δεν εκτελούνταν ΠΟΤΕ στο web:
    κάθε λειτουργία PDF (εγχειρίδιο, καρτέλα, εξαγωγές) απαντούσε «δεν
    φόρτωσε». Το ίδιο έκοβε και το `connect-src 'self'` για τη γραμματοσειρά.
    """
    assert "cdn.jsdelivr.net/npm/jspdf" not in page, "το CDN δεν περνά το CSP"
    assert "assets/vendor/jspdf.umd.min.js" in page
    assert "assets/vendor/DejaVuSans.ttf" in page
    conf = (REPO / "deploy" / "apache-etimologio.conf").read_text(encoding="utf-8")
    assert "script-src 'self'" in conf, "αν χαλαρώσει το CSP, το test χάνει το νόημά του"


def test_the_vendored_files_are_actually_there() -> None:
    for name, least in (
        ("jspdf.umd.min.js", 200_000),
        ("jspdf.plugin.autotable.min.js", 20_000),
        ("DejaVuSans.ttf", 500_000),
        ("DejaVuSans-Bold.ttf", 500_000),
    ):
        path = VENDOR / name
        assert path.exists(), f"λείπει το {name}"
        assert path.stat().st_size > least, f"το {name} είναι ύποπτα μικρό"


def test_the_font_tries_local_first(page: str) -> None:
    body = page[page.index("async function fetchFont("):]
    body = body[:body.index("\n}")]
    assert body.index("local") < body.index("FONT_CDN")


# --- 2. Τα κουτιά του browser γίνονται παράθυρα της εφαρμογής --------------
def test_no_native_dialogs_are_left(page: str) -> None:
    """`confirm()`/`prompt()`/`alert()` δεν παίρνουν θέμα, δείχνουν τη διεύθυνση
    του site, και μέσα στο QtWebEngine κάποια δεν εμφανίζονται καθόλου."""
    pattern = re.compile(r"(?<![\w.$])(confirm|prompt|alert)\s*\(")
    offenders = []
    for number, line in enumerate(page.replace("\r\n", "\n").split("\n"), 1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "<!--")):
            continue
        for match in pattern.finditer(line):
            before = line[max(0, match.start() - 8):match.start()]
            if before.endswith("await ") or before.endswith("window."):
                continue
            offenders.append(f"{number}: {stripped[:80]}")
    assert offenders == [], f"έμειναν κουτιά του browser: {offenders}"


def test_the_dialog_survives_being_asked_twice(page: str) -> None:
    """Δύο ερωτήσεις μαζί δεν χωρούν σε ένα παράθυρο· χωρίς εφεδρεία η δεύτερη
    θα κρεμούσε τη ροή για πάντα."""
    body = page[page.index("function uiAsk(opts){"):]
    body = body[:body.index("\nconst uiConfirm")]
    assert "UI_ASK_BUSY" in body
    assert "window.prompt" in body and "window.confirm" in body


def test_escape_counts_as_cancel(page: str) -> None:
    body = page[page.index("function uiAsk(opts){"):]
    assert "d.onclose=reject" in body[:3000]


# --- 3. Η αναμονή δεν σκεπάζει την οθόνη -----------------------------------
def test_the_wait_indicator_is_a_card_not_a_curtain(page: str) -> None:
    assert "#busyDlg" not in page, "το modal <dialog> με backdrop έφυγε"
    assert "#busyBox{position:fixed;right:" in page
    assert 'd.showModal()' not in page[page.index("function busyOn("):page.index("function busyOff(")]


def test_the_card_moves_into_an_open_dialog(page: str) -> None:
    """Ένα ανοιχτό <dialog> ζει στο «top layer»: ό,τι μένει στο <body> κρύβεται
    από πίσω του όσο μεγάλο κι αν είναι το z-index."""
    body = page[page.index("function busyOn("):page.index("function busyOff(")]
    assert "dialog[open]" in body and "appendChild" in body


# --- 4. Ο επιλογέας στηλών έφευγε εκτός οθόνης -----------------------------
def test_popups_are_clamped_into_the_viewport(page: str) -> None:
    assert "function popPlace(pop,r)" in page
    body = page[page.index("function popPlace(pop,r)"):]
    body = body[:body.index("\n}")]
    assert "window.innerHeight" in body and "window.innerWidth" in body
    # Και άνοιγμα προς τα ΠΑΝΩ όταν δεν χωρά από κάτω.
    assert "r.top-4-box.height" in body
    # Καμία χειροκίνητη τοποθέτηση δεν επέζησε.
    assert "pop.style.top=(r.bottom+4)" not in page


def test_resizing_closes_the_open_popup(page: str) -> None:
    """Το παράθυρο έμενε καρφωμένο εκεί που ήταν — δηλαδή συχνά εκτός οθόνης."""
    assert "window.addEventListener('resize',()=>{const pop=$('#colFilterPop');" in page


# --- 5. Το μπάνερ ρόλου και οι ενότητες της Διαχείρισης --------------------
def test_the_role_banner_only_survives_as_a_warning(page: str) -> None:
    """Ο ρόλος γράφεται ήδη στην πάνω μπάρα και στον υπότιτλο· τρίτη φορά είναι
    θόρυβος. Η προειδοποίηση για αναθέσεις που λείπουν ΔΕΝ είναι."""
    body = page[page.index("function renderScopeBanner()"):]
    body = body[:body.index("\nfunction renderBiz")]
    assert "scope-row" not in body
    assert "scope-warn" in body
    assert "box.hidden=!warn" in body


def test_the_admin_screen_is_collapsible_too(page: str) -> None:
    assert "setupSections('#view-admin')" in page
    assert "sectAll('#view-admin',true)" in page
    # Το μπάνερ δεν είναι ενότητα: δεν πρέπει να αποκτήσει κεφάλι που διπλώνει.
    assert "nosect" in page
    assert "panel.classList.contains('nosect')" in page


# --- 6. Η γρήγορη αναζήτηση ------------------------------------------------
def test_quick_search_covers_more_than_customers(page: str) -> None:
    assert "function palLocal(term)" in page
    body = page[page.index("function palLocal(term)"):]
    body = body[:body.index("\nasync function palSearch")]
    for kind in ("Είδος", "Σειρά", "Παραστατικό"):
        assert f"'{kind}'" in body, f"λείπει το «{kind}»"
    assert "palViews()" in body and "palPanels()" in body


def test_quick_search_reads_globals_that_are_not_on_window(page: str) -> None:
    """`let SERIES=[]` στο top level ενός classic script ΔΕΝ γράφεται στο
    `window`: το `window.SERIES` είναι πάντα undefined και η αναζήτηση δεν θα
    έβρισκε ποτέ σειρά — χωρίς κανένα σφάλμα."""
    body = page[page.index("function palLocal(term)"):]
    body = body[:body.index("\nasync function palSearch")]
    assert "window.SERIES" not in body and "window.PRODMAP" not in body
    assert "typeof SERIES!=='undefined'" in body


def test_enter_runs_the_row_action_not_always_open_card(page: str) -> None:
    assert "if(r&&r.go){closePalette();r.go();}" in page


def test_the_assistant_knows_about_the_search(page: str) -> None:
    assert "ψ[άα]ξε" in page
    body = page[page.index("// Αναζήτηση παντού"):]
    assert "openPalette()" in body[:900] and "palSearch()" in body[:900]


# --- 7. Επαναφορά από ανεβασμένο αρχείο ------------------------------------
def test_restore_accepts_an_uploaded_file() -> None:
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("case 'srv_backup_restore':"):]
    body = body[:body.index("case 'srv_backup_settings':")]
    assert "$_FILES['backup']" in body
    # Το πιο συχνό «δεν δουλεύει» εδώ είναι το όριο της PHP, όχι σφάλμα κώδικα.
    assert "upload_max_filesize" in body


def test_the_page_sends_a_real_multipart_request(page: str) -> None:
    """Το `apost` στέλνει urlencoded — δεν μεταφέρει αρχεία."""
    body = page[page.index("async function srvBackupUpload(input)"):]
    body = body[:body.index("\nfunction srvBackupDownload")]
    assert "new FormData()" in body and "fetch(API" in body
    assert "ΕΠΑΝΑΦΟΡΑ" in body


# --- 8. Το «malformed» μετά από επιτυχημένη επαναφορά ----------------------
def test_the_sqlite_handle_closes_before_the_file_is_overwritten() -> None:
    """Γράψιμο πάνω σε ΑΝΟΙΧΤΗ SQLite την αφήνει «malformed» για το ίδιο αίτημα:
    η επαναφορά έλεγε «επιτυχία» και η επόμενη οθόνη «η βάση δεν είναι
    διαθέσιμη». Μετρημένο σε πραγματική επαναφορά, όχι θεωρητικό."""
    db = LOCALDB.read_text(encoding="utf-8")
    assert "function localdb(bool $close = false): ?\\PDO" in db
    assert "if ($close) { $pdo = null; return null; }" in db

    sb = SERVERBACKUP.read_text(encoding="utf-8")
    body = sb[sb.index("function srv_backup_restore("):]
    assert body.index("localdb(true);") < body.index("file_put_contents($path, $files['local.sqlite'])")


# --- 9. Ο χρονοπρογραμματισμός έγινε σελίδα --------------------------------
def test_the_schedule_left_the_control_panel() -> None:
    control = (GUI / "control_panel.py").read_text(encoding="utf-8")
    assert "_schedule_box" not in control
    assert "chk_schedule" not in control
    # Και ο Πίνακας ελέγχου κυλά: σε παράθυρο που δεν είναι πλήρους οθόνης τα
    # κουτιά δεν χωρούσαν και ό,τι περίσσευε κοβόταν χωρίς μπάρα.
    assert "QScrollArea" in control


def test_the_schedule_page_lets_you_pick_the_clients() -> None:
    """Το «μόνο οι επιλεγμένοι» δεν είχε πουθενά να δείξει ΠΟΙΟΥΣ."""
    page = (GUI / "schedule_page.py").read_text(encoding="utf-8")
    assert "QListWidget" in page
    assert "def selected_vats" in page
    assert "ItemIsUserCheckable" in page
    # «Όλους»/«Κανέναν» αφορά ΟΣΟΥΣ ΦΑΙΝΟΝΤΑΙ — αλλιώς: βλέπεις τρεις,
    # κατεβάζεις τριακόσιους.
    body = page[page.index("def _check_visible"):]
    assert "isHidden()" in body[:600]


def test_the_selection_comes_from_the_page_not_from_another_screen() -> None:
    window = (GUI / "main_window.py").read_text(encoding="utf-8")
    body = window[window.index("def _on_schedule_changed"):]
    body = body[:body.index("\n    def ", 10)]
    assert "self._checked" not in body, "η επιλογή ανήκει στη σελίδα του προγράμματος"
    assert "schedule.vats" in body


def test_the_schedule_is_in_the_menu_and_in_the_tour() -> None:
    menu = (GUI / "side_menu.py").read_text(encoding="utf-8")
    assert '"schedule", "Χρονοπρογραμματισμός"' in menu
    window = (GUI / "main_window.py").read_text(encoding="utf-8")
    assert '"schedule": self._open_schedule,' in window
    assert "self.schedule_page.chk_enabled" in window, "η ξενάγηση δείχνει τη νέα σελίδα"
    assert '"schedule")' in window   # μπήκε στο _PAGES


def test_the_manual_points_at_the_new_place() -> None:
    manual = (GUI / "manual.py").read_text(encoding="utf-8")
    assert "<b>Χρονοπρογραμματισμός</b> στο μενού" in manual
    assert "Στον ίδιο πίνακα, <b>Χρονοπρογραμματισμός λήψης</b>" not in manual


# --- 10. Η ξενάγηση δεν δείχνει σε αόρατο στοιχείο -------------------------
def test_the_tour_never_points_at_a_hidden_file_input(page: str) -> None:
    """`display:none` σημαίνει μηδενικές διαστάσεις — δηλαδή δείκτη στη γωνία."""
    assert "{sel:'#sbUpload'," not in page
    assert "{sel:'#sbUploadBtn'," in page
