"""0.4.39 — η χρήση, τα στοιχεία όλης της χρήσης, οι παρακρατήσεις και η
ειδοποίηση για αχαρακτήριστα με παρακρατούμενο φόρο."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from timologio import fiscal, repo, sync  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.mydata.parse import parse_invoice  # noqa: E402
from timologio.reports import (  # noqa: E402
    analyse_client,
    documents_for,
    export_documents,
)
from timologio.repo import upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "803105689"
TODAY = date(2026, 10, 19)


# ===========================================================================
# 1. Οι κανόνες της χρήσης
# ===========================================================================
def test_discovery_covers_the_whole_fiscal_year_up_to_today():
    assert fiscal.discovery_window("01/10/2026", "19/10/2026", TODAY) == (
        "01/01/2026", "19/10/2026")
    # Περασμένη χρήση: ως 31/12.
    assert fiscal.discovery_window("01/03/2025", "31/03/2025", TODAY) == (
        "01/01/2025", "31/12/2025")
    # Δύο χρήσεις: από την αρχή της πρώτης ως σήμερα.
    assert fiscal.discovery_window("01/12/2025", "15/01/2026", TODAY) == (
        "01/01/2025", "19/10/2026")
    # Ποτέ δεν μικραίνει το αίτημα, ούτε χαλάει με άκυρες ημερομηνίες.
    assert fiscal.discovery_window("01/01/2026", "31/12/2026", TODAY)[1] == "31/12/2026"
    assert fiscal.discovery_window("x", "y", TODAY) == ("x", "y")


def test_the_year_changes_by_itself_but_a_manual_choice_holds_within_the_year():
    assert fiscal.resolve_year(None, None, TODAY) == 2026
    assert fiscal.resolve_year(2025, 2026, TODAY) == 2025          # επιλογή φέτος
    assert fiscal.resolve_year(2025, 2025, date(2027, 1, 2)) == 2027  # νέος χρόνος
    assert fiscal.year_window(2026, TODAY) == (date(2026, 1, 1), TODAY)
    assert fiscal.year_window(2025, TODAY) == (date(2025, 1, 1), date(2025, 12, 31))
    assert fiscal.year_choices([2023, 2026], TODAY) == [2026, 2025, 2023]


# ===========================================================================
# 2. Παρακρατήσεις: parser, βάση, αναφορές
# ===========================================================================
_XML = """<invoice xmlns="http://www.aade.gr/myDATA/invoice/v1.0">
  <mark>400001</mark>
  <issuer><vatNumber>076762490</vatNumber></issuer>
  <invoiceHeader><series>A</series><aa>7</aa><issueDate>2026-09-30</issueDate>
    <invoiceType>2.1</invoiceType></invoiceHeader>
  <invoiceSummary><totalNetValue>450.00</totalNetValue><totalVatAmount>108.00</totalVatAmount>
    <totalWithheldAmount>90.00</totalWithheldAmount><totalDeductionsAmount>4.5</totalDeductionsAmount>
    <totalGrossValue>468.00</totalGrossValue></invoiceSummary>
</invoice>"""


def test_the_parser_reads_withheld_taxes_and_deductions():
    doc = parse_invoice(ET.fromstring(_XML), Direction.INCOMING)
    assert (doc.withheld_amount, doc.deductions_amount) == (90.0, 4.5)
    assert doc.total_value == 468.0      # το σύνολο της myDATA δεν αλλάζει


def _seed(db: Path):
    c = init_db(db)
    crypto = Crypto(db.parent / ".enckey")
    cid = upsert_client(c, Client(vat=VAT, label="ΑΛΦΑ ΟΕ", mydata_user="u",
                                  mydata_key="k" * 32), crypto)
    for mark, day, wh, cls in [("1", "2026-03-02", 200.0, "unclassified"),
                               ("2", "2026-05-10", 0.0, "unclassified"),
                               ("3", "2026-06-11", 60.0, "classified"),
                               ("9", "2025-11-20", 1600.0, "unclassified")]:
        upsert_document(c, cid, Document(
            mark=mark, invoice_type="2.1", issuer_vat="076762490", counter_vat=VAT,
            net_value=1000, vat_amount=240, total_value=1240, withheld_amount=wh,
            issue_date=day, direction=Direction.INCOMING,
            downloading_invoice_url=f"https://x.gr/{mark}"))
        c.execute("UPDATE documents SET classification=? WHERE mark=?", (cls, mark))
    c.commit()
    return c


@pytest.fixture
def conn(tmp_path: Path):
    c = _seed(tmp_path / "timologio.db")
    yield c
    c.close()


def test_old_rows_get_flagged_for_a_one_off_refresh(conn):
    cid = conn.execute("SELECT id FROM clients").fetchone()["id"]
    assert not repo.needs_amount_refresh(conn, cid, Direction.INCOMING,
                                         "2026-01-01", "2026-12-31")
    conn.execute("UPDATE documents SET amounts_v=0 WHERE mark='1'")
    assert repo.needs_amount_refresh(conn, cid, Direction.INCOMING,
                                     "2026-01-01", "2026-12-31")
    # Το επόμενο upsert (ίδιο MARK από την ΑΑΔΕ) γεμίζει τα ποσά και το σβήνει.
    upsert_document(conn, cid, Document(mark="1", withheld_amount=210.0,
                                        direction=Direction.INCOMING))
    row = conn.execute("SELECT withheld_amount, amounts_v FROM documents WHERE mark='1'").fetchone()
    assert (row["withheld_amount"], row["amounts_v"]) == (210.0, 1)


def test_reports_are_per_fiscal_year(conn):
    a = analyse_client(conn, VAT, 2026)
    assert (a.total, a.unclassified, a.unclassified_withheld) == (3, 2, 1)
    assert a.withheld == 260.0 and a.expense.withheld == 260.0
    assert analyse_client(conn, VAT, 2025).total == 1
    assert analyse_client(conn, VAT).total == 4               # χωρίς χρήση: όλα
    assert {r["mark"] for r in documents_for(conn, VAT, "unclassified_withheld",
                                             year=2026)} == {"1"}
    alerts = repo.withheld_unclassified(conn, [VAT], "2026-01-01", "2026-12-31")
    assert [(r["vat"], r["n"], r["amount"]) for r in alerts] == [(VAT, 1, 200.0)]


def test_export_follows_the_year_and_carries_the_withheld_columns(conn, tmp_path):
    path = tmp_path / "out.csv"
    assert export_documents(conn, path, VAT, 2026) == 3
    head = path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert head.endswith("Παρακρατούμενοι φόροι;Κρατήσεις")


def test_pdfs_follow_the_users_dates_while_the_year_is_discovered(conn, monkeypatch):
    """Ο χρήστης ζητά PDF για τον Μάιο: η ΑΑΔΕ ρωτιέται για όλη τη χρήση,
    αλλά κατεβαίνει μόνο το PDF του Μαΐου."""
    client = repo.list_clients(conn)[0]
    seen: dict = {}

    def fake_discover(conn, client, settings, *, date_from, date_to, **kw):
        seen["discover"] = (date_from, date_to)
        return 0

    def fake_download(conn, client, settings, *, stats, date_from, date_to, **kw):
        seen["pdf"] = [r["mark"] for r in repo.pending_documents(
            conn, client.id, date_from_iso=sync._gr_to_iso(date_from),
            date_to_iso=sync._gr_to_iso(date_to))]

    monkeypatch.setattr(sync, "discover", fake_discover)
    monkeypatch.setattr(sync, "download_pending", fake_download)
    monkeypatch.setattr(sync, "_auto_render_pass", lambda *a, **k: None)
    monkeypatch.setattr(sync, "discovery_window",
                        lambda a, b: fiscal.discovery_window(a, b, TODAY))
    c = Client(vat=VAT, id=client["id"])
    sync.sync_client(conn, c, object(), date_from="01/05/2026", date_to="31/05/2026",
                     use_vies=False)
    assert seen["discover"] == ("01/01/2026", "19/10/2026")
    assert seen["pdf"] == ["2"]


# ===========================================================================
# 3. Το παράθυρο: χρήση παντού, ειδοποίηση με σύνδεσμο
# ===========================================================================
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app, tmp_path_factory):
    """ΕΝΑ παράθυρο για όλο το αρχείο: κάθε MainWindow μένει ζωντανό ως το
    τέλος της σουίτας και κάνει κάθε επόμενη αλλαγή θέματος πιο αργή."""
    folder = tmp_path_factory.mktemp("w39")
    _seed(folder / "timologio.db").close()
    QSettings("scanmydata", "TimologioDownloader").remove("fiscal")
    from timologio.gui.main_window import MainWindow

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TIMOLOGIO_DATA_DIR", str(folder))
        mp.setattr(MainWindow, "_notify_done", lambda *a, **k: None)
        win = MainWindow(force_show=True)
        yield win
        win._teardown()
        win.close()
    QSettings("scanmydata", "TimologioDownloader").remove("fiscal")


def _row(win, vat):
    for i in range(win.table.rowCount()):
        if win.table.item(i, 1).text() == vat:
            return i
    raise AssertionError(vat)


def test_the_fiscal_year_drives_clients_documents_and_details(window, app):
    year = date.today().year
    assert window.fiscal_combo.currentData() == year
    assert f"Χρήση {year}" in window.windowTitle()
    window._set_fiscal_year(2026, manual=True)
    assert window.table.item(_row(window, VAT), 4).text() == "3"     # μόνο το 2026
    window.fiscal_combo.setCurrentIndex(window.fiscal_combo.findData(2025))
    app.processEvents()
    assert window._fiscal_year == 2025
    assert window.table.item(_row(window, VAT), 4).text() == "1"
    assert window.sync_page.date_from.gr() == "01/01/2025"
    assert window.sync_page.date_to.gr() == "31/12/2025"
    assert window.docs._year == 2025
    prefs = QSettings("scanmydata", "TimologioDownloader")
    assert prefs.value("fiscal/year", type=int) == 2025


def test_new_year_switches_the_fiscal_year_by_itself(window, monkeypatch):
    window._set_fiscal_year(2025, manual=True)
    window._calendar_year = date.today().year - 1      # «χθες ήταν άλλος χρόνος»
    window._check_fiscal_rollover()
    assert window._fiscal_year == date.today().year


def test_the_summary_links_straight_to_the_filtered_documents(window, app):
    window._set_fiscal_year(2026, manual=True)
    window._sync_vats = [VAT]
    window._sync_window = ("2026-01-01", "2026-12-31")
    alerts = window._withheld_alerts()
    assert [(a["vat"], a["n"]) for a in alerts] == [(VAT, 1)]
    seen: dict = {}

    def click_link() -> None:
        for w in app.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                seen["text"] = w.text()
                w.findChild(QLabel, "qt_msgbox_label").linkActivated.emit(f"withheld:{VAT}")
                return
        QTimer.singleShot(50, click_link)

    QTimer.singleShot(100, click_link)
    window._show_sync_summary((3, 0, 0, 0, 0), alerts)
    assert "παρακρατούμενο φόρο" in seen["text"] and f"withheld:{VAT}" in seen["text"]
    assert window._current_page() == "documents"
    assert window.docs.combo_cls.currentData() == "unclassified_withheld"
    assert window.docs.table.rowCount() == 1


def test_finishing_a_sync_raises_the_alert(window, monkeypatch):
    got: dict = {}
    monkeypatch.setattr(type(window), "_show_sync_summary",
                        lambda self, totals, alerts=None: got.update(alerts=alerts))
    window._sync_vats = [VAT]
    window._sync_window = ("2026-01-01", "2026-12-31")
    window._last_totals = (3, 0, 0, 0, 0)
    window._on_finished(True)
    assert [a["vat"] for a in got["alerts"]] == [VAT]
    assert window._alert_vat == VAT                       # κλικ στην ειδοποίηση


def test_the_documents_table_has_the_withheld_column():
    from timologio.gui import documents_view as dv

    assert dv._COLS[dv._COL_WITHHELD][0] == "Παρακρ./Κρατ."
    assert dv._COL_CLS == dv._COL_WITHHELD + 1
    keys = [k for k, _ in dv.CLS_FILTERS]
    assert "unclassified_withheld" in keys and "withheld" in keys


def test_manual_and_tour_cover_the_fiscal_year():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "2α. Η χρήση" in manual and "Παρακρ./Κρατ." in manual
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "TOUR_VERSION = 4" in window and '"Η χρήση",' in window


def test_a_new_day_moves_the_sync_end_date_forward(window):
    from datetime import timedelta

    today = date.today()
    yesterday = today - timedelta(days=1)
    window._last_today = yesterday
    window._calendar_year = today.year
    window.sync_page.date_to.set_gr(yesterday.strftime("%d/%m/%Y"))
    window._check_fiscal_rollover()
    assert window.sync_page.date_to.gr() == today.strftime("%d/%m/%Y")
