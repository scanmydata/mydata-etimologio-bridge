"""ΕΣΚΑΠ: τα παραστατικά γίνονται PDF μόνα τους, χωρίς «Αποθήκευση ως» από τον χρήστη.

Η eskap.gr δεν εκθέτει **κανένα** αρχείο PDF — μόνο εκτυπώσιμη σελίδα
(``/invoice_print.php?authentication_code=…``). Επαληθεύτηκε ζωντανά:
``invoice_pdf.php``, ``?pdf=1``, ``?format=pdf`` → 404 ή HTML. Έτσι κάθε
παραστατικό της έμενε «μόνο online» και ο λογιστής άνοιγε τον σύνδεσμο στον
browser και το αποθήκευε με το χέρι, ένα-ένα.

Τώρα:

* ο σύνδεσμος αναγνωρίζεται και όταν είναι **ήδη** ο εκτυπώσιμος (αυτός που
  αντιγράφει ο χρήστης) — χωρίς δεύτερη κλήση στον πάροχο·
* δεν χάνεται χρόνος σε αίτημα «/pdf» που δεν υπάρχει (και που θα χάλαγε κιόλας
  τον κωδικό του συνδέσμου)·
* η σελίδα τυπώνεται σε PDF **μέσα στο ίδιο κατέβασμα**, αυτόματα.

Ζωντανή επαλήθευση με τα δύο πραγματικά URL του χρήστη: 2 PDF (100.821 B και
107.913 B), κατάσταση «Ελήφθη».
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from timologio import sync
from timologio.download.provider import (
    NotAPdf,
    ProviderDownloader,
    eskap_print_url,
    is_auto_renderable,
)
from timologio.models import Client, RunStats

REPO = Path(__file__).resolve().parents[2]
SYNC_PY = REPO / "desktop" / "src" / "timologio" / "sync.py"

PRINT_URL = (
    "https://www.eskap.gr/invoice_print.php"
    "?authentication_code=FA2B46227B976E80A7354BA252BA28D22ED04EA0"
)


class _NoNetwork:
    """Session που ΣΚΑΕΙ αν κάποιος τη χρησιμοποιήσει."""

    def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("δεν έπρεπε να γίνει κλήση στον πάροχο")


# ===========================================================================
# 1. Ο σύνδεσμος
# ===========================================================================
def test_a_print_link_is_already_the_target():
    assert eskap_print_url(PRINT_URL, session=_NoNetwork()) == PRINT_URL


def test_the_plain_invoice_php_link_becomes_the_printable_one():
    assert eskap_print_url(
        "https://www.eskap.gr/invoice.php?authentication_code=ABC123",
        session=_NoNetwork(),
    ) == "https://www.eskap.gr/invoice_print.php?authentication_code=ABC123"


def test_auto_renderable_only_for_known_providers():
    assert is_auto_renderable(PRINT_URL)
    assert is_auto_renderable("https://eskap.gr/invoice/N6SAB")
    assert not is_auto_renderable("https://epsilondigital.epsilonnet.gr/fd/abc:1")
    assert not is_auto_renderable("")


def test_no_pointless_pdf_request_to_eskap(monkeypatch):
    """Το «/pdf» δεν υπάρχει στην ΕΣΚΑΠ — και θα κολλούσε πάνω στον κωδικό."""
    settings = type("S", (), {"provider_timeout": 5.0})()
    downloader = ProviderDownloader(settings)
    monkeypatch.setattr(downloader, "_session", _NoNetwork())
    with pytest.raises(NotAPdf):
        downloader.fetch_pdf(PRINT_URL)
    with pytest.raises(NotAPdf):
        downloader.fetch_pdf("https://www.eskap.gr/invoice/N6SAB")


# ===========================================================================
# 2. Το αυτόματο πέρασμα μέσα στο κατέβασμα
# ===========================================================================
@pytest.fixture
def one_client(tmp_path: Path):
    from timologio.crypto import Crypto
    from timologio.db import init_db
    from timologio.models import Direction, Document
    from timologio.repo import mark_viewer_only, upsert_client, upsert_document

    conn = init_db(tmp_path / "t.db")
    cid = upsert_client(
        conn, Client(vat="036917866", label="ΔΕΙΓΜΑ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"),
    )
    for mark, url in (("1", PRINT_URL),
                      ("2", "https://www.eskap.gr/invoice/N6SAB"),
                      ("3", "https://epsilondigital.epsilonnet.gr/fd/abc:1")):
        upsert_document(conn, cid, Document(
            mark=mark, invoice_type="2.1", issuer_vat="094413236", counter_vat="036917866",
            net_value=80.0, vat_amount=19.2, total_value=99.2, issue_date="2026-07-10",
            direction=Direction.INCOMING, downloading_invoice_url=url))
        mark_viewer_only(conn, cid, mark)
    conn.commit()
    client = Client(id=cid, vat="036917866", label="ΔΕΙΓΜΑ",
                    mydata_user="u", mydata_key="k" * 32)
    return conn, client


def test_only_the_renderable_ones_are_taken(one_client, monkeypatch, tmp_path: Path):
    conn, client = one_client
    seen: list[list[sqlite3.Row]] = []

    monkeypatch.setattr("timologio.download.headless.find_browser", lambda: Path("edge.exe"))

    def fake_batch(_conn, _settings, rows, **kwargs):
        seen.append(rows)
        return len(rows), 0, []

    monkeypatch.setattr(sync, "_render_viewer_batch", fake_batch)
    stats = RunStats(viewer_only=3)
    sync._auto_render_pass(conn, client, object(), stats=stats,
                           progress=lambda _m: None, should_cancel=None)
    assert [row["mark"] for row in seen[0]] == ["1", "2"]     # η Epsilon μένει έξω
    assert stats.pdfs_ok == 2
    assert stats.viewer_only == 1
    assert stats.failed == 0


def test_without_edge_or_chrome_nothing_breaks(one_client, monkeypatch):
    conn, client = one_client
    monkeypatch.setattr("timologio.download.headless.find_browser", lambda: None)
    monkeypatch.setattr(sync, "_render_viewer_batch",
                        lambda *a, **k: pytest.fail("δεν υπάρχει browser"))
    said: list[str] = []
    stats = RunStats(viewer_only=3)
    sync._auto_render_pass(conn, client, object(), stats=stats,
                           progress=said.append, should_cancel=None)
    assert stats.pdfs_ok == 0 and stats.viewer_only == 3
    assert any("Edge" in line for line in said)


def test_cancelling_skips_the_pass(one_client, monkeypatch):
    conn, client = one_client
    monkeypatch.setattr(sync, "_render_viewer_batch",
                        lambda *a, **k: pytest.fail("ακυρώθηκε"))
    sync._auto_render_pass(conn, client, object(), stats=RunStats(),
                           progress=lambda _m: None, should_cancel=lambda: True)


def test_the_pass_runs_inside_every_download():
    src = SYNC_PY.read_text(encoding="utf-8")
    fn = src[src.index("def sync_client("):src.index("class AllBrowsersFailed")]
    assert "_auto_render_pass(" in fn
    assert fn.index("download_pending(") < fn.index("_auto_render_pass(")
