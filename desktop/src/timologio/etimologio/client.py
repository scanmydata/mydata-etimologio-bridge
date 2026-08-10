"""HTTP client for the e-Τιμολόγιο Pro PHP API (``etimologio.php``).

One :class:`requests.Session` per client keeps the PHP login cookie, so the
native Qt UI behaves like a logged-in browser. No business logic lives here —
every method is a thin call to an endpoint the web UI already uses.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class EtimologioError(Exception):
    """A backend call failed (transport error or non-JSON response)."""


class EtimologioClient:
    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self._base = base_url.rstrip("/")
        self._url = f"{self._base}/etimologio.php"
        self._session = requests.Session()
        self._timeout = timeout
        #: Active company VAT, appended as ``account`` to every call once set.
        self.account: str | None = None

    # --- low level ---------------------------------------------------------
    def _call(
        self,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        query = dict(params or {})
        if self.account and "account" not in query:
            query["account"] = self.account
        try:
            if data is not None or method == "POST":
                resp = self._session.post(
                    self._url, params=query, data=data or {}, timeout=self._timeout
                )
            else:
                resp = self._session.get(self._url, params=query, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EtimologioError(str(exc)) from exc
        try:
            return resp.json()
        except ValueError as exc:
            raise EtimologioError(resp.text[:200]) from exc

    def call(
        self,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Generic passthrough for endpoints without a dedicated method yet."""
        return self._call(params, data, method)

    def base_url(self) -> str:
        return self._base

    # --- auth --------------------------------------------------------------
    def login(self, email: str, password: str) -> dict[str, Any]:
        """Password step. On success → ``{'success': True, 'user': …}``.
        With 2FA enabled → ``{'success': False, 'totp_required': True}``."""
        return self._call({"auth": "login"}, data={"email": email, "password": password})

    def login_totp(self, code: str) -> dict[str, Any]:
        """Second login step when 2FA is enabled."""
        return self._call({"auth": "login_totp"}, data={"code": code})

    def logout(self) -> dict[str, Any]:
        return self._call({"auth": "logout"}, method="POST")

    def me(self) -> dict[str, Any]:
        """Current session: ``{authenticated, user, is_staff, accounts, active}``."""
        return self._call({"auth": "me"})

    # --- accounts (companies) ---------------------------------------------
    def accounts(self) -> dict[str, Any]:
        """List selectable companies; adopts the active one as the default."""
        data = self._call({"accounts": 1})
        active = data.get("active")
        if active:
            self.account = active
        return data

    def set_account(self, vat: str) -> None:
        self.account = vat

    # --- customers ---------------------------------------------------------
    def customers(
        self,
        name: str = "",
        code: str = "",
        vat: str = "",
        all_pages: bool = False,
    ) -> dict[str, Any]:
        """List/search customers → ``{success, count, customers: [...]}``.

        Each row carries ``code/type/vat/name/address/city``. An empty search
        returns the first page; ``all_pages`` walks the AADE continuation token.
        """
        params: dict[str, Any] = {"list_customers": 1}
        if name:
            params["customer_name"] = name
        if code:
            params["customer_code"] = code
        if vat:
            params["cust_vat"] = vat
        if all_pages:
            params["all_customers"] = 1
        return self._call(params)

    def customers_cached(self) -> dict[str, Any]:
        """Instant local-cache read (no AADE login) → ``{success, rows: [...]}``."""
        return self._call({"cached": "customers"})

    def create_customer(self, **fields: Any) -> dict[str, Any]:
        """Create a customer. Accepts ``name, vat, address, city, zip, doy,
        country, job_description, email, phone1, phone2, is_b2g, code``."""
        alias = {
            "vat": "cust_vat",
            "old_vat": "cust_old_vat",
            "job_description": "cust_job_description",
            "is_b2g": "cust_is_b2g",
        }
        data: dict[str, Any] = {"create_personal_customer": 1}
        for key, value in fields.items():
            if value in (None, ""):
                continue
            param = alias.get(key, f"cust_{key}")
            data[param] = "1" if value is True else value
        return self._call(data=data, method="POST")

    # --- issuance ----------------------------------------------------------
    def issue_invoice(
        self,
        lines: list[dict[str, Any]],
        invoice_type: str,
        *,
        afm: str = "",
        name: str = "",
        address: str = "",
        city: str = "",
        zip_code: str = "",
        country: str = "GR",
        branch: str = "0",
        payment: int = 3,
        series: str = "A",
        notes: str = "",
        taxes: list[dict[str, Any]] | None = None,
        live: bool = False,
        preview: bool = False,
        temp_id: str = "",
        lang: str = "el",
    ) -> dict[str, Any]:
        """Build/save/issue an invoice from ``lines`` (each ``{code, qty, price,
        rate?, cat?, disc?}``).

        Three modes, matching the web UI:
          * default (``live=False, preview=False``) → save a **draft** (πρόχειρο),
            no MARK — safe for testing.
          * ``preview=True`` → save draft **and** return a real AADE PDF
            (``pdf_b64``).
          * ``live=True`` → **issue** for real; returns the ``mark``.
        """
        data: dict[str, Any] = {
            "type": invoice_type,
            "lines": json.dumps(lines, ensure_ascii=False),
            "payment": payment,
            "issue_series": series,
            "country": country,
            "branch": branch,
            "issue_lang": lang,
        }
        if afm:
            data["afm"] = afm
        if name:
            data["name"] = name
        if address:
            data["address"] = address
        if city:
            data["city"] = city
        if zip_code:
            data["zip"] = zip_code
        if notes:
            data["notes"] = notes
        if taxes:
            data["taxes"] = json.dumps(taxes, ensure_ascii=False)
        if temp_id:
            data["temp_id"] = temp_id
        if live:
            data["live"] = 1
        if preview:
            data["preview"] = 1
        return self._call(data=data, method="POST")

    # --- invoices ----------------------------------------------------------
    def search_invoices(
        self,
        date_from: str = "",
        date_to: str = "",
        buyer_vat: str = "",
        invoice_type: str = "",
        series: str = "",
        mark: str = "",
        include_cancelled: bool = False,
    ) -> dict[str, Any]:
        """Search issued invoices → ``{success, invoices: [...]}``.

        Rows carry ``mark/type/issue_date/series/aa/buyer_vat/net_value/
        vat_value/total``. Filter by ``buyer_vat`` to build a customer card.
        """
        params: dict[str, Any] = {"search_invoices": 1}
        if date_from:
            params["issue_date_from"] = date_from
        if date_to:
            params["issue_date_to"] = date_to
        if buyer_vat:
            params["buyer_vat"] = buyer_vat
        if invoice_type:
            params["search_invoice_type"] = invoice_type
        if series:
            params["series"] = series
        if mark:
            params["mark"] = mark
        if include_cancelled:
            params["include_cancelled"] = 1
        return self._call(params)

    # --- catalogs: products & series --------------------------------------
    def products(self) -> dict[str, Any]:
        """List items → ``{success, products: [...]}``."""
        return self._call({"list_products": 1})

    def product_categories(self) -> dict[str, Any]:
        return self._call({"list_product_categories": 1})

    def create_product(
        self,
        *,
        product_code: str,
        description: str,
        unit_price: str = "0",
        vat_category: str = "1",
        product_type: str = "",
        category: str = "",
        unit: str = "",
        taric_code: str = "",
    ) -> dict[str, Any]:
        """Create an item (είδος). ``vat_category``: 1=24% 2=13% 3=6% 7=0%."""
        return self._call(
            data={
                "new_product": 1,
                "product_code": product_code,
                "product_description": description,
                "unit_price": unit_price,
                "vat_category": vat_category,
                "product_type": product_type,
                "product_category": category,
                "unit": unit,
                "taric_code": taric_code,
            },
            method="POST",
        )

    def delete_product(self, code: str) -> dict[str, Any]:
        return self._call(data={"delete_product_code": code}, method="POST")

    def series(self) -> dict[str, Any]:
        """List numbering series → ``{success, series: [...]}``."""
        return self._call({"list_series": 1})

    def create_series(
        self,
        *,
        invoice_type: str,
        code: str,
        start_aa: str = "1",
        description: str = "",
        trans_failure: bool = False,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "new_series": 1,
            "series_invoice_type": invoice_type,
            "series_code": code,
            "series_start_aa": start_aa,
            "series_description": description,
        }
        if trans_failure:
            data["series_trans_failure"] = 1
        return self._call(data=data, method="POST")

    def delete_series(self, series_id: str) -> dict[str, Any]:
        return self._call(data={"delete_series_id": series_id}, method="POST")

    # --- drafts (πρόχειρα) -------------------------------------------------
    def temp_invoices(
        self,
        date_from: str = "",
        date_to: str = "",
        temp_type: str = "",
        buyer_vat: str = "",
        temp_id: str = "",
    ) -> dict[str, Any]:
        """List saved drafts → ``{success, temp_invoices: [...]}``."""
        params: dict[str, Any] = {"search_temp": 1}
        if date_from:
            params["save_date_from"] = date_from
        if date_to:
            params["save_date_to"] = date_to
        if temp_type:
            params["temp_type"] = temp_type
        if buyer_vat:
            params["buyer_vat"] = buyer_vat
        if temp_id:
            params["temp_id"] = temp_id
        return self._call(params)

    def delete_temp(self, temp_id: str, seller_vat: str = "") -> dict[str, Any]:
        data: dict[str, Any] = {"delete_temp_id": temp_id}
        if seller_vat:
            data["seller_vat"] = seller_vat
        return self._call(data=data, method="POST")

    # --- cancellation / credit note ---------------------------------------
    def credit_note(
        self,
        cancel_mark: str,
        *,
        reason: str = "",
        description: str = "ΥΠ001",
        amount: float = 0.0,
        live: bool = False,
        preview: bool = False,
        temp_id: str = "",
    ) -> dict[str, Any]:
        """Issue a correlated credit note against ``cancel_mark`` (the original
        MARK). Same three modes as :meth:`issue_invoice`."""
        data: dict[str, Any] = {
            "cancel_mark": cancel_mark,
            "reason": reason,
            "description": description,
        }
        if amount:
            data["amount"] = amount
        if temp_id:
            data["temp_id"] = temp_id
        if live:
            data["live"] = 1
        if preview:
            data["preview"] = 1
        return self._call(data=data, method="POST")

    # --- local payments (bridge-side ledger) ------------------------------
    def payments(
        self, buyer_vat: str = "", date_from: str = "", date_to: str = ""
    ) -> dict[str, Any]:
        """Local payments for the active company → ``{success, payments: [...]}``."""
        params: dict[str, Any] = {"list_payments": 1}
        if buyer_vat:
            params["buyer_vat"] = buyer_vat
        if date_from:
            params["issue_date_from"] = date_from
        if date_to:
            params["issue_date_to"] = date_to
        return self._call(params)

    # --- statistics (cached like every dataset) ---------------------------
    def statistics(self, period: str = "month", cached: bool = False) -> dict[str, Any]:
        """Turnover statistics for a period (``month|preMonth|year``).

        ``cached=True`` returns the last DB-cached snapshot instantly (no AADE);
        a live call refreshes that cache (write-through). The cache is DB-backed,
        so it behaves identically offline, thin-client and on the VPS.
        """
        params: dict[str, Any] = {"statistics": 1, "period": period}
        if cached:
            params["stats_cached"] = 1
        return self._call(params)

    def sync(self, kind: str) -> dict[str, Any]:
        """Force a background refresh of a cached dataset (``statistics`` too)."""
        return self._call({"sync": kind})

    # --- bulk issuance ----------------------------------------------------
    def bulk_issue(self, items: list[dict[str, Any]], live: bool = False) -> dict[str, Any]:
        """Issue a batch. Each item ``{afm, type, series, payment, name, lines,
        …}``. Default = drafts (temp_id per row); ``live=True`` = real MARKs."""
        data: dict[str, Any] = {"bulk_issue": 1, "items": json.dumps(items, ensure_ascii=False)}
        if live:
            data["live"] = 1
        return self._call(data=data, method="POST")

    # --- bank import → local payments -------------------------------------
    def bank_preview(self, file_b64: str, filename: str = "", bank: str = "") -> dict[str, Any]:
        """Parse an uploaded bank statement into candidate transactions."""
        return self._call(
            data={"bank_preview": 1, "file_b64": file_b64, "filename": filename, "bank": bank},
            method="POST",
        )

    def bank_import(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Register reviewed rows as local payments (no invoice reconciliation)."""
        return self._call(
            data={"bank_import": 1, "items": json.dumps(items, ensure_ascii=False)},
            method="POST",
        )

    def add_payment(self, **fields: Any) -> dict[str, Any]:
        """Record a single local payment (``buyer_vat, customer_name, pay_amount,
        pay_method, pay_date, mark, pay_notes``)."""
        data: dict[str, Any] = {"add_payment": 1}
        data.update({k: v for k, v in fields.items() if v not in (None, "")})
        return self._call(data=data, method="POST")

    def delete_payment(self, payment_id: int | str) -> dict[str, Any]:
        return self._call(data={"delete_payment_id": payment_id}, method="POST")

    # --- notifications / scheduler (used by later phases) -----------------
    def notifications(self, unread_only: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"notifications": 1}
        if unread_only:
            params["unread"] = 1
        return self._call(params)

    def notif_count(self) -> int:
        return int(self._call({"notif_count": 1}).get("unread", 0))

    def scheduled_jobs(self) -> dict[str, Any]:
        return self._call({"sched_list": 1})
