"""HTTP client for the e-Τιμολόγιο Pro PHP API (``etimologio.php``).

One :class:`requests.Session` per client keeps the PHP login cookie, so the
native Qt UI behaves like a logged-in browser. No business logic lives here —
every method is a thin call to an endpoint the web UI already uses.
"""

from __future__ import annotations

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
