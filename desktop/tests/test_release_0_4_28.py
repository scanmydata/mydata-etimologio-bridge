"""Οριστική έκδοση χωρίς σφάλματα XSD, πελάτες με όλα τους τα στοιχεία, και ταχύτητα.

* **«itemUnitPrice 2419.3548 … FractionDigits».** Η τιμή μονάδας προέκυπτε από
  «σύνολο ÷ 1,24» με 4 δεκαδικά. Η προεπισκόπηση περνούσε· η οριστική έκδοση όχι.

* **«address has incomplete content … postalCode».** Η λίστα πελατών της ΑΑΔΕ δεν
  έχει Τ.Κ., email, τηλέφωνα, ΔΟΥ — μόνο η σελίδα κάθε πελάτη. Η φόρμα πελάτη
  έδειχνε κενά πεδία που στην ΑΑΔΕ ήταν γεμάτα, και η διεύθυνση έφευγε χωρίς Τ.Κ.

* **Αργή Έκδοση.** Κάθε ανανέωση λίστας έκανε πλήρη σύνδεση στην ΑΑΔΕ (~1 δευτ.),
  και ο τοπικός server εξυπηρετεί ένα αίτημα τη φορά.

* **Email:** «Καλημέρα/Καλησπέρα <επωνυμία>», υπογραφή χωρίς ΑΦΜ.
* **Στατιστικά:** ρητά «καθαρή αξία» / «σύνολο με ΦΠΑ», πιστωτικά με αφαίρεση.
* **Νέο είδος:** επόμενος ελεύθερος κωδικός· από την Έκδοση επιλέγεται μόνο του.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"


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


php_only = pytest.mark.skipif(not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe")


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


@pytest.fixture(scope="module")
def etim() -> str:
    return _read(ETIM_PHP)


# ===========================================================================
# 1. Δύο δεκαδικά
# ===========================================================================
def test_server_rounds_unit_price(etim: str):
    fn = _block(etim, "function buildInvoiceLine(")
    assert fn.index("$unitNet = round($unitNet, 2);") < fn.index("$gross = round($unitNet * $qty, 2);")


def test_no_four_decimal_prices_in_the_page(page: str):
    assert "elFmtField(this,4)" not in page
    assert ",4)" not in "".join(l for l in page.splitlines() if "elFmt(" in l and "price" in l.lower())


def test_unit_for_gross_has_two_decimals_and_nearest_cent(page: str):
    fn = _js_block(page, "function unitForGross(G,q,r){")
    res = _node(fn + """
const C=[[3000,1],[124,1],[1000,3],[99.99,1],[250,2],[12400,1]];
console.log(JSON.stringify(C.map(([G,q])=>{const u=unitForGross(G,q,0.24);
  const net=Math.round(u*q*100)/100;return [u,Math.round((net+Math.round(net*0.24*100)/100)*100)/100];})));""")
    for (u, gross), (G, _q) in zip(res, [[3000, 1], [124, 1], [1000, 3], [99.99, 1], [250, 2], [12400, 1]]):
        assert round(u, 2) == u
        assert abs(gross - G) <= 0.011
    assert res[1] == [100, 124] and res[5] == [10000, 12400]


def test_collected_lines_send_rounded_prices(page: str):
    assert "const price=price2(r.querySelector('.ln-price').value);" in _js_block(page, "function collectLines(){")


# ===========================================================================
# 2. Στοιχεία πελάτη και διεύθυνση
# ===========================================================================
def test_customer_list_keeps_view_url_server_side(etim: str):
    assert "$customer['view_url'] = html_entity_decode(" in _block(etim, "function listCustomers(")
    enrich = _block(etim, "function enrichCustomerDetails(")
    assert "unset($r['view_url']);" in enrich
    assert "CUST_DETAILS_TTL" in enrich and "$budget" in enrich


@php_only
def test_customer_details_are_parsed_from_the_view_page(tmp_path: Path, etim: str):
    html = ('<input name="customer.CustomerZipCode" value="16672">'
            '<input name="customer.CustomerEmail" value="angelica.misk@gmail.com">'
            '<input name="customer.CustomerPhone1" value="6944182346">'
            '<input name="customer.CustomerPhone2" value="">'
            '<input name="customer.Doy" value="&#x39A;&#x395;&#x3A6;&#x39F;&#x394;&#x395;">'
            '<input name="customer.JobDescription" value="&#x399;&#x394;&#x399;&#x3A9;&#x3A4;&#x397;&#x3A3;">'
            '<input name="customer.CustomerAddress" value="X 16"><input name="customer.CustomerCity" value="BAPH">')
    code = (
        "const BASE_URL='https://mydata.aade.gr/timologio';\n"
        "$GLOBALS['H']=" + json.dumps(html) + ";\n$GLOBALS['U']='';\n"
        "function curlGet($ch,$url){$GLOBALS['U']=$url;return $GLOBALS['H'];}\n"
        + _block(etim, "function htmlInputValue(") + "\n"
        + _block(etim, "function customerDetailsFromView(").replace("\\CurlHandle $ch", "$ch") + "\n"
        "$d=customerDetailsFromView(null,'/timologio/Customer/viewcustomer?cd=1');unset($d['fetched_at']);"
        "echo json_encode([$d,$GLOBALS['U'],customerDetailsFromView(null,'')],JSON_UNESCAPED_UNICODE);"
    )
    d, url, empty = json.loads(_php(tmp_path, code))
    assert d["zip"] == "16672" and d["email"] == "angelica.misk@gmail.com"
    assert d["phone1"] == "6944182346" and d["doy"] == "ΚΕΦΟΔΕ" and d["job_description"] == "ΙΔΙΩΤΗΣ"
    assert url == "https://mydata.aade.gr/timologio/Customer/viewcustomer?cd=1"
    assert empty is None


def test_invoice_address_gets_zip_or_is_dropped(etim: str):
    fn = _block(etim, "function createInvoice(")
    block = fn[fn.index("Ο Τ.Κ. και η πόλη είναι ΥΠΟΧΡΕΩΤΙΚΑ"):fn.index("// Normalise to a list of lines.")]
    assert block.index("custDetailsFind(") < block.index("findCustomerViewUrl(")
    assert "$address = ''; $zip = ''; $city = '';" in block
    assert "empty($delivery)" in block          # τα δελτία έχουν δικό τους έλεγχο
    assert etim.count("$result['warning'] = 'Η διεύθυνση του πελάτη δεν μπήκε") == 2


def test_edit_form_fills_from_db_then_verifies(page: str):
    fn = _js_block(page, "async function ceFillDetails(vat,code){")
    assert fn.index("api(q)") < fn.index("verify:1")
    # Ό,τι έγραψε ήδη ο χρήστης δεν πειράζεται.
    assert "!el.value.trim()" in fn
    assert "ceFillDetails(c.vat,c.code);" in _js_block(page, "function editCustomer(vat){")


# ===========================================================================
# 3. Μνήμη χωρίς σύνδεση
# ===========================================================================
def test_fast_paths_run_before_login(etim: str):
    login = etim.index("$ch = login();\n\n// Serve e-timologio's own client-side PDF scripts")
    for marker in ("$__syncFast = trim(", "cache_get(COMPANY_VAT, 'taxcats')", "cache_get(COMPANY_VAT, 'prodcats')",
                   "customer_details'] ?? $_POST['customer_details'] ?? '') && defined('COMPANY_VAT')",
                   "customer_contact_get(COMPANY_VAT, $__cv)['email']", "cacheMarkDirty(COMPANY_VAT, $__dirty);"):
        assert etim.index(marker) < login, marker


def test_fast_sync_respects_dirty_force_and_missing_details(etim: str):
    fast = etim[etim.index("$__syncFast = trim("):etim.index("// Κατηγορίες φόρων")]
    assert "setting_get(cacheDirtyKey(COMPANY_VAT, $__syncFast)) === ''" in fast
    assert "empty($_GET['force'] ?? $_POST['force'] ?? '')" in fast
    # Χωρίς ολοκληρωμένα στοιχεία πελατών, ΠΟΤΕ από τη μνήμη.
    assert "setting_get('cache.pending.' . COMPANY_VAT . '.customers') !== '0'" in fast
    assert "'newdocs'" not in fast           # ο έλεγχος νέων παραστατικών πάει πάντα στην ΑΑΔΕ
    assert "$__age < SYNC_TRUST_SECONDS" in fast


def test_mutations_mark_lists_dirty(etim: str):
    mut = etim[etim.index("$__mut = ["):etim.index("$__dirty = [];")]
    for p in ("'new_product'", "'update_product_code'", "'update_customer'", "'new_series'", "'save_category_cls'"):
        assert p in mut
    assert "register_shutdown_function(" in etim[etim.index("$__dirty = [];"):etim.index("$__syncFast = trim(")]


def test_sync_always_stamps_and_clears_dirty(etim: str):
    sync = etim[etim.index("$syncKind = trim("):etim.index("if ($ledgerFlag) {")]
    assert "if ($changed) cache_set(" not in sync
    assert "cache_set(COMPANY_VAT, $syncKind, $rows);" in sync
    assert "setting_set(cacheDirtyKey(COMPANY_VAT, $syncKind), '')" in sync
    assert "$syncKind === 'prodcats'" in sync


def test_client_skips_fresh_lists_and_forces_dirty(page: str):
    fn = _js_block(page, "async function cachedThenSync(kind,onRows){")
    assert "if(shown&&fresh&&!dirty)return;" in fn
    assert "force:dirty?1:''" in fn
    assert "custFillDetails()" in fn


def test_issue_view_defers_tax_categories(page: str):
    sv = page[page.index("if(v==='issue'){"):]
    sv = sv[: sv.index("\n")]
    assert "loadIssueTypes().finally(()=>setTimeout(loadTaxCats,300))" in sv


# ===========================================================================
# 4. Email
# ===========================================================================
@php_only
def test_server_greeting_follows_send_time(tmp_path: Path, etim: str):
    code = (
        _block(etim, "function mailGreeting(") + "\n" + _block(etim, "function mailFixGreeting(") + "\n"
        "$m=strtotime('2026-09-14 09:00:00 Europe/Athens');$e=strtotime('2026-09-14 18:30:00 Europe/Athens');"
        "$n=strtotime('2026-09-14 12:00:00 Europe/Athens');"
        "echo json_encode([mailGreeting($m),mailGreeting($n),mailFixGreeting(\"Καλημέρα Χ,\\nΚαλημέρα\",$e),"
        "mailFixGreeting('Γεια σας',$e)],JSON_UNESCAPED_UNICODE);"
    )
    assert json.loads(_php(tmp_path, code)) == ["Καλημέρα", "Καλησπέρα", "Καλησπέρα Χ,\nΚαλημέρα", "Γεια σας"]


def test_email_document_fixes_greeting_on_send(etim: str):
    h = etim[etim.index("if (!empty($_POST['email_document']"):]
    assert "$bodyRaw = mailFixGreeting((string)($_POST['body'] ?? ''));" in h[:2000]


def test_client_greeting_and_company_without_vat(page: str):
    code = (_js_block(page, "function mailGreeting(d){") + "\n" + _js_block(page, "function mailHello(name){")
            + "\nfunction $(s){return {textContent:'ΤΟ ΒΑΨΙΜΟ Ε Ε (802576637)'};}\n" + _js_block(page, "function mailCompany(){"))
    res = _node(code + """
const m=new Date(2026,8,14,9),e=new Date(2026,8,14,19);
console.log(JSON.stringify([mailGreeting(m),mailGreeting(e),mailCompany(),
  mailHello('ΜΙΣΚΑΚΗ ΑΓΓΕΛΙΚΗ').replace(/^Καλ\\S+/,'X'),mailHello('046307992').replace(/^Καλ\\S+/,'X'),mailHello('').replace(/^Καλ\\S+/,'X')]));""")
    assert res == ["Καλημέρα", "Καλησπέρα", "ΤΟ ΒΑΨΙΜΟ Ε Ε", "X ΜΙΣΚΑΚΗ ΑΓΓΕΛΙΚΗ,", "X σας,", "X σας,"]
    md = _js_block(page, "function mailDefaults(kind,info){")
    assert "const company=mailCompany();" in md and "#account option:checked" not in md


def test_auto_and_ledger_mails_greet_and_sign(etim: str):
    auto = _block(etim, "function autoSendIssuedDocument(")
    assert "mailGreeting()" in auto and "mailCompanyName($accountVat)" in auto
    assert "'αγαπητέ συνεργάτη,'" not in auto
    led = _block(etim, "function ledgerMailBody(")
    assert "mailGreeting()" in led and "mailCompanyName($accountVat)" in led


# ===========================================================================
# 5. Στατιστικά και νέο είδος
# ===========================================================================
def test_statistics_net_vat_gross_with_credit_sign(etim: str, page: str):
    fn = _block(etim, "function getStatistics(")
    assert "['5.1', '5.2', '11.4']" in fn
    assert "$gross = $net + $vat;" in fn        # όχι το «πληρωτέο» της ΑΑΔΕ
    assert "'total_gross'" in fn and "'total_vat'" in fn
    load = _js_block(page, "async function loadStats(){")
    assert "Καθαρή αξία" in load and "(με ΦΠΑ)" in load
    assert "Καθαρή αξία (€)" in page and "Σύνολο με ΦΠΑ (€)" in page


def test_next_product_code(page: str):
    fn = _js_block(page, "function nextProductCode(){")
    res = _node(fn + """
globalThis.PRODMAP={'1':{},'2':{},'14':{},'A-7':{}};globalThis.PRODUCTS=[{product_code:'15'}];
const a=nextProductCode();PRODMAP={};PRODUCTS=[];const b=nextProductCode();
console.log(JSON.stringify([a,b]));""")
    assert res == ["16", "1"]
    assert "nextProductCode()" in _js_block(page, "function openProductModal(")


def test_new_product_from_issue_is_selected_on_the_row(page: str):
    fn = _js_block(page, "function newProdForLine(el){")
    assert "pickProd(row.querySelector('.ln-code'),code)" in fn
    assert "pickProd(el,code)" not in fn
