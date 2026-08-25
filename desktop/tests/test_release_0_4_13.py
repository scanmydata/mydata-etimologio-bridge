"""Φύλακες για τις αλλαγές της 0.4.13.

Το μοτίβο είναι το ίδιο με της 0.4.11: κάθε test αντιστοιχεί σε κάτι που
**έσπασε σιωπηλά** — χωρίς σφάλμα, χωρίς γραμμή σε log, με τον χρήστη να
κοιτάζει μια οθόνη που απλώς «δεν είναι σωστή».
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
ZIPWRITER = REPO / "zipwriter.php"
SERVERBACKUP = REPO / "serverbackup.php"
GUI = REPO / "desktop" / "src" / "timologio" / "gui"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


# --- 1. Το popup «Στήλες» ---------------------------------------------------
def test_the_popup_stylesheet_has_no_self_nested_selectors(page: str) -> None:
    """`#colFilterPop .cf-item .cf-item` δεν ταιριάζει ΠΟΤΕ με τίποτα.

    Κάθε κανόνας του παραθύρου είχε τον επιλογέα του γραμμένο δύο φορές, οπότε
    ολόκληρο το styling ήταν νεκρό: οι επιλογές έπεφταν η μία δίπλα στην άλλη
    σαν τρεχούμενο κείμενο. Κανένα σφάλμα πουθενά — απλώς λάθος εικόνα.
    """
    block = page[page.index("#colFilterPop{"):page.index("th.grid-check,td.grid-check")]
    doubled = [
        line.strip() for line in block.splitlines()
        if (m := re.match(r"\s*#colFilterPop\s+(\.[\w-]+)\b.*\1\b", line))
    ]
    assert doubled == [], f"ξαναδιπλασιάστηκαν επιλογείς: {doubled}"


def test_every_column_is_its_own_row(page: str) -> None:
    block = page[page.index("#colFilterPop{"):page.index("th.grid-check,td.grid-check")]
    assert "#colFilterPop .cf-list{" in block
    assert "flex-direction:column" in block
    assert "#colFilterPop .cf-item{" in block
    # Το `text-overflow` πάνω σε flex container δεν πιάνει ποτέ — θέλει παιδί.
    assert "#colFilterPop .cf-item span{" in block
    assert "text-overflow:ellipsis" in block[block.index("#colFilterPop .cf-item span{"):]


def test_column_labels_lose_the_sort_arrow(page: str) -> None:
    """«Επωνυμία ▲» είναι ΚΑΤΑΣΤΑΣΗ του πίνακα, όχι όνομα στήλης."""
    assert "function colLabel(th)" in page
    body = page[page.index("function colLabel(th)"):]
    assert ".sort-ind" in body[:300] and ".filter-btn" in body[:300]
    # Και ο τίτλος του φίλτρου υπολογίζεται τη ΣΤΙΓΜΗ του κλικ.
    assert "openColFilter(tableId,logical,th,colLabel(th))" in page


def test_the_nameless_actions_column_is_not_offered(page: str) -> None:
    """Μια στήλη χωρίς τίτλο εμφανιζόταν ως «(χωρίς τίτλο)» — δεν επιλέγεται."""
    assert "(χωρίς τίτλο)" not in page


# --- 2. Το φίλτρο τιμών -----------------------------------------------------
def test_the_filter_popup_no_longer_hides_columns(page: str) -> None:
    """Η ίδια ενέργεια ζει στο «⚙ Στήλες», όπου υπάρχει και επιστροφή."""
    assert "cf-hide" not in page
    assert "🚫 Απόκρυψη" not in page


# --- 3. VIES ----------------------------------------------------------------
def test_the_name_lookup_does_not_need_an_aade_session() -> None:
    """Το Taxisnet θέλει εταιρεία ΗΔΗ επιλεγμένη.

    Στο παράθυρο «Νέα εταιρεία» δεν υπάρχει καμία — γι' αυτό η αυτόματη
    συμπλήρωση επωνυμίας δεν δούλεψε ποτέ εκεί, και η αποτυχία καταπινόταν.
    """
    php = ETIM_PHP.read_text(encoding="utf-8")
    assert "function viesName(string $afm)" in php
    assert "vies/rest-api/ms/EL/vat/" in php
    # Το endpoint ζει στο μπλοκ `?auth=`, που τρέχει ΠΡΙΝ το `login()` της ΑΑΔΕ.
    assert php.index("case 'vies_name':") < php.index("$ch = login();")


def test_multiple_vies_names_keep_the_first() -> None:
    """Το VIES δίνει «ΤΟ ΒΑΨΙΜΟ Ε Ε||ΤΟ ΒΑΨΙΜΟ» — δεύτερο όνομα, όχι επωνυμία."""
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("function viesName(string $afm)"):]
    body = body[:body.index("\n}")]
    assert "'||'" in body
    assert "trim($name, '-')" in body, "το «---» σημαίνει «δεν δίνεται όνομα»"


def test_the_page_falls_back_from_taxisnet_to_vies(page: str) -> None:
    body = page[page.index("async function nameForVat(vat)"):]
    body = body[:body.index("\n}")]
    assert body.index("taxis_name") < body.index("vies_name"), "ΑΑΔΕ πρώτα"


def test_the_lookup_shows_that_it_is_working(page: str) -> None:
    """Χωρίς σημάδι, ο χρήστης κοιτά κενό πεδίο και το γράφει στο χέρι."""
    body = page[page.index("function coVatLookup()"):]
    assert "withBusy(" in body[:400]


# --- 4. Δοκιμή διαπιστευτηρίων ---------------------------------------------
def test_credentials_are_tested_against_both_services() -> None:
    """Ένα πράσινο myDATA ΔΕΝ αποδεικνύει ότι θα μπεις στο e-timologio.

    Είναι άλλη πύλη, με δική της εγγραφή — και τα δύο κλειδιά έχουν την ίδια
    μορφή, οπότε το λάθος κλειδί μπαίνει «σωστά» και φαίνεται ώρες αργότερα.
    """
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("function aadeCredentialTest("):]
    body = body[:body.index("\n/**", 10)]
    assert "RequestMyExpenses" in body
    assert "ocp-apim-subscription-key" in body and "aade-user-id" in body
    assert "/Account/Login" in body, "και το e-timologio, που είναι αυτό που εκδίδει"
    assert "$out['mydata']" in body and "$out['etimologio']" in body


def test_zero_expenses_is_not_a_failure_on_the_server() -> None:
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("function aadeCredentialTest("):]
    assert "χωρίς έξοδα" in body[:4000]


def test_the_probe_never_touches_the_live_session() -> None:
    """Δικό της cookie jar: μια αποτυχημένη δοκιμή δεν βγάζει τον χρήστη έξω."""
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("function aadeCredentialTest("):]
    body = body[:body.index("\n/**", 10)]
    assert "tempnam(" in body and "COOKIE_FILE" not in body


# --- 5. Επαναφορά του server ------------------------------------------------
def test_zip_reader_is_not_named_after_a_real_php_function() -> None:
    """`zip_read()` ΥΠΑΡΧΕΙ στην PHP (ext/zip, το παλιό procedural API).

    Η επέκταση `zip` είναι φορτωμένη για τα .xlsx των τραπεζών, οπότε η δική
    μας δήλωση έριχνε ΟΛΗ την εφαρμογή με «Cannot redeclare» — στον server, όχι
    στη φορητή PHP της ανάπτυξης.
    """
    zw = ZIPWRITER.read_text(encoding="utf-8")
    assert "function zip_read(" not in zw
    assert "function zip_unpack(" in zw
    assert "function zip_unpack" in SERVERBACKUP.read_text(encoding="utf-8") or \
           "zip_unpack(" in SERVERBACKUP.read_text(encoding="utf-8")


def test_the_unpacker_verifies_every_crc() -> None:
    """Ένα αντίγραφο που ξεπακετάρει σκουπίδια χωρίς να διαμαρτυρηθεί είναι
    χειρότερο από ένα που αρνείται να ανοίξει."""
    zw = ZIPWRITER.read_text(encoding="utf-8")
    body = zw[zw.index("function zip_unpack("):]
    assert "crc32($data)" in body


def test_restore_takes_a_safety_copy_before_touching_anything() -> None:
    sb = SERVERBACKUP.read_text(encoding="utf-8")
    body = sb[sb.index("function srv_backup_restore("):]
    body = body[:body.index("\n/**")]
    assert body.index("srv_backup_run('pre-restore')") < body.index("zip_unpack(")
    # Και δεν γράφεται ΤΙΠΟΤΑ πριν επιβεβαιωθεί ότι μέσα υπάρχει βάση.
    assert body.index("$files = zip_unpack(") < body.index("file_put_contents")


def test_restore_refuses_a_backup_from_the_other_engine() -> None:
    """Αντίγραφο SQLite πάνω σε server Postgres είναι το συνηθισμένο λάθος."""
    sb = SERVERBACKUP.read_text(encoding="utf-8")
    body = sb[sb.index("function srv_backup_restore("):]
    assert "db.dump" in body and "local.sqlite" in body
    assert "ο server τρέχει" in body


def test_restore_needs_a_typed_word_not_just_a_click() -> None:
    """Ένα confirm() πατιέται αντανακλαστικά· αυτό εδώ δεν ξεγίνεται."""
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("case 'srv_backup_restore':"):]
    body = body[:body.index("case 'srv_backup_settings':")]
    assert "'ΕΠΑΝΑΦΟΡΑ'" in body
    assert "in_array($src, ['local', 'drive', 'upload'], true)" in body


def test_restore_is_master_only() -> None:
    php = ETIM_PHP.read_text(encoding="utf-8")
    head = php[php.index("case 'srv_backup_status': case 'srv_backup_run'"):]
    head = head[:head.index("switch ($authAction)")]
    assert "srv_backup_restore" in head
    assert "if (!is_master())" in head


def test_drive_downloads_bytes_not_json() -> None:
    """Το `gdrive_call` περνά την απάντηση από json_decode — ένα κρυπτογραφημένο
    αντίγραφο δεν είναι JSON και θα καταστρεφόταν σιωπηλά."""
    gd = (REPO / "gdrive.php").read_text(encoding="utf-8")
    assert "function gdrive_download(" in gd
    body = gd[gd.index("function gdrive_download("):]
    body = body[:body.index("\nfunction ")]
    assert "alt=media" in body


def test_the_admin_card_offers_restore_for_both_sources(page: str) -> None:
    assert "function srvBackupRestore(" in page
    body = page[page.index("function srvBackupRestore("):]
    assert "ΕΠΑΝΑΦΟΡΑ" in body[:1600]
    # Το id του αρχείου του Drive πρέπει να φτάνει στη σελίδα.
    assert "'id'   => (string)($f['id'] ?? '')" in SERVERBACKUP.read_text(encoding="utf-8")


# --- 6. Η έκδοση ------------------------------------------------------------
def test_the_version_is_readable() -> None:
    """Ήταν γραμμένη στο χρώμα ΤΩΝ ΓΡΑΜΜΩΝ (#2b3b54 σε φόντο #0a111e), στα 10px."""
    qss = (GUI / "theme.py").read_text(encoding="utf-8")
    rule = qss[qss.index("QLabel#menuVersion {{"):]
    rule = rule[:rule.index("\n\n")]
    assert "{p.line}" not in rule, "το χρώμα των διαχωριστικών δεν διαβάζεται"
    assert "{p.muted}" in rule
    assert "font-size: 10px" not in rule


def test_clicking_the_version_checks_for_updates() -> None:
    side = (GUI / "side_menu.py").read_text(encoding="utf-8")
    launcher = (GUI / "launcher.py").read_text(encoding="utf-8")
    window = (GUI / "main_window.py").read_text(encoding="utf-8")
    assert "version_clicked = Signal()" in side
    assert "self.version.mousePressEvent = self._version_pressed" in side
    assert "update_check_requested = Signal()" in launcher
    assert "self._version_label.mousePressEvent = self._version_pressed" in launcher
    # ΕΝΑΣ έλεγχος για όλα τα σημεία: δύο θα σήμαιναν δύο νήματα και δύο απαντήσεις.
    assert "self.menu.version_clicked.connect(self._check_updates_requested)" in window
    assert "self.launcher.update_check_requested.connect(self._check_updates_requested)" in window


# --- 7. Η γραμμή τίτλου -----------------------------------------------------
def test_the_title_bar_uses_the_palette_not_just_dark_mode() -> None:
    """Η «σκούρη λειτουργία» δίνει το #202020 ΤΟΥ ΣΥΣΤΗΜΑΤΟΣ, όχι το χρώμα της
    εφαρμογής — πάνω από το ναυτικό μπλε φαίνεται ξένο κομμάτι."""
    theme = (GUI / "theme.py").read_text(encoding="utf-8")
    body = theme[theme.index("def paint_title_bar("):]
    for attribute in ("(35, palette.menu_bg)", "(36, palette.txt)", "(34, palette.line)"):
        assert attribute in body, f"λείπει το {attribute}"


def test_colorref_swaps_the_bytes() -> None:
    """Τα Windows θέλουν 0x00BBGGRR — ανάποδα από το #RRGGBB."""
    from timologio.gui.theme import _colorref

    assert _colorref("#ff0000") == 0x0000FF
    assert _colorref("#0000ff") == 0xFF0000
    assert _colorref("#0a111e") == 0x1E110A


def test_a_theme_switch_repaints_open_dialogs() -> None:
    window = (GUI / "main_window.py").read_text(encoding="utf-8")
    body = window[window.index("def _on_theme(self, light: bool)"):]
    body = body[:body.index("def _repaint_everything")]
    assert "QApplication.topLevelWidgets()" in body


# --- 8. Το εγχειρίδιο του web ----------------------------------------------
def test_the_manual_never_prints_markup(page: str) -> None:
    """Οι εγγραφές του `MANUAL` περιέχουν `<b>`. Ο παλιός renderer τα τύπωνε
    **ως κείμενο**, «<b>έτσι</b>», μέσα στο PDF."""
    assert "function mnRuns(text)" in page
    body = page[page.index("function mnRuns(text)"):]
    body = body[:body.index("\n}")]
    assert "<b>" in body and "replace(/<[^>]+>/g" in body


def test_the_manual_has_the_downloader_layout(page: str) -> None:
    body = page[page.index("async function downloadManual()"):]
    body = body[:body.index("\n// ===== Σύνδεση με web server")]
    assert "manualLogo()" in body, "εξώφυλλο με σήμα"
    assert "e-Τιμολόγιο Pro" in body
    assert "'•'" in body, "κουκκίδες, όχι σκέτες παράγραφοι"
    assert "getNumberOfPages()" in body, "αρίθμηση σελίδων"
    assert "ScanmyData Suite" in body, "υποσέλιδο σε κάθε σελίδα"


def test_the_manual_starts_on_the_first_page(page: str) -> None:
    """Το jsPDF ΞΕΚΙΝΑ με μία σελίδα· ένα addPage() στην αρχή έδινε κενή πρώτη."""
    body = page[page.index("const newPage=()=>{"):]
    assert "if(page++)doc.addPage();" in body[:120]


def test_missing_version_is_omitted_not_printed_as_a_dash(page: str) -> None:
    """Στον server το APP_VERSION_LABEL δεν ορίζεται· «έκδοση —» δεν λέει τίποτα."""
    assert "(APP_VER?' · έκδοση '+APP_VER:'')" in page


# --- 9. Το include που έσκαγε ανάλογα με τη σειρά --------------------------
def test_the_entry_point_includes_each_file_once() -> None:
    php = ETIM_PHP.read_text(encoding="utf-8")
    head = php[:php.index("// --- RESPONSE HELPERS")]
    plain = re.findall(r"^require __DIR__", head, re.MULTILINE)
    assert plain == [], "σκέτο require δίπλα σε require_once = «Cannot redeclare»"
