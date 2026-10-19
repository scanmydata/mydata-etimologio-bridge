"""0.4.42 — ο έλεγχος ενημερώσεων ρωτά πρώτα τη σελίδα εκδόσεων (χωρίς όριο
ερωτήσεων) και μόνο ένα repo· ο πίνακας παραστατικών σχεδιάζει μόνο ό,τι
φαίνεται, ώστε η εναλλαγή σε πελάτη με χιλιάδες παραστατικά να μην παγώνει."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableView, QTableWidget  # noqa: E402

from timologio import updates  # noqa: E402
from timologio.config import Settings  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.gui import documents_view as dv  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.repo import upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"
REPO = "scanmydata/mydata-etimologio-bridge"


# ===========================================================================
# 1. Έλεγχος ενημερώσεων
# ===========================================================================
class _Resp:
    def __init__(self, status=200, *, text="", content=b"", headers=None, json=None):
        self.status_code = status
        self.text = text
        self.content = content or text.encode("utf-8")
        self.headers = headers or {}
        self._json = json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")

    def json(self):
        return self._json


_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <link rel="alternate" type="text/html" href="https://github.com/{repo}/releases/tag/v9.9.9"/>
    <content type="html">&lt;h2&gt;Νέα&lt;/h2&gt;</content>
  </entry>
</feed>"""


def _web(calls: list[str], *, page_ok=True, api_ok=True):
    """Ψεύτικο GitHub: σελίδα εκδόσεων, λίστα αρχείων, atom και API."""

    def get(url, **kw):
        calls.append(url)
        if "api.github.com" in url:
            if not api_ok:
                return _Resp(403)
            assert REPO in url
            return _Resp(json={
                "tag_name": "v9.9.8", "html_url": f"https://github.com/{REPO}/releases/tag/v9.9.8",
                "assets": [{"name": "S-9.9.8-setup.exe", "browser_download_url": "https://x/a.exe",
                            "size": 5}], "body": "md",
            })
        if not page_ok:
            raise requests.ConnectionError("χωρίς δίκτυο")
        if url.endswith("/releases/latest"):
            assert kw.get("allow_redirects") is False
            return _Resp(302, headers={"Location": f"https://github.com/{REPO}/releases/tag/v9.9.9"})
        if "/expanded_assets/" in url:
            return _Resp(text=f'<a href="/{REPO}/releases/download/v9.9.9/ScanmyDataSuite-9.9.9-setup.exe">')
        if url.endswith("releases.atom"):
            return _Resp(text=_ATOM.format(repo=REPO))
        raise AssertionError(url)

    def head(url, **kw):
        calls.append("HEAD " + url)
        return _Resp(headers={"Content-Length": "466212083"})

    return get, head


def test_the_release_page_is_asked_first_and_only_this_repo(monkeypatch):
    calls: list[str] = []
    get, head = _web(calls)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "head", head)
    info = updates.check("0.4.41")
    assert info.latest == "9.9.9" and info.is_newer
    assert info.asset_name == "ScanmyDataSuite-9.9.9-setup.exe"
    assert info.asset_url == (f"https://github.com/{REPO}/releases/download/v9.9.9/"
                              "ScanmyDataSuite-9.9.9-setup.exe")
    assert info.asset_size == 466212083
    assert "Νέα" in info.notes_html
    assert not any("api.github.com" in c for c in calls), "το API ρωτήθηκε χωρίς λόγο"
    assert all("MyData-Invoice-Downloader" not in c for c in calls)
    assert not hasattr(updates, "OWNER_REPOS")


def test_the_api_is_the_fallback_when_the_page_fails(monkeypatch):
    calls: list[str] = []
    get, head = _web(calls, page_ok=False)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "head", head)
    info = updates.check("0.4.41")
    assert info.latest == "9.9.8" and info.notes == "md"
    assert calls[0].endswith("/releases/latest") and "api.github.com" in calls[-1]


def test_a_real_error_when_both_fail(monkeypatch):
    """Ποτέ ψεύτικο «είστε ενημερωμένοι» πάνω από άγνωστη κατάσταση."""
    get, head = _web([], page_ok=False, api_ok=False)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "head", head)
    with pytest.raises(requests.ConnectionError):
        updates.check("0.4.41")


def test_rate_limited_api_no_longer_matters(monkeypatch):
    """Το σφάλμα της οθόνης: «403 rate limit exceeded» από το API."""
    get, head = _web([], api_ok=False)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "head", head)
    assert updates.check("0.4.41").latest == "9.9.9"


def test_html_notes_are_shown(app):
    from timologio.gui.updater import Updater

    src = (SRC / "gui" / "updater.py").read_text(encoding="utf-8")
    assert "notes.setHtml(info.notes_html)" in src
    assert Updater is not None


# ===========================================================================
# 2. Πίνακας παραστατικών: μόνο ό,τι φαίνεται
# ===========================================================================
VAT = "998027242"
N = 3000


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app, tmp_path):
    conn = init_db(tmp_path / "timologio.db")
    cid = upsert_client(conn, Client(vat=VAT, label="ΜΕΓΑΛΟΣ ΠΕΛΑΤΗΣ", mydata_user="u",
                                     mydata_key="k" * 32), Crypto(tmp_path / ".enckey"))
    for n in range(N):
        upsert_document(conn, cid, Document(
            mark=f"{n:06d}", invoice_type="2.1" if n % 3 else "5.1",
            issuer_vat="094057575", counter_vat=VAT,
            issue_date=f"2026-{n % 12 + 1:02d}-{n % 28 + 1:02d}",
            net_value=float(n), vat_amount=0.0, total_value=float(n),
            direction=Direction.INCOMING, downloading_invoice_url=f"https://x.gr/{n}"))
    conn.execute("UPDATE documents SET local_path='a/' || mark || '.pdf'")
    conn.commit()
    page = dv.DocumentsView(Settings(data_dir=tmp_path), QSettings(str(tmp_path / "p.ini"),
                                                                   QSettings.Format.IniFormat))
    page.resize(1400, 600)
    page.show()
    yield page, conn
    page.close()
    conn.close()


def test_the_table_is_a_model_view_not_an_item_per_cell(view):
    page, conn = view
    assert isinstance(page.table, QTableView) and not isinstance(page.table, QTableWidget)
    t = time.perf_counter()
    page.show_client(conn, VAT, "ΜΕΓΑΛΟΣ ΠΕΛΑΤΗΣ", "all")
    QApplication.processEvents()
    assert time.perf_counter() - t < 2.0
    assert page.table.rowCount() == N
    # Ο δίσκος ρωτήθηκε μόνο για τις γραμμές που φαίνονται, όχι για 3.000.
    assert 0 < len(page.model._files) < 100


def test_default_order_is_newest_first_and_header_sorts_amounts_numerically(view):
    page, conn = view
    page.show_client(conn, VAT, "ΜΕΓΑΛΟΣ ΠΕΛΑΤΗΣ", "all")
    dates = [r["issue_date"] for r in page.model.rows]
    assert dates == sorted(dates, reverse=True)
    page.table.sortByColumn(dv._COL_NET, Qt.SortOrder.AscendingOrder)
    nets = [dv.signed(r["net_value"], r["invoice_type"]) for r in page.model.rows]
    assert nets == sorted(nets)
    # Πιστωτικά (5.1) με αρνητικό πρόσημο: πρώτα στην αύξουσα σειρά.
    assert page.model.rows[0]["invoice_type"] == "5.1"
    # Η ταξινόμηση του χρήστη επιβιώνει το ξαναγέμισμα.
    page.reload()
    nets = [dv.signed(r["net_value"], r["invoice_type"]) for r in page.model.rows]
    assert nets == sorted(nets)


def test_cells_keep_their_text_colour_and_checkbox(view):
    page, conn = view
    page.show_client(conn, VAT, "ΜΕΓΑΛΟΣ ΠΕΛΑΤΗΣ", "all")
    first = page.model.rows[0]
    cell = page.table.item(0, dv._COL_TYPE)
    assert cell.text().startswith(first["invoice_type"])
    assert page.table.item(0, dv._COL_NET).data(Qt.ItemDataRole.TextAlignmentRole)
    assert page.table.item(0, dv._COL_KIND).data(Qt.ItemDataRole.ForegroundRole) is not None
    assert page.table.horizontalHeaderItem(dv._COL_DATE).text() == "Ημ/νία"

    check = page.table.item(0, dv._COL_CHECK)
    check.setCheckState(Qt.CheckState.Checked)
    assert first["mark"] in page._checked and not page._selected_badge.isHidden()
    assert page.table.item(0, dv._COL_CHECK).checkState() == Qt.CheckState.Checked
    page._check_all(True)
    assert len(page._checked) == N
    page._check_all(False)
    assert not page._checked and page._selected_badge.isHidden()


def test_search_and_column_filter_still_work(view):
    page, conn = view
    page.show_client(conn, VAT, "ΜΕΓΑΛΟΣ ΠΕΛΑΤΗΣ", "all")
    page._col_filters[dv._COL_TYPE] = {dv.type_label("5.1")}
    page._fill()
    assert page.table.rowCount() == N // 3
    page._col_filters.clear()
    page.search.setText("002999")
    page._fill()
    assert page.table.rowCount() == 1 and page.model.rows[0]["mark"] == "002999"


def test_the_table_styles_reach_the_new_table():
    theme = (SRC / "gui" / "theme.py").read_text(encoding="utf-8")
    assert "QTableView {{" in theme and "QTableView::indicator" in theme
    assert "QTableWidget {{" not in theme


def test_changing_the_fiscal_year_shows_the_veil():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    body = src[src.index("def _set_fiscal_year("):src.index("def _check_fiscal_rollover(")]
    assert 'with self._busy(f"Χρήση {year}…"):' in body
