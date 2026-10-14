"""Τέσσερα σημεία που έτριβαν: ημερομηνίες, κλειδωμένα κουτάκια, αποεπιλογή, λίστα εκκρεμών.

* **Ημερομηνίες.** Το QDateEdit γράφει «ανά τμήμα»: πληκτρολογώντας 12/10/2026
  έβγαινε «12/10//2026», και επειδή αυτό δεν διαβαζόταν **έμενε η παλιά
  ημερομηνία** — χωρίς κανένα μήνυμα. Τώρα κρατάμε εμείς ό,τι γράφεται, οι
  κάθετοι μπαίνουν μόνες τους, και δεκτά είναι «12/10/26», «1/2/26»,
  «12102026», «3.4.26», «1-1-2025», ακόμη και «12/10» (τρέχον έτος).

* **Κλειδωμένα κουτάκια.** Όσο έτρεχε λήψη, τα πεδία κλείδωναν σωστά — αλλά το
  ✓ ζωγραφιζόταν σκούρο πάνω σε σκούρο και δεν φαινόταν τι είχε επιλέξει ο
  χρήστης.

* **«Αποεπιλογή όλων»** άφηνε τον ενεργό πελάτη φωτισμένο, και η Λήψη συνέχιζε
  να λέει «1 επιλεγμένος».

* **Η λίστα εκκρεμών** ήταν κείμενο σε γραμματοσειρά μηχανής γραφής, κομμένο
  στους οκτώ πρώτους πελάτες.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from timologio.gui.widgets import (  # noqa: E402
    GrDateEdit,
    parse_typed_date,
    type_date,
)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "desktop" / "src" / "timologio"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ===========================================================================
# 1. Πληκτρολόγηση ημερομηνίας
# ===========================================================================
def test_slashes_appear_on_their_own():
    buffer = ""
    for char in "12102026":
        buffer = type_date(buffer, char)
    assert buffer == "12/10/2026"


def test_typed_separators_are_respected_and_never_doubled():
    buffer = ""
    for char in "1/2/26":
        buffer = type_date(buffer, char)
    assert buffer == "1/2/26"
    assert type_date("12/", "/") == "12/"          # δεύτερη κάθετος: αγνοείται
    assert type_date("", "/") == ""                # ούτε κάθετος στην αρχή
    assert type_date("12/10/2026", "9") == "12/10/2026"   # το έτος γέμισε
    assert type_date("12/10/2026", "/") == "12/10/2026"   # ούτε τέταρτο μέρος
    assert type_date("1", "α") == "1"              # γράμματα δεν περνούν


def test_partial_and_short_forms_are_understood():
    today = QDate(2026, 10, 12)
    assert parse_typed_date("12/10/26") == QDate(2026, 10, 12)
    assert parse_typed_date("1/2/26") == QDate(2026, 2, 1)
    assert parse_typed_date("12102026") == QDate(2026, 10, 12)
    assert parse_typed_date("121026") == QDate(2026, 10, 12)
    assert parse_typed_date("3.4.26") == QDate(2026, 4, 3)
    assert parse_typed_date("1-1-2025") == QDate(2025, 1, 1)
    assert parse_typed_date("12/10", today) == QDate(2026, 10, 12)
    # Ανύπαρκτη ημερομηνία ΔΕΝ «διορθώνεται» στα κρυφά: το πεδίο κρατά ό,τι
    # είχε και ο χρήστης το βλέπει (απόφαση της 0.4.17, δες test_dates_*).
    assert parse_typed_date("31/02/2026") is None
    assert parse_typed_date("") is None
    assert parse_typed_date("αύριο") is None


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("12/10/2026", "12/10/2026"),
        ("12/10/26", "12/10/2026"),
        ("1/2/26", "01/02/2026"),
        ("12102026", "12/10/2026"),
        ("1-1-2025", "01/01/2025"),
    ],
)
def test_the_field_keeps_what_was_typed(app, keys, expected):
    host = QWidget()
    layout = QVBoxLayout(host)
    field, other = GrDateEdit(), GrDateEdit()
    layout.addWidget(field)
    layout.addWidget(other)
    host.show()
    field.setFocus()
    try:
        for char in keys:
            QTest.keyClicks(field, char)
        # Ό,τι βλέπει ο χρήστης ΕΙΝΑΙ ό,τι πληκτρολόγησε — με τις αυτόματες
        # καθέτους και τους διαχωριστές του σε κάθετο, όχι η εκδοχή του Qt.
        typed = keys.replace("-", "/").replace(".", "/")
        assert field.lineEdit().text() in (typed, expected)
        field.commit_typed()
        assert field.gr() == expected
    finally:
        host.close()


def test_the_widget_does_not_fight_qt_anymore():
    src = (SRC / "gui" / "widgets.py").read_text(encoding="utf-8")
    show = src[src.index("def _show_typed"):src.index("def keyPressEvent")]
    assert "line.blockSignals(True)" in show and "line.blockSignals(False)" in show
    assert "self._typed = \"\"" in src
    commit = src[src.index("def commit_typed"):src.index("def focusOutEvent")]
    assert "parse_typed_date(self._typed or self.lineEdit().text())" in commit


# ===========================================================================
# 2. Κλειδωμένα αλλά ορατά
# ===========================================================================
@pytest.mark.parametrize("name", ["dark", "light"])
def test_a_locked_checkbox_still_shows_its_tick(name):
    from timologio.gui import theme

    palette = theme.DARK if name == "dark" else theme.LIGHT
    qss = theme.build(palette)
    for widget in ("QCheckBox", "QTableWidget", "QListWidget"):
        block = qss[qss.index(f"{widget}::indicator:checked:disabled"):]
        block = block[:block.index("}") + 1]
        assert palette.accent_deep in block, widget
        assert "image: url(" in block, widget
    assert f"QCheckBox:disabled {{ color: {palette.muted}; }}" in qss


# ===========================================================================
# 3. Αποεπιλογή όλων
# ===========================================================================
def test_deselect_all_also_releases_the_active_client(app, tmp_path: Path, monkeypatch):
    from timologio.crypto import Crypto
    from timologio.db import init_db
    from timologio.models import Client
    from timologio.repo import upsert_client

    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    conn = init_db(tmp_path / "timologio.db")
    for vat, label in (("123456783", "ΑΛΦΑ ΑΕ"), ("998877665", "ΒΗΤΑ ΟΕ")):
        upsert_client(conn, Client(vat=vat, label=label, mydata_user="u",
                                   mydata_key="k" * 32), Crypto(tmp_path / ".enckey"))
    conn.commit()
    conn.close()

    from timologio.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window._check_shown(True)
        window.table.selectRow(0)
        window._on_selection(animate=False)
        assert window._pinned_vat
        assert "Ενεργός πελάτης" in window.active_client.text()

        window._check_shown(False)
        assert not window._checked
        assert window._pinned_vat is None
        assert not window.table.selectedItems()
        assert window.active_client.text() == "Κανένας πελάτης επιλεγμένος"
    finally:
        window.close()


# ===========================================================================
# 4. Η λίστα των εκκρεμών
# ===========================================================================
def test_the_backlog_dialog_lists_everyone_in_a_real_table(app, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    from timologio.gui.main_window import MainWindow

    window = MainWindow()
    rows = [{"vat": f"80000000{i}", "label": f"ΠΕΛΑΤΗΣ {i}", "n": 100 - i}
            for i in range(1, 13)]
    shown: dict[str, object] = {}

    def grab():
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                table = widget.findChild(QTableWidget)
                shown["rows"] = table.rowCount() if table else 0
                shown["first"] = table.item(0, 0).text() if table else ""
                shown["last"] = table.item(11, 0).text() if table else ""
                shown["scrolls"] = bool(
                    table and table.verticalScrollBarPolicy()
                    != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )
                widget.reject()

    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, grab)
    try:
        assert window._ask_backlog(rows, 2276) is None      # «Άκυρο» = δεν ξεκινά
        assert shown["rows"] == 12                          # ΟΛΟΙ, όχι οι οκτώ πρώτοι
        assert shown["first"] == "ΠΕΛΑΤΗΣ 1" and shown["last"] == "ΠΕΛΑΤΗΣ 12"
        assert shown["scrolls"]
    finally:
        window.close()


def test_no_typewriter_font_left_in_the_dialog():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    fn = src[src.index("def _ask_backlog"):src.index("def on_cancel")]
    code = fn[fn.index('"""', fn.index('"""') + 3) + 3:]    # χωρίς το docstring
    assert "<pre>" not in code and "και άλλοι" not in code
    assert "QTableWidget(len(rows), 2)" in fn
    assert "Λήψη τώρα" in fn
