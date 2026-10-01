"""Η ουρά που δεν κατέβαινε ποτέ: «Λήψη εκκρεμών».

Ένα παραστατικό που βρέθηκε αλλά δεν πρόλαβε να κατέβει έμενε «σε αναμονή» —
για πάντα. Συμβαίνει με ακύρωση στη μέση, με κλείσιμο της εφαρμογής, και με την
«Έξυπνη λήψη», που κατεβάζει επίτηδες μόνο τα αχαρακτήριστα έξοδα. Κανείς δεν
ξαναζητούσε αυτά τα PDF και τίποτα δεν έλεγε πόσα είναι: ο λογιστής έβλεπε
παραστατικά χωρίς αρχείο και νόμιζε ότι «ο πάροχος δεν τα δίνει».

Στην πράξη (πραγματική βάση): 1.025 PDF σε αναμονή, από 18 πελάτες — ανάμεσά
τους σύνδεσμοι pegcloud.io που **κατεβαίνουν κανονικά** όταν ζητηθούν (8/8
επιτυχία σε ζωντανή δοκιμή).

Τώρα: «Λήψη εκκρεμών» από το μενού αδειάζει την ουρά για όλους τους πελάτες,
ζητώντας τα αρχεία **μόνο από τους παρόχους** — καμία νέα κλήση στην ΑΑΔΕ — και
το μήνυμα ολοκλήρωσης κάθε λήψης αναφέρει τι έμεινε πίσω.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from timologio import repo, sync
from timologio.crypto import Crypto
from timologio.db import init_db
from timologio.download.provider import pdf_url
from timologio.models import Client, Direction, Document

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "desktop" / "src" / "timologio"

PEG = "https://e-invoicing.pegcloud.io/d/Q3WS5ZZ6SK323BQ6GAW4LZ-6NX402"


@pytest.fixture
def db(tmp_path: Path):
    conn = init_db(tmp_path / "t.db")
    crypto = Crypto(tmp_path / ".enckey")
    first = repo.upsert_client(
        conn, Client(vat="803105689", label="3ΓΥΡΟ", mydata_user="u", mydata_key="k" * 32), crypto)
    second = repo.upsert_client(
        conn, Client(vat="104836713", label="ΑΝΥΦΑΝΤΑΚΗΣ", mydata_user="u", mydata_key="k" * 32), crypto)

    def add(cid, mark, url=PEG):
        repo.upsert_document(conn, cid, Document(
            mark=mark, invoice_type="1.1", issuer_vat="076762490", counter_vat="803105689",
            net_value=100.0, vat_amount=24.0, total_value=124.0, issue_date="2026-08-28",
            direction=Direction.INCOMING, downloading_invoice_url=url))

    add(first, "1")
    add(first, "2")
    add(second, "3")
    add(second, "4", url="")                      # χωρίς σύνδεσμο: δεν εκκρεμεί
    add(second, "5")
    repo.mark_downloaded(conn, second, "5", "x.pdf", 10, "sha")
    conn.commit()
    return conn, first, second


# ===========================================================================
# 1. Τι εκκρεμεί
# ===========================================================================
def test_backlog_counts_per_client(db):
    conn, _first, _second = db
    rows = {row["vat"]: row["n"] for row in repo.pending_backlog(conn)}
    assert rows == {"803105689": 2, "104836713": 1}


def test_a_matured_retry_counts_too(db):
    conn, first, _second = db
    repo.mark_failed(conn, first, "1", "ο πάροχος δεν αποκρίθηκε",
                     retryable=True, next_retry_at="")
    conn.commit()
    assert {row["vat"]: row["n"] for row in repo.pending_backlog(conn)}["803105689"] == 2
    # Ένα ραντεβού στο μέλλον ΔΕΝ μετρά — θα ωριμάσει μόνο του.
    repo.mark_failed(conn, first, "2", "πάλι", retryable=True,
                     next_retry_at="2099-01-01 00:00:00")
    conn.commit()
    assert {row["vat"]: row["n"] for row in repo.pending_backlog(conn)}["803105689"] == 1


def test_downloaded_and_url_less_documents_are_not_pending(db):
    conn, _first, _second = db
    rows = {row["vat"]: row["n"] for row in repo.pending_backlog(conn)}
    assert rows["104836713"] == 1          # το «κατέβηκε» και το χωρίς σύνδεσμο έξω


# ===========================================================================
# 2. Το άδειασμα της ουράς
# ===========================================================================
def test_backlog_download_asks_the_providers_only(db, monkeypatch, tmp_path: Path):
    conn, first, _second = db
    calls: dict[str, object] = {}

    def fake_pending(_conn, _client, _settings, *, stats, progress, should_cancel, **kw):
        calls["kwargs"] = kw
        stats.pdfs_ok += 2

    monkeypatch.setattr(sync, "download_pending", fake_pending)
    monkeypatch.setattr(sync, "_auto_render_pass", lambda *a, **k: None)
    client = Client(id=first, vat="803105689", label="3ΓΥΡΟ", mydata_user="u", mydata_key="k" * 32)
    stats = sync.download_backlog(conn, client, object(), progress=lambda _m: None)
    assert stats.pdfs_ok == 2
    # Καμία ημερομηνία, κανένα φίλτρο «έξυπνης λήψης»: όλη η ουρά.
    assert "unclassified_expenses_only" not in calls["kwargs"]
    assert "date_from" not in calls["kwargs"]


def test_backlog_never_calls_aade():
    src = (SRC / "sync.py").read_text(encoding="utf-8")
    fn = src[src.index("def download_backlog("):src.index("class AllBrowsersFailed")]
    for forbidden in ("discover(", "resolve_names_via_vies", "RequestDocs"):
        assert forbidden not in fn
    assert "download_pending(" in fn and "_auto_render_pass(" in fn
    assert "requeue_errors" in fn


def test_pegcloud_links_go_straight_to_the_pdf():
    assert pdf_url(PEG) == PEG + "/pdf"


# ===========================================================================
# 3. Η διαδρομή μέσα στην εφαρμογή
# ===========================================================================
def test_worker_has_a_backlog_mode():
    src = (SRC / "gui" / "workers.py").read_text(encoding="utf-8")
    assert "backlog_only: bool = False" in src
    assert "from ..sync import download_backlog, sync_client" in src
    run = src[src.index("    def run(self) -> None:"):]
    assert "if self._backlog_only:" in run
    assert run.index("if self._backlog_only:") < run.index("stats = sync_client(")


def test_menu_entry_and_handler_exist():
    menu = (SRC / "gui" / "side_menu.py").read_text(encoding="utf-8")
    assert '("pending_pdf", "Λήψη εκκρεμών"' in menu
    assert '"pending_pdf": "download",' in menu
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert '"pending_pdf": self.on_download_backlog,' in window
    fn = window[window.index("def on_download_backlog"):window.index("def on_cancel")]
    assert "repo.pending_backlog(self.conn)" in fn
    assert "backlog_only=True" in fn
    assert "καμία" in fn.lower() or "χωρίς νέα κλήση" in fn


def test_the_summary_reports_what_is_left():
    window = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    fn = window[window.index("def _show_sync_summary"):window.index("def _on_busy")]
    assert "repo.pending_backlog(self.conn)" in fn
    assert "Λήψη εκκρεμών" in fn


def test_manual_explains_the_queue():
    text = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "7γ. Λήψη εκκρεμών" in text
    assert "Έξυπνη λήψη" in text
