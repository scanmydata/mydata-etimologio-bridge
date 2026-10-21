"""0.4.43 — σωστά έσοδα/έξοδα στις λεπτομέρειες: οι εγγραφές εξόδων που
καταχωρεί ο ίδιος ο πελάτης (μισθοδοσία, ενοίκιο-έξοδο…) δεν είναι έσοδα, τα
δελτία αποστολής δεν είναι τίποτα από τα δύο, και από την πώληση παγίου μετρά
μόνο το κέρδος (E3_566), όχι η αξία πώλησης (E3_880)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import reports  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.doctypes import doc_kind, expense_sql, income_sql  # noqa: E402
from timologio.models import Classification, Client, Direction, Document  # noqa: E402
from timologio.mydata.e3 import E3Map, parse_e3  # noqa: E402
from timologio.repo import set_classifications, upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "802499326"
OTHER = "094057575"

#: (mark, τύπος, εκδότης, καθαρή) — μικρογραφία της CHARGELINE ΙΚΕ.
_DOCS = [
    ("1", "2.1", VAT, 1000.0),      # έσοδο
    ("2", "1.1", VAT, 2500.0),      # πώληση παγίου (E3_880_001)
    ("3", "17.3", VAT, 300.0),      # κέρδος από πώληση παγίου (E3_566)
    ("4", "11.2", VAT, 100.0),      # έσοδο
    ("5", "5.2", VAT, 50.0),        # πιστωτικό εσόδων
    ("6", "17.1", VAT, 4000.0),     # μισθοδοσία → έξοδο
    ("7", "16.1", VAT, 700.0),      # ενοίκιο-έξοδο → έξοδο
    ("8", "9.3", VAT, 0.0),         # δελτίο αποστολής → τίποτα
    ("9", "1.1", OTHER, 200.0),     # τιμολόγιο προμηθευτή → έξοδο
    ("10", "9.3", OTHER, 0.0),      # δελτίο προμηθευτή → τίποτα
    ("11", "13.1", VAT, 30.0),      # λιανικό έξοδο που δήλωσε ο ίδιος → έξοδο
]


def _e3_xml(rows: list[tuple[str, str, str, float]]) -> bytes:
    recs = "".join(
        f"<E3Info><V_Afm>{VAT}</V_Afm><V_Mark>{m}</V_Mark><IssueDate>2026-05-01</IssueDate>"
        f"<V_Class_Category>{cat}</V_Class_Category><V_Class_Type>{t}</V_Class_Type>"
        f"<V_Class_Value>{v}</V_Class_Value></E3Info>"
        for m, cat, t, v in rows
    )
    return f"<RequestedE3Info>{recs}</RequestedE3Info>".encode()


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "timologio.db")
    cid = upsert_client(c, Client(vat=VAT, label="CHARGELINE ΙΚΕ", mydata_user="u",
                                  mydata_key="k" * 32), Crypto(tmp_path / ".enckey"))
    for mark, itype, issuer, net in _DOCS:
        upsert_document(c, cid, Document(
            mark=mark, invoice_type=itype, issuer_vat=issuer,
            counter_vat="" if issuer == VAT else VAT, issue_date="2026-05-01",
            net_value=net, vat_amount=0.0, total_value=net,
            direction=Direction.OUTGOING if issuer == VAT else Direction.INCOMING))
    e3 = parse_e3(_e3_xml([
        ("1", "category1_3", "E3_561_001", 1000.0),
        ("2", "category1_4", "E3_880_001", 2500.0),
        ("3", "category1_10", "E3_566", 300.0),
        ("6", "category2_6", "E3_581_001", 4000.0),
    ]))
    set_classifications(c, cid, e3)
    c.commit()
    yield c
    c.close()


def test_the_kind_follows_the_type_not_only_the_issuer():
    assert doc_kind(VAT, VAT, "2.1") == "income"
    assert doc_kind(VAT, VAT, "17.3") == "income"
    assert doc_kind(VAT, VAT, "17.1") == "expense"       # μισθοδοσία
    assert doc_kind(VAT, VAT, "17.2") == "expense"       # αποσβέσεις
    assert doc_kind(VAT, VAT, "16.1") == "expense"       # ενοίκιο-έξοδο
    assert doc_kind(VAT, VAT, "13.30") == "expense"
    assert doc_kind(VAT, VAT, "14.5") == "expense"
    # 0.4.44: τα δελτία φαίνονται κατά τον εκδότη (δεν μετρούν στα σύνολα).
    assert doc_kind(VAT, VAT, "9.3") == "income"
    assert doc_kind(OTHER, VAT, "9.3") == "expense"
    assert doc_kind(OTHER, VAT, "1.1") == "expense"


def test_sql_and_python_agree(conn):
    for _mark, itype, issuer, _net in _DOCS:
        row = conn.execute(
            f"SELECT {income_sql(':i', ':v', ':t')} inc, {expense_sql(':i', ':v', ':t')} exp",
            {"i": issuer, "v": VAT, "t": itype},
        ).fetchone()
        kind = doc_kind(issuer, VAT, itype)
        assert (bool(row["inc"]), bool(row["exp"])) == (kind == "income", kind == "expense"), itype


def test_e3_gives_the_asset_sale_amount():
    e3 = parse_e3(_e3_xml([
        ("2", "category1_4", "E3_880_001", 2500.0),
        ("2", "category1_4", "E3_880_002", 100.0),
        ("1", "category1_3", "E3_561_001", 1000.0),
    ]))
    assert isinstance(e3, E3Map) and e3["2"] is Classification.CLASSIFIED
    assert e3.asset_sales == {"2": 2600.0}
    merged = E3Map()
    merged.update(e3)
    merged.update(parse_e3(_e3_xml([("9", "category1_4", "E3_880_001", 5.0)])))
    assert merged.asset_sales == {"2": 2600.0, "9": 5.0}


def test_reclassifying_clears_the_old_asset_amount(conn):
    cid = conn.execute("SELECT id FROM clients").fetchone()[0]
    set_classifications(conn, cid, parse_e3(_e3_xml([("2", "category1_1", "E3_561_001", 2500.0)])))
    assert conn.execute("SELECT asset_sale_amount FROM documents WHERE mark='2'").fetchone()[0] == 0


def test_income_excludes_payroll_and_counts_only_the_asset_profit(conn):
    a = reports.analyse_client(conn, VAT, 2026)
    # 2.1, 1.1 (πάγιο), 17.3, 11.2, 5.2 — ΟΧΙ 17.1, 16.1, 9.3, 13.1.
    assert a.income.count == 5
    # 1000 + (2500 − 2500 αξία παγίου) + 300 κέρδος + 100 − 50 πιστωτικό.
    assert a.income.net == pytest.approx(1350.0)
    assert a.income.gross == pytest.approx(1350.0)
    # 17.1 + 16.1 + 13.1 του πελάτη και το τιμολόγιο του προμηθευτή.
    assert a.expense.count == 4
    assert a.expense.net == pytest.approx(4000 + 700 + 30 + 200)
    assert a.total == len(_DOCS)          # τα δελτία μετρούν στο σύνολο, όχι εδώ


def test_the_income_link_opens_exactly_what_was_counted(conn):
    a = reports.analyse_client(conn, VAT, 2026)
    # Η λίστα έχει και τα δελτία αποστολής, που δεν μετρούν στα σύνολα (0.4.44).
    assert (len(reports.documents_for(conn, VAT, "income", year=2026))
            == a.income.count + a.income_uncounted)
    assert (len(reports.documents_for(conn, VAT, "expense", year=2026))
            == a.expense.count + a.expense_uncounted)


def test_the_export_direction_is_no_longer_reversed(conn, tmp_path):
    rows = {r["mark"]: reports._doc_row_values(r) for r in reports._documents_rows(conn, VAT)}
    assert rows["9"][3] == "Έξοδο"        # τιμολόγιο προμηθευτή (incoming)
    assert rows["1"][3] == "Έσοδο"
    assert rows["6"][3] == "Έξοδο"        # μισθοδοσία
    assert rows["8"][3] == "Έσοδο"        # δελτίο αποστολής του πελάτη (0.4.44)


def test_the_documents_view_uses_the_same_rule(conn, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from timologio.config import Settings
    from timologio.gui import documents_view as dv

    QApplication.instance() or QApplication([])
    page = dv.DocumentsView(Settings(data_dir=tmp_path),
                            QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat))
    page.show_client(conn, VAT, "CHARGELINE ΙΚΕ", "income")
    kinds = {r["mark"]: page._col_value(r, dv._COL_KIND) for r in page.model.rows}
    assert set(kinds) == {"1", "2", "3", "4", "5", "8"} and set(kinds.values()) == {"Έσοδο"}
    # Τα σύνολα κάτω από τον πίνακα συμφωνούν με την ανάλυση (το δελτίο 8
    # φαίνεται, δεν μετρά — 0.4.44).
    assert page._total_labels["count"].text() == "5 (+1 χωρίς αξία)"
    assert page._total_labels["net"].text() == f"{dv.money(1350.0)} €"
    row = next(i for i, r in enumerate(page.model.rows) if r["mark"] == "2")
    assert "E3_880" in page.table.item(row, dv._COL_NET).toolTip()
    page.close()


def test_the_client_list_uses_the_same_rule():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "{_INCOME_SQL}" in src and "{_EXPENSE_SQL}" in src
    assert "- d.asset_sale_amount" in src


def test_the_manual_explains_it():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "Μισθοδοσία" in manual and "E3_566" in manual
