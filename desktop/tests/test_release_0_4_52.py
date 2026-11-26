"""0.4.52 — αυτοτιμολόγηση (selfPricing) στα έσοδα/έξοδα, δεξί κλικ με το
φίλτρο πρώτο και εικονίδια."""

from __future__ import annotations

import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import repo, reports  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.doctypes import doc_kind  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.mydata.parse import parse_invoice  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "998354658"
GO = "801052475"
NS = "http://www.aade.gr/myDATA/invoice/v1.0"


def test_the_invoice_says_self_pricing():
    xml = (
        f'<invoice xmlns="{NS}"><mark>400015976673146</mark>'
        f"<issuer><vatNumber>{GO}</vatNumber></issuer>"
        f"<counterpart><vatNumber>{VAT}</vatNumber></counterpart>"
        "<invoiceHeader><series>1</series><aa>00338485</aa><issueDate>2026-11-09</issueDate>"
        "<invoiceType>2.1</invoiceType><selfPricing>true</selfPricing></invoiceHeader>"
        "<invoiceSummary><totalNetValue>1745.56</totalNetValue>"
        "<totalGrossValue>2135.27</totalGrossValue></invoiceSummary></invoice>"
    )
    doc = parse_invoice(ET.fromstring(xml), Direction.INCOMING)
    assert doc.self_pricing is True
    plain = parse_invoice(ET.fromstring(xml.replace("<selfPricing>true</selfPricing>", "")),
                          Direction.INCOMING)
    assert plain.self_pricing is False


def test_self_pricing_flips_the_seller():
    # Η GO DELIVERY το εξέδωσε για λογαριασμό του πελάτη: έσοδο του πελάτη.
    assert doc_kind(GO, VAT, "2.1", True) == "income"
    assert doc_kind(GO, VAT, "2.1", False) == "expense"
    # Ο πελάτης εξέδωσε αυτοτιμολόγηση ως αγοραστής: έξοδό του.
    assert doc_kind(VAT, VAT, "1.1", True) == "expense"
    assert doc_kind(VAT, VAT, "1.1", False) == "income"
    # Εγγραφές εξόδων του πελάτη μένουν έξοδα.
    assert doc_kind(VAT, VAT, "17.1", True) == "expense"


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "timologio.db")
    cid = repo.upsert_client(
        c, Client(vat=VAT, label="ΠΕΛΑΤΗΣ ΟΕ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"))

    def doc(mark, issuer, total, *, sp=False, itype="2.1"):
        repo.upsert_document(c, cid, Document(
            mark=mark, invoice_type=itype, issuer_vat=issuer, series="1", aa=mark[-3:],
            issue_date="2026-11-09", net_value=total, vat_amount=0.0, total_value=total,
            direction=Direction.INCOMING if issuer != VAT else Direction.OUTGOING,
            downloading_invoice_url="https://x.gr/a", self_pricing=sp))

    doc("M0001", GO, 2135.27, sp=True)      # αυτοτιμολόγηση προς τον πελάτη → έσοδο
    doc("M0002", "094240542", 100.0)        # κανονικό έξοδο
    doc("M0003", VAT, 50.0)                 # κανονικό έσοδο
    doc("M0004", VAT, 30.0, sp=True, itype="1.1")   # αυτοτιμολόγηση του πελάτη → έξοδο
    c.commit()
    yield c
    c.close()


def test_the_flag_is_stored_and_forces_a_refetch(conn):
    assert repo.DATA_V == 3
    row = conn.execute("SELECT self_pricing, amounts_v FROM documents WHERE mark='M0001'").fetchone()
    assert tuple(row) == (1, 3)


def test_analysis_lists_and_export_agree(conn):
    a = reports.analyse_client(conn, VAT, 2026)
    assert a.income.count == 2 and a.expense.count == 2
    income = {r["mark"] for r in reports.documents_for(conn, VAT, "income", year=2026)}
    expense = {r["mark"] for r in reports.documents_for(conn, VAT, "expense", year=2026)}
    assert income == {"M0001", "M0003"}
    assert expense == {"M0002", "M0004"}
    kinds = {r["mark"]: reports._doc_row_values(r)[3]
             for r in reports._documents_rows(conn, VAT, 2026)}
    assert kinds["M0001"] == "Έσοδο" and kinds["M0004"] == "Έξοδο"


def test_the_documents_table_agrees(conn, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from timologio.config import Settings
    from timologio.gui import documents_view as dv

    QApplication.instance() or QApplication([])
    page = dv.DocumentsView(Settings(data_dir=tmp_path),
                            QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat))
    page.show_client(conn, VAT, "ΠΕΛΑΤΗΣ ΟΕ", "all")
    row = next(i for i, r in enumerate(page.model.rows) if r["mark"] == "M0001")
    assert page.table.item(row, dv._COL_KIND).text() == "Έσοδο"
    page.close()


def test_the_client_list_totals_agree():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert 'income_sql("d.issuer_vat", "c.vat", "d.invoice_type")' in src
    from timologio.doctypes import income_sql

    assert "d.self_pricing" in income_sql("d.issuer_vat", "c.vat", "d.invoice_type")
    assert "COALESCE(self_pricing,0)" in income_sql("issuer_vat", ":vat")


# ===========================================================================
# Δεξί κλικ
# ===========================================================================
def test_the_filter_comes_first_with_icons(tmp_path):
    from PySide6.QtWidgets import QApplication, QMenu, QTableWidget, QTableWidgetItem

    from timologio.gui.table_filter import TableColumnFilter, cell_menu_actions

    QApplication.instance() or QApplication([])
    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["ΑΦΜ", "Επωνυμία"])
    for r in range(2):
        for c in range(2):
            table.setItem(r, c, QTableWidgetItem(f"τιμή{r}{c}"))
    table.resize(400, 200)
    flt = TableColumnFilter(table, (0, 1))
    menu = QMenu()
    menu.addAction("Διαγραφή πελάτη")
    cell_menu_actions(menu, table, table.visualItemRect(table.item(0, 1)).center(), flt)
    acts = [a for a in menu.actions() if not a.isSeparator()]
    assert acts[1].text().startswith("Φίλτρο: Επωνυμία")
    assert acts[2].text().startswith("Αντιγραφή «")
    assert all(not a.icon().isNull() for a in acts[1:])
