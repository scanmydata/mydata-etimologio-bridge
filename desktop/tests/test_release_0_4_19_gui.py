"""Ο χρονοπρογραμματισμός, η αναζήτηση και τα κουτάκια που δεν φαίνονταν."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client  # noqa: E402
from timologio.repo import upsert_client  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


# --- ο χρονοπρογραμματισμός --------------------------------------------------
@pytest.fixture()
def schedule(app):
    from timologio.gui.schedule_page import SchedulePage

    page = SchedulePage()
    yield page
    page.deleteLater()


def test_the_group_is_called_customers(schedule) -> None:
    """«Ποιοι πελάτες» ήταν ερώτηση σε τίτλο ενότητας."""
    from PySide6.QtWidgets import QGroupBox

    titles = [box.title() for box in schedule.findChildren(QGroupBox)]
    assert "Πελάτες" in titles
    assert "Ποιοι πελάτες" not in titles


def test_each_row_reads_vat_then_name(schedule) -> None:
    schedule.set_clients([("031174383", "ΑΛΦΑ ΕΜΠΟΡΙΚΗ ΑΕ")])
    item = schedule.list.item(0)
    assert item.text() == "031174383 — ΑΛΦΑ ΕΜΠΟΡΙΚΗ ΑΕ"
    # Το ΑΦΜ μένει το κλειδί, ό,τι κι αν γράφει η γραμμή.
    assert item.data(Qt.ItemDataRole.UserRole) == "031174383"


def test_a_missing_name_is_not_faked_from_the_vat(schedule) -> None:
    """Έδειχνε «031174383 · 031174383»: το ΑΦΜ δύο φορές, σαν να ήταν επωνυμία."""
    schedule.set_clients([("031174383", "")])
    assert schedule.list.item(0).text() == "031174383"


def test_search_matches_both_halves(schedule) -> None:
    schedule.set_clients([("031174383", "ΑΛΦΑ ΑΕ"), ("998877665", "ΒΗΤΑ ΟΕ")])
    for needle, visible in (("αλφα", 1), ("9988", 1), ("ΟΕ", 1), ("ζζζ", 0)):
        schedule.search.setText(needle)
        shown = [i for i in range(schedule.list.count())
                 if not schedule.list.item(i).isHidden()]
        assert len(shown) == visible, needle


def test_names_reach_the_page_from_the_label_column(app, tmp_path, monkeypatch) -> None:
    """Η αιτία: ζητούσαμε στήλη `name`, ενώ η στήλη λέγεται `label`.

    Ο έλεγχος ήταν πάντα ψευδής, οπότε κάθε πελάτης έπεφτε στο fallback και η
    λίστα γέμιζε με ΑΦΜ. Δεν έσκαγε τίποτα — γι' αυτό επέζησε.
    """
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    conn = init_db(tmp_path / "timologio.db")
    upsert_client(
        conn,
        Client(vat="123456783", label="ΔΕΙΓΜΑ ΕΜΠΟΡΙΚΗ ΑΕ",
               mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"),
    )
    conn.commit()
    conn.close()

    from timologio.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window._refresh_schedule_clients()
        rows = [window.schedule_page.list.item(i).text()
                for i in range(window.schedule_page.list.count())]
        assert rows == ["123456783 — ΔΕΙΓΜΑ ΕΜΠΟΡΙΚΗ ΑΕ"]
    finally:
        window.close()


# --- τα κουτάκια που μόλις που φαίνονταν ------------------------------------
def test_list_checkboxes_are_styled_at_all(app) -> None:
    """Οι λίστες δεν είχαν ΚΑΝΕΝΑΝ κανόνα — έμεναν στο προεπιλεγμένο του Qt."""
    from timologio.gui.theme import DARK, build

    qss = build(DARK)
    for rule in ("QListWidget::indicator", "QListWidget::indicator:checked"):
        assert rule in qss, rule


def test_empty_checkboxes_stand_out_from_the_background(app) -> None:
    """Το άδειο κουτάκι είχε περίγραμμα στο χρώμα των γραμμών: αόρατο."""
    from timologio.gui.theme import DARK, build

    qss = build(DARK)
    for widget in ("QCheckBox", "QTableWidget", "QListWidget"):
        block = qss[qss.index(widget + "::indicator {"):]
        block = block[: block.index("}")]
        assert f"2px solid {DARK.muted}" in block, widget
        assert DARK.line not in block, widget


# --- η αναζήτηση σε όλες τις στήλες -----------------------------------------
def _seeded(tmp_path):
    conn = init_db(tmp_path / "timologio.db")
    crypto = Crypto(tmp_path / ".enckey")
    upsert_client(conn, Client(vat="123456783", label="ΑΛΦΑ ΑΕ",
                               mydata_user="u", mydata_key="k" * 32), crypto)
    upsert_client(conn, Client(vat="998877665", label="ΒΗΤΑ ΟΕ"), crypto)
    conn.commit()
    conn.close()


def test_client_search_covers_every_column(app, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    _seeded(tmp_path)
    from timologio.gui.main_window import MainWindow

    window = MainWindow()
    try:
        def rows(term: str) -> int:
            window.search.setText(term)
            return window.table.rowCount()

        assert rows("") == 2
        assert rows("αλφα") == 1                 # επωνυμία (όπως και πριν)
        assert rows("1234567") == 1              # ΑΦΜ (όπως και πριν)
        # Οι στήλες που δεν αναζητούνταν ποτέ, ενώ ήταν μπροστά στα μάτια:
        assert rows("Διαθέσιμος") == 1           # κατάσταση
        assert rows("Χωρίς κλειδί") == 1
        assert rows("ζζζ") == 0
    finally:
        window.close()


def test_download_page_search_covers_every_column(app, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    from timologio.gui import sync_page as sp

    rows = [
        {"vat": "123456783", "label": "ΑΛΦΑ ΑΕ", "docs": 47,
         "last_run": "2026-08-26 10:00:00"},
        {"vat": "998877665", "label": "ΒΗΤΑ ΟΕ", "docs": 0, "last_run": ""},
    ]
    hay = [sp._row_haystack(r) for r in rows]
    assert "αλφα αε" in hay[0]
    assert "47" in hay[0]
    # Και οι δύο μορφές ημερομηνίας: όπως αποθηκεύεται και όπως εμφανίζεται.
    assert "2026-08-26" in hay[0] and "26/08/2026" in hay[0]
    assert "47" not in hay[1]


def test_the_placeholders_stop_promising_less_than_they_deliver() -> None:
    repo = Path(__file__).resolve().parents[2]
    for name in ("main_window.py", "sync_page.py"):
        src = (repo / "desktop" / "src" / "timologio" / "gui" / name).read_text("utf-8")
        assert "Αναζήτηση σε όλες τις στήλες…" in src, name
