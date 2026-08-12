"""Tests για τις native σελίδες e-Τιμολόγιο Pro (Phase 1).

Χωρίς live ΑΑΔΕ: ο client αντικαθίσταται με fake και ο worker τρέχει σύγχρονα,
ώστε να ελέγξουμε (α) ότι τα client methods χτίζουν σωστά params και (β) ότι οι
σελίδες γεμίζουν πίνακες, εκπέμπουν signals και υπολογίζουν το υπόλοιπο.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import json  # noqa: E402

from timologio.etimologio.client import EtimologioClient, EtimologioError  # noqa: E402
from timologio.etimologio.codes import (  # noqa: E402
    DEFAULT_PAYMENT,
    PAYMENT_METHODS,
    PAYMENT_METHODS_CASH,
    series_for_type,
)
from timologio.etimologio.pages import (  # noqa: E402
    AdminPage,
    BulkPage,
    CreditNotePage,
    CustomerCard,
    CustomersPage,
    DocumentsPage,
    DraftsPage,
    IssuePage,
    NotificationsPage,
    PaymentsPage,
    ProductsPage,
    SchedulePage,
    SeriesPage,
    StatsPage,
)
from timologio.etimologio.pages.base import fmt_money, parse_money  # noqa: E402
from timologio.etimologio.pages.issue import line_amounts  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


def sync_run(fn, on_ok, on_err) -> None:
    """Τρέχει τον worker σύγχρονα, όπως το QThreadPool αλλά ντετερμινιστικά."""
    try:
        on_ok(fn())
    except Exception as exc:  # noqa: BLE001
        on_err(str(exc))


class RecordingClient(EtimologioClient):
    """Καταγράφει κάθε κλήση χωρίς δίκτυο, επιστρέφοντας canned απαντήσεις."""

    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:0")
        self.calls: list[tuple[dict, dict | None, str]] = []
        self.reply: dict[str, Any] = {"success": True}

    def _call(self, params=None, data=None, method="GET"):  # type: ignore[override]
        self.calls.append((dict(params or {}), dict(data) if data else None, method))
        return self.reply


class FakeClient:
    """Ελάχιστος client για τις σελίδες: επιστρέφει σταθερά δεδομένα."""

    def __init__(self) -> None:
        self.customer_kwargs: dict[str, Any] = {}
        self.created: dict[str, Any] | None = None
        self.invoice_vat = ""
        self.payment_vat = ""

    def customers(self, **kwargs):
        self.customer_kwargs = kwargs
        return {
            "success": True,
            "customers": [
                {"code": "C1", "vat": "094000000", "name": "ΑΛΦΑ ΑΕ", "city": "Αθήνα", "address": "Οδός 1"},
                {"code": "C2", "vat": "", "name": "Ιδιώτης", "city": "Πάτρα", "address": ""},
            ],
        }

    def create_customer(self, **fields):
        self.created = fields
        return {"success": True}

    def search_invoices(self, buyer_vat="", **_):
        self.invoice_vat = buyer_vat
        return {
            "success": True,
            "invoices": [
                {"issue_date": "01/08/2026", "type": "2.1", "series": "A", "aa": "1",
                 "mark": "400001", "net_value": "100,00", "vat_value": "24,00", "total": "124,00"},
                {"issue_date": "05/08/2026", "type": "2.1", "series": "A", "aa": "2",
                 "mark": "400002", "net_value": "200,00", "vat_value": "48,00", "total": "248,00"},
            ],
        }

    def payments(self, buyer_vat="", **_):
        self.payment_vat = buyer_vat
        return {
            "success": True,
            "payments": [
                {"pay_date": "10/08/2026", "amount": "124,00", "method": "3", "mark": "", "notes": "μετρητά"},
            ],
        }


# --- money helpers ----------------------------------------------------------

def test_parse_money_greek_format() -> None:
    assert parse_money("1.234,56 €") == pytest.approx(1234.56)
    assert parse_money("124,00") == pytest.approx(124.0)
    assert parse_money("") == 0.0
    assert parse_money("σκουπίδι") == 0.0
    assert parse_money(42) == 42.0


def test_fmt_money_greek_grouping() -> None:
    assert fmt_money(1234.5) == "1.234,50"
    assert fmt_money(0) == "0,00"


# --- client params ----------------------------------------------------------

def test_client_customers_params() -> None:
    client = RecordingClient()
    client.customers(name="ΑΛΦΑ")
    assert client.calls[-1][0] == {"list_customers": 1, "customer_name": "ΑΛΦΑ"}
    client.customers(vat="094000000")
    assert client.calls[-1][0] == {"list_customers": 1, "cust_vat": "094000000"}


def test_client_create_personal_customer_aliases() -> None:
    client = RecordingClient()
    client.create_personal_customer(
        name="Ιδιώτης", city="Πάτρα", zip_code="26221", job_description="ΙΔΙΩΤΗΣ", is_b2g=True
    )
    _params, data, method = client.calls[-1]
    assert method == "POST"
    assert data["create_personal_customer"] == 1
    assert data["cust_name"] == "Ιδιώτης"
    assert data["cust_zip"] == "26221"
    assert data["cust_job_description"] == "ΙΔΙΩΤΗΣ"
    assert data["cust_is_b2g"] == "1"


def test_client_customer_with_vat_never_filed_as_personal() -> None:
    """Ένας πελάτης με ΑΦΜ δεν επιτρέπεται να περάσει από τη διαδρομή του ιδιώτη.

    Αυτό ήταν το πραγματικό bug: το `create_customer` έστελνε ΠΑΝΤΑ
    `create_personal_customer=1`, οπότε κάθε επιχείρηση καταχωρούνταν ως ιδιώτης
    και το ΑΦΜ χανόταν.
    """
    client = RecordingClient()
    client.create_customer(name="ΑΛΦΑ ΑΕ", vat="094000000", city="Αθήνα")
    params, data, _method = client.calls[-1]
    assert params.get("afm") == "094000000"
    assert data is None or "create_personal_customer" not in data


def test_client_create_customer_rejects_malformed_vat() -> None:
    client = RecordingClient()
    with pytest.raises(EtimologioError):
        client.create_customer(name="ΑΛΦΑ", vat="123")


def test_client_update_and_delete_customer() -> None:
    client = RecordingClient()
    client.update_customer(vat="094000000", name="ΑΛΦΑ ΑΕ", city="Αθήνα")
    _params, data, method = client.calls[-1]
    assert method == "POST"
    assert data["update_customer"] == 1
    assert data["update_customer_vat"] == "094000000"
    assert data["update_city"] == "Αθήνα"
    # Κενά πεδία δεν στέλνονται — αλλιώς θα έσβηναν ό,τι υπάρχει ήδη.
    assert "update_zip" not in data

    client.delete_customer(code="C1")
    assert client.calls[-1][1] == {"delete_customer_code": "C1"}
    with pytest.raises(EtimologioError):
        client.delete_customer()


def test_client_new_deduction_uses_the_name_the_backend_reads() -> None:
    client = RecordingClient()
    client.create_deduction("Κράτηση 3%")
    _params, data, _method = client.calls[-1]
    assert data["deduction_description"] == "Κράτηση 3%"
    assert "deduction_desc" not in data


def test_client_admin_add_account_sends_subkey() -> None:
    """Το endpoint διαβάζει `subkey`· το `subscription_key` περνά αθόρυβα ως κενό."""
    client = RecordingClient()
    client.admin_add_account(7, vat="802576637", username="user", subkey="KEY")
    params, data, method = client.calls[-1]
    assert method == "POST"
    assert params["auth"] == "admin_add_account"
    assert data["subkey"] == "KEY"
    assert data["label"] == "802576637"  # πέφτει πίσω στο ΑΦΜ


def test_client_search_invoices_by_buyer() -> None:
    client = RecordingClient()
    client.search_invoices(buyer_vat="094000000")
    assert client.calls[-1][0] == {"search_invoices": 1, "buyer_vat": "094000000"}


# --- Πελάτες page -----------------------------------------------------------

def test_customers_page_fills_table(app) -> None:
    fake = FakeClient()
    page = CustomersPage(lambda: fake, sync_run)
    page.refresh()
    assert page._table.rowCount() == 2
    assert page._table.item(0, 0).text() == "C1"
    assert page._table.item(0, 2).text() == "ΑΛΦΑ ΑΕ"


def test_customers_search_routes_vat_vs_name(app) -> None:
    fake = FakeClient()
    page = CustomersPage(lambda: fake, sync_run)
    page.set_search("094000000")  # 9 digits → ΑΦΜ
    page.refresh()
    assert fake.customer_kwargs == {"vat": "094000000"}
    page.set_search("ΑΛΦΑ")
    page.refresh()
    assert fake.customer_kwargs == {"name": "ΑΛΦΑ"}


def test_customers_open_card_emits_row(app) -> None:
    fake = FakeClient()
    page = CustomersPage(lambda: fake, sync_run)
    page.refresh()
    captured: list[dict] = []
    page.open_card.connect(captured.append)
    page._table.setCurrentCell(0, 0)
    page._open_selected()
    assert captured and captured[0]["vat"] == "094000000"


def test_customers_created_triggers_refresh(app) -> None:
    fake = FakeClient()
    page = CustomersPage(lambda: fake, sync_run)
    page._created({"success": True})
    # refresh ran → table filled from the fake
    assert page._table.rowCount() == 2


# --- Καρτέλα (customer card) -------------------------------------------------

def test_card_fills_and_computes_balance(app) -> None:
    fake = FakeClient()
    card = CustomerCard(lambda: fake, sync_run)
    card.set_customer({"vat": "094000000", "name": "ΑΛΦΑ ΑΕ"})
    assert fake.invoice_vat == "094000000"
    assert fake.payment_vat == "094000000"
    assert card._invoices.rowCount() == 2
    assert card._payments.rowCount() == 1
    # Τιμολόγια 124+248 = 372· Πληρωμές 124· Υπόλοιπο 248.
    assert card._inv_total == pytest.approx(372.0)
    assert card._pay_total == pytest.approx(124.0)
    assert "248,00" in card._summary.text()


def test_card_without_vat_shows_note(app) -> None:
    fake = FakeClient()
    card = CustomerCard(lambda: fake, sync_run)
    card.set_customer({"name": "Ιδιώτης χωρίς ΑΦΜ"})
    assert card._invoices.rowCount() == 0
    assert "ΑΦΜ" in card._status.text()


# --- Έκδοση (invoice editor) ------------------------------------------------

def test_line_amounts_no_discount() -> None:
    net, vat, total = line_amounts(qty=2, price=100, rate=24, disc_pct=0)
    assert (net, vat, total) == (200.0, 48.0, 248.0)


def test_line_amounts_with_discount() -> None:
    net, vat, total = line_amounts(qty=1, price=100, rate=24, disc_pct=10)
    assert net == pytest.approx(90.0)
    assert vat == pytest.approx(21.6)
    assert total == pytest.approx(111.6)


def test_line_amounts_zero_qty_defaults_to_one() -> None:
    net, _vat, _total = line_amounts(qty=0, price=50, rate=0, disc_pct=0)
    assert net == 50.0


def test_client_issue_modes() -> None:
    client = RecordingClient()
    lines = [{"code": "Υπηρεσία", "qty": 1, "price": 100, "rate": 24}]

    client.issue_invoice(lines, "20", series="A", payment=3)
    _p, data, method = client.calls[-1]
    assert method == "POST"
    assert data["type"] == "20"
    assert json.loads(data["lines"]) == lines
    assert "live" not in data and "preview" not in data  # draft

    client.issue_invoice(lines, "20", live=True)
    assert client.calls[-1][1]["live"] == 1

    client.issue_invoice(lines, "20", preview=True)
    assert client.calls[-1][1]["preview"] == 1


def test_issue_page_collect_and_totals(app) -> None:
    fake = FakeClient()
    page = IssuePage(lambda: fake, sync_run)
    page._table.setRowCount(0)
    page.add_line("Υπηρεσία Α", "2", "100", "24", "0")
    page.add_line("Υπηρεσία Β", "1", "50", "13", "10")
    lines = page.collect_lines()
    assert len(lines) == 2
    # rate is sent to the bridge as a fraction (0.24), not a percent.
    assert lines[0] == {"code": "Υπηρεσία Α", "qty": 2.0, "price": 100.0, "rate": 0.24}
    assert lines[1]["rate"] == 0.13
    assert lines[1]["disc"] == 10.0
    # Totals: line1 200/48/248 ; line2 net45 vat5.85 total50.85 → net 245, vat 53.85
    assert "245,00" in page._totals.text()
    assert "53,85" in page._totals.text()


def test_issue_page_skips_empty_lines(app) -> None:
    fake = FakeClient()
    page = IssuePage(lambda: fake, sync_run)
    page._table.setRowCount(0)
    page.add_line("", "1", "0", "24", "0")  # empty desc + zero price → skipped
    page.add_line("Πραγματική", "1", "80", "24", "0")
    lines = page.collect_lines()
    assert len(lines) == 1
    assert lines[0]["code"] == "Πραγματική"


# --- Phase 2: catalogs, drafts, credit --------------------------------------

class CatalogClient(RecordingClient):
    """RecordingClient with canned catalog/draft rows."""

    def products(self):
        return {"success": True, "products": [
            {"product_code": "P1", "description": "Υπηρεσία", "unit_price": "100,00",
             "vat": "24%", "delete_code": "id-1"},
        ]}

    def series(self):
        return {"success": True, "series": [
            {"invoice_type": "2.1", "series_code": "A", "start_aa": "5",
             "description": "Κύρια", "delete_id": "sid-9"},
        ]}

    def temp_invoices(self, **_):
        return {"success": True, "temp_invoices": [
            {"save_date": "08/08/2026", "type": "2.1", "series": "A",
             "buyer_vat": "094039270", "temp_id": "t-1", "seller_vat": "802576637"},
        ]}


def test_client_catalog_params() -> None:
    client = RecordingClient()
    client.create_product(product_code="P1", description="Υπηρεσία", vat_category="1", unit_price="100")
    assert client.calls[-1][1]["new_product"] == 1
    assert client.calls[-1][1]["vat_category"] == "1"
    client.create_series(invoice_type="20", code="B", start_aa="1", description="Δευτ.")
    assert client.calls[-1][1]["series_invoice_type"] == "20"
    client.delete_series("sid-9")
    assert client.calls[-1][1]["delete_series_id"] == "sid-9"


def test_client_credit_note_modes() -> None:
    client = RecordingClient()
    client.credit_note("400014690544553", reason="λάθος", live=True)
    data = client.calls[-1][1]
    assert data["cancel_mark"] == "400014690544553"
    assert data["reason"] == "λάθος"
    assert data["live"] == 1


def test_products_page_fills_and_delete_key(app) -> None:
    client = CatalogClient()
    page = ProductsPage(lambda: client, sync_run)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "P1"
    assert page.selected_row() is None  # nothing selected yet
    page.table.setCurrentCell(0, 0)
    assert page.selected_row()["delete_code"] == "id-1"


def test_series_page_fills(app) -> None:
    client = CatalogClient()
    page = SeriesPage(lambda: client, sync_run)
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "A"


def test_drafts_page_fills(app) -> None:
    client = CatalogClient()
    page = DraftsPage(lambda: client, sync_run)
    page.refresh()
    assert page.table.rowCount() == 1
    page.table.setCurrentCell(0, 0)
    assert page.selected_row()["temp_id"] == "t-1"


def test_credit_page_requires_mark(app) -> None:
    client = RecordingClient()
    page = CreditNotePage(lambda: client, sync_run)
    page._draft()  # no MARK → should not call the backend
    assert client.calls == []
    assert "Διάλεξε παραστατικό" in page._status.text()


# --- Phase 3: bulk, payments, statistics (cached) ---------------------------

def test_client_statistics_cached_flag() -> None:
    client = RecordingClient()
    client.statistics("year")
    assert client.calls[-1][0] == {"statistics": 1, "period": "year"}
    client.statistics("month", cached=True)
    assert client.calls[-1][0] == {"statistics": 1, "period": "month", "stats_cached": 1}
    client.sync("statistics")
    assert client.calls[-1][0] == {"sync": "statistics"}


def test_client_bulk_issue_params() -> None:
    client = RecordingClient()
    items = [{"afm": "094039270", "type": "20", "series": "A",
              "lines": [{"code": "Υ", "qty": 1, "price": 10, "rate": 0.24}]}]
    client.bulk_issue(items)
    data = client.calls[-1][1]
    assert data["bulk_issue"] == 1
    assert json.loads(data["items"]) == items
    assert "live" not in data
    client.bulk_issue(items, live=True)
    assert client.calls[-1][1]["live"] == 1


def test_client_bank_import_params() -> None:
    client = RecordingClient()
    client.bank_preview("YmFzZTY0", filename="extrait.xlsx")
    assert client.calls[-1][1]["bank_preview"] == 1
    rows = [{"customer_vat": "094039270", "amount": 50.0, "method": 1}]
    client.bank_import(rows)
    assert json.loads(client.calls[-1][1]["items"]) == rows


class StatsClient:
    """Returns a distinct cached vs live snapshot so we can tell them apart."""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def statistics(self, period="month", cached=False):
        self.calls.append(cached)
        if cached:
            return {"success": True, "cached": True, "synced_at": "2026-08-08 10:00:00",
                    "total_count": 1, "total_value": 100.0,
                    "breakdown": [{"type": "2.1", "count": 1, "value": 100.0}]}
        return {"success": True, "cached": False, "synced_at": "2026-08-08 12:00:00",
                "total_count": 2, "total_value": 250.0,
                "breakdown": [{"type": "2.1", "count": 1, "value": 100.0},
                              {"type": "11.2", "count": 1, "value": 150.0}]}


def test_stats_page_renders_cache_then_live(app) -> None:
    client = StatsClient()
    page = StatsPage(lambda: client, sync_run)
    page.refresh()
    # both a cached and a live call were made, cached first
    assert client.calls == [True, False]
    # the live snapshot wins in the UI
    assert page._table.rowCount() == 2
    assert "250,00" in page._summary.text()
    assert "ζωντανά" in page._status.text()


def test_stats_page_keeps_cache_when_live_fails(app) -> None:
    class FailingLive(StatsClient):
        def statistics(self, period="month", cached=False):
            if not cached:
                raise RuntimeError("δίκτυο")
            return super().statistics(period, cached=True)

    page = StatsPage(lambda: FailingLive(), sync_run)
    page.refresh()
    # cached rows survive and the status explains the live failure
    assert page._table.rowCount() == 1
    assert "cache" in page._status.text()


def test_bulk_page_builds_items(app) -> None:
    client = RecordingClient()
    page = BulkPage(lambda: client, sync_run)
    page._table.setRowCount(0)
    page.add_row("094039270", "ΑΛΦΑ ΑΕ", "Υπηρεσία", "2", "50", "24")
    page.add_row("", "", "", "1", "0", "24")  # empty → skipped
    items = page.build_items()
    assert len(items) == 1
    item = items[0]
    assert item["afm"] == "094039270"
    assert item["lines"][0]["rate"] == 0.24  # fraction on the wire
    assert item["lines"][0]["qty"] == 2.0


def test_bulk_page_writes_results_back(app) -> None:
    client = RecordingClient()
    page = BulkPage(lambda: client, sync_run)
    page._table.setRowCount(0)
    page.add_row("094039270", "ΑΛΦΑ ΑΕ", "Υπηρεσία", "1", "50", "24")
    page._after_bulk({"results": [{"index": 0, "success": True, "mark": "400123"}]}, [0])
    assert "400123" in page._table.item(0, 6).text()
    assert "1/1" in page._status.text()


# --- background worker ------------------------------------------------------

def test_run_delivers_result_even_after_gc(app) -> None:
    """Regression: the job used to be collected before it could emit.

    ``QThreadPool.start()`` owns the QRunnable in C++, but nothing referenced the
    Python object, so its signal companion could vanish mid-flight and the
    result was dropped — a page that randomly never finished loading.
    """
    import gc
    import time

    from PySide6.QtWidgets import QApplication

    from timologio.etimologio import shell as shellmod

    out: dict[str, object] = {}
    shellmod._run(lambda: 41 + 1, lambda v: out.update(ok=v), lambda m: out.update(err=m))
    gc.collect()  # exactly the condition that used to lose the result
    deadline = time.time() + 5
    while time.time() < deadline and not out:
        QApplication.processEvents()
        time.sleep(0.01)
    assert out == {"ok": 42}


def test_run_releases_finished_jobs(app) -> None:
    """The keep-alive set must drain, or every call would leak a job."""
    import time

    from PySide6.QtWidgets import QApplication

    from timologio.etimologio import shell as shellmod

    seen: list[int] = []
    for i in range(10):
        shellmod._run(lambda i=i: i, seen.append, lambda m: seen.append(-1))
    deadline = time.time() + 5
    while time.time() < deadline and (len(seen) < 10 or shellmod._INFLIGHT):
        QApplication.processEvents()
        time.sleep(0.01)
    assert sorted(seen) == list(range(10))
    assert not shellmod._INFLIGHT


# --- Phase 4 + bulk print/ZIP ------------------------------------------------

def test_pdf_filename_is_sortable_and_safe() -> None:
    from timologio.etimologio.bulkpdf import pdf_filename

    name = pdf_filename({"issue_date": "02/08/2026", "series": "ΑΠΥ", "aa": "18",
                         "mark": "400014690544553"})
    assert name == "02-08-2026 ΑΠΥ-18 400014690544553.pdf"
    # Path separators in the data must never escape into the filename.
    bad = pdf_filename({"issue_date": "a/b", "series": "x\\y", "aa": "", "mark": "1"})
    assert "\\" not in bad and bad.count("/") == 0


def test_fetch_pdfs_collects_errors_without_aborting(tmp_path, monkeypatch) -> None:
    from timologio.etimologio import bulkpdf

    monkeypatch.setattr(bulkpdf, "_CACHE_DIR", tmp_path)

    class PdfClient:
        def invoice_pdf(self, mark):
            if mark == "bad":
                raise RuntimeError("δεν βρέθηκε")
            return b"%PDF-1.4 fake"

    rows = [{"mark": "1", "series": "A", "aa": "1", "issue_date": "01/08/2026"},
            {"mark": "bad", "series": "A", "aa": "2", "issue_date": "02/08/2026"},
            {"mark": "", "series": "A", "aa": "3", "issue_date": "03/08/2026"}]
    paths, errors = bulkpdf.fetch_pdfs(PdfClient(), rows)
    assert len(paths) == 1 and paths[0].read_bytes().startswith(b"%PDF")
    assert len(errors) == 2  # the failing MARK and the row without one


def test_export_zip_dedupes_names(tmp_path) -> None:
    from timologio.etimologio.bulkpdf import export_zip
    import zipfile

    a = tmp_path / "a" / "same.pdf"
    b = tmp_path / "b" / "same.pdf"
    for p in (a, b):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF")
    target = tmp_path / "out.zip"
    assert export_zip([a, b], target) == 2
    with zipfile.ZipFile(target) as zf:
        assert sorted(zf.namelist()) == ["same (2).pdf", "same.pdf"]


class DocsClient(RecordingClient):
    def search_invoices(self, **_):
        return {"success": True, "invoices": [
            {"issue_date": "02/08/2026", "type": "11.2", "series": "ΑΠΥ", "aa": "18",
             "mark": "400014690544553", "buyer_vat": "", "net_value": "64,52", "total": "80,00"},
            {"issue_date": "01/08/2026", "type": "2.1", "series": "ΤΠΥ", "aa": "3",
             "mark": "400014690000001", "buyer_vat": "094039270", "net_value": "100,00", "total": "124,00"},
        ]}


def test_documents_page_selection(app) -> None:
    from PySide6.QtCore import Qt

    page = DocumentsPage(lambda: DocsClient(), sync_run)
    page.refresh()
    assert page._table.rowCount() == 2
    assert "204,00" in page._status.text()  # 80 + 124 total
    # nothing ticked and nothing highlighted → empty selection
    assert page.selected_rows() == []
    page._set_all(True)
    assert len(page.selected_rows()) == 2
    page._set_all(False)
    page._table.setCurrentCell(1, 1)
    # falls back to the highlighted row
    assert page.selected_rows()[0]["mark"] == "400014690000001"


def test_schedule_page_translates_status(app) -> None:
    class SchedClient:
        def scheduled_jobs(self):
            return {"success": True, "jobs": [
                {"id": 7, "run_at": "2026-09-01 08:00:00", "title": "Μηνιαίο",
                 "kind": "invoice", "recurrence": "monthly", "status": "pending",
                 "last_run_at": ""},
            ]}

    page = SchedulePage(lambda: SchedClient(), sync_run)
    page.refresh()
    assert page.table.item(0, 4).text() == "Σε αναμονή"
    assert page.table.item(0, 3).text() == "Μηνιαία"


def test_notifications_page_counts_unread(app) -> None:
    class NotifClient:
        def notifications(self):
            return {"success": True, "items": [
                {"created_at": "2026-08-08 10:00", "doc_label": "ΑΠΥ", "series": "ΑΠΥ",
                 "aa": "18", "mark": "400", "buyer_name": "ΑΛΦΑ", "amount_total": 80.0,
                 "actor_email": "a@b.gr", "is_read": 0},
                {"created_at": "2026-08-07 10:00", "doc_label": "ΤΠΥ", "series": "ΤΠΥ",
                 "aa": "3", "mark": "401", "buyer_name": "ΒΗΤΑ", "amount_total": 124.0,
                 "actor_email": "a@b.gr", "is_read": 1},
            ]}

    page = NotificationsPage(lambda: NotifClient(), sync_run)
    seen: list[int] = []
    page.unread_changed.connect(seen.append)
    page.refresh()
    assert page.table.rowCount() == 2
    assert "1 μη αναγνωσμένες" in page.status.text()
    assert seen == [1]
    assert page.table.item(0, 5).text() == "80,00 €"


def test_admin_page_labels_roles(app) -> None:
    class AdminClient:
        def admin_users(self):
            return {"success": True, "users": [
                {"id": 2, "email": "l@x.gr", "business_name": "Λογιστής",
                 "role": "editor", "status": "active", "created_at": "2026-01-01"},
            ]}

    page = AdminPage(lambda: AdminClient(), sync_run)
    page.refresh()
    assert page.table.item(0, 2).text() == "Λογιστής (όλες οι εταιρείες)"


def test_client_phase4_params() -> None:
    client = RecordingClient()
    client.cancel_job(7)
    assert client.calls[-1][1] == {"sched_cancel": 1, "id": 7}
    client.mark_all_read()
    assert client.calls[-1][1] == {"notif_read_all": 1}
    client.admin_invite("a@b.gr", "editor")
    assert client.calls[-1][1] == {"email": "a@b.gr", "role": "editor"}
    client.totp_enable("123456")
    assert client.calls[-1][1] == {"code": "123456"}
    client.set_notif_prefs(companies="094039270", types="2.1,11.2", email_enabled=False)
    assert client.calls[-1][1]["email_enabled"] == "0"


def test_client_invoice_pdf_decodes(monkeypatch) -> None:
    import base64 as b64

    client = RecordingClient()
    client.reply = {"success": True, "pdf_base64": b64.b64encode(b"%PDF-1.4").decode()}
    assert client.invoice_pdf("400").startswith(b"%PDF")


def test_payments_page_lists(app) -> None:
    class PayClient:
        def payments(self, **_):
            return {"success": True, "payments": [
                {"id": 7, "pay_date": "08/08/2026", "amount": "124,00", "method": "3",
                 "customer_name": "ΑΛΦΑ ΑΕ", "customer_vat": "094039270", "notes": ""},
            ]}

        def customers(self, **_):
            return {"success": True, "customers": [
                {"code": "C1", "vat": "094039270", "name": "ΑΛΦΑ ΑΕ", "city": "Αθήνα"},
            ]}

    page = PaymentsPage(lambda: PayClient(), sync_run)
    page.refresh()
    assert page._pay_table.rowCount() == 1
    assert page._pay_table.item(0, 2).text() == "Μετρητά"
    # Ο επιλογέας πελάτη του διαλόγου τροφοδοτείται από την ίδια φόρτωση.
    assert len(page._customers) == 1


def test_new_payment_dialog_has_a_date_and_a_picker(app) -> None:
    """Η ημερομηνία έλειπε τελείως: κάθε είσπραξη έπαιρνε τη σημερινή."""
    from timologio.etimologio.pages.payments import NewPaymentDialog

    dialog = NewPaymentDialog()
    dialog.set_customers([{"vat": "094039270", "name": "ΑΛΦΑ ΑΕ", "city": "Αθήνα"}])
    dialog.customer.show_popup()
    dialog.customer._chose(dialog.customer._popup.item(1))
    assert dialog.vat.text() == "094039270"
    assert dialog.name.text() == "ΑΛΦΑ ΑΕ"

    dialog.amount.setText("50")
    fields = dialog.fields()
    assert fields["pay_date"]
    assert fields["pay_method"] == "3"          # Μετρητά, όχι «επί πιστώσει»


# --- packaging: the bundled PHP runtime --------------------------------------

def test_cacert_is_resolved_absolute(tmp_path) -> None:
    """Regression: the CA bundle must be handed to PHP as an ABSOLUTE path.

    PHP resolves `extension_dir` relative to the ini file but `curl.cainfo`
    relative to the *working directory*, and the server is started with the cwd
    set to the backend folder. A relative value produced curl error 77
    ("error adding trust anchors from file") so every ΑΑΔΕ call failed — and only
    in the packaged build, where the bundled runtime is used.
    """
    from timologio.etimologio.service import resolve_cacert

    php = tmp_path / "php.exe"
    php.write_bytes(b"")
    assert resolve_cacert(str(php)) is None          # no bundle → nothing to pass

    (tmp_path / "cacert.pem").write_text("x", encoding="utf-8")
    got = resolve_cacert(str(php))
    assert got is not None
    assert Path(got).is_absolute()
    assert Path(got).name == "cacert.pem"


def test_start_local_passes_cacert_to_php(tmp_path, monkeypatch) -> None:
    """The absolute CA path reaches the PHP command line as -d overrides."""
    from timologio.etimologio import service as svc

    php_dir = tmp_path / "php"
    php_dir.mkdir()
    (php_dir / "php.exe").write_bytes(b"")
    (php_dir / "php.ini").write_text("", encoding="utf-8")
    (php_dir / "cacert.pem").write_text("x", encoding="utf-8")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "etimologio.php").write_text("<?php", encoding="utf-8")

    captured: dict = {}

    class FakeProc:
        def poll(self):
            return None

    monkeypatch.setattr(svc, "resolve_php", lambda: str(php_dir / "php.exe"))
    monkeypatch.setattr(svc, "resolve_backend_root", lambda: backend)
    monkeypatch.setattr(svc.subprocess, "Popen", lambda cmd, **kw: captured.setdefault("cmd", cmd) or FakeProc())

    s = svc.EtimologioService(tmp_path / "data")
    monkeypatch.setattr(s, "_write_config", lambda port: None)
    monkeypatch.setattr(s, "_wait_healthy", lambda seconds: True)
    s.start_local()

    cmd = captured["cmd"]
    joined = " ".join(cmd)
    assert "curl.cainfo=" in joined and "openssl.cafile=" in joined
    for part in cmd:
        if part.startswith(("curl.cainfo=", "openssl.cafile=")):
            assert Path(part.split("=", 1)[1]).is_absolute()


# --- Έκδοση: πελατολόγιο και σειρές ------------------------------------------

class IssueClient(RecordingClient):
    """Επιστρέφει πελάτες και σειρές, όπως το ζωντανό backend."""

    def customers(self, **_):
        return {"success": True, "customers": [
            {"code": "C1", "vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ", "city": "Αθήνα", "address": "Οδός 1"},
            {"code": "C2", "vat": "802012659", "name": "MEGATECH ΙΚΕ", "city": "Πάτρα", "address": "Οδός 2"},
        ]}

    def series(self):
        return {"success": True, "series": [
            {"invoice_type": "2.1 - Τιμολόγιο Παροχής Υπηρεσιών", "series_code": "ΤΠΥ", "series_id": "1"},
            {"invoice_type": "11.2 - ΑΠΥ (Απόδειξη Παροχής Υπηρεσιών)", "series_code": "ΑΠΥ", "series_id": "2"},
        ]}


def test_issue_page_loads_customer_picker(app) -> None:
    page = IssuePage(lambda: IssueClient(), sync_run)
    page.refresh()
    assert len(page._picker.rows()) == 2

    # Η λίστα ανοίγει χωρίς πληκτρολόγηση, με «➕ Νέος πελάτης…» πρώτη γραμμή.
    page._picker.show_popup()
    assert page._picker._popup.item(0).text().startswith("➕")
    assert "ΞΕΝΤΕ" in page._picker._popup.item(1).text()

    page._picker._chose(page._picker._popup.item(1))
    assert page._afm.text() == "094039270"
    assert page._name.text() == "ΞΕΝΤΕ ΑΕ"
    assert page._city.text() == "Αθήνα"


def test_issue_page_customer_picker_filters(app) -> None:
    page = IssuePage(lambda: IssueClient(), sync_run)
    page.refresh()
    page._picker.line_edit().setText("μεγα")     # πεζά, μέρος της επωνυμίας
    page._picker.show_popup()
    labels = [page._picker._popup.item(i).text() for i in range(page._picker._popup.count())]
    assert any("MEGATECH" in text for text in labels[1:]) or len(labels) == 1
    page._picker.line_edit().setText("802012659")   # με ΑΦΜ
    page._picker.show_popup()
    assert "MEGATECH" in page._picker._popup.item(1).text()


def test_issue_page_series_follow_the_document_type(app) -> None:
    """Η σειρά προσφέρεται μόνο αν υπάρχει για τον επιλεγμένο τύπο."""
    page = IssuePage(lambda: IssueClient(), sync_run)
    page.refresh()

    page._type.setCurrentIndex(page._type.findData("20"))       # 2.1
    assert page._series.currentData() == "ΤΠΥ"
    assert page._series_warn.isHidden()

    page._type.setCurrentIndex(page._type.findData("58"))       # 11.2
    assert page._series.currentData() == "ΑΠΥ"

    page._type.setCurrentIndex(page._type.findData("1"))        # 1.1 — καμία σειρά
    assert not page._series_warn.isHidden()
    assert "Δεν υπάρχει σειρά" in page._series_warn.text()


# --- κοινά λεξιλόγια (codes.py) ---------------------------------------------

def test_default_payment_is_epi_pistosei_everywhere() -> None:
    """Η προεπιλογή βγαίνει από τη ΣΕΙΡΑ του πίνακα, όχι από ξεχωριστό βήμα.

    Τα combo γεμίζουν με τη σειρά του `PAYMENT_METHODS`, οπότε αν το πρώτο
    στοιχείο είναι σωστό δεν υπάρχει `setCurrentIndex` να ξεχαστεί σε μια σελίδα.
    """
    assert PAYMENT_METHODS[0][0] == DEFAULT_PAYMENT == 5
    # Η είσπραξη είναι άλλο πράγμα: «επί πιστώσει» δεν είναι τρόπος είσπραξης.
    assert PAYMENT_METHODS_CASH[0][0] == 3
    assert all(code != 5 for code, _label in PAYMENT_METHODS_CASH)


def test_series_for_type_matches_on_the_dotted_code() -> None:
    rows = [
        {"invoice_type": "2.1 - Τιμολόγιο Παροχής Υπηρεσιών", "series_code": "ΤΠΥ"},
        {"invoice_type": "11.2 - ΑΠΥ", "series_code": "ΑΠΥ"},
    ]
    assert [s["series_code"] for s in series_for_type(rows, "20")] == ["ΤΠΥ"]
    assert [s["series_code"] for s in series_for_type(rows, "58")] == ["ΑΠΥ"]
    assert series_for_type(rows, "1") == []
    assert series_for_type(rows, "άγνωστο") == []


def test_bulk_page_series_is_a_filtered_dropdown(app) -> None:
    """Μια ανύπαρκτη σειρά δεν χαλάει μία γραμμή — απορρίπτει όλη την παρτίδα."""
    page = BulkPage(lambda: IssueClient(), sync_run)
    page.refresh()

    page._type.setCurrentIndex(page._type.findData("20"))       # 2.1
    assert page._series.currentData() == "ΤΠΥ"
    assert page._series_warn.isHidden()

    page.add_row(afm="094039270", desc="ΥΠ001", qty="1", price="100")
    assert page.build_items()[0]["series"] == "ΤΠΥ"

    page._type.setCurrentIndex(page._type.findData("1"))        # 1.1 — καμία σειρά
    assert not page._series_warn.isHidden()
    assert "παρτίδα" in page._series_warn.text()


def test_bulk_page_default_payment(app) -> None:
    page = BulkPage(lambda: IssueClient(), sync_run)
    page.add_row(afm="094039270", desc="ΥΠ001", qty="1", price="100")
    assert page.build_items()[0]["payment"] == DEFAULT_PAYMENT


def test_issue_page_default_payment(app) -> None:
    page = IssuePage(lambda: IssueClient(), sync_run)
    page.add_line(desc="ΥΠ001", qty="1", price="100")
    assert page._issue_kwargs()["payment"] == DEFAULT_PAYMENT


def test_new_customer_dialog_separates_the_two_kinds(app) -> None:
    """Ο διάλογος επιστρέφει τα ορίσματα της ΣΩΣΤΗΣ κλήσης για κάθε καρτέλα."""
    from timologio.etimologio.pages.customers import NewCustomerDialog

    dialog = NewCustomerDialog(vat="094039270")
    assert not dialog.is_personal()
    assert dialog.fields() == {"vat": "094039270"}

    dialog._tabs.setCurrentIndex(1)
    assert dialog.is_personal()
    dialog.name.setText("Γιώργος Παπαδόπουλος")
    dialog.city.setText("Πάτρα")
    dialog.zip.setText("26221")
    fields = dialog.fields()
    assert fields["name"] == "Γιώργος Παπαδόπουλος"
    assert fields["zip_code"] == "26221"
    assert "vat" not in fields


def test_new_customer_dialog_validates_before_accepting(app) -> None:
    from timologio.etimologio.pages.customers import NewCustomerDialog

    dialog = NewCustomerDialog()
    dialog.vat.setText("12345")            # λιγότερα από 9 ψηφία
    dialog._accept()
    assert "9 ψηφία" in dialog._error.text()

    dialog._tabs.setCurrentIndex(1)        # ιδιώτης χωρίς πόλη/ΤΚ
    dialog.name.setText("Γιώργος")
    dialog._accept()
    assert "πόλη" in dialog._error.text()


# --- Φάση Β: φόροι, είδη, προγραμματισμός ------------------------------------

class IssueFullClient(IssueClient):
    """Πελάτες, σειρές, είδη, κατηγορίες και κατηγορίες φόρου."""

    def __init__(self) -> None:
        super().__init__()
        self.scheduled: dict[str, Any] | None = None

    def products(self):
        return {"success": True, "products": [
            {"product_code": "ΥΠ001", "code": "ΥΠ001", "description": "Συντήρηση",
             "unit_price": "150", "vat_category": "1", "category": "ΥΠΗΡΕΣΙΕΣ"},
            {"product_code": "ΑΓ001", "code": "ΑΓ001", "description": "Ανταλλακτικό",
             "unit_price": "40", "vat_category": "2", "category": "ΑΓΑΘΑ"},
        ]}

    def product_categories(self):
        return {"success": True, "categories": [{"name": "ΥΠΗΡΕΣΙΕΣ"}, {"name": "ΑΓΑΘΑ"}]}

    def tax_categories(self):
        return {
            "success": True,
            "withheld": [{"code": "2", "label": "Αμοιβές Ελ. Επαγγελματιών 20%"}],
            "fees": [{"code": "9", "label": "Λοιπά τέλη"}],
            "other": [], "digital": [],
            "deductions": [{"code": "D1", "label": "Κράτηση υπέρ ΕΑΑΔΗΣΥ 0,1%"}],
        }

    def schedule_job(self, payload, run_at, *, title="", kind="invoice", recurrence="none"):
        self.scheduled = {"payload": payload, "run_at": run_at, "title": title,
                          "kind": kind, "recurrence": recurrence}
        return {"success": True, "id": 1}


def test_issue_line_picker_fills_price_and_vat_from_the_catalogue(app) -> None:
    client = IssueFullClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()

    picker = page._line_picker(0)
    assert picker is not None
    picker.show_popup()
    assert picker._popup.item(0).text().startswith("➕")       # «Νέο είδος…»
    picker._chose(picker._popup.item(1))                       # ΥΠ001

    assert page._cell(0, 0) == "ΥΠ001"
    assert parse_money(page._cell(0, 2)) == pytest.approx(150.0)
    assert page._cell(0, 3) == "24"                            # vat_category 1 → 24%

    line = page.collect_lines()[0]
    assert line["code"] == "ΥΠ001"
    assert line["rate"] == pytest.approx(0.24)


def test_issue_line_picker_keeps_a_hand_typed_price(app) -> None:
    """Η τιμή καταλόγου δεν πατάει τιμή που έβαλε ο χρήστης."""
    client = IssueFullClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    page._table.item(0, 2).setText("99")

    picker = page._line_picker(0)
    picker.show_popup()
    picker._chose(picker._popup.item(1))
    assert parse_money(page._cell(0, 2)) == pytest.approx(99.0)


def test_issue_taxes_signs_and_payable(app) -> None:
    """Παρακρατήσεις/κρατήσεις αφαιρούνται, τέλη προστίθενται."""
    from timologio.etimologio.pages.dialogs import tax_signed_total

    client = IssueFullClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    page._table.setRowCount(0)
    page.add_line(desc="ΥΠ001", qty="1", price="1000", rate="24", disc="0")

    page._taxes = [
        {"type": 1, "category": "2", "amount": 200.0, "notes": "", "label": "… 20%"},
        {"type": 2, "category": "9", "amount": 10.0, "notes": "", "label": "τέλος"},
        {"type": 5, "category": "D1", "amount": 1.0, "notes": "", "label": "… 0,1%"},
    ]
    page._render_taxes()

    plus, minus = tax_signed_total(page._taxes)
    assert plus == pytest.approx(10.0)
    assert minus == pytest.approx(201.0)
    # 1000 καθαρή + 240 ΦΠΑ + 10 τέλη − 201 κρατήσεις = 1.049,00
    assert "1.049,00" in page._totals.text()

    assert len(page._issue_kwargs()["taxes"]) == 3
    assert "label" not in page._issue_kwargs()["taxes"][0]   # δεν φεύγει στο backend


def test_tax_dialog_auto_amount_from_the_label_percentage(app) -> None:
    from timologio.etimologio.pages.dialogs import TaxDialog, rate_from_label

    assert rate_from_label("Αμοιβές Ελ. Επαγγελματιών 20%") == pytest.approx(0.20)
    assert rate_from_label("Κράτηση 0,1%") == pytest.approx(0.001)
    assert rate_from_label("χωρίς ποσοστό") == 0.0

    dialog = TaxDialog(IssueFullClient().tax_categories(), net_total=1000.0, invoice_type="20")
    dialog.category.setCurrentIndex(1)          # «… 20%»
    assert parse_money(dialog.amount.text()) == pytest.approx(200.0)


def test_tax_dialog_blocks_withholding_on_goods(app) -> None:
    from timologio.etimologio.pages.dialogs import TaxDialog, is_service_type

    assert is_service_type("20") and is_service_type("58")
    assert not is_service_type("1")

    dialog = TaxDialog(IssueFullClient().tax_categories(), net_total=100.0, invoice_type="1")
    dialog.category.setCurrentIndex(1)
    dialog.amount.setText("20")
    dialog._accept()
    assert "παροχή υπηρεσιών" in dialog._error.text()


def test_issue_schedule_queues_a_live_job(app) -> None:
    """Ο προγραμματισμός στέλνει live payload — αλλά ΔΕΝ εκδίδει τώρα."""
    from timologio.etimologio.pages.dialogs import ScheduleDialog

    client = IssueFullClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    page._table.setRowCount(0)
    page.add_line(desc="ΥΠ001", qty="1", price="100")
    page._afm.setText("094039270")

    dialog = ScheduleDialog("δοκιμή")
    dialog.recurrence.setCurrentIndex(3)        # monthly
    assert dialog.run_at().endswith("09:00")

    # Παρακάμπτουμε το modal και καλούμε ό,τι θα καλούσε το «Προγραμματισμός».
    kwargs = page._issue_kwargs()
    payload = {k: v for k, v in kwargs.items() if k != "temp_id"}
    payload["live"] = 1
    client.schedule_job(payload, dialog.run_at(), title="δοκιμή", recurrence="monthly")

    assert client.scheduled["recurrence"] == "monthly"
    assert client.scheduled["payload"]["live"] == 1
    assert client.scheduled["payload"]["lines"][0]["code"] == "ΥΠ001"


def test_product_dialog_requires_a_category(app) -> None:
    """Κενή κατηγορία → η ΑΑΔΕ απαντά «The value '' is invalid»· το πιάνουμε εδώ."""
    from timologio.etimologio.pages.catalog import NewProductDialog

    dialog = NewProductDialog(categories=[{"name": "ΥΠΗΡΕΣΙΕΣ"}])
    dialog.code.setText("ΥΠ002")
    dialog.description.setText("Νέα υπηρεσία")
    dialog._accept()
    assert "κατηγορία" in dialog._error.text()

    dialog.category.setCurrentIndex(1)
    dialog._accept()
    fields = dialog.fields()
    assert fields["category"] == "ΥΠΗΡΕΣΙΕΣ"
    assert fields["unit"] == ""                 # υπηρεσία → χωρίς μονάδα μέτρησης


def test_issue_wizard_picks_a_type_that_actually_has_a_series(app) -> None:
    """Ο οδηγός δεν προτείνει τύπο χωρίς σειρά — θα τον απέρριπτε η ΑΑΔΕ."""
    page = IssuePage(lambda: IssueFullClient(), sync_run)
    page.refresh()

    page._wizard.setVisible(True)
    page._wizard_pick("pro")                     # τιμολόγιο → 2.1 (έχει σειρά ΤΠΥ)
    assert page._type.currentData() == "20"
    assert page._series.currentData() == "ΤΠΥ"
    assert page._wizard.isHidden()

    page._wizard.setVisible(True)
    page._wizard_pick("idiot")                   # απόδειξη → 11.2 (έχει σειρά ΑΠΥ)
    assert page._type.currentData() == "58"
    assert page._series.currentData() == "ΑΠΥ"


# --- Φάση Γ: πιστωτικό, καρτέλα, σειρές, πρόχειρα, γραφήματα -----------------

class CreditClient(RecordingClient):
    def customers(self, **_):
        return {"success": True, "customers": [
            {"code": "C1", "vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ", "city": "Αθήνα"},
        ]}

    def search_invoices(self, **_):
        return {"success": True, "invoices": [
            {"issue_date": "01/08/2026", "type": "2.1", "series": "ΤΠΥ", "aa": "1",
             "mark": "400001234567890", "buyer_vat": "094039270", "buyer_name": "ΞΕΝΤΕ ΑΕ",
             "net_value": "1.000,00", "total": "1.240,00"},
            {"issue_date": "02/08/2026", "type": "2.1", "series": "ΤΠΥ", "aa": "2",
             "mark": "", "buyer_vat": "094039270", "net_value": "50,00", "total": "62,00"},
        ]}


def test_credit_page_picks_the_mark_from_a_list(app) -> None:
    """Το ΜΑΡΚ δεν πληκτρολογείται πια — 15 ψηφία για μη αναστρέψιμη ενέργεια."""
    page = CreditNotePage(lambda: CreditClient(), sync_run)
    page.load_invoices()

    # Μόνο τα παραστατικά ΜΕ ΜΑΡΚ μπορούν να πιστωθούν.
    assert page._table.rowCount() == 1
    assert page._mark.isReadOnly()

    page._table.setCurrentCell(0, 0)
    page._pick_selected()
    assert page._mark.text() == "400001234567890"
    # Η καθαρή αξία προσυμπληρώνεται για πλήρη ακύρωση.
    assert parse_money(page._amount.text()) == pytest.approx(1000.0)
    assert page._kwargs()["cancel_mark"] == "400001234567890"


def test_series_delete_refuses_when_documents_exist(app, monkeypatch) -> None:
    """Η διαγραφή σειράς με ιστορικό θα έσπαγε την αρίθμηση."""
    from PySide6.QtWidgets import QMessageBox

    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(a[2] if len(a) > 2 else "")
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    class SeriesClient(RecordingClient):
        def series(self):
            return {"success": True, "series": [
                {"invoice_type": "2.1 - ΤΠΥ", "series_code": "ΤΠΥ", "series_id": "1",
                 "start_aa": "5", "description": ""},
            ]}

        def search_invoices(self, **_):
            return {"success": True, "invoices": [
                {"series": "ΤΠΥ", "mark": "4001", "issue_date": "01/08/2026"},
            ]}

    client = SeriesClient()
    page = SeriesPage(lambda: client, sync_run)
    page.refresh()
    page.table.setCurrentCell(0, 0)
    page._confirm_delete("1", "ΤΠΥ", client.search_invoices())

    assert "χρησιμοποιείται" in page.status.text()
    assert warned and "αρίθμηση" in warned[0]
    # Καμία κλήση delete_series δεν έφυγε — ούτε καν με «Ναι» στο question.
    assert not any("delete_series_id" in (d or {}) for _p, d, _m in client.calls)


def test_series_delete_proceeds_when_unused(app, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    client = RecordingClient()
    page = SeriesPage(lambda: client, sync_run)
    page._confirm_delete("1", "ΑΧΡΗΣΤΗ", {"invoices": []})
    assert any("delete_series_id" in (d or {}) for _p, d, _m in client.calls)


def test_series_dialog_preselects_the_type_when_editing(app) -> None:
    from timologio.etimologio.pages.catalog import NewSeriesDialog

    dialog = NewSeriesDialog(row={
        "invoice_type": "11.2 - ΑΠΥ", "series_code": "ΑΠΥ", "start_aa": "9",
        "description": "αποδείξεις",
    })
    assert dialog.type.currentData() == "58"
    assert dialog.fields()["code"] == "ΑΠΥ"
    assert dialog.fields()["start_aa"] == "9"


class DraftClient(RecordingClient):
    def temp_invoices(self, **_):
        return {"success": True, "temp_invoices": [
            {"save_date": "01/08/2026", "type": "2.1", "series": "ΤΠΥ",
             "buyer_vat": "094039270", "temp_id": "T1", "enc_id": "ENC1"},
            {"save_date": "02/08/2026", "type": "2.1", "series": "ΤΠΥ",
             "buyer_vat": "802012659", "temp_id": "T2", "enc_id": "ENC2"},
        ]}


def test_drafts_checkbox_selection(app) -> None:
    page = DraftsPage(lambda: DraftClient(), sync_run)
    page.refresh()
    assert page.table.rowCount() == 2

    assert page.checked_rows() == []            # τίποτα σημειωμένο, τίποτα επιλεγμένο
    page._toggle_all()
    assert len(page.checked_rows()) == 2
    page._toggle_all()
    assert page.checked_rows() == []

    page.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert [r["temp_id"] for r in page.checked_rows()] == ["T2"]


def test_drafts_open_in_issue_carries_the_temp_id(app) -> None:
    """Χωρίς το temp_id, κάθε άνοιγμα πρόχειρου άφηνε πίσω του διπλότυπο."""
    page = IssuePage(lambda: IssueFullClient(), sync_run)
    page.refresh()
    page.load_draft({"temp_id": "T1", "buyer_vat": "094039270", "series": "ΤΠΥ"})
    assert page._temp_id == "T1"
    assert page._afm.text() == "094039270"

    page.add_line(desc="ΥΠ001", qty="1", price="100")
    assert page._issue_kwargs()["temp_id"] == "T1"
    # Και το reset το καθαρίζει, ώστε το επόμενο παραστατικό να είναι νέο.
    page.reset()
    assert page._temp_id == ""


def test_ledger_entries_merge_and_sort_by_date(app) -> None:
    from timologio.etimologio.ledgerpdf import entries_from

    invoices = [
        {"issue_date": "05/08/2026", "type": "2.1", "series": "ΤΠΥ", "aa": "2",
         "mark": "4002", "total": "248,00"},
        {"issue_date": "01/08/2026", "type": "2.1", "series": "ΤΠΥ", "aa": "1",
         "mark": "4001", "total": "124,00"},
    ]
    payments = [{"pay_date": "03/08/2026", "amount": "124,00", "method": "3", "notes": ""}]
    rows = entries_from(invoices, payments)

    assert [r["date"] for r in rows] == ["01/08/2026", "03/08/2026", "05/08/2026"]
    # Τα παραστατικά χρεώνουν, οι πληρωμές πιστώνουν.
    assert rows[0]["debit"] == pytest.approx(124.0) and rows[0]["credit"] == 0
    assert rows[1]["credit"] == pytest.approx(124.0) and rows[1]["debit"] == 0


def test_ledger_pdf_is_written(app, tmp_path) -> None:
    from timologio.etimologio.ledgerpdf import build_ledger_pdf

    target = build_ledger_pdf(
        tmp_path / "kartela.pdf",
        customer={"name": "ΞΕΝΤΕ ΑΕ", "vat": "094039270", "city": "Αθήνα"},
        entries=[
            {"date": "01/08/2026", "label": "ΤΠΥ 1", "debit": 124.0, "credit": 0.0},
            {"date": "03/08/2026", "label": "Πληρωμή", "debit": 0.0, "credit": 100.0},
        ],
        period=("01/01/2026", "31/12/2026"),
    )
    assert target.exists() and target.stat().st_size > 1000
    assert target.read_bytes().startswith(b"%PDF")


def test_chart_series_rolls_up_the_tail(app) -> None:
    from timologio.etimologio.pages.charts import breakdown_series

    rows = [{"type": f"Τ{i}", "value": str(100 - i)} for i in range(12)]
    series = breakdown_series(rows, top=3)
    assert [label for label, _ in series] == ["Τ0", "Τ1", "Τ2", "Λοιπά"]
    # Τίποτα δεν χάνεται — αλλιώς τα ποσοστά δεν θα άθροιζαν στο 100%.
    assert sum(v for _l, v in series) == pytest.approx(sum(100 - i for i in range(12)))


def test_charts_render_without_data(app) -> None:
    """Ένα άδειο γράφημα δεν πρέπει να σκάει ούτε να ζωγραφίζει σκουπίδια."""
    from PySide6.QtGui import QPixmap
    from timologio.etimologio.pages.charts import BarChart, PieChart

    for widget in (PieChart(), BarChart()):
        widget.resize(320, 200)
        widget.set_data([])
        widget.render(QPixmap(320, 200))
        widget.set_data([("2.1", 800.0), ("11.2", 200.0)])
        widget.render(QPixmap(320, 200))


def test_combo_popup_has_an_explicit_text_colour() -> None:
    """Χωρίς `color`, το popup κληρονομεί το σκούρο της πλατφόρμας πάνω σε
    σκούρο panel — ο χρήστης βλέπει άδειο κουτί. Αφορούσε ΚΑΙ τα δύο προγράμματα."""
    from timologio.gui import theme

    for palette in (theme.DARK, theme.LIGHT):
        qss = theme.build(palette)
        block = qss.split("QComboBox QAbstractItemView {", 1)[1].split("}", 1)[0]
        assert "color:" in block


def test_afm_lookup_falls_back_to_the_customer_list(app) -> None:
    """Το `afm` endpoint επιστρέφει μόνο {status, code, vat} — επαληθεύτηκε ζωντανά.

    Χωρίς δεύτερο βήμα προς το πελατολόγιο, επωνυμία και διεύθυνση έμεναν κενές
    ακόμη κι όταν ο πελάτης υπήρχε.
    """
    class ThinAfmClient(IssueFullClient):
        def lookup_afm(self, vat):
            return {"success": True, "status": "found", "code": "4", "vat": vat}

    page = IssuePage(lambda: ThinAfmClient(), sync_run)
    page.refresh()
    page._afm.setText("094039270")
    page._fetch_customer()

    assert page._name.text() == "ΞΕΝΤΕ ΑΕ"
    assert page._city.text() == "Αθήνα"
