"""0.4.46 — στήλη «Καύσιμο» (fuelCode), διπλές υποβολές του ίδιου
παραστατικού (ίδιο UID, νέο ΜΑΡΚ) κρυμμένες, φίλτρο στήλης σε σειρά και ποσά."""

from __future__ import annotations

import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import repo, reports  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db, mark_duplicates  # noqa: E402
from timologio.doctypes import fuel_label  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.mydata.parse import parse_invoice  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "998027242"
NS = "http://www.aade.gr/myDATA/invoice/v1.0"


def _invoice(mark: str, uid: str, fuels: list[str]) -> ET.Element:
    lines = "".join(
        f"<invoiceDetails><lineNumber>{i}</lineNumber><netValue>10</netValue>"
        f"<fuelCode>{code}</fuelCode></invoiceDetails>"
        for i, code in enumerate(fuels, 1)
    )
    xml = (
        f'<invoice xmlns="{NS}"><uid>{uid}</uid><mark>{mark}</mark>'
        f"<issuer><vatNumber>{VAT}</vatNumber></issuer>"
        "<invoiceHeader><series>FIM</series><aa>181</aa><issueDate>2026-04-08</issueDate>"
        "<invoiceType>11.1</invoiceType></invoiceHeader>"
        f"{lines}<invoiceSummary><totalNetValue>30</totalNetValue>"
        "<totalGrossValue>37.2</totalGrossValue></invoiceSummary></invoice>"
    )
    return ET.fromstring(xml)


def test_the_invoice_gives_its_uid_and_fuels():
    doc = parse_invoice(_invoice("400013226701592", "E8E61C89", ["20", "10", "999", "20"]),
                        Direction.OUTGOING)
    assert doc.uid == "E8E61C89"
    assert doc.fuel_codes == "10,20"                 # μοναδικά, χωρίς το 999
    assert fuel_label(doc.fuel_codes) == "Benzine 95RON, Diesel"
    assert fuel_label("21,77") == "Diesel premium, 77"   # άγνωστος κωδικός: ως έχει
    assert fuel_label("") == ""


# ===========================================================================
# Διπλές υποβολές
# ===========================================================================
@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "timologio.db")
    cid = upsert_client = repo.upsert_client(
        c, Client(vat=VAT, label="ΝΤΟΥΣΙΑΣ ΕΕ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"))
    del upsert_client

    def doc(mark, *, uid="", aa="181", total=37.2, url="https://x.gr/a", fuel=""):
        repo.upsert_document(c, cid, Document(
            mark=mark, invoice_type="11.1", issuer_vat=VAT, series="FIM", aa=aa,
            issue_date="2026-04-08", net_value=30.0, vat_amount=7.2, total_value=total,
            direction=Direction.OUTGOING, uid=uid, downloading_invoice_url=url,
            fuel_codes=fuel))

    doc("400013226652157", uid="E8E6")                 # πρώτη διαβίβαση
    doc("400013226701592", uid="E8E6", fuel="20")      # ίδιο UID, νεότερο ΜΑΡΚ
    doc("400013226000001", aa="190")                   # χωρίς UID…
    doc("400013226000002", aa="190")                   # …ίδια στοιχεία → διπλό
    doc("400013226000003", aa="191", total=10.0)
    doc("400013226000004", aa="191", total=12.0)       # άλλο ποσό → δεν είναι διπλό
    doc("400013226000005", aa="")                      # χωρίς α/α και UID…
    doc("400013226000006", aa="")                      # …δεν συγκρίνονται
    mark_duplicates(c, cid)
    c.commit()
    yield c, cid
    c.close()


def _hidden(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT mark FROM documents WHERE superseded=1")}


def test_only_the_newest_transmission_counts(conn):
    c, _cid = conn
    assert _hidden(c) == {"400013226652157", "400013226000001"}


def test_hidden_everywhere_but_the_duplicates_filter(conn):
    c, cid = conn
    a = reports.analyse_client(c, VAT, 2026)
    assert a.total == 6 and a.duplicates == 2
    assert a.income.count == 6
    listed = {r["mark"] for r in reports.documents_for(c, VAT, "all", year=2026)}
    assert not listed & _hidden(c)
    dups = {r["mark"] for r in reports.documents_for(c, VAT, "duplicates", year=2026)}
    assert dups == _hidden(c)
    pending = {r["mark"] for r in repo.pending_documents(c, cid, client_vat=VAT)}
    assert not pending & _hidden(c), "κατέβηκε PDF για διπλή υποβολή"
    exported = {r["mark"] for r in reports._documents_rows(c, VAT, 2026)}
    assert not exported & _hidden(c)


def test_marking_is_recomputed(conn):
    """Αν φύγει η νεότερη διαβίβαση, η παλιά ξαναμετρά."""
    c, cid = conn
    c.execute("DELETE FROM documents WHERE mark='400013226701592'")
    mark_duplicates(c, cid)
    assert "400013226652157" not in _hidden(c)


def test_uid_and_fuels_force_a_one_off_refetch(conn):
    c, cid = conn
    row = c.execute("SELECT amounts_v, uid, fuel_codes FROM documents "
                    "WHERE mark='400013226701592'").fetchone()
    assert tuple(row) == (repo.DATA_V, "E8E6", "20")
    assert repo.DATA_V == 2
    c.execute("UPDATE documents SET amounts_v=1")
    assert repo.needs_amount_refresh(c, cid, Direction.OUTGOING, "2026-01-01", "2026-12-31")


def test_sync_marks_duplicates_after_every_download():
    src = (SRC / "sync.py").read_text(encoding="utf-8")
    body = src[src.index("def discover("):src.index("def problem_text(")]
    assert "mark_duplicates(conn, client.id)" in body


# ===========================================================================
# Πίνακας παραστατικών
# ===========================================================================
@pytest.fixture
def view(conn, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from timologio.config import Settings
    from timologio.gui import documents_view as dv

    QApplication.instance() or QApplication([])
    page = dv.DocumentsView(Settings(data_dir=tmp_path),
                            QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat))
    page.show_client(conn[0], VAT, "ΝΤΟΥΣΙΑΣ ΕΕ", "all")
    yield page, dv
    page.close()


def test_the_fuel_column(view):
    page, dv = view
    assert dv._COLS[dv._COL_FUEL][0] == "Καύσιμο"
    row = next(i for i, r in enumerate(page.model.rows) if r["mark"] == "400013226701592")
    assert page.table.item(row, dv._COL_FUEL).text() == "Diesel"
    other = next(i for i, r in enumerate(page.model.rows) if r["mark"] == "400013226000002")
    assert page.table.item(other, dv._COL_FUEL).text() == "—"
    page.search.setText("diesel")
    page._fill()
    assert [r["mark"] for r in page.model.rows] == ["400013226701592"]


def test_series_and_amounts_have_column_filters(view):
    page, dv = view
    for col in (dv._COL_SERIES, dv._COL_FUEL, dv._COL_NET, dv._COL_VAT, dv._COL_GROSS):
        assert col in dv._FILTERABLE_COLS
    # Ποσά: αριθμητική σειρά, όχι αλφαβητική.
    assert page._distinct_col_values(dv._COL_GROSS) == ["10,00", "12,00", "37,20"]
    page._col_filters[dv._COL_GROSS] = {"12,00"}
    page._fill()
    assert [r["mark"] for r in page.model.rows] == ["400013226000004"]


def test_the_duplicates_filter_exists_and_the_analysis_points_to_it(view, conn):
    from PySide6.QtWidgets import QLabel

    from timologio.gui.analysis_panel import AnalysisPanel

    page, dv = view
    assert ("duplicates", "Διπλές υποβολές") in dv.STATUS_FILTERS
    page.show_client(conn[0], VAT, "ΝΤΟΥΣΙΑΣ ΕΕ", "duplicates")
    assert {r["mark"] for r in page.model.rows} == _hidden(conn[0])
    panel = AnalysisPanel()
    panel.show_client(conn[0], VAT, 2026)
    assert "Διπλές υποβολές" in " ".join(w.text() for w in panel.findChildren(QLabel))
    panel.close()


def test_the_export_has_the_fuel(conn):
    rows = {r["mark"]: reports._doc_row_values(r)
            for r in reports._documents_rows(conn[0], VAT, 2026)}
    assert reports._DOC_HEADERS[-1] == "Καύσιμα"
    assert rows["400013226701592"][-1] == "Diesel"


def test_the_manual_explains_it():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "Καύσιμο" in manual and "Διπλές υποβολές" in manual
