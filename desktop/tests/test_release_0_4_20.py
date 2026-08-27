"""Τέσσερα παράπονα της 0.4.20.

* «η ακύρωση δεν συμπεριλαμβάνει φόρους και κρατήσεις» — το πιστωτικό αντέγραφε
  τις γραμμές του πρωτοτύπου αλλά **όχι τους φόρους του**. Ένα τιμολόγιο
  10.000 € με 3% παρακράτηση (πληρωτέο 12.100 €) ακυρωνόταν με πιστωτικό
  12.400 €: πίστωνε 300 € που ο πελάτης δεν είχε ποτέ χρεωθεί.
* «στην καρτέλα, πελάτη χωρίς ΑΦΜ δεν τον φορτώνει» — η καρτέλα ήταν κλειδωμένη
  στο ΑΦΜ, και η λίστα της ΑΑΔΕ έχει **κενό ΑΦΜ αγοραστή σε κάθε απόδειξη
  λιανικής**. Ο ιδιώτης αναγνωρίζεται πλέον από τον κωδικό πελάτη.
* «στους πελάτες να ψάχνει και στην πόλη» — έψαχνε ήδη, αλλά ποτέ δεν έβρισκε:
  τα δεδομένα της ΑΑΔΕ είναι ΚΕΦΑΛΑΙΑ ΚΑΙ ΑΤΟΝΑ και ο χρήστης γράφει «Βάρη».
* «στα παραστατικά να ψάχνει και σε ημερομηνία/καθαρή/ΦΠΑ/σύνολο».
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
NODE = shutil.which("node")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i)]


# --- 1. Το πιστωτικό κουβαλά τους φόρους του πρωτοτύπου ---------------------
def test_credit_note_mirrors_the_original_taxes():
    fn = _block(_read(ETIM_PHP), "function createCreditNote(", "// --- 7. GET INVOICE PDF")
    # Πηγή: πρώτα το `invoiceTaxes` του πρωτοτύπου, αλλιώς τα σύνολα φόρων.
    assert "$corr['invoiceTaxes']" in fn
    assert "$corr['taxesTotals']['taxes']" in fn
    # Σε μερική πίστωση μοιράζονται αναλογικά, όπως οι γραμμές.
    assert "* $factor" in fn
    # Και φτάνουν όντως στο παραστατικό — όχι απλώς υπολογίζονται.
    assert "$creditSeries, $mirrorTaxes," in fn
    assert "$creditSeries, []," not in fn


def test_credit_note_direction_comes_from_aade_not_from_a_guess():
    fn = _block(_read(ETIM_PHP), "function createCreditNote(", "// --- 7. GET INVOICE PDF")
    assert "'decrease' => !empty($t['taxDecreaseTotalPaid'])" in fn


def test_payable_is_not_simply_net_plus_vat():
    """Οι παρακρατήσεις ΜΕΙΩΝΟΥΝ το πληρωτέο, τα τέλη το αυξάνουν.

    Με «καθαρή + ΦΠΑ» το πιστωτικό δήλωνε 12.400 € για συσχετιζόμενο 12.100 €.
    """
    fn = _block(_read(ETIM_PHP), "function createInvoice(", "// --- 6b. CREDIT NOTE")
    assert "$taxAdjust" in fn
    assert "$payable = round($total + $taxAdjust, 2);" in fn
    assert "'ccr_grossValue'            => (string)$payable," in fn
    assert "'ccr_grossValue'            => (string)$total," not in fn
    # 1 = παρακρατούμενοι, 5 = κρατήσεις: μειώνουν. 2/3/4: αυξάνουν.
    assert "in_array($ttype, [1, 5], true)" in fn


def test_previewing_a_saved_draft_keeps_its_taxes():
    src = _read(ETIM_PHP)
    assert "function tempTaxesToForm(" in src
    fn = _block(src, "function previewTempInvoice(", "\n}\n\n")
    assert "'invoiceTaxes' => tempTaxesToForm(" in fn


# --- 2. Η καρτέλα του πελάτη χωρίς ΑΦΜ --------------------------------------
def test_ledger_can_be_keyed_by_customer_code():
    src = _read(ETIM_PHP)
    fn = _block(src, "function ledgerInvoices(", "\nfunction buildLedger(")
    # Ο ιδιώτης βρίσκεται ΜΟΝΟ ανάμεσα στα παραστατικά χωρίς ΑΦΜ αγοραστή.
    assert "if (trim((string)($iv['buyer_vat'] ?? '')) !== '') continue;" in fn
    assert "counterpartOfMark(" in fn
    # Μία κλήση ανά ΜΑΡΚ, μία φορά στη ζωή του: το ΜΑΡΚ δεν αλλάζει κάτοχο.
    assert "cache_get(COMPANY_VAT, 'ledger_counterparts')" in fn
    assert "cache_set(COMPANY_VAT, 'ledger_counterparts'" in fn
    # Ο πελάτης ΜΕ ΑΦΜ δεν πληρώνει τίποτα από αυτά.
    assert "if (strncmp($ledgerKey, '#', 1) !== 0) {" in fn


def test_ledger_reply_never_shows_the_hash_as_a_vat():
    fn = _block(_read(ETIM_PHP), "function buildLedger(", "// Normalise a display date")
    assert "'customer_code'   => strncmp($buyerVat, '#', 1) === 0 ? substr($buyerVat, 1) : ''," in fn
    assert "'customer_vat'    => strncmp($buyerVat, '#', 1) === 0 ? '' : $buyerVat," in fn


def test_router_and_zip_accept_the_customer_code():
    src = _read(ETIM_PHP)
    assert "if ($cv === '' && $cc !== '') $cv = '#' . $cc;" in src
    # Το ZIP της καρτέλας ξεκινά από το ίδιο κλειδί, αλλιώς γυρίζει άδειο.
    zip_block = _block(src, "if (!empty($_GET['invoices_zip']", "streamInvoicesZip(")
    assert "ledgerInvoices($ch, $bv, $issueDateFrom, $issueDateTo)" in zip_block


def test_the_page_carries_the_code_through_every_entry_point():
    src = _read(APP_PHP)
    assert "function cardKey(vat,code){" in src
    assert "function cardParam(key){" in src
    # Και οι τρεις αφετηρίες: γραμμή πίνακα, κουμπί «Καρτέλα →», επιλογέας.
    assert src.count("openCard('${q1(c.vat)}','${q1(c.name)}','${q1(c.code)}')") == 2
    assert "pickCardCust('${q1(c.vat)}','${q1(c.name)}','${q1(c.code)}')" in src
    # Και η κλήση στο backend δεν στέλνει πια σκέτο ΑΦΜ.
    assert "api({ledger:1,buyer_vat:vat" not in src


# --- 3+4. Οι δύο αναζητήσεις, πάνω στον ΙΔΙΟ κώδικα που τρέχει --------------
CUSTOMERS = [
    {"code": "1", "vat": "802012659", "name": "MEGATECH ΜΟΝΟΠΡΟΣΩΠΗ ΙΚΕ",
     "address": "5 ΧΛΜ ΤΡΙΠΟΛΗΣ", "city": "ΣΤΑΔΙΟ", "type": "Ημεδαπή επιχείρηση"},
    {"code": "2", "vat": "000000000", "name": "ΤΟΥΛΟΥΜΗ ΑΛΕΞΑΝΔΡΑ",
     "address": "ΑΓΙΑΣ ΛΑΥΡΑΣ 1", "city": "ΒΑΡΗ", "type": "Ιδιώτης"},
    {"code": "3", "vat": "", "name": "ΒΑΡΕΛΑΣ ΝΙΚΟΛΑΟΣ",
     "address": "ΜΙΜΟΖΑΣ 19", "city": "ΕΚΑΛΗ", "type": "Ιδιώτης"},
    {"code": "4", "vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ",
     "address": "ΛΑΛΕΞΑΝΔΡΑΣ 10", "city": "ΑΘΗΝΑ", "type": "Ημεδαπή επιχείρηση"},
]

DOCS = [
    {"mark": "400014973506434", "type": "2.1 - Τιμολόγιο Παροχής Υπηρεσιών",
     "issue_date": "24/08/2026", "series": "ΤΠΥ", "aa": "17", "buyer_vat": "802391747",
     "net_value": "10.000,00", "vat_value": "2.400,00", "total": "12.100,00"},
    {"mark": "400014690544553", "type": "11.2 - ΑΠΥ (Απόδειξη Παροχής Υπηρεσιών)",
     "issue_date": "02/08/2026", "series": "ΑΠΥ", "aa": "18", "buyer_vat": "996980453",
     "net_value": "64,52", "vat_value": "15,48", "total": "80,00"},
]

#: Οι συναρτήσεις που εξάγονται από το `app.php` και τρέχουν αυτούσιες.
_WANTED = ("grFold", "elNum", "dtParse", "custFields", "docWho", "docHay")


def _extract(src: str, name: str) -> str:
    """Το σώμα μιας συνάρτησης, με ταίριασμα αγκυλών.

    Αγνοεί αγκύλες μέσα σε συμβολοσειρές, σχόλια και regex — αλλιώς ένα `{` σε
    template literal θα έκοβε το κείμενο στη μέση. Το αποτέλεσμα περνά από
    `node --check`, οπότε μια αστοχία εδώ γίνεται αποτυχία test, όχι σιωπή.
    """
    i = src.index("function " + name + "(")
    depth, started = 0, False
    in_str = None
    in_re = in_line = in_blk = False
    j = i
    while j < len(src):
        c, n = src[j], src[j + 1 : j + 2]
        prev = src[j - 1] if j else "\n"
        if in_line:
            if c == "\n":
                in_line = False
        elif in_blk:
            if c == "*" and n == "/":
                in_blk = False
                j += 1
        elif in_str:
            if c == "\\":
                j += 1
            elif c == in_str:
                in_str = None
        elif in_re:
            if c == "\\":
                j += 1
            elif c == "[":
                while src[j] != "]":
                    j += 1
                    if src[j] == "\\":
                        j += 1
            elif c == "/":
                in_re = False
        elif c == "/" and n == "/":
            in_line = True
            j += 1
        elif c == "/" and n == "*":
            in_blk = True
            j += 1
        elif c in "\"'`":
            in_str = c
        elif c == "/" and prev in "=(,:[!&|?{};+-*%\n ":
            in_re = True
        elif c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return src[i : j + 1]
        j += 1
    raise AssertionError(f"δεν έκλεισε η {name}")


@pytest.mark.skipif(NODE is None, reason="δεν υπάρχει node")
def test_the_two_searches_find_what_the_table_shows(tmp_path: Path):
    src = _read(APP_PHP)
    funcs = "\n".join(_extract(src, n) for n in _WANTED)

    driver = tmp_path / "search.js"
    driver.write_text(
        funcs
        + "\nconst CUSTOMERS=" + json.dumps(CUSTOMERS, ensure_ascii=False)
        + ";\nconst DOCS=" + json.dumps(DOCS, ensure_ascii=False)
        + ";\nglobalThis.ALL_CUSTOMERS=CUSTOMERS;"
        + "\nconst cust=t=>CUSTOMERS.map(custFields).filter(c=>"
          "grFold([c.code,c.vat,c.name,c.city,c.address,c.type].join(' '))"
          ".includes(grFold(t).trim())).length;"
        + "\nconst doc=t=>DOCS.filter(i=>docHay(i).includes(grFold(t).trim())).length;"
        + "\nconst out={};"
        + "\n['ΒΑΡΗ','βαρη','Βάρη','Αθήνα','ΣΤΑΔΙΟ','Ρέικιαβικ','802012659','ΕΚΑΛΗ']"
          ".forEach(t=>out['c:'+t]=cust(t));"
        + "\n['24/08/2026','2026-08-24','12.100,00','12100','10000','2400','15,48','999999',"
          "'400014973506434','τιμολόγιο']"
          ".forEach(t=>out['d:'+t]=doc(t));"
        + "\nconsole.log(JSON.stringify(out));\n",
        encoding="utf-8",
    )

    # Αν η εξαγωγή αστόχησε, εδώ σκάει — δεν περνά σιωπηλά.
    chk = subprocess.run([NODE, "--check", str(driver)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr

    run = subprocess.run([NODE, str(driver)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert run.returncode == 0, run.stderr
    got = json.loads(run.stdout)

    # Πελάτες: η πόλη βρίσκεται όπως κι αν γραφτεί.
    assert got["c:ΒΑΡΗ"] == 1
    assert got["c:βαρη"] == 1, "πεζά πρέπει να βρίσκουν κεφαλαία"
    assert got["c:Βάρη"] == 1, "ο τόνος που γράφει ο χρήστης δεν υπάρχει στα δεδομένα"
    assert got["c:Αθήνα"] == 1
    assert got["c:ΣΤΑΔΙΟ"] == 1
    assert got["c:ΕΚΑΛΗ"] == 1
    assert got["c:Ρέικιαβικ"] == 0
    assert got["c:802012659"] == 1

    # Παραστατικά: ημερομηνία και τα τρία ποσά, με ή χωρίς τελείες.
    assert got["d:24/08/2026"] == 1
    assert got["d:2026-08-24"] == 1, "και σε μορφή ISO"
    assert got["d:12.100,00"] == 1
    assert got["d:12100"] == 1, "«12100» πρέπει να βρίσκει το «12.100,00»"
    assert got["d:10000"] == 1, "καθαρή αξία"
    assert got["d:2400"] == 1, "ΦΠΑ"
    assert got["d:15,48"] == 1, "ο ΦΠΑ μιας μικρής απόδειξης, όπως γράφεται"
    assert got["d:999999"] == 0
    assert got["d:400014973506434"] == 1
    assert got["d:τιμολόγιο"] == 1, "ο τύπος, τονισμένος"


@pytest.mark.skipif(NODE is None, reason="δεν υπάρχει node")
def test_the_inline_javascript_parses():
    """Ένα σπασμένο string ρίχνει ΟΛΟ το script και η σελίδα φαίνεται μια χαρά.

    Ο `php -l` δεν βλέπει τίποτα, ο server απαντά 200, το healthz λέει «ok».
    Το μόνο σημάδι είναι ότι κανένα κουμπί δεν πατιέται.
    """
    checker = REPO / "tools" / "js_check.js"
    assert checker.exists()
    pages = [str(REPO / "app.php"), str(REPO / "authview.php")]
    run = subprocess.run([NODE, str(checker), *pages], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert run.returncode == 0, run.stdout + run.stderr
