"""e-Τιμολόγιο Pro: ακύρωση που φτάνει ως το τέλος, οδηγός από το πρώτο καρέ, ορατή αναμονή.

* **«address … has incomplete content … postalCode».** Το πιστωτικό έπαιρνε από
  το πρωτότυπο επωνυμία και γραμμές — αλλά ΟΧΙ τη διεύθυνση. Το Taxisnet δεν
  δίνει τίποτα για ιδιώτες, οπότε η διεύθυνση έφευγε κενή· και επειδή ο
  «αριθμός» έφευγε πάντα ως «0», η ΑΑΔΕ έβλεπε διεύθυνση δίχως Τ.Κ. και έκοβε
  την έκδοση. Ζωντανή επαλήθευση: η ίδια προεπισκόπηση «Αδυναμία
  προεπισκόπησης» → κανονικό PDF με «ΠΑΡΑΔΕΙΣΟΥ 16 - ΒΑΡΗ 16672».

* **Δεν έμπαινε αιτιολογία στο ακυρωτικό.** Το φίλτρο ΑΦΜ αγοραστή της ΑΑΔΕ
  αγνοείται σιωπηλά στα λιανικά: αναζήτηση με ΑΦΜ 046307992 → 0 παραστατικά,
  χωρίς ΑΦΜ → 19 (η ίδια ΑΠΥ μέσα). Η οθόνη «Ακύρωση» δεν εμφάνιζε ποτέ την
  απόδειξη, άρα δεν άνοιγε ποτέ η κάρτα με το πεδίο της αιτιολογίας.

* **Ο οδηγός «άργαγε».** Η γυμνή φόρμα έκδοσης ήταν ορατή από το πρώτο καρέ και
  κρυβόταν μόνο μετά από δύο κλήσεις δικτύου της εκκίνησης.

* **Τι τρέχει τώρα:** κάρτα πάνω δεξιά, αυτόματα, σε κάθε κλήση προς τον server.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
VENDORED = REPO / "desktop" / "backend" / "etimologio"
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"

php_only = pytest.mark.skipif(not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _block(src: str, header: str, end: str = "\n}") -> str:
    body = src[src.index(header):]
    return body[: body.index(end) + len(end)]


def _js_block(src: str, header: str) -> str:
    i = src.index(header)
    depth, started = 0, False
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
            started = True
        elif src[j] == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:j + 1]
    raise AssertionError(header)


def _node(code: str):
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _php(tmp_path: Path, code: str) -> str:
    script = tmp_path / "t.php"
    script.write_text("<?php\n" + code, encoding="utf-8")
    out = subprocess.run([str(PHP_EXE), str(script)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


@pytest.fixture(scope="module")
def etim() -> str:
    return _read(ETIM_PHP)


# ===========================================================================
# 1. Η διεύθυνση του λήπτη
# ===========================================================================
def test_credit_note_copies_the_address_of_the_original(etim: str):
    fn = _block(etim, "function createCreditNote(")
    assert "$counterStreet = (string)($cAddr['street'] ?? '');" in fn
    assert "$counterZip    = (string)($cAddr['postalCode'] ?? '');" in fn
    assert "$counterCity   = (string)($cAddr['city'] ?? '');" in fn
    # Και φτάνει ΩΣ την κλήση — αλλιώς η αντιγραφή δεν θα άλλαζε τίποτα.
    assert "$buyer, $counterName, $counterStreet, $counterCity, $counterZip, $counterCountry, '0'," in fn
    assert "$buyer, $counterName, '', '', ''" not in fn


def test_address_never_ships_a_lone_number(etim: str):
    fn = _block(etim, "function createInvoice(")
    assert "'number'     => ($zip !== '' && $city !== '') ? '0' : ''," in fn
    # Η συμπλήρωση Τ.Κ./πόλης δεν εξαρτάται πια από το αν υπάρχει οδός.
    assert "if (empty($delivery) && defined('COMPANY_VAT') && ($zip === '' || $city === '')) {" in fn
    assert "&& ($address !== '' || $zip !== '' || $city !== '')) {" not in fn


@php_only
def test_number_follows_zip_and_city(tmp_path: Path):
    code = ("""
$cases = [['ΣΤΑΔΙΟΥ 10','ΑΘΗΝΑ','10564'], ['ΣΤΑΔΙΟΥ 10','ΑΘΗΝΑ',''], ['','',''], ['','ΑΘΗΝΑ','10564'], ['','','10564']];
$out = [];
foreach ($cases as [$address, $city, $zip]) {
    $out[] = ($zip !== '' && $city !== '') ? '0' : '';
}
echo json_encode($out);
""")
    assert json.loads(_php(tmp_path, code)) == ["0", "", "", "0", ""]


# ===========================================================================
# 2. Η ακύρωση βρίσκει το παραστατικό — και δέχεται αιτιολογία
# ===========================================================================
def test_buyer_vat_is_filtered_locally_not_by_aade(etim: str):
    handler = etim[etim.index("if ($searchInvoicesFlag) {"):]
    handler = handler[:handler.index("jsonResponse($result);")]
    call = handler[handler.index("$result = searchInvoices("):handler.index(");") + 2]
    assert "$buyerVatFilter" not in call        # στην ΑΑΔΕ πάει ΚΕΝΟ
    assert "        '',\n" in call
    assert "(string)($iv['buyer_vat'] ?? '') === $buyerVatFilter" in handler
    assert "$result['count'] = count($result['invoices']);" in handler


@php_only
def test_local_filter_keeps_retail_invoices(tmp_path: Path, etim: str):
    """Η ΑΠΥ 11.2 του ιδιώτη επιβιώνει· τα ξένα παραστατικά φεύγουν."""
    handler = etim[etim.index("if ($buyerVatFilter !== '' && !empty($result['success'])) {"):]
    body = handler[:handler.index("\n    }") + 6]
    code = (
        "$buyerVatFilter='046307992';\n"
        "$result=['success'=>true,'invoices'=>["
        "['mark'=>'1','buyer_vat'=>'046307992','type'=>'11.2'],"
        "['mark'=>'2','buyer_vat'=>'801355228','type'=>'2.1'],"
        "['mark'=>'3','buyer_vat'=>'046307992','type'=>'11.4']]];\n"
        + body + "\n"
        "echo json_encode([$result['count'], array_column($result['invoices'],'mark')]);"
    )
    assert json.loads(_php(tmp_path, code)) == [2, ["1", "3"]]


def test_cancel_card_asks_for_the_reason_first(page: str):
    card = _js_block(page, "function cxPick(idx){")
    assert card.index("Αιτιολογία ακύρωσης") < card.index("Καθαρή αξία πιστωτικού")
    assert 'id="cxReason" placeholder="π.χ. λάθος τιμολόγηση" autofocus' in card
    assert "Παρατηρήσεις</b> του πιστωτικού" in card
    # Και η αιτιολογία ταξιδεύει και στην προεπισκόπηση και στην έκδοση.
    for fn in ("async function previewCredit(mark){", "async function doCredit(viaIssue,mark){"):
        assert "reason:$('#cxReason').value" in _js_block(page, fn)


def test_cancel_from_card_finds_a_document_outside_the_range(page: str):
    fn = _js_block(page, "async function cancelFromCard(mark){")
    assert "api({search_invoices:1,mark:mark})" in fn
    assert "CX_INV=[hit].concat(CX_INV);idx=0;" in fn
    assert "if(idx<0){toast('Το παραστατικό δεν βρέθηκε" in fn
    assert fn.index("if(idx<0){toast(") < fn.index("cxPick(idx)")


# ===========================================================================
# 3. Ο οδηγός είναι η πρώτη εικόνα
# ===========================================================================
def test_issue_form_is_hidden_until_the_wizard_says_otherwise(page: str):
    assert '<div class="panel" id="issueFormPanel" style="display:none">' in page
    assert page.index("(async()=>{wizShow(true);addEyes();") > 0
    # Ο οδηγός ΔΕΝ περιμένει τις κλήσεις της εκκίνησης.
    boot = page[page.index("(async()=>{wizShow(true);"):]
    assert boot.index("wizShow(true)") < boot.index("await initAccounts()")


# ===========================================================================
# 4. «Τι τρέχει τώρα» — πάνω δεξιά, μόνο του
# ===========================================================================
def test_busy_card_sits_top_right(page: str):
    assert "#busyBox{position:fixed;right:18px;top:18px;" in page
    assert "body.busy .toast{top:100px}" in page
    assert "document.body.classList.add('busy');" in page
    assert "document.body.classList.remove('busy');" in page


def test_every_server_call_lights_the_card(page: str):
    wrap = page[page.index("(function(){const rawFetch=window.fetch.bind(window);"):]
    wrap = wrap[:wrap.index("};})();") + 7]
    assert "if(url.indexOf(API)!==0)return rawFetch(input,init);" in wrap
    assert "if(!label)return rawFetch(input,init);" in wrap       # σιωπηλά = παρασκήνιο
    assert "setTimeout(()=>{on=true;busyOn(label,'');" in wrap     # όχι τρεμόπαιγμα
    assert "δευτ." in wrap                                        # πόση ώρα τρέχει
    assert "const done=()=>{clearTimeout(t);" in wrap and "e=>{done();throw e;}" in wrap


def test_busy_labels_name_the_job(page: str):
    rules = page[page.index("const BUSY_DELAY=150;"):page.index("function busyQuery(url,init){")]
    fn = _js_block(page, "function busyQuery(url,init){")
    cases = [
        "etimologio.php?credit_note=1&cancel_mark=4000&live=1",
        "etimologio.php?search_invoices=1&issue_date_from=01/01/2026",
        "etimologio.php?delete_temp_id=abc",
        "etimologio.php?notif_count=1",
        "etimologio.php?sync=customers",
        "etimologio.php?cached=products",
        "etimologio.php?statistics=1",
        "etimologio.php?sync=newdocs",
        "etimologio.php?auth=local_tick",
    ]
    got = _node(rules + fn + """
const C=""" + json.dumps(cases) + """;
console.log(JSON.stringify(C.map(u=>busyLabel(busyQuery(u,null)))));""")
    assert got == [
        "Οριστική έκδοση στην ΑΑΔΕ…",
        "Λήψη παραστατικών…",
        "Διαγραφή…",
        "",                                   # παρασκήνιο: καμία κάρτα
        "Συγχρονισμός με ΑΑΔΕ…",
        "Φόρτωση δεδομένων…",
        "Υπολογισμός στατιστικών…",
        "",                                   # ο ωριαίος έλεγχος νέων: σιωπηλός
        "",                                   # και το ημερήσιο αντίγραφο
    ]
    # Και το σώμα ενός POST μετρά όσο και το query.
    posted = _node(rules + fn + """
console.log(JSON.stringify([busyLabel(busyQuery('etimologio.php','{}'&&{body:'bulk_issue=1&items=[]'}))]));""")
    assert posted == ["Μαζική έκδοση…"]


# ===========================================================================
# 5. Ο καθρέφτης της εφαρμογής υπολογιστή
# ===========================================================================
def test_vendored_copies_match():
    for name in ("app.php", "etimologio.php"):
        assert (VENDORED / name).read_bytes() == (REPO / name).read_bytes(), name
