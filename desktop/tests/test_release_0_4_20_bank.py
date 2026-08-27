"""Η εισαγωγή πληρωμών: πελάτες, τράπεζα, λογαριασμός, ημερομηνίες.

* «στην αναζήτηση πελάτη δεν φέρνει τους πελάτες» — ένας αποτυχημένος
  συγχρονισμός **έσβηνε** την κρυφή μνήμη πελατών: το `cachedThenSync` έγραφε
  `rows||[]` πάνω σε δεδομένα που είχαν ήδη φορτώσει, ακόμη κι όταν ο server
  απαντούσε `success:false` (409 «διάλεξε πρώτα εταιρεία»).
* «το dropdown αργεί» — κάθε επιλογέας περίμενε ολόκληρο γύρο προς την ΑΑΔΕ,
  ενώ η λίστα ήταν ήδη στη βάση.
* «να αναγράφεται ποια τράπεζα εντοπίστηκε» — εντοπιζόταν μόνο από το ΟΝΟΜΑ του
  αρχείου. Τώρα από το IBAN, από το κείμενο, και από τους δικούς σου λογαριασμούς.
* «σημείωση τράπεζας και λογαριασμού στην πληρωμή» — δύο νέες στήλες.
* «οι ημερομηνίες να συνάδουν» — η καρτέλα ανακάτευε «24/08/2026» (τιμολόγιο) με
  «2026-08-24» (πληρωμή) στην ΙΔΙΑ στήλη, και το «13/8/2026» αποθηκευόταν
  αυτούσιο, δηλαδή αόρατο σε κάθε φίλτρο διαστήματος.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
DB_PHP = REPO / "localdb.php"
BANK_PHP = REPO / "bankimport.php"

php_only = pytest.mark.skipif(
    not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe"
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def php_env(tmp_path_factory):
    """Αντίγραφο του backend με ΔΙΚΗ ΤΟΥ βάση — ποτέ πάνω στα δεδομένα του χρήστη."""
    root = tmp_path_factory.mktemp("bank")
    for name in ("localdb.php", "bankimport.php", "crypto.php"):
        (root / name).write_text(_read(REPO / name), encoding="utf-8")
    (root / "data").mkdir()
    (root / "config.php").write_text(
        "<?php\n"
        "$ACCOUNTS = [];\n"
        "const BASE_URL = 'https://mydata.aade.gr/timologio';\n"
        "const COOKIE_DIR = __DIR__ . '/data/.cookies';\n"
        "const LOCAL_DB = __DIR__ . '/data/test.sqlite';\n"
        "const ENC_KEY_FILE = __DIR__ . '/data/.enckey';\n"
        "const ZERO_VAT_TYPES = ['22','23'];\n"
        "const MASTER_ADMIN_EMAIL = 'a@b.c';\n"
        "const MASTER_ADMIN_PASSWORD = 'x';\n",
        encoding="utf-8",
    )
    return root


def _php(env: Path, body: str) -> dict:
    script = env / "run.php"
    script.write_text(
        "<?php\n"
        "require_once __DIR__ . '/config.php';\n"
        "require_once __DIR__ . '/localdb.php';\n"
        "require_once __DIR__ . '/bankimport.php';\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    run = subprocess.run(
        [str(PHP_EXE), "-c", str(PHP_EXE.parent / "php.ini"),
         "-d", "display_errors=0", "-f", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


# --- 1. Οι ημερομηνίες ------------------------------------------------------
@php_only
def test_payment_dates_accept_what_the_form_accepts(php_env):
    got = _php(php_env, """
$out = [];
foreach (['13/08/2026','13/8/2026','13-8-26','13.08.2026','2026-8-3','2026-08-13'] as $v) {
    $out[$v] = payment_date_iso($v);
}
$out['__gr'] = payment_date_gr('2026-08-13');
echo json_encode($out, JSON_UNESCAPED_UNICODE);
""")
    # Το «13/08/2026» έδινε **2020**-08-13: το `(\\d{2}|\\d{4})` δοκίμαζε πρώτα
    # τα δύο ψηφία και άρπαζε το «20» για έτος.
    assert got["13/08/2026"] == "2026-08-13"
    assert got["13/8/2026"] == "2026-08-13", "μονοψήφιος μήνας, όπως τον γράφει ο χρήστης"
    assert got["13-8-26"] == "2026-08-13"
    assert got["13.08.2026"] == "2026-08-13"
    assert got["2026-8-3"] == "2026-08-03"
    assert got["2026-08-13"] == "2026-08-13"
    assert got["__gr"] == "13/08/2026"


@php_only
def test_an_unparseable_date_becomes_today_not_garbage(php_env):
    """Μια αποθηκευμένη «σκουπιδο-ημερομηνία» δεν χάνει την πληρωμή — τη ΚΡΥΒΕΙ.

    Η στήλη συγκρίνεται ως κείμενο· ό,τι δεν είναι ISO δεν περνά κανένα φίλτρο
    διαστήματος, οπότε το ποσό λείπει από την καρτέλα χωρίς να λείπει από τη βάση.
    """
    got = _php(php_env, """
$out = [];
foreach (['', 'σκουπίδι', '31/02/2026'] as $v) $out[$v ?: '(κενό)'] = payment_date_iso($v);
$out['__today'] = date('Y-m-d');
echo json_encode($out, JSON_UNESCAPED_UNICODE);
""")
    today = got["__today"]
    assert got["(κενό)"] == today
    assert got["σκουπίδι"] == today
    assert got["31/02/2026"] == today, "31 Φεβρουαρίου δεν υπάρχει"


# --- 2. Ποια τράπεζα, ποιος λογαριασμός ------------------------------------
@php_only
def test_the_bank_is_read_from_the_file_not_from_its_name(php_env):
    got = _php(php_env, """
$cases = [
  'eurobank_iban' => 'ΤΡΑΠΕΖΑ EUROBANK A.E. | Λογαριασμός: GR26 0260 1400 0009 1020 0123 456',
  'piraeus_iban'  => 'Κατάσταση κίνησης | IBAN GR1701710010006001000012345 | περίοδος',
  'nbg_text'      => 'ΕΘΝΙΚΗ ΤΡΑΠΕΖΑ ΤΗΣ ΕΛΛΑΔΟΣ | i-bank | Αναλυτική κίνηση',
  'optima_text'   => 'OPTIMA BANK | AccountTransactions | Ημερομηνία',
  'nothing'       => 'Κίνηση | Ημερομηνία | Ποσό',
];
$out = [];
foreach ($cases as $k => $t) $out[$k] = bi_detect_bank($t, '');
echo json_encode($out, JSON_UNESCAPED_UNICODE);
""")
    # Ο κωδικός του IBAN δεν λέει ψέματα — προηγείται του κειμένου.
    assert got["eurobank_iban"]["bank"] == "Τράπεζα Eurobank"
    assert got["eurobank_iban"]["source"] == "iban"
    assert got["eurobank_iban"]["iban"] == "GR2602601400000910200123456"
    assert got["piraeus_iban"]["bank"] == "Τράπεζα Πειραιώς"
    # Χωρίς IBAN, το κείμενο του ίδιου του extrait.
    assert got["nbg_text"]["bank"] == "Εθνική Τράπεζα της Ελλάδος"
    assert got["nbg_text"]["source"] == "text"
    assert got["optima_text"]["bank"] == "Optima bank"
    # Και ποτέ μαντεψιά: άγνωστο σημαίνει άγνωστο.
    assert got["nothing"]["bank"] == ""
    assert got["nothing"]["account"] == ""


@php_only
def test_a_whole_statement_gives_bank_account_and_rows(php_env):
    got = _php(php_env, r"""
$csv = "ΤΡΑΠΕΖΑ EUROBANK A.E.;;;;\n"
     . "Λογαριασμός: GR2602601400000910200123456;;;;\n;;;;\n"
     . "Ημερομηνία;Ημ/νία αξίας;Περιγραφή;Ποσό;Υπόλοιπο\n"
     . "24/08/2026;24/08/2026;ΚΑΤΑΘΕΣΗ ΑΠΟ ΠΑΠΑΔΟΠΟΥΛΟΣ 802391747;1.234,56;5.000,00\n"
     . "25/08/2026;25/08/2026;ΧΡΕΩΣΗ ΠΡΟΜΗΘΕΙΑ;-12,50;4.987,50\n";
$csv = str_replace('\n', "\n", $csv);
echo json_encode(bank_parse($csv, 'extrait.csv', ''), JSON_UNESCAPED_UNICODE);
""")
    assert got["bank_label"] == "Τράπεζα Eurobank"
    assert got["account"] == "GR2602601400000910200123456"
    assert got["bank_source"] == "iban"
    txs = got["transactions"]
    assert len(txs) == 2
    assert txs[0]["date"] == "2026-08-24"
    assert txs[0]["amount"] == 1234.56
    assert txs[0]["direction"] == "credit"
    assert txs[0]["guess_vat"] == "802391747"
    assert txs[1]["direction"] == "debit"


# --- 3. Η πληρωμή θυμάται πού μπήκαν τα χρήματα ----------------------------
@php_only
def test_a_payment_stores_and_returns_its_bank(php_env):
    got = _php(php_env, """
$id = payment_add('802576637', [
    'customer_vat' => '802391747', 'customer_name' => 'ΑΛΦΑ ΑΕ', 'amount' => 1234.56,
    'method' => 1, 'pay_date' => '13/8/2026',
    'bank' => 'Τράπεζα Eurobank', 'bank_account' => 'GR26 0260 1400 0009 1020 0123 456',
]);
$rows = payments_list('802576637', '802391747');
echo json_encode(['id' => $id, 'row' => $rows[0] ?? null], JSON_UNESCAPED_UNICODE);
""")
    row = got["row"]
    assert row is not None
    assert row["bank"] == "Τράπεζα Eurobank"
    # Αποθηκεύεται κανονικοποιημένο, χωρίς κενά: αλλιώς δύο γραφές του ίδιου
    # λογαριασμού δεν συγκρίνονται ποτέ μεταξύ τους.
    assert row["bank_account"] == "GR2602601400000910200123456"
    assert row["pay_date"] == "2026-08-13"


def test_the_columns_are_added_to_existing_installations():
    src = _read(DB_PHP)
    assert 'ALTER TABLE payments ADD COLUMN bank TEXT' in src
    assert 'ALTER TABLE payments ADD COLUMN bank_account TEXT' in src


def test_the_bank_travels_with_the_payment_when_two_sides_sync():
    src = _read(REPO / "serverlink.php")
    fn = src[src.index("function sync_payments("):]
    fn = fn[: fn.index("\n}\n")]
    assert "'bank'" in fn and "'bank_account'" in fn
    # Το αποτύπωμα ΔΕΝ αλλάζει: αλλιώς κάθε παλιά πληρωμή θα ξαναγραφόταν διπλή.
    fp = src[src.index("function sync_pay_fingerprint("):]
    fp = fp[: fp.index("\n}\n")]
    assert "bank" not in fp


# --- 4. Η καρτέλα δείχνει μία μορφή ημερομηνίας ---------------------------
def test_the_ledger_shows_one_date_format():
    src = _read(ETIM_PHP)
    fn = src[src.index("function buildLedger("): src.index("// Normalise a display date")]
    assert "'date'       => payment_date_gr((string)$p['pay_date'])," in fn
    # Και η φόρμα επεξεργασίας εξακολουθεί να παίρνει ISO — δύο πεδία, ένα καθένα.
    assert "'date_iso'   => $p['pay_date_iso'] ?? payment_date_iso" in fn
    assert "'date'       => $p['pay_date']," not in fn


def test_the_import_table_shows_the_greek_date():
    src = _read(APP_PHP)
    fn = src[src.index("function biRender()"): src.index("async function biAc(")]
    assert "esc(isoToDmy(t.date))" in fn


# --- 5. Ο κατάλογος πελατών ------------------------------------------------
def test_a_failed_sync_never_wipes_the_cached_customers():
    src = _read(APP_PHP)
    fn = src[src.index("async function cachedThenSync("):]
    fn = fn[: fn.index("// Το πελατολόγιο ΤΩΡΑ")]
    assert "if(s.success===false)throw new Error" in fn
    assert "if(rows.length||!shown)onRows(rows,false);" in fn
    assert "onRows(s.rows||[],false)" not in fn


def test_every_customer_picker_reads_the_cache_first():
    src = _read(APP_PHP)
    assert "async function ensureCustomers(){" in src
    for picker in ("biAc", "pmAc", "cardAc"):
        fn = src[src.index("async function " + picker + "("):]
        fn = fn[: fn.index("panel.classList.add('open')")]
        assert "await ensureCustomers();" in fn, picker
        # Και ψάχνουν χωρίς τόνους, όπως οι υπόλοιπες αναζητήσεις.
        assert "grFold(" in fn, picker
    # Κανένας δεν καλεί πια τον πλήρη συγχρονισμό για να δείξει μια λίστα.
    assert "if(!ALL_CUSTOMERS.length)loadCustomers();" not in src


def test_the_detected_bank_reaches_the_screen_and_the_payment():
    src = _read(APP_PHP)
    # Η λίστα τραπεζών είναι η ΙΔΙΑ με τις Ρυθμίσεις — αλλιώς η «Πειραιώς» που
    # εντοπίστηκε δεν είχε πού να εμφανιστεί.
    assert "function biBankOptions(){" in src
    assert "banks.map(b=>" in src
    assert '<option value="eurobank">' not in src
    # Και γράφεται σε κάθε πληρωμή του αρχείου.
    fn = src[src.index("async function biImport()"):]
    fn = fn[: fn.index("$('#biInfo').innerHTML='<span class=\"spin\"></span> Καταχώρηση…';")]
    assert "bank,bank_account:BI_BANK.account||''," in fn
    assert "const bank=$('#biBank').value||BI_BANK.bank||'';" in fn


def test_the_manual_payment_can_name_the_receiving_account():
    src = _read(APP_PHP)
    assert 'id="pmBankAcc"' in src
    assert "function pmBankOptions(" in src
    fn = src[src.index("async function savePayment("):]
    fn = fn[: fn.index("if(PM_EDIT)")]
    assert "pay_bank_account:accSel?accSel.value:''," in fn
    assert "pay_bank:(accOpt&&accOpt.dataset.bank)||''" in fn
    # Ο επιλογέας κρύβεται όταν δεν υπάρχουν λογαριασμοί: με έναν είναι θόρυβος.
    assert "wrap.style.display=accs.length?'':'none';" in src


def test_the_server_stores_what_the_screen_sent():
    src = _read(ETIM_PHP)
    imp = src[src.index("if (!empty($_GET['bank_import']"):]
    imp = imp[: imp.index("$results[] = ['ok' => true")]
    assert "'bank'          => trim((string)($it['bank'] ?? ''))," in imp
    assert "'bank_account'  => trim((string)($it['bank_account'] ?? ''))," in imp
    assert "'bank'          => trim($_GET['pay_bank'] ?? $_POST['pay_bank'] ?? '')," in src
