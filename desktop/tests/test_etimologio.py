"""Tests για τις native σελίδες e-Τιμολόγιο Pro (Phase 1).

Χωρίς live ΑΑΔΕ: ο client αντικαθίσταται με fake και ο worker τρέχει σύγχρονα,
ώστε να ελέγξουμε (α) ότι τα client methods χτίζουν σωστά params και (β) ότι οι
σελίδες γεμίζουν πίνακες, εκπέμπουν signals και υπολογίζουν το υπόλοιπο.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from timologio.etimologio.client import EtimologioClient  # noqa: E402
from timologio.etimologio.pages import CustomerCard, CustomersPage  # noqa: E402
from timologio.etimologio.pages.base import fmt_money, parse_money  # noqa: E402


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


def test_client_create_customer_aliases() -> None:
    client = RecordingClient()
    client.create_customer(name="Ιδιώτης", vat="123", job_description="ΙΔΙΩΤΗΣ", is_b2g=True)
    _params, data, method = client.calls[-1]
    assert method == "POST"
    assert data["create_personal_customer"] == 1
    assert data["cust_name"] == "Ιδιώτης"
    assert data["cust_vat"] == "123"
    assert data["cust_job_description"] == "ΙΔΙΩΤΗΣ"
    assert data["cust_is_b2g"] == "1"


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
