"""Λειτουργία server χωρίς διπλό μενού, TARIC, και επεξεργασία ειδών που αποθηκεύεται.

* **Διπλό μενού σε λειτουργία server.** Η σελίδα κρύβει το δικό της μενού όταν
  ξέρει ότι είναι μέσα στην εφαρμογή — και το μάθαινε ΜΟΝΟ από το
  `desktop_token`, που (σωστά) δεν στέλνεται πια στον server του internet.

* **Η επεξεργασία είδους δεν αποθηκεύτηκε ποτέ.** Το `updateProduct` έστελνε στο
  `/product/create` και η ΑΑΔΕ απαντούσε «Ο κωδικός είδους υπάρχει». Βρέθηκε
  στον ζωντανό έλεγχο του TARIC.

* **TARIC** για αγαθά: η ΑΑΔΕ δέχεται ΜΟΝΟ 10 ψηφία (επαληθεύτηκε ζωντανά).

* **Ο βοηθός δεν διάβαζε τον κωδικό είδους** που έγραφε το ίδιο του το παράδειγμα.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
SHELL_PY = REPO / "desktop" / "src" / "timologio" / "etimologio" / "webshell.py"


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


@pytest.fixture(scope="module")
def page() -> str:
    return _read(APP_PHP)


@pytest.fixture(scope="module")
def etim() -> str:
    return _read(ETIM_PHP)


@pytest.fixture(scope="module")
def shell() -> str:
    return _read(SHELL_PY)


# ===========================================================================
# 1. Λειτουργία server: ένα μενού, μπάρα που μαζεύεται
# ===========================================================================
def test_shell_flag_marks_the_page_embedded(page: str):
    head = page[: page.index("$__resetToken")]
    assert "(string)($_GET['shell'] ?? '') === '1'" in head
    # Το cookie γράφεται και με το `shell=1`, ώστε να επιβιώνει του login.
    assert head.index("=== '1';") < head.index("setcookie('etim_shell'")


def test_thin_url_carries_shell_flag_but_no_token(shell: str):
    fn = shell[shell.index("def _app_url("):shell.index("def _load_finished(")]
    thin = fn[fn.index('if self._service.mode() == "thin":'):fn.index("token = quote(")]
    assert 'app.php?shell=1' in thin
    assert "desktop_token" not in thin.replace("# ", "")


def test_old_servers_are_covered_from_the_shell(shell: str):
    fn = shell[shell.index("def _apply_prefs("):shell.index("# --- συμβατότητα")]
    assert "classList.add('embedded')" in fn


def test_thin_bar_link_and_collapse(shell: str):
    assert "THIN_BAR_FULL_MS = 10_000" in shell
    assert "setOpenExternalLinks(True)" in shell
    sync = shell[shell.index("def _sync_thin_bar("):shell.index("def _thin_compact(")]
    assert "self._server_link()" in sync and "self._thin_timer.start()" in sync
    compact = shell[shell.index("def _thin_compact("):shell.index("def _restart(")]
    assert "self._server_link()" in compact
    assert "setToolTip(" in compact


def test_server_link_is_escaped():
    pytest.importorskip("PySide6")
    from timologio.etimologio.webshell import EtimologioWebShell

    class Svc:
        def server_url(self):
            return 'https://x.example/"><script>'

    class Fake:
        _service = Svc()

    html = EtimologioWebShell._server_link(Fake())
    assert "<script>" not in html
    assert 'href="https://x.example/&quot;&gt;&lt;script&gt;"' in html


# ===========================================================================
# 2. Είδη: TARIC και ενημέρωση που αποθηκεύεται
# ===========================================================================
def test_update_product_uses_the_update_endpoint(etim: str):
    fn = _block(etim, "function updateProduct(")
    assert "BASE_URL . '/Product/update'" in fn
    assert "'/product/create'" not in fn
    assert "'prd' => $prd" in fn
    # Αποτυχία = μήνυμα της ΑΑΔΕ ή μη-200, όχι σιωπηλή «επιτυχία».
    assert "$code === 200 && !$failed" in fn


def test_create_product_still_uses_create(etim: str):
    assert "BASE_URL . '/product/create'" in _block(etim, "function createProduct(")


def test_product_list_reads_taric(etim: str):
    fn = _block(etim, "function listProducts(")
    assert "'taric'            => $cols[7] ?? ''" in fn


def test_taric_field_only_for_goods_and_ten_digits(page: str):
    assert 'id="pdTaric"' in page and 'maxlength="10"' in page
    assert "$('#pdType').value==='1'?'':'none'" in _js_block(page, "function pdTypeChange(){")
    save = _js_block(page, "async function saveProduct(){")
    assert "taric_code:taric" in save
    assert "taric.length!==10" in save
    assert "const taric=isService?''" in save
    edit = _js_block(page, "function editProduct(code,desc){")
    # Αλλιώς η επεξεργασία θα έσβηνε τον TARIC.
    assert "$('#pdTaric').value=String(p.taric||'')" in edit
    assert "'pdTaric'" in _js_block(page, "function openProductModal(")


# ===========================================================================
# 3. Βοηθός: κωδικός ή περιγραφή είδους
# ===========================================================================
def test_assistant_example_wording(page: str):
    assert page.count("2 τεμάχια κωδικός είδους 1 αξία 10 ευρώ") == 3
    assert "2 τεμάχια κωδικός 10 ευρώ" not in page


def test_assistant_parses_code_or_description(page: str):
    code = _js_block(page, "function cbNum(") + "\n" + _js_block(page, "function cbParseIssue(t){")
    cases = [
        "έκδοση τιμολογίου στον 802012659 για 2 τεμάχια κωδικός είδους 1 αξία 10 ευρώ",
        "έκδοση τιμολογίου στον 802012659 για 2 τεμάχια, κωδικός είδους 10, αξία 10 ευρώ",
        "έκδοση τιμολογίου στον 802012659 για 3 τεμ κωδ. Α-12 10 ευρώ",
        "έκδοση τιμολογίου στον 802012659 για 2 τεμάχια περιγραφή είδους ελαιοχρωματισμός εξωτερικής και αξία 10 ευρώ",
        "έκδοση τιμολογίου στον 802012659 καθαρή αξία 100 με παρακράτηση 20%",
    ]
    out = subprocess.run(
        ["node", "-e", code + "\nconst C=" + json.dumps(cases, ensure_ascii=False) + ";"
         "console.log(JSON.stringify(C.map(t=>{const o=cbParseIssue(t);return [o.qty,o.code,o.item,o.net];})));"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        [2, "1", "", 10],
        [2, "10", "", 10],
        [3, "Α-12", "", 10],
        [2, "", "ελαιοχρωματισμός εξωτερικής", 10],
        [1, "", "", 100],
    ]


def test_unknown_code_is_reported_not_guessed(page: str):
    fn = _js_block(page, "async function cbResolveProduct(o){")
    assert fn.index("if(code&&!PRODMAP[code])") < fn.index("cbFindProdByDesc(o.item)")
    assert "Δεν βρήκα είδος με κωδικό" in fn
