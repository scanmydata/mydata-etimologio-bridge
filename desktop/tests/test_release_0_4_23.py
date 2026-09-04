"""Δέκα αναφορές του χρήστη για το e-Τιμολόγιο Pro, και τι έφταιγε πραγματικά.

Οι τρεις που δεν φαίνονταν με το μάτι:

* **Το ημερήσιο αντίγραφο του server δεν είχε τρέξει ΠΟΤΕ.** Η κλήση
  `srv_backup_tick()` ήταν γραμμένη στο ΤΕΛΟΣ του `scheduler.php`, κάτω από τις
  βοηθητικές συναρτήσεις. Οι δηλώσεις συναρτήσεων ανεβαίνουν, οι εντολές όχι:
  ο κώδικας ήταν απροσπέλαστος, γιατί το «δεν υπάρχουν εργασίες» βγαίνει με
  `exit(0)` πολύ νωρίτερα — δηλαδή σχεδόν σε κάθε τικ.

* **Το QR του 2FA το έφτιαχνε CDN που ο ίδιος ο server μπλοκάρει.** Η πολιτική
  περιεχομένου επιτρέπει scripts μόνο από `'self'`, οπότε το `qrcode.min.js`
  του jsdelivr δεν φορτωνόταν ποτέ: κανένα σφάλμα, ένα κενό τετράγωνο.

* **Το ημερολόγιο ενεργειών έκρυβε ολόκληρες κατηγορίες.** Συνδέσεις και δοκιμές
  email γράφονται με κενό ΑΦΜ, και το φίλτρο εμβέλειας (`account_vat IN (…)`)
  δεν ταιριάζει ποτέ με κενό — άρα ο λογιστής έβλεπε μισή ιστορία.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
AUTH_PHP = REPO / "auth.php"
DB_PHP = REPO / "localdb.php"
LINK_PHP = REPO / "serverlink.php"
SCHED_PHP = REPO / "scheduler.php"
QR_PHP = REPO / "qrcode.php"

php_only = pytest.mark.skipif(
    not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe"
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _php(tmp_path: Path, body: str, requires=("qrcode.php",)) -> str:
    """Τρέχει PHP με τα ζητούμενα αρχεία δίπλα του και επιστρέφει το stdout."""
    for name in requires:
        (tmp_path / name).write_text(_read(REPO / name), encoding="utf-8")
    script = tmp_path / "run.php"
    script.write_text(
        "<?php\n"
        + "".join(f"require_once __DIR__ . '/{n}';\n" for n in requires)
        + body + "\n",
        encoding="utf-8",
    )
    run = subprocess.run(
        [str(PHP_EXE), "-c", str(PHP_EXE.parent / "php.ini"),
         "-d", "display_errors=0", "-f", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


# ===========================================================================
# 1. Το ημερήσιο αντίγραφο του server έτρεχε μετά το `exit()`
# ===========================================================================
def test_the_server_daily_backup_is_reachable_at_all():
    """Ο κώδικας πρέπει να είναι ΠΑΝΩ από κάθε `exit()` — αλλιώς δεν τρέχει."""
    src = _read(SCHED_PHP)
    tick = src.index("srv_backup_tick();")
    # Ο πρώτος `exit()` που μπορεί να τερματίσει ένα κανονικό τικ: το «καμία
    # εργασία δεν είναι ώρα να τρέξει», που ισχύει σχεδόν πάντα.
    no_jobs = src.index("if (!$due) {")
    assert tick < no_jobs, "το αντίγραφο βρίσκεται μετά τον `exit` των εργασιών"
    # Και δεν έμεινε δεύτερο, νεκρό αντίγραφο της κλήσης στο τέλος του αρχείου.
    assert src.count("srv_backup_tick();") == 1


def test_a_local_only_backup_still_records_when_it_happened():
    """Χωρίς Drive, η οθόνη έδειχνε «κανένα αντίγραφο» ενώ έπαιρνε ένα κάθε μέρα."""
    src = _read(REPO / "serverbackup.php")
    body = src[src.index("function srv_backup_run("):src.index("/** Το αντίστροφο")]
    stamp = body.index("setting_set('srvbackup.last_at'")
    local_only = body.index("Χωρίς BACKUP_PASSPHRASE")
    assert stamp < local_only, "η σφραγίδα μπαίνει μόνο μετά το ανέβασμα στο Drive"


def test_a_partial_backup_is_not_logged_as_a_failure():
    src = _read(REPO / "serverbackup.php")
    tick = src[src.index("function srv_backup_tick("):]
    assert "if (empty($r['ok'])) {" in tick
    assert "ΑΠΕΤΥΧΕ" in tick


# ===========================================================================
# 2. Η τοπική εγκατάσταση δεν έπαιρνε ΚΑΝΕΝΑ αυτόματο αντίγραφο
# ===========================================================================
def test_the_local_install_has_a_daily_backup_at_all():
    src = _read(LINK_PHP)
    assert "function link_backup_tick(" in src
    fn = src[src.index("function link_backup_tick("):]
    fn = fn[: fn.index("\n}")]
    # Ο φύλακας είναι η ΗΜΕΡΟΜΗΝΙΑ: η εφαρμογή ανοίγει πολλές φορές τη μέρα και
    # ένα χρονόμετρο «κάθε 24 ώρες από την εκκίνηση» θα έπαιρνε αντίγραφο σε
    # κάθε άνοιγμα.
    assert "setting_get('link.backup.day')" in fn
    assert "setting_set('link.backup.day', $today);" in fn
    # Και η σφραγίδα μπαίνει ΠΡΙΝ τη δουλειά, ώστε μια μόνιμη αποτυχία να μη
    # γεμίζει τον δίσκο με μισογραμμένα zip σε κάθε τικ.
    assert fn.index("setting_set('link.backup.day'") < fn.index("link_backup_run()")


def test_the_local_tick_is_reachable_and_scheduled():
    assert "case 'local_tick': {" in _read(ETIM_PHP)
    src = _read(APP_PHP)
    assert "case 'backup_auto': case 'local_tick': {" in _read(ETIM_PHP)
    assert "setInterval(()=>localTick(),3600000);" in src
    # Ο παλμός αφορά ΜΟΝΟ την εγκατάσταση γραφείου: στον server τα κάνει ο cron.
    fn = src[src.index("async function localTick()"):]
    fn = fn[: fn.index("\n}")]
    assert "if(!IS_LOCAL_INSTALL)return;" in fn


# ===========================================================================
# 3. «Ανέβηκαν 0 εταιρείες» χωρίς καμία εξήγηση
# ===========================================================================
def test_the_key_travels_as_a_field_too_not_only_as_a_header():
    """Η `Authorization` χάνεται σε CGI/FastCGI και σε κάθε ενδιάμεσο proxy."""
    fn = _read(LINK_PHP)
    fn = fn[fn.index("function link_call("):fn.index("// --- Αντίγραφα ασφαλείας της τοπικής")]
    assert "$post['access_key'] = $key;" in fn
    # Και ο κωδικός HTTP ταξιδεύει, ώστε το «λάθος κλειδί» (403) να ξεχωρίζει
    # από το «δεν απαντά ο server».
    assert fn.count("'http' => $code") >= 3


def test_upload_errors_reach_the_screen():
    etim = _read(ETIM_PHP)
    assert "'errors'   => (array)($sync['errors'] ?? [])," in etim
    js = _read(APP_PHP)
    fn = js[js.index("async function linkConnect()"):]
    fn = fn[: fn.index("\n}")]
    assert "Τι εμπόδισε το ανέβασμα" in fn


def test_no_companies_at_all_says_so():
    fn = _read(LINK_PHP)
    fn = fn[fn.index("function link_sync_all("):]
    fn = fn[: fn.index("\n}")]
    assert "Δεν υπάρχει καμία εταιρεία σε αυτή την εγκατάσταση" in fn


def test_a_wrong_key_reads_like_a_wrong_key():
    etim = _read(ETIM_PHP)
    assert "Το κλειδί δεν αναγνωρίστηκε από τον server" in etim
    assert "(int)($r['http'] ?? 0) === 403" in etim


# ===========================================================================
# 4. Το email του διαχειριστή σε ξένη οθόνη
# ===========================================================================
def test_the_provision_answer_carries_no_email():
    src = _read(ETIM_PHP)
    block = src[src.index("case 'access_provision': {"):]
    block = block[: block.index("case 'access_keys_list'")]
    # Το `$u['email']` χρησιμοποιείται ακόμη για τον έλεγχο, αλλά ΔΕΝ επιστρέφεται.
    assert "'email'   => $u['email']," not in block
    assert "'signup_url' =>" in block


@pytest.mark.parametrize("gone", [
    "'email' => (string)($d['email'] ?? ''),",
    "(d.email||d.label||'')",
    "(d.email?(' ('+d.email+')'):'')",
])
def test_the_screen_no_longer_shows_anyones_email(gone: str):
    assert gone not in _read(ETIM_PHP) + _read(APP_PHP)


# ===========================================================================
# 5. Ο σύνδεσμος εγγραφής και ο «προσωρινός» λογαριασμός
# ===========================================================================
def test_a_key_carries_its_own_signup_link():
    db = _read(DB_PHP)
    assert "ALTER TABLE access_keys ADD COLUMN claim_token" in db
    assert "ALTER TABLE access_keys ADD COLUMN claimed_uid" in db
    assert "function access_key_by_claim(" in db
    etim = _read(ETIM_PHP)
    assert "'signup_url' => rtrim(app_base_url(), '/') . '/app.php?join='" in etim


def test_signup_through_the_link_claims_the_key():
    auth = _read(AUTH_PHP)
    sig = auth[auth.index("function auth_signup("):]
    sig = sig[: sig.index("\n}")]
    assert "string $joinToken = ''" in sig
    assert "access_key_set_claimed((int)$join['id'], $id);" in sig


def test_verified_email_activates_and_delivers_the_companies():
    """Ο διαχειριστής εγγυήθηκε ήδη εκδίδοντας το κλειδί — δεύτερη ουρά δεν έχει νόημα."""
    auth = _read(AUTH_PHP)
    fn = auth[auth.index("function auth_verify_email("):]
    fn = fn[: fn.index("\n}\n")]
    assert "access_key_by_claimed_uid" in fn
    assert "'status' => 'active'" in fn
    assert "auth_claim_deliver" in fn
    # Και η παράδοση αφορά ΜΟΝΟ όσα ήρθαν από αυτό το κλειδί.
    deliver = auth[auth.index("function auth_claim_deliver("):]
    deliver = deliver[: deliver.index("\n}")]
    assert "access_key_vats((int)$key['id'])" in deliver
    assert "account_set_owner" in deliver


def test_the_sync_records_which_key_brought_which_company():
    src = _read(ETIM_PHP)
    assert "access_key_note_vat(auth_access_key_id(), $vat);" in src
    assert "function auth_access_key_id(" in _read(AUTH_PHP)


def test_an_unknown_join_token_promises_nothing():
    src = _read(APP_PHP)
    assert "!access_key_by_claim($__joinToken)" in src
    assert "$__joinToken = '';" in src


def test_switching_to_the_server_refuses_without_an_account_there():
    src = _read(ETIM_PHP)
    block = src[src.index("case 'link_use_server': {"):]
    block = block[: block.index("case 'link_use_local'")]
    assert "if (empty($r['data']['ready'])) {" in block
    # Το κουμπί όμως ΜΕΝΕΙ ενεργό: αλλιώς η μόνη διαδρομή που ξαναρωτά τον
    # server ήταν κλειδωμένη πίσω από την πληροφορία που ήθελε να ανανεώσει.
    js = _read(APP_PHP)
    assert "mb.disabled=!d.has_key;" in js


def test_readiness_is_rechecked_by_itself():
    src = _read(ETIM_PHP)
    block = src[src.index("case 'link_get': {"):]
    block = block[: block.index("case 'link_connect': {")]
    assert "setting_get('link.ready') !== '1'" in block
    assert "time() - (int)setting_get('link.ready_at', '0') > 60" in block


# ===========================================================================
# 6. Τα κλειδιά: διαγραφή, και να μη χάνονται από τα μάτια του διαχειριστή
# ===========================================================================
def test_keys_can_be_deleted_not_only_revoked():
    assert "function access_key_delete(" in _read(DB_PHP)
    assert "case 'access_key_delete': {" in _read(ETIM_PHP)
    assert "async function deleteAccessKey(" in _read(APP_PHP)


def test_a_claimed_key_stays_visible_to_the_admin():
    """Το κλειδί αλλάζει κάτοχο μόλις δουλέψει — και εξαφανιζόταν από τη λίστα."""
    db = _read(DB_PHP)
    assert "function access_keys_all(" in db
    etim = _read(ETIM_PHP)
    block = etim[etim.index("case 'access_keys_list': {"):]
    block = block[: block.index("case 'access_key_create'")]
    assert "access_keys_all()" in block


# ===========================================================================
# 7. Το ημερολόγιο ενεργειών
# ===========================================================================
def test_the_failed_mail_test_is_written_down():
    src = _read(ETIM_PHP)
    assert "$ok ? 'mail_test_sent' : 'mail_test_failed'" in src
    # Και το μήνυμα δεν στέλνει πια τον χρήστη σε αρχείο που δεν μπορεί να δει.
    assert "δες το αρχείο καταγραφής του server" not in src


def test_events_without_a_company_are_not_filtered_away():
    fn = _read(DB_PHP)
    fn = fn[fn.index("function audit_log_list("):]
    fn = fn[: fn.index("\n}")]
    assert """$conds[] = '(' . $where . " OR account_vat = '')";""" in fn


@pytest.mark.parametrize("action", [
    "auto_email_failed", "auto_email_skipped", "mail_test_failed",
    "ledger_dispatch", "aade_discovery_email",
])
def test_every_recorded_action_has_a_greek_name(action: str):
    src = _read(APP_PHP)
    labels = src[src.index("const AUDIT_LABELS="):]
    labels = labels[: labels.index("};")]
    assert action + ":" in labels


# ===========================================================================
# 8. Το QR του 2FA: από τον server, χωρίς δίκτυο
# ===========================================================================
def test_the_qr_no_longer_comes_from_a_blocked_cdn():
    src = _read(APP_PHP)
    assert "qrcode@1.5.1" not in src
    assert "QRCode.toCanvas" not in src
    assert "box.innerHTML=d.qr_svg" in src
    assert "'qr_svg'  => function_exists('qr_svg')" in _read(AUTH_PHP)


def test_the_content_security_policy_would_still_block_it():
    """Η αιτία, γραμμένη ως έλεγχος: τα scripts επιτρέπονται μόνο από 'self'."""
    conf = _read(REPO / "deploy" / "apache-etimologio.conf")
    assert "script-src 'self' 'unsafe-inline'" in conf
    assert "cdn.jsdelivr.net" not in conf


#: Ο κωδικός για ένα σταθερό otpauth URI — παρήχθη από αυτόν τον κωδικοποιητή
#: και επαληθεύτηκε ΔΥΟ φορές: (α) είναι ίδιος, μονάδα προς μονάδα, με τη
#: βιβλιοθήκη `qrcode` της Python, (β) διαβάζεται από τον σαρωτή του OpenCV και
#: δίνει πίσω ακριβώς αυτό το κείμενο. Έκδοση 5, επίπεδο διόρθωσης M.
GOLDEN_TEXT = ("otpauth://totp/Test:a@b.gr?secret=JBSWY3DPEHPK3PXP"
               "&issuer=Test&digits=6&period=30")
GOLDEN = (
    "1111111011010110101001000101001111111",
    "1000001011011001100101100100101000001",
    "1011101010010011100101001101001011101",
    "1011101001111011100101011101001011101",
    "1011101010011100101111100011101011101",
    "1000001001001101000000011010001000001",
    "1111111010101010101010101010101111111",
    "0000000000011110100100010111100000000",
    "1001111110101100110100011010010010111",
    "0100110110101010011100010011100110110",
    "0100001010011010001010010001000001001",
    "1111110111101111011100100011100101111",
    "0001101111010110010100111001111101101",
    "1101110111111100101000111101000110011",
    "1011111010110111100110101111100111111",
    "1011010111001010001000011000111001101",
    "1101001011000011101000011101101001110",
    "1101010101111010110111000011000000000",
    "0011101101100011001100010011000110001",
    "0000010010010010001100101100110110010",
    "0010101110100001100100011011011010010",
    "0110100010101100010101010001010010101",
    "0001111110110111110011111111011010001",
    "0110010011111111110100011010000011101",
    "1111011110101001101110111001101010001",
    "1001000101110100100000110101110010000",
    "1110011110111100111100101111011100011",
    "1011110101111011000010000010001001111",
    "1010101100110110110000111111111110011",
    "0000000010101001110110110011100011111",
    "1111111010000111001100010100101010101",
    "1000001010101100000010001111100011001",
    "1011101010001110111110101001111110001",
    "1011101011100010100100110111011000111",
    "1011101001011011000011111110110111001",
    "1000001001010010110110000001011001111",
    "1111111010110111010110011000100010101",
)


@php_only
def test_the_encoder_reproduces_a_known_good_code(tmp_path):
    out = _php(tmp_path, (
        "$m = qr_matrix(" + json.dumps(GOLDEN_TEXT) + ");\n"
        "foreach ($m as $row) echo implode('', array_map(fn($v) => $v ? '1' : '0', $row)), \"\\n\";"
    ))
    assert tuple(line for line in out.split() if line) == GOLDEN


@php_only
@pytest.mark.parametrize(("text", "version"), [
    ("hello", 1),
    ("x" * 16, 2),                      # 16 bytes δεν χωρούν στην έκδοση 1: η
                                        # κεφαλίδα (τρόπος + πλήθος) θέλει κι αυτή θέση
    ("x" * 86, 6),
    ("x" * 108, 7),                     # πρώτη έκδοση με πληροφορία έκδοσης
    ("x" * 124, 8),                     # πρώτη με δύο ομάδες μπλοκ διαφορετικού μήκους
    ("x" * 216, 11),                    # πρώτη με μετρητή πλήθους 16 bit
])
def test_the_smallest_version_that_fits_is_chosen(tmp_path, text: str, version: int):
    out = _php(tmp_path, f"$m = qr_matrix({json.dumps(text)}); echo count($m);")
    assert int(out.strip()) == version * 4 + 17


@php_only
def test_the_code_keeps_its_three_finder_patterns(tmp_path):
    """Χωρίς αυτά κανένας σαρωτής δεν βρίσκει καν πού είναι ο κωδικός."""
    out = _php(tmp_path, (
        "$m = qr_matrix('hello');\n"
        "foreach ($m as $row) echo implode('', array_map(fn($v) => $v ? '1' : '0', $row)), \"\\n\";"
    ))
    rows = [line for line in out.split() if line]
    n = len(rows)
    for top, left in ((0, 0), (0, n - 7), (n - 7, 0)):
        block = [row[left:left + 7] for row in rows[top:top + 7]]
        assert block[0] == "1111111", f"σήμα θέσης στο ({top},{left})"
        assert block[3] == "1000101" or block[3] == "1011101", block[3]
        assert block[6] == "1111111"


@php_only
def test_text_that_cannot_fit_returns_nothing_rather_than_garbage(tmp_path):
    out = _php(tmp_path, "var_export(qr_matrix(str_repeat('x', 900)) === []);")
    assert out.strip() == "true"


@php_only
def test_the_svg_is_white_backed_and_self_contained(tmp_path):
    out = _php(tmp_path, "echo qr_svg('hello');")
    assert out.startswith("<svg xmlns=")
    assert 'fill="#ffffff"' in out and 'fill="#000000"' in out
    # Καμία εξωτερική αναφορά: το SVG μπαίνει σε `innerHTML` και πρέπει να
    # ζωγραφίζεται μόνο του, χωρίς αίτημα δικτύου.
    assert "http://" not in out.replace('xmlns="http://www.w3.org/2000/svg"', "")
    # Και ζώνη ησυχίας — χωρίς αυτή οι σαρωτές αστοχούν σε σκούρο φόντο.
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', out)
    assert int(vb.group(1)) == 21 + 8


# ===========================================================================
# 9. Ο ωριαίος έλεγχος ΑΝΑ εταιρεία, με email
# ===========================================================================
def test_every_company_is_checked_not_only_the_selected_one():
    src = _read(APP_PHP)
    assert "const AADE_ALL_MIN=60;" in src
    assert "setInterval(()=>checkAllAccounts(),AADE_ALL_MIN*60000);" in src
    fn = src[src.index("async function checkAllAccounts()"):]
    fn = fn[: fn.index("\n}")]
    assert "notify_due:1" in fn


def test_the_due_list_costs_nothing():
    """Απαντά ΠΡΙΝ από κάθε σύνδεση στην ΑΑΔΕ — αλλιώς δέκα πελάτες = δέκα συνδέσεις."""
    src = _read(ETIM_PHP)
    due = src.index("$_GET['notify_due']")
    login_marker = src.index("$syncKind = trim($_GET['sync']")
    assert due < login_marker


def test_a_discovery_sends_one_email_for_the_batch():
    src = _read(ETIM_PHP)
    assert "function notifyAadeDiscoveryEmail(" in src
    fn = src[src.index("function notifyAadeDiscoveryEmail("):]
    fn = fn[: fn.index("\n}\n")]
    # Ίδιοι κανόνες παραληπτών με τις εκδόσεις — όχι δεύτερη, αποκλίνουσα λίστα.
    assert "notify_prefs_match(notify_prefs_get((int)$u['id']), $accountVat" in fn
    # Ένα μήνυμα ανά σάρωση, όχι ανά παραστατικό.
    assert "if ($found_new) {" in src
    assert "setting_set('notify.tick.' . COMPANY_VAT" in src


# ===========================================================================
# 10. Μικρότερα, αλλά ζητημένα
# ===========================================================================
def test_the_credential_test_stops_reporting_mydata():
    """Αυτή η εφαρμογή εκδίδει μέσα από το e-timologio· το myDATA δεν το αγγίζει."""
    src = _read(ETIM_PHP)
    assert "aadeCredentialTest($vat, $username, $subkey, false)" in src
    assert "function aadeMyDataProbe(" in src
    js = _read(APP_PHP)
    # Η γραμμή e-timologio πρώτη, και η myDATA μόνο αν σταλεί.
    assert "box.innerHTML=line(d.etimologio&&d.etimologio.ok?'✅':'❌','e-timologio',d.etimologio)" in js
    assert "+(d.mydata?line(" in js


def test_the_long_paragraph_about_working_fine_offline_is_gone():
    src = _read(APP_PHP)
    assert "Δουλεύεις μια χαρά και χωρίς αυτήν" not in src
    # Και στη θέση του λέει ΠΟΥ γίνεται η εγγραφή.
    assert "https://etimologiopro.scanmydata.gr/" in src


def test_the_client_invite_needs_a_server():
    etim = _read(ETIM_PHP)
    block = etim[etim.index("case 'staff_invite_client': {"):]
    block = block[: block.index("case 'srv_backup_status'")]
    assert "link_is_local() && setting_get('link.ready') !== '1'" in block
    # Και ο φύλακας ΔΕΝ ακούμπησε την αποθήκευση εταιρείας, που έχει πανομοιότυπη
    # αρχή — εκεί είχε πέσει κατά λάθος και έκλεινε δουλειά που δούλευε.
    save = etim[etim.index("case 'admin_account_save': {"):]
    save = save[: save.index("case 'staff_add_company'")] if "case 'staff_add_company'" in save else save[:4000]
    assert "Η πρόσκληση πελάτη χρειάζεται σύνδεση" not in save


def test_the_quick_add_company_button_exists_for_the_admin():
    src = _read(APP_PHP)
    assert 'id="acctQuickAdd"' in src
    assert "function quickAddCompany()" in src
    # Ανοίγει την ΙΔΙΑ φόρμα με τη Διαχείριση — μία διαδρομή προσθήκης.
    fn = src[src.index("function quickAddCompany()"):]
    fn = fn[: fn.index("\n}")]
    assert "openNewCompany()" in fn


def test_the_daily_backup_can_be_switched_off():
    src = _read(APP_PHP)
    assert 'id="bkAuto"' in src
    assert "async function backupAuto(" in src
    assert "case 'backup_auto': {" in _read(ETIM_PHP)
