"""Native Qt shell for e-Τιμολόγιο Pro.

Phase 0: owns the backend :class:`EtimologioService`, shows a native login
(with 2FA step) and a home page with the company switcher. Individual sections
(issue/customers/…) are rebuilt natively in later phases; until then the home
page can open them in the browser against the *same* backend.

All backend calls run off the UI thread via :class:`QThreadPool`; slots update
widgets on the main thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .client import EtimologioClient
from .pages import (
    BulkPage,
    CreditNotePage,
    CustomerCard,
    CustomersPage,
    DraftsPage,
    IssuePage,
    PaymentsPage,
    ProductsPage,
    SeriesPage,
    StatsPage,
)
from .service import EtimologioService

log = logging.getLogger(__name__)


class _Signals(QObject):
    ok = Signal(object)
    err = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:  # runs on a pool thread
        try:
            self.signals.ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI
            self.signals.err.emit(str(exc))


def _run(fn: Callable[[], Any], on_ok: Callable[[Any], None], on_err: Callable[[str], None]) -> None:
    job = _Job(fn)
    job.signals.ok.connect(on_ok)
    job.signals.err.connect(on_err)
    QThreadPool.globalInstance().start(job)


#: The e-Τιμολόγιο sections, as (key, label). Sections with a native page are
#: marked and open in-app; the rest still open app.php#<key> in the browser
#: against the *same* backend until they are ported in a later phase.
_NATIVE = {
    "customers", "issue", "products", "series", "drafts", "credit",
    "bulk", "payments", "stats",
}
_SECTIONS = [
    ("issue", "🧾 Έκδοση"),
    ("credit", "↩️ Ακύρωση/Πιστωτικό"),
    ("bulk", "📚 Μαζική έκδοση"),
    ("customers", "👥 Πελάτες"),
    ("products", "📦 Είδη"),
    ("series", "🔢 Σειρές"),
    ("drafts", "📝 Πρόχειρα"),
    ("payments", "💶 Πληρωμές"),
    ("stats", "📊 Στατιστικά"),
    ("schedule", "⏰ Προγραμματισμός"),
    ("settings", "⚙️ Ρυθμίσεις"),
]


class EtimologioShell(QWidget):
    """Self-contained e-Τιμολόγιο Pro surface, embeddable as one page."""

    def __init__(self, data_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = EtimologioService(data_dir)
        self._client: EtimologioClient | None = None
        self._started = False
        #: Set by focus_customer() before login; replayed once home is reached.
        self._pending_focus_vat = ""

        self._stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)

        self._status = self._build_status_page()
        self._login = self._build_login_page()
        self._home = self._build_home_page()

        # Native pages (Phase 1). They read the live client lazily via the
        # accessor, so they can be built before login completes.
        self._customers = CustomersPage(lambda: self._client, _run)
        self._card = CustomerCard(lambda: self._client, _run)
        self._issue = IssuePage(lambda: self._client, _run)
        self._products = ProductsPage(lambda: self._client, _run)
        self._series = SeriesPage(lambda: self._client, _run)
        self._drafts = DraftsPage(lambda: self._client, _run)
        self._credit = CreditNotePage(lambda: self._client, _run)
        self._bulk = BulkPage(lambda: self._client, _run)
        self._payments = PaymentsPage(lambda: self._client, _run)
        self._stats = StatsPage(lambda: self._client, _run)
        self._customers.go_back.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._customers.open_card.connect(self._show_card)
        self._card.go_back.connect(lambda: self._stack.setCurrentWidget(self._customers))
        for page in (
            self._issue, self._products, self._series, self._drafts, self._credit,
            self._bulk, self._payments, self._stats,
        ):
            page.go_back.connect(lambda: self._stack.setCurrentWidget(self._home))

        for w in (
            self._status, self._login, self._home, self._customers, self._card,
            self._issue, self._products, self._series, self._drafts, self._credit,
            self._bulk, self._payments, self._stats,
        ):
            self._stack.addWidget(w)
        self._stack.setCurrentWidget(self._status)

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Start the backend once (idempotent), then route to login/home."""
        if self._started:
            return
        self._started = True
        self._set_status("Εκκίνηση e-Τιμολόγιο Pro…")
        _run(self._service.start_local, self._on_backend_ready, self._on_backend_error)

    def shutdown(self) -> None:
        self._service.stop()

    def _on_backend_ready(self, url: str) -> None:
        self._client = EtimologioClient(url)
        # Offline mode = single local accountant → auto-login with the bootstrap
        # master. Thin mode (VPS) → show the login form.
        if self._service.mode() == "offline":
            email, password = self._service.bootstrap_credentials()
            _run(
                lambda: self._client.login(email, password),
                self._after_login,
                lambda m: self._show_login(),
            )
        else:
            self._show_login()

    def _on_backend_error(self, msg: str) -> None:
        self._started = False
        self._set_status(f"Αποτυχία εκκίνησης backend:\n{msg}")

    # --- status page -------------------------------------------------------
    def _build_status_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        box.addWidget(self._status_label)
        return page

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)
        self._stack.setCurrentWidget(self._status)

    # --- login page --------------------------------------------------------
    def _build_login_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Σύνδεση — e-Τιμολόγιο Pro")
        title.setStyleSheet("font-size:18px;font-weight:600;")
        outer.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)

        form = QFormLayout()
        self._email = QLineEdit()
        self._email.setPlaceholderText("email")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("κωδικός")
        form.addRow("Email", self._email)
        form.addRow("Κωδικός", self._password)
        self._totp = QLineEdit()
        self._totp.setPlaceholderText("6ψήφιος κωδικός authenticator")
        self._totp_row_label = QLabel("2FA")
        form.addRow(self._totp_row_label, self._totp)
        self._totp.hide()
        self._totp_row_label.hide()
        outer.addLayout(form)

        self._login_btn = QPushButton("Σύνδεση")
        self._login_btn.clicked.connect(self._do_login)
        outer.addWidget(self._login_btn)
        self._password.returnPressed.connect(self._do_login)
        self._totp.returnPressed.connect(self._do_login)

        self._login_err = QLabel("")
        self._login_err.setStyleSheet("color:#dc2626;")
        self._login_err.setWordWrap(True)
        outer.addWidget(self._login_err)
        return page

    def _show_login(self) -> None:
        self._login_err.setText("")
        self._stack.setCurrentWidget(self._login)

    def _do_login(self) -> None:
        if self._client is None:
            return
        self._login_btn.setEnabled(False)
        self._login_err.setText("")
        if self._totp.isVisible():
            code = self._totp.text().strip()
            _run(lambda: self._client.login_totp(code), self._after_login, self._login_failed)
        else:
            email = self._email.text().strip()
            password = self._password.text()
            _run(lambda: self._client.login(email, password), self._after_login, self._login_failed)

    def _login_failed(self, msg: str) -> None:
        self._login_btn.setEnabled(True)
        self._login_err.setText(msg)

    def _after_login(self, result: dict) -> None:
        self._login_btn.setEnabled(True)
        if result.get("success"):
            self._enter_home()
            return
        if result.get("totp_required"):
            self._totp.show()
            self._totp_row_label.show()
            self._totp.setFocus()
            self._show_login()
            return
        self._login_err.setText(result.get("error", "Αποτυχία σύνδεσης"))
        self._show_login()

    # --- home page ---------------------------------------------------------
    def _build_home_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)

        topbar = QHBoxLayout()
        self._who = QLabel("")
        self._who.setStyleSheet("font-weight:600;")
        topbar.addWidget(self._who)
        topbar.addStretch(1)
        topbar.addWidget(QLabel("Εταιρία:"))
        self._accounts = QComboBox()
        self._accounts.setMinimumWidth(240)
        self._accounts.currentIndexChanged.connect(self._account_changed)
        topbar.addWidget(self._accounts)
        self._mode_label = QLabel("")
        self._mode_label.setStyleSheet("color:#93a4bd;")
        topbar.addWidget(self._mode_label)
        logout = QPushButton("Έξοδος")
        logout.clicked.connect(self._do_logout)
        topbar.addWidget(logout)
        box.addLayout(topbar)

        note = QLabel(
            "Οι εγγενείς (native) οθόνες προστίθενται σταδιακά. Μέχρι τότε, κάθε "
            "ενότητα ανοίγει στον browser πάνω στο ίδιο backend."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#93a4bd;margin:8px 0;")
        box.addWidget(note)

        grid = QHBoxLayout()
        grid.setSpacing(8)
        for key, label in _SECTIONS:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=key: self._open_section(k))
            grid.addWidget(btn)
        grid.addStretch(1)
        box.addLayout(grid)
        box.addStretch(1)
        return page

    def _enter_home(self) -> None:
        self._mode_label.setText(
            "backend: τοπικό (offline)" if self._service.mode() == "offline" else "backend: server"
        )
        _run(self._client.me, self._fill_home, lambda m: None)
        _run(self._client.accounts, self._fill_accounts, lambda m: None)
        self._stack.setCurrentWidget(self._home)
        self._apply_pending_focus()

    def _fill_home(self, me: dict) -> None:
        user = me.get("user", {}) if isinstance(me, dict) else {}
        who = user.get("business_name") or user.get("email") or ""
        role = user.get("role", "")
        self._who.setText(f"{who}  ·  {role}" if role else who)

    def _fill_accounts(self, data: dict) -> None:
        self._accounts.blockSignals(True)
        self._accounts.clear()
        active = data.get("active", "")
        for acc in data.get("accounts", []):
            self._accounts.addItem(f"{acc.get('label', '')} ({acc.get('vat', '')})", acc.get("vat"))
        if active:
            idx = self._accounts.findData(active)
            if idx >= 0:
                self._accounts.setCurrentIndex(idx)
        self._accounts.blockSignals(False)

    def _account_changed(self, _index: int) -> None:
        if self._client is None:
            return
        vat = self._accounts.currentData()
        if vat:
            self._client.set_account(str(vat))

    def _open_section(self, key: str) -> None:
        if self._client is None:
            return
        if key in _NATIVE:
            if key == "customers":
                self._show_customers()
            elif key == "issue":
                self._stack.setCurrentWidget(self._issue)
            elif key == "credit":
                self._stack.setCurrentWidget(self._credit)
            elif key == "bulk":
                self._stack.setCurrentWidget(self._bulk)
            elif key in ("products", "series", "drafts", "payments", "stats"):
                page = {
                    "products": self._products, "series": self._series,
                    "drafts": self._drafts, "payments": self._payments,
                    "stats": self._stats,
                }[key]
                self._stack.setCurrentWidget(page)
                page.refresh()
            return
        base = self._client.base_url()
        vat = self._accounts.currentData()
        url = f"{base}/app.php"
        if vat:
            url += f"?account={vat}"
        url += f"#{key}"
        QDesktopServices.openUrl(QUrl(url))

    # --- native navigation -------------------------------------------------
    def _show_customers(self) -> None:
        self._stack.setCurrentWidget(self._customers)
        self._customers.refresh()

    def _show_card(self, customer: dict) -> None:
        self._card.set_customer(customer)
        self._stack.setCurrentWidget(self._card)

    def focus_customer(self, vat: str) -> None:
        """Jump straight to a customer (used by "open client from Downloader").

        Ensures the backend is up, opens the native Πελάτες page pre-filtered by
        the ΑΦΜ so the accountant lands on that client with one action.
        """
        self.start()
        self._pending_focus_vat = vat
        # If we are already logged in, act now; otherwise _enter_home() replays it.
        if self._client is not None and self._stack.currentWidget() is self._home:
            self._apply_pending_focus()

    def _apply_pending_focus(self) -> None:
        vat = getattr(self, "_pending_focus_vat", "")
        if not vat:
            return
        self._pending_focus_vat = ""
        self._customers.set_search(vat)
        self._show_customers()

    def _do_logout(self) -> None:
        if self._client is not None:
            _run(self._client.logout, lambda r: None, lambda m: None)
        # Offline: re-auth silently; thin: back to the login form.
        if self._service.mode() == "offline":
            self._on_backend_ready(self._client.base_url() if self._client else self._service.base_url())
        else:
            self._show_login()
