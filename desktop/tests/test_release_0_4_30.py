"""Timologio Downloader: πιστωτικά με μείον, και ζουμ προεπισκόπησης που φαίνεται.

* **Πιστωτικά (5.1, 5.2, 11.4, 14.31).** Η myDATA τα δίνει με θετικά ποσά· ο
  πίνακας τα έδειχνε θετικά και τα σύνολα τα ΠΡΟΣΘΕΤΑΝ. Τώρα αφαιρούνται
  παντού: πίνακας, σύνολα, ανάλυση πελάτη, αρχική οθόνη, εξαγωγές CSV/Excel.

* **Άδειο ζουμ στην προεπισκόπηση εκτύπωσης.** Δεν ήταν χρώμα. Ο ελληνικός
  μεταφραστής γύριζε `""` για «δεν έχω μετάφραση»· το PySide το κάνει μη-null
  κενό QString, που το Qt διαβάζει ως «η μετάφραση είναι το κενό». Το «%1%» των
  ποσοστών έσβηνε — και μαζί κάθε κείμενο του Qt εκτός λεξικού.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from timologio.crypto import Crypto
from timologio.db import init_db
from timologio.doctypes import CREDIT_TYPES, is_credit, signed, signed_sql
from timologio.models import Client, Direction, Document
from timologio.reports import analyse_client
from timologio.repo import upsert_client, upsert_document

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "desktop" / "src" / "timologio"
CLIENT_VAT = "123456783"


# ===========================================================================
# 1. Μεταφραστής
# ===========================================================================
def test_translator_returns_null_for_unknown_texts():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from timologio.gui.i18n import GreekTranslator

    t = GreekTranslator()
    app.installTranslator(t)
    try:
        tr = QCoreApplication.translate
        # Το «%1%» του ζουμ και κάθε άγνωστο κείμενο μένουν ΑΥΤΟΥΣΙΑ.
        assert tr("QPrintPreviewDialog", "%1%") == "%1%"
        assert tr("QDialogButtonBox", "Discard") == "Απόρριψη"
        assert tr("QDialogButtonBox", "Some Unknown Button") == "Some Unknown Button"
        assert tr("QMessageBox", "&Yes") == "&Ναι"
        assert tr("OtherContext", "Cancel") == "Cancel"
    finally:
        app.removeTranslator(t)


def test_translator_never_returns_empty_string():
    src = (SRC / "gui" / "i18n.py").read_text(encoding="utf-8")
    fn = src[src.index("def translate("):]
    assert "return _STRINGS.get(source)" in fn
    assert "return None" in fn
    assert 'return ""' not in fn and '_STRINGS.get(source, "")' not in fn


# ===========================================================================
# 2. Πρόσημο πιστωτικών
# ===========================================================================
def test_signed_helpers():
    assert CREDIT_TYPES == {"5.1", "5.2", "11.4", "14.31"}
    assert is_credit(" 11.4 ") and not is_credit("1.4") and not is_credit(None)
    assert signed(30, "11.4") == -30 and signed(-20, "5.1") == -20
    assert signed(7, "2.1") == 7 and signed(None, "5.2") == 0
    conn = sqlite3.connect(":memory:")
    conn.execute("create table d(invoice_type text, total_value real)")
    conn.executemany("insert into d values(?,?)",
                     [("1.1", 100), ("11.4", 30), ("5.1", -20), (" 5.2 ", 10), (None, 5)])
    assert conn.execute(f"select sum({signed_sql('total_value')}) from d").fetchone()[0] == 45


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "t.db")
    cid = upsert_client(
        conn, Client(vat=CLIENT_VAT, label="ΔΕΙΓΜΑ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"),
    )

    def add(mark, itype, issuer, counter, net, vat, direction):
        upsert_document(conn, cid, Document(
            mark=mark, invoice_type=itype, issuer_vat=issuer, counter_vat=counter,
            net_value=net, vat_amount=vat, total_value=net + vat, issue_date="2026-08-02",
            direction=direction, downloading_invoice_url="https://x.gr/a"))

    add("1", "11.2", CLIENT_VAT, "", 5174.40, 1241.86, Direction.OUTGOING)   # ΑΠΥ
    add("2", "11.4", CLIENT_VAT, "", 5174.40, 1241.86, Direction.OUTGOING)   # το πιστωτικό της
    add("3", "2.1", CLIENT_VAT, "044004008", 100.0, 24.0, Direction.OUTGOING)
    add("4", "5.1", "987654324", CLIENT_VAT, 50.0, 12.0, Direction.INCOMING)  # πιστωτικό προμηθευτή
    add("5", "1.1", "987654324", CLIENT_VAT, 200.0, 48.0, Direction.INCOMING)
    conn.commit()
    return conn


def test_client_analysis_subtracts_credits(conn: sqlite3.Connection):
    a = analyse_client(conn, CLIENT_VAT)
    assert a is not None
    # Έσοδα: ΑΠΥ − πιστωτικό της + ΤΠΥ = 100 καθαρή.
    assert a.income.net == pytest.approx(100.0)
    assert a.income.gross == pytest.approx(124.0)
    # Έξοδα: 200 − 50.
    assert a.expense.net == pytest.approx(150.0)
    assert a.net_value == pytest.approx(250.0)
    by_type = dict((t, v) for t, _c, v in a.by_type)
    assert by_type["11.4"] == pytest.approx(-6416.26)


def test_documents_table_and_totals_are_signed():
    src = (SRC / "gui" / "documents_view.py").read_text(encoding="utf-8")
    assert 'net += signed(r["net_value"], r["invoice_type"])' in src
    assert '_COL_GROSS: money(signed(r["total_value"], r["invoice_type"])),' in src
    assert 'SortableItem(text, signed(amount, r["invoice_type"]))' in src


def test_exports_and_home_screen_are_signed():
    rep = (SRC / "reports.py").read_text(encoding="utf-8")
    assert "COALESCE(SUM({signed_sql('net_value')}),0) net," in rep
    assert 'signed(r["total_value"], r["invoice_type"]),' in rep          # Excel
    assert "signed(r['total_value'], r['invoice_type'])" in rep          # CSV
    main = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert main.count("{signed_sql('d.total_value', 'd.invoice_type')}") == 2
