"""0.4.53 — το πέρασμα «μόνο online» μέσα στη λήψη ακολουθεί το διάστημα και
την έξυπνη λήψη, η Epsilon πάει κατευθείαν στο stealth (όχι πρώτα 43″ σε
αόρατο browser που δεν την περνά ποτέ), και το κρυφό παράθυρο δεν έχει κουμπί
στη γραμμή εργασιών."""

from __future__ import annotations

import inspect
import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import repo, sync  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.sync import RunStats  # noqa: E402

VAT = "803105689"
EPS = "https://epsilondigital-3rdparte.epsilonnet.gr/fd/abcdef0123456789abcdef0123456789:169"
ESKAP = "https://www.eskap.gr/invoice/N6SAB"


@pytest.fixture
def client(tmp_path: Path):
    conn = init_db(tmp_path / "t.db")
    cid = repo.upsert_client(
        conn, Client(vat=VAT, label="3ΓΥΡΟ ΟΕ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"))

    def doc(mark, url, day, *, issuer="094413236", cls="unclassified"):
        repo.upsert_document(conn, cid, Document(
            mark=mark, invoice_type="1.1", issuer_vat=issuer, counter_vat=VAT,
            net_value=10.0, vat_amount=2.4, total_value=12.4, issue_date=f"2026-{day}",
            direction=Direction.INCOMING if issuer != VAT else Direction.OUTGOING,
            downloading_invoice_url=url))
        repo.mark_viewer_only(conn, cid, mark)
        conn.execute("UPDATE documents SET classification=? WHERE mark=?", (cls, mark))

    doc("E10", EPS, "10-05")                               # Οκτ., αχαρακτ. έξοδο
    doc("K10", ESKAP, "10-20")                             # Οκτ., αχαρακτ. έξοδο
    doc("E10c", EPS, "10-21", cls="classified")            # Οκτ., χαρακτηρισμένο
    doc("E10i", EPS, "10-22", issuer=VAT)                  # Οκτ., έσοδο
    doc("E03", EPS, "03-15")                               # Μάρτιος
    conn.commit()
    yield conn, Client(id=cid, vat=VAT, label="3ΓΥΡΟ ΟΕ", mydata_user="u", mydata_key="k" * 32)
    conn.close()


def test_viewer_only_rows_follow_the_dates_and_smart_mode(client):
    conn, _ = client
    marks = lambda **kw: {r["mark"] for r in repo.viewer_only_documents(conn, [VAT], **kw)}  # noqa: E731
    assert marks() == {"E10", "K10", "E10c", "E10i", "E03"}
    assert marks(date_from_iso="2026-10-01", date_to_iso="2026-10-31") == {"E10", "K10", "E10c", "E10i"}
    assert marks(unclassified_expenses_only=True, date_from_iso="2026-10-01",
                 date_to_iso="2026-10-31") == {"E10", "K10"}


def _fake(monkeypatch, stealth: bool):
    calls: list[tuple[list[str], bool]] = []

    def fake_batch(_conn, _settings, rows, **kwargs):
        calls.append(([r["mark"] for r in rows], kwargs.get("stealth_cls") is not None))
        return len(rows), 0, []

    monkeypatch.setattr("timologio.download.headless.find_browser", lambda: Path("edge.exe"))
    monkeypatch.setattr("timologio.download.stealth.available", lambda: stealth)
    monkeypatch.setattr(sync, "_render_viewer_batch", fake_batch)
    return calls


def test_the_fetch_pass_takes_only_what_the_fetch_asked_for(client, monkeypatch):
    conn, c = client
    calls = _fake(monkeypatch, stealth=True)
    stats = RunStats(viewer_only=2)
    sync._auto_render_pass(conn, c, object(), stats=stats, progress=lambda _m: None,
                           should_cancel=None, unclassified_expenses_only=True,
                           date_from="01/10/2026", date_to="31/10/2026")
    # Η ΕΣΚΑΠ στον αόρατο browser, η Epsilon ΚΑΤΕΥΘΕΙΑΝ στο stealth.
    assert calls == [(["K10"], False), (["E10"], True)]
    assert stats.pdfs_ok == 2


def test_without_stealth_everything_stays_headless(client, monkeypatch):
    conn, c = client
    calls = _fake(monkeypatch, stealth=False)
    sync._auto_render_pass(conn, c, object(), stats=RunStats(), progress=lambda _m: None,
                           should_cancel=None, date_from="01/10/2026", date_to="31/10/2026")
    assert len(calls) == 1 and not calls[0][1]
    assert set(calls[0][0]) == {"E10", "K10", "E10c", "E10i"}


def test_the_menu_download_skips_headless_for_epsilon(client, monkeypatch):
    conn, _ = client
    calls = _fake(monkeypatch, stealth=True)
    monkeypatch.setattr(sync, "_direct_fetch_batch",
                        lambda _c, _s, rows, **kw: (0, list(rows)))
    sync.download_viewer_only(conn, object(), vats=[VAT], headed_fallback=False)
    headless = [m for m, st in calls if not st]
    assert all(not m.startswith("E") for batch in headless for m in batch)
    assert any(st and "E10" in m for m, st in calls)


def test_sync_passes_its_limits_to_the_render_pass():
    src = inspect.getsource(sync.sync_client)
    call = src[src.index("_auto_render_pass("):]
    assert "unclassified_expenses_only=unclassified_expenses_only" in call
    assert "date_from=date_from" in call


def test_the_hidden_window_has_no_taskbar_button():
    from timologio.download import stealth

    assert stealth.hide_from_taskbar(None) == 0
    src = inspect.getsource(stealth.StealthRenderer)
    assert src.count("self._hide_window()") == 2          # εκκίνηση και νέα συνεδρία
    helper = inspect.getsource(stealth.hide_from_taskbar)
    assert "0x00000080" in helper and "~ws_ex_appwindow" in helper


def test_smart_mode_uses_the_same_expense_rule(tmp_path):
    conn = init_db(tmp_path / "t.db")
    cid = repo.upsert_client(
        conn, Client(vat=VAT, label="Χ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"))
    for mark, issuer, sp in (("A", "801052475", True), ("B", "801052475", False)):
        repo.upsert_document(conn, cid, Document(
            mark=mark, invoice_type="2.1", issuer_vat=issuer, issue_date="2026-10-02",
            direction=Direction.INCOMING, downloading_invoice_url="https://x.gr/a",
            self_pricing=sp))
    conn.execute("UPDATE documents SET classification='unclassified'")
    rows = repo.pending_documents(conn, cid, unclassified_expenses_only=True, client_vat=VAT)
    # Η αυτοτιμολόγηση προς τον πελάτη είναι έσοδο: δεν είναι «αχαρακτήριστο έξοδο».
    assert [r["mark"] for r in rows] == ["B"]
    assert isinstance(rows[0], sqlite3.Row)
    conn.close()
