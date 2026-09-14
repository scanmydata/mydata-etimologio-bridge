"""Παραστατικά που λένε την αλήθεια, και σύνδεση server που δεν φεύγει στον Edge.

* **Τα πιστωτικά μετρούσαν θετικά.** Η ΑΑΔΕ γράφει κάθε ποσό θετικό· ένα
  πιστωτικό 6.416,26 φούσκωνε το σύνολο αντί να το μειώνει.

* **Πελάτης χωρίς ΑΦΜ = «—».** Ο κατάλογος της ΑΑΔΕ έχει μόνο ΑΦΜ, οπότε ένας
  ιδιώτης σε ΑΠΥ δεν είχε με τι να αντιστοιχιστεί. Η επωνυμία υπάρχει μόνο στην
  «Προβολή» του παραστατικού — ρωτιέται μία φορά ανά ΜΑΡΚ και μένει στη μνήμη.

* **Λειτουργία server στην εφαρμογή υπολογιστή.** Μόνο το loopback θεωρούνταν
  «δικό μας»: το «μπες» μετά τον κωδικό άνοιγε τον Edge. Και το «Τοπικά
  δεδομένα» έσκαγε σε κουμπί που είχε σβηστεί.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
SHELL_PY = REPO / "desktop" / "src" / "timologio" / "etimologio" / "webshell.py"
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _block(src: str, header: str, end: str = "\n}") -> str:
    body = src[src.index(header):]
    return body[: body.index(end) + len(end)]


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


@pytest.fixture(scope="module")
def etim() -> str:
    return _read(ETIM_PHP)


def _node(code: str) -> str:
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


# ===========================================================================
# 1. Πρόσημο πιστωτικών + σύνολα ανά στήλη
# ===========================================================================
def test_credit_notes_are_negative(page: str):
    fns = "\n".join([
        _block(page, "function elNum(v){", "return parseFloat(s)||0;}"),
        _block(page, "function docIsCredit(i){", "}"),
        _block(page, "function docSigned(i,field){", "}"),
        _block(page, "function docAmt(i,field){"),
    ])
    rows = [
        {"type": "11.4 - Πιστωτικό Στοιχείο Λιανικής (Συσχετιζόμενο)", "total": "6.416,26"},
        {"type": "5.1 - Πιστωτικό Τιμολόγιο / Συσχετιζόμενο", "total": "100,00"},
        {"type": "5.2 - Πιστωτικό Τιμολόγιο / Μη Συσχετιζόμενο", "total": "-50,00"},
        {"type": "11.2 - ΑΠΥ (Απόδειξη Παροχής Υπηρεσιών)", "total": "6.416,26"},
        {"type": "2.1 - Τιμολόγιο Παροχής Υπηρεσιών", "total": "2.108,00"},
        # «1.4» δεν είναι «11.4»: η αντιστοίχιση είναι στην ΑΡΧΗ του τύπου.
        {"type": "1.4 - Τιμολόγιο Πώλησης για Λογαριασμό Τρίτων", "total": "10,00"},
    ]
    out = _node(fns + "\nconst R=" + json.dumps(rows, ensure_ascii=False) + ";"
                "console.log(JSON.stringify(R.map(i=>[docAmt(i,'total'),docSigned(i,'total')])));")
    assert json.loads(out) == [
        ["-6.416,26", -6416.26], ["-100,00", -100], ["-50,00", -50],
        ["6.416,26", 6416.26], ["2.108,00", 2108], ["10,00", 10],
    ]


def test_rows_render_signed_amounts(page: str):
    fn = _block(page, "function renderDocs(){")
    assert "docAmt(i,'net_value')" in fn
    assert "docAmt(i,'vat_value')" in fn
    assert "docAmt(i,'total')" in fn
    # Το ενιαίο «€ σύνολο» στη γραμμή πλήθους αντικαταστάθηκε από σύνολα ανά στήλη.
    assert "€ σύνολο" not in fn


def test_totals_row_per_column(page: str):
    assert 'id="docSumNet"' in page and 'id="docSumVat"' in page and 'id="docSumTotal"' in page
    foot = page[page.index('<tfoot><tr class="doc-totals">'):]
    foot = foot[: foot.index("</tfoot>")]
    head = page[page.index('<table id="docTable"'):]
    head = head[: head.index("</thead>")]
    # Ίδιος αριθμός κελιών με την κεφαλίδα — αλλιώς τα ποσά πέφτουν σε λάθος στήλη.
    assert foot.count("<td") == len(re.findall(r"<th[\s>]", head))
    totals = _block(page, "function docTotals(){")
    # ΜΟΝΟ ό,τι φαίνεται: αναζήτηση και φίλτρα στηλών μετράνε.
    assert "tr.style.display==='none'" in totals
    assert "docSigned(i,'total')" in totals


def test_totals_follow_filters_order_and_hidden_columns(page: str):
    assert "if(tableId==='docTable')docTotals();" in _block(page, "function applyColumnFilters(tableId){")
    assert "table.tFoot" in _block(page, "function applyGridLayout(tableId){")
    assert "table.tFoot" in _block(page, "function applyHidden(tableId){")


# ===========================================================================
# 2. Επωνυμίες χωρίς ΑΦΜ + μνήμη
# ===========================================================================
@pytest.mark.skipif(not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe")
def test_counterpart_name_is_parsed_from_the_view_page(tmp_path: Path, etim: str):
    fn = _block(etim, "function invoiceCounterpartName(")
    html_named = ('<label for="counterpartData">x</label>'
                  '<input type="text" class="form-control mt-0 inputData" placeholder="" '
                  'id="counterpartData" name="counterpartData" '
                  'value="&#x394;&#x399;&#x391;&#x3A7;&#x395;&#x399;&#x3A1;&#x399;&#x3A3;&#x397; &amp; &#x3A3;&#x399;&#x391; ">')
    html_empty = '<input id="counterpartData" name="counterpartData" value="">'
    script = tmp_path / "t.php"
    script.write_text(
        "<?php\nconst BASE_URL='x';\n$PAGES=json_decode(base64_decode('"
        + base64.b64encode(json.dumps(
            {"a": html_named, "b": html_empty, "c": "<html>login</html>"}).encode()).decode()
        + "'),true);\n"
        "function curlGet($ch,$url){global $PAGES;return $PAGES[substr($url,-1)]??'';}\n"
        + fn.replace("\\CurlHandle $ch", "$ch") + "\n"
        "echo json_encode([invoiceCounterpartName(null,'a'),invoiceCounterpartName(null,'b'),"
        "invoiceCounterpartName(null,'c'),invoiceCounterpartName(null,'')],JSON_UNESCAPED_UNICODE);\n",
        encoding="utf-8",
    )
    out = subprocess.run([str(PHP_EXE), str(script)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    # Όνομα · όντως κενό (δεν ξαναρωτάμε) · άγνωστη απάντηση (ξαναδοκιμάζεται) · χωρίς κλειδί.
    assert json.loads(out.stdout) == ["ΔΙΑΧΕΙΡΙΣΗ & ΣΙΑ", "", None, None]


def test_names_are_resolved_once_and_remembered(etim: str):
    fn = _block(etim, "function enrichInvoiceNames(")
    # Πρώτα η μόνιμη μνήμη, μετά το πελατολόγιο, και μόνο τότε η ΑΑΔΕ.
    assert fn.index("isset($known[$mk])") < fn.index("isset($custNames[$vat])") < fn.index("invoiceCounterpartName(")
    assert "cache_set(COMPANY_VAT, 'docnames', $known)" in fn
    # Αποτυχία δικτύου ΔΕΝ γράφεται ως «χωρίς όνομα».
    assert "if ($name === null) { $pending++; continue; }" in fn
    assert "microtime(true) - $t0 > $budget" in fn


def test_view_keys_never_reach_the_browser(etim: str):
    handler = _block(etim, "if ($searchInvoicesFlag) {")
    assert handler.index("stripViewKeys($result);") < handler.index("jsonResponse(")
    assert "unset($result['invoices'][$i]['view_k'])" in _block(etim, "function stripViewKeys(")


def test_issuance_seeds_the_name_without_asking_aade(etim: str):
    fn = _block(etim, "function notifyIssue(")
    assert "rememberInvoiceName($accountVat, $data['mark'], $data['buyer_name']);" in fn


def test_documents_open_from_cache_then_refresh(page: str, etim: str):
    load = _block(page, "async function loadDocs(){")
    assert load.index("api({cached:'docs'})") < load.index("search_invoices:1")
    # Παλιά απάντηση δεν σκεπάζει νεότερη (άλλαξε διάστημα στο μεταξύ).
    assert "seq!==DOCS_SEQ" in load
    assert "docFillNames(seq,from,to)" in load
    handler = _block(etim, "if ($searchInvoicesFlag) {")
    assert "cache_set(COMPANY_VAT, 'docs'" in handler
    # Μόνο η σκέτη αναζήτηση διαστήματος γράφει τη μνήμη.
    assert "$mark === '' && $seriesFilter === ''" in handler


def test_customer_name_prefers_server_name(page: str):
    fn = _block(page, "function docWho(i){")
    assert fn.index("counterpart_name") < fn.index("ALL_CUSTOMERS")


# ===========================================================================
# 3. Κείμενα βοηθού + φωνή σε κινητό
# ===========================================================================
def test_assistant_wording(page: str):
    assert "2 τεμ " not in page and "τεμ ΚΩΔ" not in page
    assert "2 τεμάχια κωδικός 10 ευρώ" in page
    assert "πατήσεις εσύ το κόκκινο" not in page
    assert "όταν επιλέξεις «Οριστική Έκδοση»" in page
    for rel in ("assistant.py", "help.py", "pages/assistant_panel.py"):
        src = _read(REPO / "desktop" / "src" / "timologio" / "etimologio" / rel)
        assert "πατήσεις εσύ" not in src, rel


def test_mobile_speaks_without_the_windows_warning(page: str):
    fn = _block(page, "function cbSpeakBrowser(text,lang,retried){try{", "}catch(e){}}")
    assert fn.index("if(cbIsMobile()){cbSpeakLang(text,lang);return;}") < fn.index("CB_VOICE_WARNED=true")
    # Η οδηγία των Windows μόνο σε Windows.
    assert "(Windows:" not in fn
    how = _block(page, "function cbVoiceHowTo(){")
    assert "/Windows/i.test(ua)" in how
    mob = _block(page, "function cbIsMobile(){")
    out = _node(mob + """
const cases={
 'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36':[0,true],
 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148':[0,true],
 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15':[5,true],
 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15 ':[0,false],
 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36':[0,false],
};
const bad=[];
for(const [ua,[tp,want]] of Object.entries(cases)){
  Object.defineProperty(globalThis,'navigator',{value:{userAgent:ua,maxTouchPoints:tp},configurable:true,writable:true});
  if(cbIsMobile()!==want)bad.push(ua);
}
console.log(JSON.stringify(bad));""")
    assert json.loads(out) == []
    speak = _block(page, "function cbSpeak(t,retried){")
    assert "if(cbIsMobile()&&window.speechSynthesis){cbSpeakLang(text,lang);return;}" in speak


# ===========================================================================
# 4. Κέλυφος: λειτουργία server
# ===========================================================================
@pytest.fixture(scope="module")
def shell() -> str:
    return _read(SHELL_PY)


def test_server_pages_stay_inside_the_window():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QUrl

    from timologio.etimologio.webshell import EtimologioWebShell

    class Fake:
        _base = "https://etimologiopro.scanmydata.gr"

    ours = lambda u: EtimologioWebShell.is_ours(Fake(), QUrl(u))  # noqa: E731
    assert ours("https://etimologiopro.scanmydata.gr/app.php")
    assert ours("https://ETIMOLOGIOPRO.scanmydata.gr/authview.php?x=1")
    assert ours("http://127.0.0.1:8123/app.php")
    assert not ours("https://mydata.aade.gr/timologio")
    assert not ours("http://etimologiopro.scanmydata.gr/app.php")  # άλλο σχήμα
    assert not ours("https://etimologiopro.scanmydata.gr.evil.example/")
    Fake._base = ""
    assert not ours("https://etimologiopro.scanmydata.gr/app.php")


def test_navigation_uses_is_ours(shell: str):
    page_cls = shell[shell.index("class _Page(QWebEnginePage):"):shell.index("class EtimologioWebShell(")]
    assert page_cls.count("self._shell.is_ours(url)") == 2
    assert "not _is_local(url)" not in page_cls


def test_back_to_local_button_exists(shell: str):
    assert 'self._go_local = QPushButton("💻 Τοπικά δεδομένα")' in shell
    assert "self._go_local.clicked.connect(self._back_to_local)" in shell
    init = shell[shell.index("def __init__(self, data_dir: Path"):shell.index("# --- η γέφυρα σελίδας")]
    assert "self._go_local =" in init
    back = shell[shell.index("def _back_to_local(self)"):shell.index("def _set_status(")]
    assert "self._loaded_ok = False" in back


def test_desktop_token_stays_on_loopback(shell: str):
    fn = shell[shell.index("def _app_url("):shell.index("def _load_finished(")]
    assert fn.index('if self._service.mode() == "thin":') < fn.index("desktop_token=")
