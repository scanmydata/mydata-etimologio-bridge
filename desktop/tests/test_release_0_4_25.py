"""Η επεξεργασία είδους έσβηνε ό,τι δεν έδειχνε, και το κλειδί σταματούσε βουβά.

* **Η επεξεργασία είδους ήταν καταστροφική.** Η αποθήκευση στέλνει ΠΑΝΤΑ
  κατηγορία, ΦΠΑ, μονάδα και τιμή από τη φόρμα· η φόρμα όμως γέμιζε μόνο κωδικό
  και περιγραφή. Κάθε «✎ Επεξεργασία» έγραφε λοιπόν από πάνω ό,τι δεν φαινόταν:
  ΦΠΑ 24%, τιμή 0, μονάδα «Τεμάχιο» — και η κατηγορία έμενε «—», που έκοβε την
  αποθήκευση με μήνυμα που δεν εξηγούσε γιατί.

* **Το email σύνδεσης στις «Παρατηρήσεις»** δεν το έβαζε η εφαρμογή: το έβαζε ο
  **browser**. Τα πεδία δεν δήλωναν `autocomplete`, οπότε η αυτόματη συμπλήρωση
  τα θεωρούσε στοιχεία επικοινωνίας. Ο ίδιος μηχανισμός απειλούσε να βάλει τη
  διεύθυνση ΤΟΥ ΧΡΗΣΤΗ στη διεύθυνση του ΠΕΛΑΤΗ.

* **Ανακληθέν ή ληγμένο κλειδί** δεν άνοιγε συνεδρία, οπότε η γενική πύλη
  απαντούσε «Απαιτείται σύνδεση»: σωστό γράμμα, λάθος νόημα. Η σύνδεση
  σταματούσε και ο χρήστης δεν μάθαινε ποτέ γιατί.

* **Δύο εγκαταστάσεις, δύο email.** Γραφείο και server κρατούσαν χωριστές
  μνήμες για το «ποιο παραστατικό βγήκε από εμάς». Η μνήμη ταξιδεύει πλέον μόνη
  της — καμία ρύθμιση δεν χρειάζεται από κανέναν λογιστή.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
DB_PHP = REPO / "localdb.php"
LINK_PHP = REPO / "serverlink.php"
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"

php_only = pytest.mark.skipif(
    not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe"
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


def _php(tmp_path: Path, body: str) -> str:
    """Τρέχει PHP πάνω σε ΔΙΚΗ ΤΟΥ βάση — ποτέ πάνω στα δεδομένα του χρήστη."""
    for name in ("localdb.php", "crypto.php"):
        (tmp_path / name).write_text(_read(REPO / name), encoding="utf-8")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "config.php").write_text(
        "<?php\n$ACCOUNTS = [];\n"
        "const BASE_URL = 'https://mydata.aade.gr/timologio';\n"
        "const COOKIE_DIR = __DIR__ . '/data/.cookies';\n"
        "const LOCAL_DB = __DIR__ . '/data/test.sqlite';\n"
        "const ENC_KEY_FILE = __DIR__ . '/data/.enckey';\n"
        "const ZERO_VAT_TYPES = ['22','23'];\n"
        "const MASTER_ADMIN_EMAIL = 'a@b.c';\n"
        "const MASTER_ADMIN_PASSWORD = 'x';\n",
        encoding="utf-8",
    )
    script = tmp_path / "run.php"
    script.write_text(
        "<?php\nrequire_once __DIR__ . '/config.php';\n"
        "require_once __DIR__ . '/localdb.php';\n" + body + "\n",
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
# 1. Η επεξεργασία είδους κρατά ό,τι είχε το είδος
# ===========================================================================
def test_editing_a_product_fills_every_field_the_save_will_send(page: str):
    fn = page[page.index("function editProduct(code,desc){"):]
    fn = fn[: fn.index("\n}")]
    for field in ("#pdVat", "#pdUnit", "#pdPrice", "#pdType"):
        assert field in fn, f"το {field} δεν γεμίζει — η αποθήκευση θα το σβήσει"
    # Η περιγραφή έρχεται από τη ΓΡΑΜΜΗ, με το όρισμα ως εφεδρεία.
    assert "PRODUCTS||[]).find(" in fn.replace("(", "").replace(")", "") or "(PRODUCTS||[]).find(" in fn
    # Και η κατηγορία δίνεται στο `loadCategories`, που τη διαλέγει μόλις γεμίσει.
    assert "loadCategories(p.category_id||p.category||'')" in fn


def test_the_category_is_chosen_after_the_list_arrives(page: str):
    """Ασύγχρονη φόρτωση: μια επιλογή πριν από αυτήν γράφεται σε άδειο select."""
    fn = page[page.index("async function loadCategories(pick){"):]
    fn = fn[: fn.index("\n}")]
    assert "sel.innerHTML=" in fn
    assert fn.index("sel.innerHTML=") < fn.index("byVal")
    # Ταιριάζει και με αναγνωριστικό και με ΟΝΟΜΑ: παλιότερες εγγραφές έχουν
    # μόνο το δεύτερο.
    assert "o.value===want" in fn
    assert "grFold(o.textContent)===grFold(want)" in fn


@pytest.mark.parametrize(("text", "code"), [
    ("24%", "1"), ("13%", "2"), ("6%", "3"), ("9%", "5"), ("0%", "7"),
    ("Απαλλαγή", "8"), ("", "1"),
])
def test_the_vat_text_maps_back_to_its_mydata_code(page: str, text: str, code: str):
    """Η ΑΑΔΕ δίνει «24%», η φόρμα θέλει «1»."""
    fn = page[page.index("function vatCodeFromText(t){"):]
    # +2 για να μπει ΚΑΙ το κλείσιμο: το απόσπασμα εδώ ΕΚΤΕΛΕΙΤΑΙ, δεν διαβάζεται.
    fn = fn[: fn.index("\n}") + 2]
    out = subprocess.run(
        ["node", "-e", fn + f"\nprocess.stdout.write(vatCodeFromText({json.dumps(text)}))"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == code


# ===========================================================================
# 2. Ο browser δεν συμπληρώνει πια τη φόρμα μόνος του
# ===========================================================================
def test_the_notes_field_refuses_autofill(page: str):
    """Το email σύνδεσης το έβαζε η αυτόματη συμπλήρωση, όχι η εφαρμογή."""
    line = page[page.index('id="iNotes"'):]
    line = line[: line.index(">")]
    assert 'autocomplete="off"' in line


@pytest.mark.parametrize("field", ["iName", "iAddress", "iCity", "iZip"])
def test_the_customer_fields_refuse_autofill_too(page: str, field: str):
    """Χειρότερο από το email: η διεύθυνση ΤΟΥ ΧΡΗΣΤΗ στη διεύθυνση του ΠΕΛΑΤΗ."""
    line = page[page.index(f'id="{field}"'):]
    line = line[: line.index(">")]
    assert 'autocomplete="off"' in line


def test_every_field_is_covered_not_just_the_ones_we_remembered(page: str):
    """Ένα πεδίο που θα προστεθεί αύριο δεν πρέπει να ξαναφέρει το ίδιο."""
    assert "function noAutofill(" in page
    fn = page[page.index("function noAutofill(root){"):]
    fn = fn[: fn.index("\n}")]
    assert "querySelectorAll('input,textarea')" in fn
    assert "el.type==='password'" in fn, "η φόρμα σύνδεσης δεν πειράζεται"
    # Ο Chromium αγνοεί το «off» σε πεδία που θεωρεί διεύθυνση· ένα άγνωστο
    # `name` το σταματά.
    assert "el.name='etim-'" in fn
    assert "noAutofill();" in page


# ===========================================================================
# 3. Λήξη κλειδιού, ανάκληση, πληρωμή — με λόγο
# ===========================================================================
def test_keys_can_expire_and_carry_a_paid_until():
    db = _read(DB_PHP)
    assert "ALTER TABLE access_keys ADD COLUMN expires_at" in db
    assert "ALTER TABLE access_keys ADD COLUMN paid_until" in db
    assert "function access_key_state(" in db
    assert "function access_key_set_dates(" in db


@php_only
@pytest.mark.parametrize(("expires", "paid", "revoked", "state"), [
    ("", "", 0, "ok"),
    ("2099-01-01", "", 0, "ok"),
    ("2000-01-01", "", 0, "expired"),
    ("", "2000-01-01", 0, "unpaid"),
    ("", "", 1, "revoked"),
    ("2000-01-01", "", 1, "revoked"),          # η ανάκληση προηγείται
])
def test_the_state_of_a_key_is_computed_not_guessed(tmp_path, expires, paid, revoked, state):
    out = _php(tmp_path, f"""
        $uid = user_create('k@x.gr', 'h', 'master', 'active', 'Δ');
        $made = access_key_create($uid, 'δοκιμή');
        $st = localdb()->prepare("SELECT id FROM access_keys WHERE key_hash = :h");
        $st->execute([':h' => hash('sha256', $made['secret'])]);
        $id = (int)$st->fetchColumn();
        access_key_set_dates($id, {json.dumps(expires)}, {json.dumps(paid)});
        if ({revoked}) access_key_revoke($id, 0);
        $s = access_key_state($made['secret']);
        echo $s['state'];
    """)
    assert out.strip() == state


@php_only
def test_an_unknown_key_reveals_nothing(tmp_path):
    out = _php(tmp_path, "echo access_key_state('δεν-υπάρχει')['state'];")
    assert out.strip() == "unknown"


def test_the_reason_travels_but_only_to_whoever_holds_the_secret():
    src = _read(ETIM_PHP)
    block = src[src.index("case 'access_provision': {"):]
    block = block[: block.index("case 'access_keys_list'")]
    # Άγνωστο κλειδί: σκέτο, χωρίς λεπτομέρεια.
    assert "$ks['state'] === 'unknown'" in block
    assert "jsonError('Το κλειδί δεν αναγνωρίστηκε', 403);" in block
    # Ταυτοποιημένο κλειδί: ο λόγος, με το όνομά του.
    for word in ("ΑΝΑΚΛΗΘΗΚΕ", "ΕΛΗΞΕ", "συνδρομή/δωρεά"):
        assert word in block


def test_the_reason_is_checked_before_the_login_gate():
    """Χωρίς αυτό, η πύλη απαντά «Απαιτείται σύνδεση» και ο λόγος χάνεται."""
    src = _read(ETIM_PHP)
    probe = src.index("$__ks = access_key_state($__pk);")
    gate = src.index("if (!$__user) jsonError('Απαιτείται σύνδεση', 401);")
    assert probe < gate


def test_the_app_remembers_why_it_stopped(page: str):
    etim = _read(ETIM_PHP)
    assert "setting_set('link.blocked'" in etim
    assert "'blocked'     => setting_get('link.blocked')," in etim
    # Και η οθόνη το δείχνει.
    assert 'id="lkBlocked"' in page
    assert "Η σύνδεση με τον server σταμάτησε" in page
    # Το «κάνε εγγραφή» δεν εμφανίζεται μαζί: το πρόβλημα είναι το κλειδί.
    assert "!d.thin&&!d.ready&&!d.blocked" in page


def test_the_admin_can_set_both_dates():
    src = _read(ETIM_PHP)
    assert "case 'access_key_dates': {" in src
    page = _read(APP_PHP)
    assert "async function akDates(" in page
    assert 'title="Λήξη κλειδιού"' in page
    assert 'title="Πληρωμένο/δωρεά ως"' in page


# ===========================================================================
# 4. Δύο εγκαταστάσεις, ΕΝΑ email — χωρίς καμία ρύθμιση
# ===========================================================================
def test_the_issued_marks_are_shared_state_not_a_local_secret():
    db = _read(DB_PHP)
    assert "function issued_marks_add(" in db
    assert "function issued_marks_all(" in db
    # Φραγμένο μέγεθος: μια ρύθμιση δεν επιτρέπεται να μεγαλώνει για πάντα.
    assert "ISSUED_MARKS_KEEP = 300" in db


@php_only
def test_the_shared_list_dedupes_and_stays_bounded(tmp_path):
    out = _php(tmp_path, """
        issued_marks_add('999888777', ['400000000000001', '400000000000002']);
        issued_marks_add('999888777', ['400000000000002']);   // διπλό
        echo count(issued_marks_all('999888777')), ' ';
        $many = [];
        for ($i = 0; $i < 400; $i++) $many[] = '4000000000' . str_pad((string)$i, 5, '0', STR_PAD_LEFT);
        issued_marks_add('999888777', $many);
        $all = issued_marks_all('999888777');
        echo count($all), ' ';
        // Τα ΤΕΛΕΥΤΑΙΑ κρατιούνται: το παλιότερο πέφτει έξω, όχι το νεότερο.
        echo in_array(end($many), $all, true) ? 'νεότερο-μέσα' : 'ΝΕΟΤΕΡΟ-ΕΞΩ';
    """)
    n1, n2, keep = out.split()
    assert n1 == "2", "διπλό ΜΑΡΚ μπήκε δεύτερη φορά"
    assert n2 == "300"
    assert keep == "νεότερο-μέσα"


def test_the_scan_consults_both_memories():
    src = _read(ETIM_PHP)
    fn = src[src.index("function issuedMarksFor("):]
    fn = fn[: fn.index("\n}")]
    assert "issuedMarksFromAudit($accountVat)" in fn
    assert "issued_marks_all($accountVat)" in fn
    assert "$mine = issuedMarksFor(COMPANY_VAT);" in src


def test_an_issue_tells_the_other_side_immediately():
    """Ο ωριαίος έλεγχος της άλλης πλευράς προλαβαίνει τον επόμενο συγχρονισμό."""
    src = _read(ETIM_PHP)
    assert "function pushIssuedMark(" in src
    fn = src[src.index("function pushIssuedMark("):]
    fn = fn[: fn.index("\n}")]
    assert "['api' => 'issued']" in fn
    # Best-effort, με κοντό όριο: η έκδοση έχει ήδη πετύχει.
    assert ", 6, $secret);" in fn
    mark = src[src.index("function markIssuedHere("):]
    mark = mark[: mark.index("\n}")]
    assert "issued_marks_add(COMPANY_VAT, [$mk])" in mark
    assert "pushIssuedMark(COMPANY_VAT, $mk)" in mark


def test_the_endpoint_that_receives_them_checks_the_company():
    src = _read(ETIM_PHP)
    block = src[src.index("if ($apiAction === 'issued') {"):]
    block = block[: block.index("\n    }")]
    assert "auth_may_access_vat($__user, $vat)" in block, "θα δεχόταν ΜΑΡΚ ξένης εταιρείας"


def test_the_sync_carries_them_both_ways():
    link = _read(LINK_PHP)
    assert "'issued_marks'  => issued_marks_all($vat)," in link
    assert "issued_marks_add($vat, (array)($r['data']['issued_marks'] ?? []));" in link
    etim = _read(ETIM_PHP)
    assert "issued_marks_add($vat, (array)($payload['issued_marks'] ?? []));" in etim
    assert "'issued_marks'  => issued_marks_all($vat)," in etim
