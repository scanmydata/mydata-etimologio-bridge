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
