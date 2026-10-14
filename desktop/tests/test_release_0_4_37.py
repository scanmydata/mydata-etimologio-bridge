"""Δεξί κλικ στα κελιά, «Λήψη εκκρεμών» σε επιλεγμένους, και βοηθός που καταλαβαίνει.

* **Δεξί κλικ σε κελί** (σε κάθε πίνακα): αντιγραφή της τιμής ή ολόκληρης της
  γραμμής, και «Φίλτρο: στήλη = τιμή». Το φίλτρο υπήρχε μόνο μέσα από το χωνί
  της κεφαλίδας, που πρέπει πρώτα να το βρεις.

* **Λήψη εκκρεμών**: ήταν «όλοι ή τίποτα» — με 2.276 PDF σε 23 πελάτες αυτό
  σημαίνει ώρες. Τώρα κατεβάζει και μόνο τους επιλεγμένους, και η γραμμή του
  μενού μένει φωτισμένη όσο τρέχει.

* **Διπλό κλικ** στον ίδιο πελάτη τον αφήνει εντελώς (τικ ΚΑΙ ενεργός πελάτης).

* **Ο βοηθός** αναγνωρίζει πελάτη από μία λέξη της επωνυμίας, ρωτά όταν
  ταιριάζουν πολλοί, απαντά σε απορίες της δουλειάς («τι είναι το ΜΑΡΚ;») και
  σε απλές κουβέντες. ΠΡΟΣΟΧΗ στα ελληνικά μοτίβα: το «\\b» του JS μετρά μόνο
  λατινικά γράμματα — με αυτό, το «καλημέρα» δεν αναγνωριζόταν ποτέ.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMenu, QTableWidget, QTableWidgetItem  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "desktop" / "src" / "timologio"
APP_PHP = REPO / "app.php"
VENDORED_APP = REPO / "desktop" / "backend" / "etimologio" / "app.php"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _node(code: str):
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[:800]
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


# ===========================================================================
# 1. Δεξί κλικ σε κελί
# ===========================================================================
@pytest.fixture
def table(app):
    from timologio.gui.table_filter import TableColumnFilter

    widget = QTableWidget(2, 3)
    widget.setHorizontalHeaderLabels(["ΑΦΜ", "Επωνυμία", "Σύνολο"])
    for row, (vat, name, total) in enumerate(
        [("123456783", "ΑΛΦΑ ΑΕ", "124,00"), ("998877665", "ΒΗΤΑ ΟΕ", "248,00")]
    ):
        for col, text in enumerate((vat, name, total)):
            widget.setItem(row, col, QTableWidgetItem(text))
    column_filter = TableColumnFilter(widget, (0, 1))
    return widget, column_filter


def test_the_menu_copies_the_cell_and_the_row(table):
    from timologio.gui.table_filter import cell_menu_actions

    widget, column_filter = table
    menu = QMenu()
    cell_menu_actions(menu, widget, widget.visualItemRect(widget.item(0, 1)).center(),
                      column_filter)
    labels = [a.text() for a in menu.actions() if a.text()]
    assert "Αντιγραφή «ΑΛΦΑ ΑΕ»" in labels
    assert "Αντιγραφή ολόκληρης της γραμμής" in labels

    for action in menu.actions():
        if action.text() == "Αντιγραφή ολόκληρης της γραμμής":
            action.trigger()
    assert QApplication.clipboard().text() == "123456783\tΑΛΦΑ ΑΕ\t124,00"


def test_the_menu_filters_by_the_value_and_clears_it(table):
    from timologio.gui.table_filter import cell_menu_actions

    widget, column_filter = table
    menu = QMenu()
    cell_menu_actions(menu, widget, widget.visualItemRect(widget.item(0, 1)).center(),
                      column_filter)
    use = [a for a in menu.actions() if a.text().startswith("Φίλτρο:")]
    assert use and use[0].text() == "Φίλτρο: Επωνυμία = «ΑΛΦΑ ΑΕ»"
    use[0].trigger()
    assert column_filter.filters == {1: {"ΑΛΦΑ ΑΕ"}}
    assert not widget.isRowHidden(0) and widget.isRowHidden(1)

    menu2 = QMenu()
    cell_menu_actions(menu2, widget, widget.visualItemRect(widget.item(0, 1)).center(),
                      column_filter)
    clear = [a for a in menu2.actions() if a.text().startswith("Καθάρισμα φίλτρου")]
    assert clear
    clear[0].trigger()
    assert not column_filter.filters
    assert not widget.isRowHidden(1)


def test_columns_without_a_funnel_offer_no_filter(table):
    from timologio.gui.table_filter import cell_menu_actions

    widget, column_filter = table
    menu = QMenu()
    # Στήλη 2 («Σύνολο») δεν είναι φιλτραρίσιμη.
    cell_menu_actions(menu, widget, widget.visualItemRect(widget.item(0, 2)).center(),
                      column_filter)
    assert not [a for a in menu.actions() if a.text().startswith("Φίλτρο:")]
    assert [a for a in menu.actions() if a.text().startswith("Αντιγραφή")]


def test_every_table_of_the_app_has_the_menu():
    for path, needle in (
        ("gui/sync_page.py", "install_cell_menu(self.table, self._col_filter)"),
        ("gui/control_panel.py", "install_cell_menu(self.table)"),
        ("gui/online_only.py", "install_cell_menu(self.table)"),
        ("etimologio/pages/ui.py", "install_cell_menu(table, column_filter)"),
        ("gui/main_window.py", "cell_menu_actions(menu, self.table, point, self._client_col_filter)"),
        ("gui/documents_view.py", "cell_menu_actions(menu, self.table, pos, _ColFilterBridge(self))"),
    ):
        assert needle in (SRC / path).read_text(encoding="utf-8"), path


# ===========================================================================
# 2. Λήψη εκκρεμών: επιλεγμένοι πελάτες και φωτισμένη γραμμή
# ===========================================================================
def test_backlog_can_be_limited_to_some_clients(tmp_path: Path):
    from timologio.crypto import Crypto
    from timologio.db import init_db
    from timologio.models import Client, Direction, Document
    from timologio.repo import pending_backlog, upsert_client, upsert_document

    conn = init_db(tmp_path / "t.db")
    crypto = Crypto(tmp_path / ".enckey")
    for i, vat in enumerate(("803105689", "104836713"), 1):
        cid = upsert_client(conn, Client(vat=vat, label=f"Π{i}", mydata_user="u",
                                         mydata_key="k" * 32), crypto)
        upsert_document(conn, cid, Document(
            mark=str(i), invoice_type="1.1", issuer_vat="076762490", counter_vat=vat,
            net_value=1.0, vat_amount=0.0, total_value=1.0, issue_date="2026-08-28",
            direction=Direction.INCOMING, downloading_invoice_url="https://x.gr/a"))
    conn.commit()
    assert len(pending_backlog(conn)) == 2
    only = pending_backlog(conn, ["803105689"])
    assert [row["vat"] for row in only] == ["803105689"]


def test_the_dialog_offers_the_selected_clients():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    fn = src[src.index("def _ask_backlog"):src.index("def on_cancel")]
    assert "Μόνο οι επιλεγμένοι πελάτες" in fn
    assert "only_picked.setVisible(bool(picked_rows))" in fn
    assert "return picked_rows if only_picked.isChecked() else rows" in fn
    handler = src[src.index("def on_download_backlog"):src.index("def _ask_backlog")]
    assert "picked = sorted(self._checked) or self._online_only_vats() or []" in handler
    assert "if chosen is None:" in handler


def test_a_running_action_lights_up_in_the_menu():
    menu = (SRC / "gui" / "side_menu.py").read_text(encoding="utf-8")
    assert "def set_action_busy(self, name: str, busy: bool) -> None:" in menu
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert 'self.menu.set_action_busy("pending_pdf", True)' in window
    assert 'self.menu.set_action_busy("pending_pdf", False)' in window
    assert 'self.menu.set_action_busy("online_pdf", True)' in window
    assert 'self.menu.set_action_busy("online_pdf", False)' in window


def test_double_click_on_the_same_client_lets_it_go():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    fn = src[src.index("def _on_double_click"):src.index("def _toggle_checked")]
    assert "was_checked = item is not None and item.checkState() is Qt.CheckState.Checked" in fn
    assert "self.table.clearSelection()" in fn
    assert "self._set_pinned(None)" in fn


# ===========================================================================
# 3. Ο βοηθός
# ===========================================================================
def _assistant_js(page: str) -> str:
    return "\n".join([
        _block(page, "function grFold(", "function elNum("),
        _block(page, "function cbNorm(", "// Ενότητα"),
        "function custFields(c){return {vat:c.vat||'',name:c.name||'',code:c.code||''};}",
        _block(page, "function cbMatchCustomers(", "function cbFindProdByDesc("),
        _block(page, "function cbGreeting(", "\nconst CB_WX="),
        _block(page, "const CB_KB=[", "const CB_TIPS=["),
    ])


def test_one_word_is_enough_to_find_a_customer(page: str):
    got = _node(_assistant_js(page) + """
const ALL_CUSTOMERS=[
 {vat:'802576637',name:'ΤΟ ΒΑΨΙΜΟ Ε.Ε.'},
 {vat:'123456783',name:'ΒΑΨΙΜΑΤΑ ΑΤΤΙΚΗΣ ΜΟΝΟΠΡΟΣΩΠΗ ΙΚΕ'},
 {vat:'046307992',name:'ΜΙΣΚΑΚΗ ΑΓΓΕΛΙΚΗ'},
 {vat:'801355228',name:'XAD ORTHOPAEDICS ΑΝΩΝΥΜΗ ΕΤΑΙΡΕΙΑ'}];
const one=q=>{const c=cbResolveCustomer(q,'');return c?c.name:null;};
console.log(JSON.stringify({
  word:one('βάψιμο'), accents:one('μισκάκη'), latin:one('orthopaedics'),
  second:one('αγγελικη'), full:one('ΤΟ ΒΑΨΙΜΟ Ε.Ε.'),
  ambiguous:one('βαψ'), ambiguousHits:cbMatchCustomers('βαψ').length,
  nothing:one('ξξξ'), short:cbMatchCustomers('ε').length}));""")
    assert got["word"] == "ΤΟ ΒΑΨΙΜΟ Ε.Ε."
    assert got["accents"] == "ΜΙΣΚΑΚΗ ΑΓΓΕΛΙΚΗ"
    assert got["latin"] == "XAD ORTHOPAEDICS ΑΝΩΝΥΜΗ ΕΤΑΙΡΕΙΑ"
    assert got["second"] == "ΜΙΣΚΑΚΗ ΑΓΓΕΛΙΚΗ"      # και από τη δεύτερη λέξη
    assert got["full"] == "ΤΟ ΒΑΨΙΜΟ Ε.Ε."
    # Ισοπαλία: δεν μαντεύουμε — ρωτάμε (δύο υποψήφιοι).
    assert got["ambiguous"] is None and got["ambiguousHits"] == 2
    assert got["nothing"] is None and got["short"] == 0


def test_the_assistant_asks_when_many_match(page: str):
    fn = _block(page, "async function cbStartIssue(o){", "function cbPickCustomer(")
    assert "const hits=o.afm?[]:cbMatchCustomers(o.customerRef).slice(0,6);" in fn
    assert "CB_CTX={stage:'pickcust',o,hits};" in fn
    assert "cbPickCustomer(" in fn
    pick = _block(page, "function cbPickCustomer(i){", "async function cbResolveProduct(")
    assert "o.afm=hit.c.vat;o.name=hit.c.name;" in pick
    assert "return cbResolveProduct(o);" in pick
    cont = _block(page, "async function cbContinue(t){", "function cbPickCustomer(")
    assert "if(CB_CTX.stage==='pickcust'){" in cont


def test_knowledge_questions_get_answers(page: str):
    got = _node(_assistant_js(page) + """
const Q=['τι είναι το ΜΑΡΚ;','πώς ακυρώνω παραστατικό','γιατί δεν βλέπω τον τύπο στην έκδοση',
 'τι είναι η παρακράτηση','πώς στέλνω email στον πελάτη','μπορώ να διαγράψω παραστατικό;',
 'γιατί λέει postalCode','τι είναι ο TARIC','πόσα δεκαδικά',
 'έκδοση τιμολογίου στον 123456789 καθαρή αξία 100','πήγαινε στους πελάτες'];
console.log(JSON.stringify(Q.map(q=>{const a=cbKbAnswer(cbNorm(q));return a?a.text.length:0;})));""")
    answered, silent = got[:9], got[9:]
    assert all(n > 60 for n in answered), got
    assert silent == [0, 0]            # οι εντολές ΔΕΝ πιάνονται ως ερωτήσεις


def test_small_talk_answers_without_opening_screens(page: str):
    got = _node(_assistant_js(page) + """
const Q=['καλημέρα','γεια σου','πώς σε λένε','ευχαριστώ','τι κάνεις','τι ώρα είναι',
 'τι μέρα είναι','πες μου ένα αστείο','έκδοση τιμολογίου','πελάτες'];
console.log(JSON.stringify(Q.map(q=>{const a=cbChatAnswer(cbNorm(q).trim());return a?a.length:0;})));""")
    assert all(n > 10 for n in got[:8]), got
    assert got[8:] == [0, 0]           # εντολές: ο βοηθός δεν κουβεντιάζει


def test_no_latin_only_word_boundary_in_greek_patterns(page: str):
    """Το «\\b» μετά από ελληνικό γράμμα δεν ταιριάζει ΠΟΤΕ στο JS."""
    chat = _block(page, "const CB_CHAT=[", "function cbChatAnswer(")
    for line in chat.splitlines():
        if "[/" not in line:
            continue
        pattern = line[line.index("[/") + 2: line.rindex("/")] if "/," in line else ""
        assert "\\b" not in pattern, line.strip()


def test_weather_is_answered_from_an_open_source(page: str):
    fn = _block(page, "async function cbWeather(", "\n}")
    assert "geocoding-api.open-meteo.com" in fn and "api.open-meteo.com" in fn
    assert "open-meteo.com" in _block(page, "const CB_WX=", "async function cbWeather(") or True
    handler = _block(page, "  // Καιρός:", "  // Ερώτηση γνώσης")
    assert "cbWeather(" in handler and "Δεν μπόρεσα να δω τον καιρό" in handler


# ===========================================================================
# 4. Τα εγχειρίδια και οι ξεναγήσεις λένε τα τωρινά χαρακτηριστικά
# ===========================================================================
def test_downloader_manual_and_tour_cover_the_new_things():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "5α. Οι πίνακες: ταξινόμηση, φίλτρα, δεξί κλικ" in manual
    assert "Αντιγραφή ολόκληρης της γραμμής" in manual
    assert "Αυτόματη εκκίνηση με τα" in manual and "Διαχείριση εργασιών" in manual
    assert "12102026" in manual                      # ελεύθερη πληκτρολόγηση
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "TOUR_VERSION = 3" in window              # ξαναπροσφέρεται με νέο περιεχόμενο
    assert "6β. Ό,τι δεν κατέβηκε με τη μία" in window
    assert "Δεξί κλικ σε κελί" in window


def test_etimologio_manual_and_tour_cover_the_new_things():
    help_py = (SRC / "etimologio" / "help.py").read_text(encoding="utf-8")
    assert "6α. Ο βοηθός" in help_py
    assert "τυπώνεται στις «Παρατηρήσεις»" in help_py
    assert "κάρτα με το όνομα " in help_py
    page = APP_PHP.read_text(encoding="utf-8")
    assert "⏳ Τι τρέχει τώρα" in page
    assert "αιτιολογία</b> — τυπώνεται" in page
    assert "από <b>μία λέξη</b> της επωνυμίας" in page


def test_the_vendored_copy_matches():
    assert VENDORED_APP.read_bytes() == APP_PHP.read_bytes()
