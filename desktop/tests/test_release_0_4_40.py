"""0.4.40 — η βάση δεν μένει κλειδωμένη όσο η λήψη μιλά με το δίκτυο, φίλτρο
στήλης στις παρακρατήσεις, και χωρίς κενό σελίδας στο εγχειρίδιο."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import sync  # noqa: E402
from timologio.config import Settings  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.download import NotAPdf  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.repo import list_clients, upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "803105689"


def _db_is_free(db: Path) -> bool:
    """Μπορεί ΑΛΛΗ σύνδεση (π.χ. το παράθυρο) να γράψει αυτή τη στιγμή;"""
    # 0,5″: μια στιγμιαία εγγραφή από το παράλληλο νήμα λήψης περνά· ένα
    # κλείδωμα που κρατιέται ΟΣΟ διαρκεί η κλήση (το σφάλμα) δεν περνά ποτέ,
    # γιατί όποιος το κρατά περιμένει αυτή την ίδια κλήση να τελειώσει.
    other = sqlite3.connect(db, timeout=0.5)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    db = tmp_path / "timologio.db"
    conn = init_db(db)
    crypto = Crypto(tmp_path / ".enckey")
    cid = upsert_client(conn, Client(vat=VAT, label="ΑΛΦΑ ΟΕ", mydata_user="u",
                                     mydata_key="k" * 32), crypto)
    upsert_document(conn, cid, Document(
        mark="1", invoice_type="2.1", issuer_vat="999999999", counter_vat=VAT,
        issue_date="2026-05-01", direction=Direction.INCOMING,
        downloading_invoice_url="https://x.gr/1"))
    conn.commit()
    checks: list[tuple[str, bool]] = []

    last: list[str] = []
    conn.set_trace_callback(lambda sql: last.append(sql) if sql.split()[0].upper() in ("INSERT", "UPDATE", "DELETE", "BEGIN", "COMMIT") else None)

    def probe(what: str) -> None:
        if os.environ.get("TRACE_LOCK"):
            print(">>", what, conn.in_transaction, [l.split("(")[0][:70] for l in last[-3:]])
        checks.append((what, _db_is_free(db)))

    class FakeApi:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def fetch(self, direction, **kw):
            probe(f"ΑΑΔΕ {direction.value}")
            return [Document(mark="2", invoice_type="2.1", issuer_vat="888888888",
                             counter_vat=VAT, issue_date="2026-05-02",
                             direction=direction, downloading_invoice_url="https://x.gr/2")]

        def fetch_e3(self, **kw):
            probe("ΑΑΔΕ E3")
            return []

    class FakeVies:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def lookup(self, vat):
            probe(f"VIES {vat}")
            return "ΠΡΟΜΗΘΕΥΤΗΣ"

    class FakeDownloader:
        def __init__(self, *a, **k): ...
        def close(self): ...

        def fetch_pdf(self, url):
            probe(f"πάροχος {url}")
            raise NotAPdf("σελίδα")

    monkeypatch.setattr(sync, "MydataClient", FakeApi)
    monkeypatch.setattr(sync, "ViesClient", FakeVies)
    monkeypatch.setattr(sync, "ProviderDownloader", FakeDownloader)
    monkeypatch.setattr(sync, "_auto_render_pass", lambda *a, **k: None)
    settings = Settings(data_dir=tmp_path)
    yield conn, settings, checks
    conn.close()


def test_the_database_is_free_during_every_network_call(setup):
    conn, settings, checks = setup
    client = Client(vat=VAT, id=list_clients(conn)[0]["id"], mydata_user="u",
                    mydata_key="k" * 32)
    sync.sync_client(conn, client, settings, date_from="01/05/2026",
                     date_to="31/05/2026")
    assert any(w.startswith("ΑΑΔΕ") for w, _ in checks)
    assert any(w.startswith("VIES") for w, _ in checks)
    assert any(w.startswith("πάροχος") for w, _ in checks)
    locked = [w for w, free in checks if not free]
    assert not locked, f"η βάση ήταν κλειδωμένη κατά τις κλήσεις: {locked}"


def test_the_backlog_also_leaves_the_database_free(setup):
    conn, settings, checks = setup
    conn.execute("UPDATE documents SET status='failed_retryable'")
    conn.commit()
    client = Client(vat=VAT, id=list_clients(conn)[0]["id"])
    sync.download_backlog(conn, client, settings)
    assert checks and all(free for _, free in checks), checks


def test_the_window_survives_a_locked_database(tmp_path, monkeypatch):
    """Ακόμη κι αν η βάση είναι απασχολημένη, το διπλό κλικ ξαναγεμίζει τη
    λίστα και η Ανανέωση εξηγεί τι συμβαίνει αντί για «database is locked»."""
    src = (SRC / "gui" / "documents_view.py").read_text(encoding="utf-8")
    single = src[src.index("def _download_pending_row"):src.index("def _toggle_current")]
    assert "finally:" in single and "self.reload()" in single
    assert "_busy_text(" in src
    from timologio.gui.documents_view import _busy_text

    assert "λήψη" in _busy_text(sqlite3.OperationalError("database is locked"))
    assert _busy_text(OSError("άλλο")) == "άλλο"


def test_the_withheld_column_has_a_column_filter():
    from timologio.gui import documents_view as dv

    assert dv._COL_WITHHELD in dv._FILTERABLE_COLS


def test_the_manual_has_no_forced_page_break():
    """Η αναγκαστική αλλαγή σελίδας άφηνε τη σελίδα 3 σχεδόν άδεια."""
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "page-break-before:always" not in manual


# ===========================================================================
# Ο περιορισμός της ΑΑΔΕ (HTTP 429): αναμονή, διάσωση, αναφορά
# ===========================================================================
class _Resp:
    def __init__(self, code, body=b"", headers=None):
        self.status_code, self.content, self.headers = code, body, headers or {}
        self.text = body.decode("utf-8", "replace")


_PAGE = (b'<RequestedDoc xmlns="http://www.aade.gr/myDATA/invoice/v1.0">'
         b'<invoicesDoc><invoice><mark>%s</mark><invoiceHeader><issueDate>2026-05-01'
         b'</issueDate><invoiceType>11.1</invoiceType></invoiceHeader></invoice>'
         b'</invoicesDoc>%s</RequestedDoc>')
_EMPTY = b'<RequestedDoc xmlns="http://www.aade.gr/myDATA/invoice/v1.0"></RequestedDoc>'
_MORE = b"<continuationToken><nextPartitionKey>p</nextPartitionKey><nextRowKey>r</nextRowKey></continuationToken>"


def _client(monkeypatch, responses, **kw):
    from timologio.mydata import client as mc

    waits: list[str] = []
    api = mc.MydataClient("u", "k" * 32, Settings(data_dir=Path(".")),
                          on_wait=waits.append, **kw)
    seq = iter(responses)
    monkeypatch.setattr(api._session, "get", lambda *a, **k: next(seq))
    monkeypatch.setattr(mc.time, "sleep", lambda s: None)
    monkeypatch.setattr(mc.time, "monotonic", _fake_clock())
    return api, waits


def _fake_clock():
    now = [0.0]

    def tick():
        now[0] += 50.0
        return now[0]
    return tick


def test_a_429_waits_as_long_as_aade_asks_and_continues(monkeypatch):
    api, waits = _client(monkeypatch, [
        _Resp(200, _PAGE % (b"1", _MORE)),
        _Resp(429, headers={"Retry-After": "272"}),      # μετρημένο στην ΑΑΔΕ
        _Resp(200, _PAGE % (b"2", b"")),
        _Resp(200, _EMPTY),                                # «τίποτα μετά το 2»
    ])
    docs = api.fetch(Direction.OUTGOING, date_from="01/01/2026", date_to="19/10/2026")
    assert sorted(d.mark for d in docs) == ["1", "2"]
    assert waits and "περιορισμό" in waits[0] and "4:32 λεπτά" in waits[0]


def test_when_aade_keeps_refusing_the_pages_already_fetched_survive(monkeypatch):
    from timologio.mydata.errors import RateLimitError

    api, _ = _client(monkeypatch, [_Resp(200, _PAGE % (b"1", _MORE))]
                     + [_Resp(429)] * 10)
    with pytest.raises(RateLimitError) as info:
        api.fetch(Direction.OUTGOING)
    assert [d.mark for d in info.value.partial] == ["1"]


def test_the_credentials_check_does_not_wait(monkeypatch):
    from timologio.mydata.errors import RateLimitError

    api, waits = _client(monkeypatch, [_Resp(429, headers={"Retry-After": "272"})],
                         retry=False)
    with pytest.raises(RateLimitError):
        api.check_credentials(date_from="01/10/2026", date_to="19/10/2026")
    assert waits == []


def test_a_refused_client_is_named_in_the_summary(setup, monkeypatch):
    """Μέχρι τώρα ο πελάτης χανόταν σε ένα ανώνυμο «1 σφάλμα»."""
    from timologio.mydata.errors import RateLimitError

    conn, settings, _ = setup

    class Refusing:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def fetch(self, direction, **kw):
            exc = RateLimitError(272)
            exc.partial = [Document(mark="77", invoice_type="11.1", issuer_vat=VAT,
                                    issue_date="2026-05-03", direction=direction)]
            raise exc

    monkeypatch.setattr(sync, "MydataClient", Refusing)
    client = Client(vat=VAT, id=list_clients(conn)[0]["id"], mydata_user="u",
                    mydata_key="k" * 32)
    stats = sync.sync_client(conn, client, settings, date_from="01/05/2026",
                             date_to="31/05/2026")
    assert "Προσωρινός περιορισμός" in stats.problem
    # Ό,τι ήρθε κρατήθηκε· η κάλυψη ΔΕΝ γράφτηκε (θα ξαναζητηθεί).
    assert conn.execute("SELECT 1 FROM documents WHERE mark='77'").fetchone()
    assert not conn.execute("SELECT 1 FROM coverage").fetchone()
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "self._worker.problem.connect(self._on_client_problem)" in window
    assert "_sync_problems" in window[window.index("def _show_sync_summary"):]
