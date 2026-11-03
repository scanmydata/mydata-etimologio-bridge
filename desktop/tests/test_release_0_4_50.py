"""0.4.50 — φίλτρα στην εξαγωγή Excel/CSV, «ΠΑΡΑΣΤΑΤΙΚΑ» με κεφαλαία, κουμπί
«Εμφάνιση», φίλτρο στήλης στο Α/Α και φίλτρα στήλης που ακολουθούν τα ενεργά
φίλτρα, ανάδραση στο «Εμπρός-πίσω», Alpha Ψηφιακή σε αυτόματη απόδοση, μπάρα
προόδου που δεν «ξεχνά» τη λήψη μετά από προσθήκη/διαγραφή πελάτη."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio import repo, reports, sync  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
VAT = "802499326"
ALPHA = "https://alphapsifiaki.gr/invoices/AC94F2DE703F020B3204DE50E1ECF719AF99C330"


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "timologio.db")
    cid = repo.upsert_client(
        c, Client(vat=VAT, label="CHARGELINE ΙΚΕ", mydata_user="u", mydata_key="k" * 32),
        Crypto(tmp_path / ".enckey"))

    def doc(mark, issuer, aa, day, *, total=10.0, status="downloaded", cls="classified"):
        repo.upsert_document(c, cid, Document(
            mark=mark, invoice_type="2.1" if issuer == VAT else "1.1", issuer_vat=issuer,
            series="A", aa=aa, issue_date=f"2026-{day}", net_value=total, vat_amount=0.0,
            total_value=total, direction=Direction.OUTGOING if issuer == VAT
            else Direction.INCOMING, downloading_invoice_url="https://x.gr/a"))
        c.execute("UPDATE documents SET status=?, classification=? WHERE mark=?",
                  (status, cls, mark))

    doc("M1", VAT, "9", "01-10")                                   # έσοδο
    doc("M2", VAT, "10", "03-05", cls="unclassified")              # έσοδο αχαρακτ.
    doc("M3", "051476942", "288", "10-19", status="viewer_only")   # έξοδο μόνο online
    doc("M4", "051476942", "100", "11-20", total=20.0, status="no_provider_url",
        cls="unclassified")
    c.commit()
    yield c, cid
    c.close()


def _marks(rows) -> set[str]:
    return {r["mark"] for r in rows}


# ===========================================================================
# Εξαγωγή
# ===========================================================================
def test_export_rows_follow_the_chosen_filters(conn):
    c, _ = conn
    rows = lambda **kw: _marks(reports._documents_rows(c, VAT, 2026, **kw))  # noqa: E731
    assert rows() == {"M1", "M2", "M3", "M4"}
    assert rows(filters=["income"]) == {"M1", "M2"}
    assert rows(filters=["expense"]) == {"M3", "M4"}
    assert rows(filters=["unclassified"]) == {"M2", "M4"}
    assert rows(filters=["expense", "unclassified"]) == {"M4"}
    assert rows(filters=["viewer_only"]) == {"M3"}
    assert rows(filters=["no_provider_url"]) == {"M4"}
    assert rows(date_from="2026-03-01", date_to="31/10/2026") == {"M2", "M3"}
    # Οι διπλές υποβολές δεν βγαίνουν ποτέ στην εξαγωγή.
    assert rows(filters=["duplicates"]) == rows()


def test_export_files_honour_the_filters(conn, tmp_path):
    c, _ = conn
    xlsx = tmp_path / "out.xlsx"
    assert reports.export_documents_xlsx(c, xlsx, VAT, 2026, filters=["income"]) == 2
    path = tmp_path / "out.csv"
    assert reports.export_documents(c, path, VAT, 2026, filters=["viewer_only"]) == 1
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lines = list(csv.reader(fh, delimiter=";"))
    assert lines[0][-1] == "Καύσιμα" and len(lines) == 2 and lines[1][2] == "M3"


def test_the_export_dialog_offers_the_filters_and_an_uppercase_name():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    body = src[src.index("def on_export("):src.index("def _on_client_started(")]
    for needle in ("KIND_FILTERS", "CLS_FILTERS", "STATUS_FILTERS", "GrDateEdit",
                   "set_range", "**options", 'f"ΠΑΡΑΣΤΑΤΙΚΑ {vats[0]}'):
        assert needle in body, needle
    assert "παραστατικά {vats" not in body


# ===========================================================================
# «Εμφάνιση» αντί για «Δείξε τα»
# ===========================================================================
def test_the_withheld_popup_says_show():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert 'addButton("Εμφάνιση"' in src
    assert "Δείξε τα" not in src and ">δείξε τα<" not in src


# ===========================================================================
# Φίλτρα στήλης
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
    page.show_client(conn[0], VAT, "CHARGELINE ΙΚΕ", "all")
    yield page, dv
    page.close()


def test_aa_has_a_numeric_column_filter(view):
    page, dv = view
    assert dv._COL_AA == 7 and dv._COL_AA in dv._FILTERABLE_COLS
    assert page._distinct_col_values(dv._COL_AA) == ["9", "10", "100", "288"]
    page._col_filters[dv._COL_AA] = {"288"}
    page._fill()
    assert [r["mark"] for r in page.model.rows] == ["M3"]


def test_column_filters_offer_only_what_the_other_filters_leave(view):
    page, dv = view
    assert page._distinct_col_values(dv._COL_KIND) == ["Έξοδο", "Έσοδο"]
    page._col_filters[dv._COL_KIND] = {"Έσοδο"}
    page._fill()
    # Οι άλλες στήλες: μόνο οι τιμές των εσόδων.
    assert page._distinct_col_values(dv._COL_AA) == ["9", "10"]
    assert page._distinct_col_values(dv._COL_STATUS) == ["Ελήφθη"]
    # Η ίδια η στήλη δεν περιορίζεται από το δικό της φίλτρο.
    assert page._distinct_col_values(dv._COL_KIND) == ["Έξοδο", "Έσοδο"]
    # Και η αναζήτηση μετρά.
    page._col_filters.clear()
    page.search.setText("288")
    assert page._distinct_col_values(dv._COL_KIND) == ["Έξοδο"]


# ===========================================================================
# Εμπρός-πίσω: η ετικέτα λέει τι ισχύει
# ===========================================================================
class _Doc:
    def __init__(self, pages: int) -> None:
        self._pages = pages

    def pageCount(self) -> int:  # noqa: N802
        return self._pages

    def close(self) -> None: ...


def test_the_duplex_button_says_what_will_happen(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from timologio.gui import printing

    QApplication.instance() or QApplication([])
    prefs = QSettings(str(tmp_path / "print.ini"), QSettings.Format.IniFormat)
    job = printing.PrintJob([_Doc(2), _Doc(1), _Doc(1)], prefs)
    job.duplex = False
    assert job.sheets() == 4
    assert job.duplex_text() == "Μόνο εμπρός · 4 φύλλα"
    assert "ΣΒΗΣΤΟ" in job.duplex_tooltip()
    job.duplex = True
    assert job.sheets() == 3          # 2σέλιδο = 1 φύλλο, κάθε μονοσέλιδο = 1
    assert job.duplex_text() == "✔ Εμπρός-πίσω · 3 φύλλα"
    assert "ΑΝΑΜΜΕΝΟ" in job.duplex_tooltip()
    src = (SRC / "gui" / "printing.py").read_text(encoding="utf-8")
    body = src[src.index("def _install_print_controls("):src.index("def print_pdfs(")]
    assert "duplex.setText(job.duplex_text())" in body
    assert ":checked" in body


# ===========================================================================
# Alpha Ψηφιακή: αυτόματη αόρατη απόδοση
# ===========================================================================
def test_alpha_psifiaki_is_rendered_automatically(tmp_path, monkeypatch):
    from timologio.config import Settings
    from timologio.download import provider

    assert provider.is_auto_renderable(ALPHA)
    assert provider.is_auto_renderable(ALPHA + "/pdf")

    def no_network(*_a, **_k):
        raise AssertionError("άσκοπη κλήση: η σελίδα δεν δίνει αρχείο PDF")

    downloader = provider.ProviderDownloader(Settings(data_dir=tmp_path))
    monkeypatch.setattr(downloader._session, "get", no_network)
    with pytest.raises(provider.NotAPdf):
        downloader.fetch_pdf(ALPHA)
    downloader.close()


def test_direct_pass_skips_page_only_providers_and_reports(conn, tmp_path, monkeypatch):
    from timologio.config import Settings
    from timologio.download.provider import NotAPdf

    c, _ = conn
    c.execute("UPDATE documents SET downloading_invoice_url=? WHERE mark='M3'", (ALPHA,))
    c.execute("UPDATE documents SET status='viewer_only' WHERE mark='M4'")
    c.commit()
    asked: list[str] = []

    def fake_fetch(self, url):
        asked.append(url)
        raise NotAPdf("html")

    monkeypatch.setattr("timologio.download.provider.ProviderDownloader.fetch_pdf",
                        fake_fetch)
    said: list[str] = []
    saved, remaining = sync._direct_fetch_batch(
        c, Settings(data_dir=tmp_path), repo.viewer_only_documents(c),
        progress=said.append, should_cancel=None)
    assert saved == 0
    assert {r["mark"] for r in remaining} == {"M3", "M4"}
    assert ALPHA not in asked and len(asked) == 1
    assert any("άμεσο PDF" in m for m in said)


def test_the_online_only_window_says_what_is_happening():
    src = (SRC / "sync.py").read_text(encoding="utf-8")
    body = src[src.index("def _render_viewer_batch("):src.index("def _direct_fetch_batch(")]
    assert "φόρτωση σελίδας" in body
    gui = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "def _headless_label(" in gui
    msg = gui[gui.index("def _on_headless_message("):gui.index("def _teardown_headless(")]
    assert "setLabelText(self._headless_label())" in msg


# ===========================================================================
# Μπάρα προόδου: η λήψη δεν «ξεχνιέται» μετά από αλλαγή στους πελάτες
# ===========================================================================
def test_reloading_clients_keeps_the_running_state(conn, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from timologio.gui.sync_page import SyncPage

    QApplication.instance() or QApplication([])
    page = SyncPage(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    page.set_fiscal_year(2026)
    page.load_clients(conn[0])
    assert page.btn_sync.isEnabled()
    page.set_running(True)
    page.load_clients(conn[0])          # π.χ. μόλις προστέθηκε/σβήστηκε πελάτης
    assert not page.btn_sync.isEnabled()
    assert "σε εξέλιξη" in page.target.text()
    page.set_running(False)
    assert page.btn_sync.isEnabled()
    assert "σε εξέλιξη" not in page.target.text()
    page.close()


def test_a_client_being_downloaded_is_not_deleted():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    for fn in ("def on_delete_clients(", "def on_wipe("):
        start = src.index(fn)
        body = src[start:src.index("\n    def ", start + 10)]
        assert "self._refuse_running_delete(" in body, fn
    assert "self._running_vats = set(vats or ())" in src


def test_the_manual_explains_it():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "«Εμφάνιση»" in manual
    assert "Τι θα εξαχθεί" in manual
    assert "Μόνο εμπρός" in manual


# ===========================================================================
# Stealth (Epsilon πίσω από Turnstile): σταθερό, κρυφό, παντού
# ===========================================================================
def test_stealth_works_without_distutils(monkeypatch):
    """Η Python 3.12+ δεν έχει distutils· στο .exe το stealth έλειπε σιωπηλά."""
    import sys

    from timologio.download import stealth

    monkeypatch.setitem(sys.modules, "distutils", None)
    monkeypatch.delitem(sys.modules, "distutils.version", raising=False)
    stealth._ensure_distutils()
    from distutils.version import LooseVersion

    assert LooseVersion("156.0.8078.74").version[0] == 156
    assert LooseVersion("156.0.1") > LooseVersion("155.9.9")
    assert LooseVersion("114.0") == "114.0"


def test_the_driver_follows_the_installed_chrome(tmp_path):
    from timologio.download import stealth

    app = tmp_path / "Application"
    (app / "155.0.1.2").mkdir(parents=True)
    (app / "156.0.8078.74").mkdir()
    (app / "chrome.exe").write_bytes(b"")
    assert stealth.chrome_major(app / "chrome.exe") == 156
    assert stealth.chrome_major(None) is None
    assert stealth._mismatch_major(
        "This version of ChromeDriver only supports Chrome version 157\n"
        "Current browser version is 156.0.8078.74") == 156


def test_the_turnstile_click_uses_valid_cdp_parameters():
    src = (SRC / "download" / "stealth.py").read_text(encoding="utf-8")
    assert '"buttons": 1 if ev == "mousePressed" else 0' in src
    assert '"buttons": [{' not in src          # «Invalid parameters»: δεν πατιόταν ποτέ


def test_a_fresh_session_every_few_pages():
    from timologio.download import stealth

    r = stealth.StealthRenderer.__new__(stealth.StealthRenderer)
    r._renders = 0
    restarts: list[int] = []
    r._restart = lambda: restarts.append(r._renders) or True
    r._goto = lambda url: False
    for _ in range(9):
        assert r.render_pdf("https://epsilondigital-x.epsilonnet.gr/fd/ab:1") is None
    assert stealth._PAGES_PER_SESSION == 4
    assert restarts == [5, 9]


def test_stealth_runs_hidden_in_the_fetch_and_the_automatic_pass():
    import inspect

    src = inspect.getsource(sync._auto_render_pass)
    assert "functools.partial(StealthRenderer, hidden=True)" in src
    dvo = inspect.getsource(sync.download_viewer_only)
    gate = dvo[dvo.index("Πέρασμα 1.5"):dvo.index("Πέρασμα 2")]
    assert "hidden=not headed_fallback" in gate
    assert "if remaining and not (should_cancel" in gate     # όχι μόνο στο ορατό
    flags = (SRC / "download" / "stealth.py").read_text(encoding="utf-8")
    assert "--window-position=-32000,-32000" in flags
    assert "--disable-backgrounding-occluded-windows" in flags
