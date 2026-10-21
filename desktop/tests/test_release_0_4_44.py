"""0.4.44 — δελτία αποστολής και αυτοπαραδόσεις: φαίνονται στα έσοδα (του
πελάτη) ή στα έξοδα (των προμηθευτών), αλλά δεν μετρούν στα σύνολα."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import reports  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.doctypes import counting_sql, counts_in_totals, doc_kind  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.repo import upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "802499326"
OTHER = "094057575"

_DOCS = [
    ("1", "2.1", VAT, 1000.0),
    ("2", "9.3", VAT, 500.0),      # δελτίο αποστολής του πελάτη, ΜΕ αξία
    ("3", "6.1", VAT, 80.0),       # αυτοπαράδοση
    ("4", "6.2", VAT, 20.0),       # ιδιοχρησιμοποίηση
    ("5", "1.1", OTHER, 300.0),
    ("6", "9.3", OTHER, 0.0),      # δελτίο προμηθευτή
    ("7", "9.3", OTHER, 0.0),
]


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "timologio.db")
    cid = upsert_client(c, Client(vat=VAT, label="ΔΟΚΙΜΗ ΙΚΕ", mydata_user="u",
                                  mydata_key="k" * 32), Crypto(tmp_path / ".enckey"))
    for mark, itype, issuer, net in _DOCS:
        upsert_document(c, cid, Document(
            mark=mark, invoice_type=itype, issuer_vat=issuer,
            counter_vat="" if issuer == VAT else VAT, issue_date="2026-06-01",
            net_value=net, vat_amount=0.0, total_value=net,
            direction=Direction.OUTGOING if issuer == VAT else Direction.INCOMING))
    c.commit()
    yield c
    c.close()


def test_delivery_notes_and_self_deliveries_belong_to_a_side_but_do_not_count():
    assert doc_kind(VAT, VAT, "9.3") == "income"
    assert doc_kind(OTHER, VAT, "9.3") == "expense"
    assert doc_kind(VAT, VAT, "6.1") == "income"
    for code in ("9.3", "6.1", "6.2"):
        assert not counts_in_totals(code)
    for code in ("1.1", "2.1", "11.1", "17.1", "5.2", ""):
        assert counts_in_totals(code)


def test_sql_matches_python(conn):
    for _m, code, _i, _n in _DOCS:
        got = conn.execute(f"SELECT {counting_sql(':t')}", {"t": code}).fetchone()[0]
        assert bool(got) == counts_in_totals(code), code


def test_totals_leave_them_out_the_lists_keep_them(conn):
    a = reports.analyse_client(conn, VAT, 2026)
    assert (a.income.count, a.income.net) == (1, 1000.0)       # όχι οι 500+80+20
    assert (a.expense.count, a.expense.net) == (1, 300.0)
    assert (a.income_uncounted, a.expense_uncounted) == (3, 2)
    incomes = {r["mark"] for r in reports.documents_for(conn, VAT, "income", year=2026)}
    expenses = {r["mark"] for r in reports.documents_for(conn, VAT, "expense", year=2026)}
    assert incomes == {"1", "2", "3", "4"} and expenses == {"5", "6", "7"}


def test_the_documents_view_shows_them_greyed_and_out_of_the_totals(conn, tmp_path):
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication

    from timologio.config import Settings
    from timologio.gui import documents_view as dv

    QApplication.instance() or QApplication([])
    page = dv.DocumentsView(Settings(data_dir=tmp_path),
                            QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat))
    page.show_client(conn, VAT, "ΔΟΚΙΜΗ ΙΚΕ", "income")
    assert page.table.rowCount() == 4
    assert page._total_labels["count"].text() == "1 (+3 χωρίς αξία)"
    assert page._total_labels["net"].text() == f"{dv.money(1000.0)} €"
    row = next(i for i, r in enumerate(page.model.rows) if r["mark"] == "2")
    assert "δεν μετρά στα σύνολα" in page.table.item(row, dv._COL_NET).toolTip()
    assert page.table.item(row, dv._COL_KIND).text() == "Έσοδο"
    assert page.table.item(row, dv._COL_NET).data(Qt.ItemDataRole.ForegroundRole) is not None
    page.close()


def test_the_analysis_says_why_the_list_is_longer(conn):
    from PySide6.QtWidgets import QApplication, QLabel

    from timologio.gui.analysis_panel import AnalysisPanel

    QApplication.instance() or QApplication([])
    panel = AnalysisPanel()
    panel.show_client(conn, VAT, 2026)
    texts = " ".join(w.text() for w in panel.findChildren(QLabel))
    assert "3 στα έσοδα" in texts and "2 στα έξοδα" in texts
    assert "δεν μετρούν στα σύνολα" in texts
    panel.close()


def test_the_client_list_counts_the_same_way():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    head = src[:src.index("class MainWindow")]
    assert head.count('counting_sql("d.invoice_type")') == 2


def test_the_manual_explains_it():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "Αυτοπαραδόσεις" in manual and "δεν μετρούν στα σύνολα" in manual
