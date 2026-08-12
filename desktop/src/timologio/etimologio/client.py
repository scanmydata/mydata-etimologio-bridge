"""HTTP client for the e-Τιμολόγιο Pro PHP API (``etimologio.php``).

One :class:`requests.Session` per client keeps the PHP login cookie, so the
native Qt UI behaves like a logged-in browser. No business logic lives here —
every method is a thin call to an endpoint the web UI already uses.
"""

from __future__ import annotations

import base64
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

    def lookup_afm(self, vat: str) -> dict[str, Any]:
        """Taxisnet lookup for a 9-digit ΑΦΜ → ``{customer|info: {name, address,
        city, zip, …}}``.

        This is **also how a customer with a VAT number gets created**: the AADE
        lookup registers the customer as a side effect, which is exactly what the
        web UI relies on (``saveCustomer()`` calls nothing else for that tab).
        Such customers must never go through ``create_personal_customer``.
        """
        return self._call({"afm": vat})

    def create_personal_customer(
        self,
        *,
        name: str,
        address: str = "",
        city: str = "",
        zip_code: str = "",
        job_description: str = "ΙΔΙΩΤΗΣ",
        email: str = "",
        phone1: str = "",
        phone2: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a customer **without** a VAT number (ιδιώτης).

        e-timologio requires ονοματεπώνυμο, πόλη and ΤΚ for these; the caller is
        expected to have validated them.
        """
        fields: dict[str, Any] = {
            "name": name,
            "address": address,
            "city": city,
            "zip": zip_code,
            "job_description": job_description,
            "email": email,
            "phone1": phone1,
            "phone2": phone2,
        }
        fields.update(extra)
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
            data[alias.get(key, f"cust_{key}")] = "1" if value is True else value
        return self._call(data=data, method="POST")

    def create_customer(self, **fields: Any) -> dict[str, Any]:
        """Create a customer, picking the right path from the ΑΦΜ.

        The two paths are not interchangeable. Sending a real ΑΦΜ down the
        ``create_personal_customer`` route files a taxpayer as an ιδιώτης — the
        VAT number is dropped, invoices to that customer end up as retail, and
        nothing surfaces the mistake until the ΑΑΔΕ rejects a Τιμολόγιο.
        """
        vat = str(fields.pop("vat", "") or "").strip()
        if vat:
            if not (vat.isdigit() and len(vat) == 9):
                raise EtimologioError(f"Μη έγκυρο ΑΦΜ «{vat}» (χρειάζονται 9 ψηφία).")
            return self.lookup_afm(vat)
        name = str(fields.pop("name", "") or "")
        return self.create_personal_customer(name=name, **fields)

    def update_customer(
        self,
        *,
        vat: str = "",
        code: str = "",
        name: str = "",
        address: str = "",
        city: str = "",
        zip_code: str = "",
        doy: str = "",
        email: str = "",
        phone1: str = "",
        phone2: str = "",
        job_description: str = "",
    ) -> dict[str, Any]:
        """Edit an existing customer, identified by ΑΦΜ **or** customer code."""
        data: dict[str, Any] = {"update_customer": 1}
        for key, value in (
            ("update_customer_vat", vat),
            ("update_customer_code", code),
            ("update_name", name),
            ("update_address", address),
            ("update_city", city),
            ("update_zip", zip_code),
            ("update_doy", doy),
            ("update_email", email),
            ("update_phone1", phone1),
            ("update_phone2", phone2),
            ("update_job_description", job_description),
        ):
            if value:
                data[key] = value
        return self._call(data=data, method="POST")

    def delete_customer(self, *, code: str = "", vat: str = "") -> dict[str, Any]:
        data: dict[str, Any] = {}
        if code:
            data["delete_customer_code"] = code
        elif vat:
            data["delete_customer_vat"] = vat
        else:
            raise EtimologioError("Χρειάζεται κωδικός ή ΑΦΜ πελάτη για διαγραφή.")
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

    def update_product(
        self,
        code: str,
        *,
        description: str = "",
        unit_price: str = "",
        vat_category: str = "",
        product_type: str = "",
        category: str = "",
        unit: str = "",
        taric_code: str = "",
    ) -> dict[str, Any]:
        """Edit an item. ``code`` is the key and cannot change."""
        data: dict[str, Any] = {"update_product_code": code}
        for key, value in (
            ("product_description", description),
            ("unit_price", unit_price),
            ("vat_category", vat_category),
            ("product_type", product_type),
            ("product_category", category),
            ("unit", unit),
            ("taric_code", taric_code),
        ):
            if value != "":
                data[key] = value
        return self._call(data=data, method="POST")

    def delete_product(self, code: str) -> dict[str, Any]:
        return self._call(data={"delete_product_code": code}, method="POST")

    def create_product_category(self, name: str) -> dict[str, Any]:
        return self._call(
            data={"new_product_category": 1, "category_name": name}, method="POST"
        )

    def delete_product_category(self, category_id: str) -> dict[str, Any]:
        return self._call(
            data={"delete_product_category_id": category_id}, method="POST"
        )

    def category_classifications(self) -> dict[str, Any]:
        """Product categories with their χαρακτηρισμοί + the invoice-type list."""
        return self._call({"category_cls": 1})

    def save_category_classifications(
        self, *, category_id: str = "", name: str, cls: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Create or update a product category together with its classifications.

        ``cls`` entries are ``{invoice_type, category, code}`` — one per invoice
        type. The key names matter: the backend skips (silently) any entry whose
        ``invoice_type`` or ``category`` is missing, so a wrong name produces a
        category with **zero** classifications and a cheerful ``success: true``.
        """
        return self._call(
            data={
                "save_category_cls": 1,
                "category_id": category_id,
                "category_name": name,
                "cls": json.dumps(cls, ensure_ascii=False),
            },
            method="POST",
        )

    def classification_options(self, invoice_type: str, *, self_pricing: bool = False) -> dict[str, Any]:
        """Allowed classification categories + E3 codes for an invoice type."""
        params: dict[str, Any] = {"cls_options": 1, "type": invoice_type}
        if self_pricing:
            params["self"] = 1
        return self._call(params)

    def classifications(self, product: str, invoice_type: str) -> dict[str, Any]:
        """The χαρακτηρισμοί e-timologio derives for a product within a type."""
        return self._call({"classifications": 1, "product": product, "type": invoice_type})

    def invoice_types(self) -> dict[str, Any]:
        """The live invoice-type catalogue (numeric value + dotted code + label)."""
        return self._call({"invoice_types": 1})

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

    def update_series(
        self,
        series_id: str,
        *,
        invoice_type: str = "",
        code: str = "",
        start_aa: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"update_series_id": series_id}
        for key, value in (
            ("series_invoice_type", invoice_type),
            ("series_code", code),
            ("series_start_aa", start_aa),
            ("series_description", description),
        ):
            if value != "":
                data[key] = value
        return self._call(data=data, method="POST")

    def delete_series(self, series_id: str) -> dict[str, Any]:
        return self._call(data={"delete_series_id": series_id}, method="POST")

    # --- taxes, withholdings, deductions ----------------------------------
    def tax_categories(self) -> dict[str, Any]:
        """The five tax dropdowns of «Νέος Φόρος».

        Returns ``{withheld, fees, other, digital, deductions: [{code, label}]}``.
        Four of them are fixed by the ΑΑΔΕ; ``deductions`` (Κρατήσεις) are the
        company's own saved entries, so that is the only list we can extend.
        """
        return self._call({"tax_categories": 1})

    def deductions(self) -> dict[str, Any]:
        return self._call({"list_deductions": 1})

    def create_deduction(
        self,
        description: str,
        *,
        amount_type: str = "1",
        amount: str = "0",
        decrease_total_paid: bool = False,
    ) -> dict[str, Any]:
        return self._call(
            data={
                "new_deduction": 1,
                # Το web έστελνε `deduction_desc` ενώ το backend διαβάζει
                # `deduction_description` — η ονομασία δεν έφτανε ποτέ.
                "deduction_description": description,
                "deduction_amount_type": amount_type,
                "deduction_amount": amount,
                # Πρέπει να στέλνεται ΠΑΝΤΑ, ακόμη και ως «0»: το endpoint απαιτεί
                # και τα τέσσερα πεδία και αλλιώς απαντά «Description, amount type,
                # amount, and decrease_total_paid are required».
                "deduction_decrease_total_paid": "1" if decrease_total_paid else "0",
            },
            method="POST",
        )

    def update_deduction(self, code: str, **fields: Any) -> dict[str, Any]:
        data: dict[str, Any] = {"update_deduction_code": code}
        alias = {
            "description": "deduction_description",
            "amount_type": "deduction_amount_type",
            "amount": "deduction_amount",
        }
        for key, value in fields.items():
            if value not in (None, ""):
                data[alias.get(key, key)] = value
        return self._call(data=data, method="POST")

    def delete_deduction(self, code: str) -> dict[str, Any]:
        return self._call(data={"delete_deduction_code": code}, method="POST")

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

    def preview_temp(self, temp_id: str) -> bytes:
        """The AADE PDF of a saved draft. ``temp_id`` is the (encrypted) token.

        Drafts have no ΜΑΡΚ, so :meth:`invoice_pdf` cannot fetch them — this is
        the only way to see a πρόχειρο as a document.
        """
        data = self._call({"preview_temp": temp_id})
        b64 = data.get("pdf_b64") or data.get("pdf_base64")
        if not b64:
            raise EtimologioError(data.get("error", "Χωρίς PDF για το πρόχειρο"))
        return base64.b64decode(b64)

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

    # --- PDFs --------------------------------------------------------------
    def invoice_pdf(self, mark: str) -> bytes:
        """Fetch the real AADE PDF for a MARK. Raises on failure."""
        data = self._call({"mark": mark})
        b64 = data.get("pdf_base64") or data.get("pdf_b64")
        if not b64:
            raise EtimologioError(data.get("error", f"Χωρίς PDF για ΜΑΡΚ {mark}"))
        return base64.b64decode(b64)

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

    def ledger(self, buyer_vat: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """A customer's card as the backend builds it → ``{customer_vat,
        customer_name, total_invoiced, total_paid, balance, entries: [...]}``.

        ``entries`` already merges issued documents with local payments in date
        order, which is what the running balance needs — rebuilding it from two
        separate calls (as the native page used to) gets the order wrong as soon
        as a payment and an invoice share a date.
        """
        params: dict[str, Any] = {"ledger": 1, "buyer_vat": buyer_vat}
        if date_from:
            params["issue_date_from"] = date_from
        if date_to:
            params["issue_date_to"] = date_to
        return self._call(params)

    # --- company / Taxisnet ------------------------------------------------
    def company_profile(self) -> dict[str, Any]:
        """The active company's own registry details (έδρα, επωνυμία, ΔΟΥ)."""
        return self._call({"company_profile": 1})

    def taxis_name(self, vat: str) -> dict[str, Any]:
        """Registered name for a VAT number, without creating a customer."""
        return self._call({"taxis_name": 1, "vat": vat})

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

    def mark_read(self, notification_id: int) -> dict[str, Any]:
        return self._call(data={"notif_read": 1, "id": notification_id}, method="POST")

    def mark_all_read(self) -> dict[str, Any]:
        return self._call(data={"notif_read_all": 1}, method="POST")

    def scheduled_jobs(self) -> dict[str, Any]:
        return self._call({"sched_list": 1})

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        return self._call(data={"sched_cancel": 1, "id": job_id}, method="POST")

    def schedule_job(
        self,
        payload: dict[str, Any],
        run_at: str,
        *,
        title: str = "",
        kind: str = "invoice",
        recurrence: str = "none",
    ) -> dict[str, Any]:
        """Queue an issuance for ``run_at`` (``YYYY-MM-DD HH:MM``)."""
        return self._call(
            data={
                "sched_add": 1,
                "sched_payload": json.dumps(payload, ensure_ascii=False),
                "run_at": run_at,
                "title": title,
                "kind": kind,
                "recurrence": recurrence,
            },
            method="POST",
        )

    # --- settings & administration ----------------------------------------
    def change_password(self, current: str, new: str) -> dict[str, Any]:
        return self._call(
            {"auth": "change_password"},
            data={"current_password": current, "password": new},
            method="POST",
        )

    def totp_setup(self) -> dict[str, Any]:
        """Begin 2FA enrolment → ``{secret, uri}`` for the QR code."""
        return self._call({"auth": "totp_setup"}, method="POST")

    def totp_enable(self, code: str) -> dict[str, Any]:
        return self._call({"auth": "totp_enable"}, data={"code": code}, method="POST")

    def totp_disable(self, verify: str) -> dict[str, Any]:
        return self._call({"auth": "totp_disable"}, data={"verify": verify}, method="POST")

    def notif_prefs(self) -> dict[str, Any]:
        return self._call({"auth": "notif_prefs_get"})

    def set_notif_prefs(
        self, companies: str = "*", types: str = "*", email_enabled: bool = True
    ) -> dict[str, Any]:
        return self._call(
            {"auth": "notif_prefs_set"},
            data={
                "companies": companies,
                "types": types,
                "email_enabled": "1" if email_enabled else "0",
            },
            method="POST",
        )

    def admin_users(self) -> dict[str, Any]:
        return self._call({"auth": "admin_users"})

    def admin_invite(self, email: str, role: str = "editor") -> dict[str, Any]:
        return self._call(
            {"auth": "admin_invite"}, data={"email": email, "role": role}, method="POST"
        )

    def admin_set_role(self, user_id: int, role: str) -> dict[str, Any]:
        return self._call(
            {"auth": "admin_set_role"}, data={"user_id": user_id, "role": role}, method="POST"
        )

    def admin_set_status(self, user_id: int, status: str) -> dict[str, Any]:
        return self._call(
            {"auth": "admin_set_status"}, data={"user_id": user_id, "status": status},
            method="POST",
        )

    def admin_approve(self, user_id: int) -> dict[str, Any]:
        return self._call(
            {"auth": "admin_approve"}, data={"user_id": user_id}, method="POST"
        )

    def admin_reset_password(self, user_id: int) -> dict[str, Any]:
        """Issue a 24-hour reset link for a user → ``{token, reset_link}``."""
        return self._call(
            {"auth": "admin_reset_pw"}, data={"user_id": user_id}, method="POST"
        )

    def admin_create_user(self, email: str, password: str, business_name: str = "") -> dict[str, Any]:
        return self._call(
            {"auth": "admin_create_user"},
            data={"email": email, "password": password, "business_name": business_name},
            method="POST",
        )

    # --- AADE company accounts --------------------------------------------
    # Without these there is no way to register a company from inside the app: a
    # fresh offline install signs in as master with zero companies and every page
    # comes back empty, with nothing in the UI to fix it.
    def admin_accounts(self) -> dict[str, Any]:
        """Every AADE account on the installation (master only)."""
        return self._call({"auth": "admin_accounts"})

    def admin_user_accounts(self, user_id: int) -> dict[str, Any]:
        return self._call({"auth": "admin_user_accounts", "user_id": user_id})

    def admin_add_account(
        self, user_id: int, *, vat: str, label: str = "", username: str = "", subkey: str = ""
    ) -> dict[str, Any]:
        """Link an AADE company to a user.

        ``subkey`` is the e-timologio subscription key. The parameter really is
        named ``subkey`` — sending ``subscription_key`` is accepted by the form
        and silently produces a zero-length key, which surfaces much later as a
        plain «Login failed».
        """
        return self._call(
            {"auth": "admin_add_account"},
            data={
                "user_id": user_id,
                "vat": vat,
                "label": label or vat,
                "username": username,
                "subkey": subkey,
            },
            method="POST",
        )

    def admin_update_account(
        self, account_id: int, *, vat: str = "", label: str = "", username: str = "", subkey: str = ""
    ) -> dict[str, Any]:
        return self._call(
            {"auth": "admin_update_account"},
            data={
                "account_id": account_id,
                "vat": vat,
                "label": label,
                "username": username,
                "subkey": subkey,
            },
            method="POST",
        )

    def admin_delete_account(self, account_id: int) -> dict[str, Any]:
        return self._call(
            {"auth": "admin_delete_account"}, data={"account_id": account_id}, method="POST"
        )
