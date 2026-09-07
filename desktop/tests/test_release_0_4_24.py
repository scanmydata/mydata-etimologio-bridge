"""Οκτώ αναφορές, και δύο από αυτές είχαν κοινή ρίζα.

* **Το «+» έλειπε ακριβώς εκεί που χρειαζόταν.** Ο έλεγχος ήταν «μόνο
  διαχειριστής», αλλά στην εγκατάσταση υπολογιστή ο συνδεδεμένος χρήστης είναι
  **λογιστής** (`editor`, δες ``auth_desktop_workspace_user``) — και το ίδιο
  ισχύει για κάθε λογιστή στο web. Το κουμπί ήταν αόρατο στους δύο ακριβώς
  ρόλους που θα το πατούσαν.

* **Δύο email για ένα παραστατικό.** Ο έλεγχος ΑΑΔΕ ξεχώριζε τα δικά μας
  παραστατικά ρωτώντας **μόνο** τον πίνακα ειδοποιήσεων — που ο χρήστης τον
  αδειάζει με το «✕». Σβησμένη ειδοποίηση ⇒ το τιμολόγιο ξαναφαινόταν άγνωστο
  ⇒ δεύτερο email, «Έλεγχος ΑΑΔΕ», για ό,τι μόλις εκδόθηκε από εδώ.

* **Ο σύνδεσμος εγγραφής δεν άνοιγε.** Μέσα στο παράθυρο της εφαρμογής δεν
  υπάρχουν καρτέλες: το ``target="_blank"`` πέφτει στο κενό, σιωπηλά.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
AUTH_PHP = REPO / "auth.php"
AUTHVIEW = REPO / "authview.php"
SHELL_PY = REPO / "desktop" / "src" / "timologio" / "etimologio" / "webshell.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """Το απόσπασμα ΧΩΡΙΣ τα σχόλιά του.

    Χρειάζεται για τους ελέγχους «αυτό ΔΕΝ πρέπει να υπάρχει»: το σχόλιο που
    εξηγεί γιατί κάτι αφαιρέθηκε περιέχει αναγκαστικά το ίδιο κείμενο, και ο
    έλεγχος θα έπεφτε πάνω στην ίδια του την τεκμηρίωση.
    """
    kept = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return "\n".join(kept)


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


@pytest.fixture(scope="module")
def shell() -> str:
    return _read(SHELL_PY)


# ===========================================================================
# 1. Ένα παραστατικό, ένα email
# ===========================================================================
def test_the_scan_remembers_what_we_issued_even_after_the_bell_is_cleared():
    """Ο πίνακας ειδοποιήσεων ΔΕΝ είναι μνήμη: το «✕» τον αδειάζει."""
    src = _read(ETIM_PHP)
    assert "function markIssuedHere(" in src
    assert "function issuedMarksFromAudit(" in src
    loop = src[src.index("foreach ($found as $inv) {"):]
    loop = loop[: loop.index("notification_add(")]
    # Και οι δύο μνήμες ρωτιούνται ΠΡΙΝ γραφτεί οτιδήποτε.
    assert "isset($mine[$mk])" in loop
    assert "$mine = issuedMarksFromAudit(COMPANY_VAT);" in src


def test_the_issue_writes_itself_into_the_scan_memory():
    src = _read(ETIM_PHP)
    fn = src[src.index("function markIssuedHere("):]
    fn = fn[: fn.index("\n}")]
    assert "cache_get(COMPANY_VAT, 'newdocs')" in fn
    assert "cache_set(COMPANY_VAT, 'newdocs', $rows)" in fn
    # Χωρίς προηγούμενη σάρωση ο έλεγχος δεν τρέχει — ούτε να γράψουμε έχει νόημα.
    assert "if (!$c) return;" in fn
    # Και δεν διπλογράφει το ίδιο ΜΑΡΚ.
    assert "if ((string)($r['mark'] ?? '') === $mk) return;" in fn


def test_delivery_notes_are_remembered_too():
    """Τα δελτία (9.x) επίτηδες δεν γράφουν ειδοποίηση — άρα φαίνονταν «ξένα»."""
    src = _read(ETIM_PHP)
    assert "if ($live && !$previewFlag) markIssuedHere($result);" in src
    # Και η κανονική έκδοση περνά από το ίδιο σημείο.
    notify = src[src.index("function notifyIssue("):]
    notify = notify[: notify.index("\n}")]
    assert "markIssuedHere($result);" in notify


def test_a_notification_that_fails_to_save_is_no_longer_silent():
    """Ειδοποίηση που δεν γράφτηκε = καμπάνα που δεν χτύπησε."""
    src = _read(ETIM_PHP)
    assert "error_log('notification_add: '" in src


def test_a_genuinely_foreign_document_is_still_reported():
    """Η διόρθωση δεν επιτρέπεται να σκοτώσει τη λειτουργία μαζί με το σφάλμα."""
    src = _read(ETIM_PHP)
    loop = src[src.index("foreach ($found as $inv) {"):]
    loop = loop[: loop.index("if (++$discovered")]
    assert "notification_add(COMPANY_VAT, [" in loop
    assert "'source'        => 'aade'," in loop


# ===========================================================================
# 2. Το «+» ανήκει και στον λογιστή
# ===========================================================================
def test_the_quick_add_button_is_visible_to_accountants(page: str):
    start = page.index('id="acctQuickAdd"')
    guard = page.rindex("<?php if (", 0, start)
    line = page[guard:page.index("?>", guard)]
    assert "'master','editor'" in line, f"ο φύλακας του «+» είναι ακόμη: {line}"


def test_the_endpoint_behind_it_accepts_accountants():
    """Το κουμπί χωρίς δικαίωμα θα ήταν απλώς ένα 403 με ωραίο χρώμα."""
    src = _read(ETIM_PHP)
    block = src[src.index("case 'staff_add_company': {"):]
    block = block[: block.index("case 'staff_invite_client'")]
    assert "user_is_staff($u)" in block
    # Και αναθέτει μόνο του τη νέα εταιρεία, αλλιώς ο λογιστής δεν θα την έβλεπε.
    assert "($u['role'] ?? '') === 'editor'" in block
    assert "manager_set_accounts" in block


# ===========================================================================
# 3. Οι εξωτερικοί σύνδεσμοι ανοίγουν στον browser του χρήστη
# ===========================================================================
def test_the_page_asks_the_shell_to_open_external_links(page: str, shell: str):
    assert "function openExternalUrl(" in page
    assert "h.openExternal(url)" in page
    assert "def openExternal(" in shell
    assert "open_external_requested" in shell


def test_the_signup_link_and_its_popup_both_go_through_it(page: str):
    nag = page[page.index("const nag=$('#lkSignup');"):]
    nag = nag[: nag.index("\n    }")]
    assert "openExternalUrl(" in nag
    assert 'target="_blank"' not in _code(nag), "μέσα στην εφαρμογή δεν υπάρχει καρτέλα να ανοίξει"
    # Και το παράθυρο της καταχώρησης προσφέρει το ίδιο, ως κουμπί.
    connect = page[page.index("async function linkConnect()"):]
    connect = connect[: connect.index("\n}")]
    assert "🌐 Άνοιγμα εγγραφής" in connect
    assert "openExternalUrl(url)" in connect


def test_the_dialog_can_carry_a_real_link(page: str):
    """Το `uiAsk` έκανε escape τα πάντα — ένας σύνδεσμος έβγαινε ως κείμενο."""
    fn = page[page.index("function uiAsk(opts){"):]
    fn = fn[: fn.index("\n}")]
    assert "opts.html!==undefined" in fn
    # Το κείμενο του χρήστη ΕΞΑΚΟΛΟΥΘΕΙ να περνά από esc().
    assert "esc(part).replace(/\\n/g,'<br>')" in fn


def test_only_real_external_addresses_leave_the_app(shell: str):
    """Ένα `file://` από τη σελίδα θα άνοιγε αρχείο του δίσκου."""
    fn = shell[shell.index("def open_external("):]
    fn = fn[: fn.index("\n    # ---")]
    assert 'target.scheme() not in ("http", "https")' in fn
    assert "_is_local(target)" in fn
    # Και το loopback μένει μέσα: ο εξωτερικός browser δεν έχει τη συνεδρία μας.
    local = shell[shell.index("def _is_local("):]
    local = local[: local.index("\n\nclass")]
    assert '"127.0.0.1", "localhost"' in local


def test_link_clicks_and_popups_are_routed_too(shell: str):
    assert "class _Page(QWebEnginePage):" in shell
    assert "def acceptNavigationRequest(" in shell
    assert "NavigationTypeLinkClicked" in shell
    assert "def createWindow(" in shell
    # Η σελίδα μπαίνει ΠΡΙΝ δεθούν οι υπόλοιποι χειριστές, αλλιώς χάνονται.
    made = shell.index("self._page = _Page(")
    dl = shell.index("downloadRequested.connect")
    assert made < dl


# ===========================================================================
# 4. Η εγγραφή: λογιστής, και με ρητό μήνυμα
# ===========================================================================
def test_signing_up_through_a_key_link_makes_an_accountant():
    """Το κλειδί το παίρνει γραφείο, όχι μία επιχείρηση."""
    src = _read(AUTH_PHP)
    fn = src[src.index("function auth_signup("):]
    fn = fn[: fn.index("\n}")]
    assert "$role = $join ? 'editor' : 'business';" in fn
    assert "user_create($email, password_hash($password, PASSWORD_DEFAULT), $role," in fn


def test_the_delivered_companies_are_actually_assigned_to_them():
    """Ο λογιστής βλέπει ό,τι του **ανατίθεται**, όχι ό,τι του ανήκει."""
    src = _read(AUTH_PHP)
    fn = src[src.index("function auth_claim_deliver("):]
    fn = fn[: fn.index("\n}")]
    assert "manager_set_accounts($uid" in fn
    assert "($me['role'] ?? '') === 'editor'" in fn


def test_the_signup_says_an_email_is_on_its_way():
    view = _read(AUTHVIEW)
    assert 'id="signup-done"' in view
    assert "Στάλθηκε email επιβεβαίωσης στο" in view
    # Και λέει καθαρά όταν ΔΕΝ στάλθηκε — αλλιώς ο χρήστης περιμένει για πάντα.
    assert "d.verification_sent===false" in view


# ===========================================================================
# 5. Μετά την έκδοση, το παραστατικό δείχνεται
# ===========================================================================
def test_a_live_issue_lands_on_the_document(page: str):
    assert "async function docJump(" in page
    fn = page[page.index("async function submitInvoice(viaIssue)"):]
    fn = fn[: fn.index("\nasync function ")]
    assert "docJump(d.mark)" in fn
    # Μόνο σε ΟΡΙΣΤΙΚΗ έκδοση: το πρόχειρο δεν έχει ΜΑΡΚ να δείξει.
    assert "if(d.live&&d.mark&&!window.__dnFromInv)" in fn
    # Και η πρόταση δελτίου της προηγούμενης έκδοσης καθαρίζεται, αλλιώς
    # μένει καρφωμένη και μπλοκάρει κάθε επόμενο άλμα.
    assert "window.__dnFromInv=null;" in fn


def test_the_row_is_marked_and_the_mark_is_temporary(page: str):
    assert "tr.row-found>td{animation:rowFound" in page
    fn = page[page.index("function focusDocRow()"):]
    fn = fn[: fn.index("\n}")]
    assert "scrollIntoView" in fn
    assert "row-found" in fn
    # Παραστατικό εκτός διαστήματος: το λέμε, δεν αφήνουμε τον χρήστη να ψάχνει.
    assert "δεν βρέθηκε στο επιλεγμένο διάστημα" in fn


def test_the_list_is_reloaded_not_reused(page: str):
    """Το μόλις εκδοθέν δεν υπάρχει στην παλιά λίστα."""
    fn = page[page.index("async function docJump("):]
    fn = fn[: fn.index("\n}")]
    assert "await loadDocs();" in fn
    # ΟΧΙ μέσω `docsYear()`: εκείνο φορτώνει κι από μόνο του (διπλή αναμονή).
    assert "docsYear()" not in _code(fn)


# ===========================================================================
# 6. Η ειδοποίηση οδηγεί στην ενέργεια
# ===========================================================================
def test_double_click_on_a_notification_opens_the_document(page: str):
    assert 'ondblclick="notifOpen(' in page
    fn = page[page.index("async function notifOpen("):]
    fn = fn[: fn.index("\nasync function notifRead")]
    assert "docJump(mark)" in fn
    # Το διπλό κλικ δεν πρέπει να μετρήσει και ως «διάβασέ το» δύο φορές.
    assert "ev.stopPropagation()" in fn


def test_it_switches_company_when_the_notification_belongs_to_another(page: str):
    """Ο λογιστής βλέπει ειδοποιήσεις ΟΛΩΝ των πελατών του."""
    fn = page[page.index("async function notifOpen("):]
    fn = fn[: fn.index("\nasync function notifRead")]
    assert "if(vat&&vat!==ACCOUNT)" in fn
    assert "ALL_DOCS=[]" in fn, "χωρίς αυτό θα έδειχνε τη λίστα της προηγούμενης εταιρείας"
