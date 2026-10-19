"""0.4.41 — ταχύτερη λήψη PDF σε μεγάλους πελάτες: 6 ταυτόχρονα ανά πάροχο,
καταγραφή με τη σειρά που τελειώνουν, και οι αποδείξεις λιανικής του πελάτη
σε αναμονή με ερώτηση στο τέλος της λήψης."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from timologio import repo, sync  # noqa: E402
from timologio.config import Settings  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client, Direction, Document, RunStats  # noqa: E402
from timologio.repo import list_clients, upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "998027242"

#: (mark, τύπος, εκδότης, ημερομηνία)
_DOCS = [
    ("1", "11.1", VAT, "2026-07-01"),          # απόδειξη του πελάτη
    ("2", "11.4", VAT, "2026-07-02"),          # πιστωτικό λιανικής του πελάτη
    ("3", "1.1", VAT, "2026-07-03"),           # τιμολόγιο του πελάτη
    ("4", "11.1", "094057575", "2026-07-04"),  # απόδειξη ΑΛΛΟΥ (έξοδο) — κατεβαίνει
    ("5", "11.1", VAT, "2025-12-31"),          # εκτός διαστήματος
]


def _seed(db: Path):
    conn = init_db(db)
    cid = upsert_client(conn, Client(vat=VAT, label="ΝΤΟΥΣΙΑΣ, ΑΝΔΡΕΑΣ ΚΑΙ ΣΙΑ ΕΕ",
                                     mydata_user="u", mydata_key="k" * 32),
                        Crypto(db.parent / ".enckey"))
    for mark, itype, issuer, day in _DOCS:
        upsert_document(conn, cid, Document(
            mark=mark, invoice_type=itype, issuer_vat=issuer,
            counter_vat=VAT if issuer != VAT else "", issue_date=day,
            direction=Direction.OUTGOING if issuer == VAT else Direction.INCOMING,
            downloading_invoice_url=f"https://einvoice.impact.gr/{mark}"))
    conn.commit()
    return conn, cid


@pytest.fixture
def db(tmp_path):
    conn, cid = _seed(tmp_path / "timologio.db")
    yield conn, cid, tmp_path
    conn.close()


def test_six_parallel_downloads_per_provider():
    s = Settings(data_dir=Path("."))
    assert s.max_per_host == 6 and s.max_workers >= s.max_per_host


def test_normal_download_skips_the_clients_own_receipts(db):
    conn, cid, _ = db
    marks = lambda **kw: sorted(r["mark"] for r in repo.pending_documents(  # noqa: E731
        conn, cid, client_vat=VAT, **kw))
    assert marks(retail="skip") == ["3", "4"]
    assert marks(retail="only") == ["1", "2", "5"]
    assert marks(retail="only", date_from_iso="2026-07-01",
                 date_to_iso="2026-07-31") == ["1", "2"]
    assert marks() == ["1", "2", "3", "4", "5"]          # «Λήψη εκκρεμών»: όλα
    rows = repo.pending_retail_receipts(conn, [VAT], "2026-07-01", "2026-07-31")
    assert [(r["vat"], r["n"]) for r in rows] == [(VAT, 2)]


def test_sync_leaves_receipts_pending_and_the_retail_run_takes_only_them(db, monkeypatch):
    conn, cid, tmp = db
    got: list[str] = []

    class Fake:
        def __init__(self, *a, **k): ...
        def close(self): ...

        def fetch_pdf(self, url):
            got.append(url.rsplit("/", 1)[1])
            raise sync.NotAPdf("σελίδα")

    monkeypatch.setattr(sync, "ProviderDownloader", Fake)
    client = Client(vat=VAT, id=cid)
    stats = RunStats()
    sync.download_pending(conn, client, Settings(data_dir=tmp), stats=stats,
                          date_from="01/07/2026", date_to="31/07/2026", retail="skip")
    assert sorted(got) == ["3", "4"]
    got.clear()
    sync.download_backlog(conn, client, Settings(data_dir=tmp), retail="only",
                          date_from="01/07/2026", date_to="31/07/2026")
    assert sorted(got) == ["1", "2"]
    src = (SRC / "sync.py").read_text(encoding="utf-8")
    body = src[src.index("def sync_client("):src.index("def _auto_render_pass(")]
    assert 'retail="skip"' in body


def test_results_are_saved_as_they_finish_not_in_list_order(db, monkeypatch):
    """Ένα αργό PDF δεν κρατά πίσω την καταγραφή όσων τελείωσαν."""
    conn, cid, tmp = db
    release = threading.Event()
    order: list[str] = []

    class Fake:
        def __init__(self, *a, **k): ...
        def close(self): ...

        def fetch_pdf(self, url):
            mark = url.rsplit("/", 1)[1]
            if mark == "1":            # το πρώτο της λίστας αργεί
                release.wait(5)
            raise sync.NotAPdf("σελίδα")

    def progress(text: str) -> None:
        if "⧉" in text:
            mark = text.split("⧉ ")[1].split(":")[0]
            order.append(mark)
            if len(order) == 2:
                release.set()

    monkeypatch.setattr(sync, "ProviderDownloader", Fake)
    t0 = time.time()
    sync.download_pending(conn, Client(vat=VAT, id=cid), Settings(data_dir=tmp),
                          stats=RunStats(), progress=progress)
    assert order[0] != "1" and order[-1] == "1", order
    assert time.time() - t0 < 4


# ===========================================================================
# Η ερώτηση στο τέλος της λήψης
# ===========================================================================
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app, tmp_path_factory):
    folder = tmp_path_factory.mktemp("w41")
    _seed(folder / "timologio.db")[0].close()
    from timologio.gui.main_window import MainWindow

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TIMOLOGIO_DATA_DIR", str(folder))
        mp.setattr(MainWindow, "_notify_done", lambda *a, **k: None)
        mp.setattr(MainWindow, "_show_sync_summary", lambda *a, **k: None)
        win = MainWindow(force_show=True)
        yield win
        win._teardown()
        win.close()
    QSettings("scanmydata", "TimologioDownloader").remove("fiscal")


def _answer(app, seen: dict, button_text: str):
    def go() -> None:
        for w in app.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                seen["text"] = w.text()
                for b in w.buttons():
                    if b.text().startswith(button_text):
                        b.click()
                        return
        QTimer.singleShot(50, go)
    return go


def test_after_a_sync_the_user_is_asked_about_the_receipts(window, app, monkeypatch):
    started: list = []
    monkeypatch.setattr(type(window), "_start_retail_download",
                        lambda self, vats, a, b: started.append((vats, a, b)))
    window._run_kind = "sync"
    window._sync_vats = [VAT]
    window._sync_pdf_range = ("2026-07-01", "2026-07-31")
    window._last_totals = (5, 2, 0, 0, 0)
    seen: dict = {}
    QTimer.singleShot(100, _answer(app, seen, "Λήψη τώρα"))
    window._on_finished(True)
    assert "αποδείξεις λιανικής" in seen["text"] and "ΝΤΟΥΣΙΑΣ, ΑΝΔΡΕΑΣ" in seen["text"]
    assert started == [([VAT], "2026-07-01", "2026-07-31")]


def test_no_question_without_receipts_or_after_other_runs(window, app, monkeypatch):
    asked: list = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: asked.append(1) or 0)
    window._sync_vats = [VAT]
    window._sync_pdf_range = ("2027-01-01", "2027-01-31")      # καμία απόδειξη
    window._run_kind = "sync"
    window._on_finished(True)
    window._sync_pdf_range = ("2026-07-01", "2026-07-31")
    for kind in ("backlog", "retail"):
        window._run_kind = kind
        window._on_finished(True)
    assert asked == []


def test_the_retail_run_uses_the_receipts_only_worker(window, monkeypatch):
    captured: dict = {}

    class FakeWorker:
        def __init__(self, vats, a, b, full, **kw):
            captured.update(vats=vats, a=a, b=b, **kw)
            for name in ("message", "client_started", "client_finished", "totals",
                         "finished", "failed", "busy", "problem"):
                setattr(self, name, _Sig())

        def moveToThread(self, t): ...
        def run(self): ...

    class _Sig:
        def connect(self, *_): ...

    import timologio.gui.main_window as mw
    monkeypatch.setattr(mw, "SyncWorker", FakeWorker)
    monkeypatch.setattr(mw.QThread, "start", lambda self: None)
    window._start_retail_download([VAT], "2026-07-01", "2026-07-31")
    assert captured == {"vats": [VAT], "a": "01/07/2026", "b": "31/07/2026",
                        "backlog_only": True, "retail_only": True}
    assert window._run_kind == "retail"
    window._thread = None
    window._worker = None
    window._set_running(False, 0)


def test_the_worker_passes_retail_only_down():
    src = (SRC / "gui" / "workers.py").read_text(encoding="utf-8")
    assert 'retail="only" if self._retail_only else "include"' in src


def test_manual_mentions_the_receipts_question():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "Αποδείξεις λιανικής του πελάτη" in manual and "Λήψη τώρα" in manual
