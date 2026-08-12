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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..gui.icons import logo_pixmap
from ..gui.theme import CURRENT
from .client import EtimologioClient
from .pages import (
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
    SettingsPage,
    StatsPage,
    ui,
)
from .pages.base import fmt_money, parse_money
from .service import EtimologioService

log = logging.getLogger(__name__)


class _Signals(QObject):
    ok = Signal(object)
    err = Signal(str)
    #: Emitted after ok/err, so the runner can release the job.
    done = Signal()


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:  # runs on a pool thread
        try:
            try:
                result = self._fn()
            except Exception as exc:  # noqa: BLE001 — surfaced to the UI
                self._emit(self.signals.err, str(exc))
            else:
                self._emit(self.signals.ok, result)
        finally:
            self._emit(self.signals.done)

    @staticmethod
    def _emit(signal, *payload) -> None:
        """Emit unless the receiver is already gone.

        A job can still be in flight when its page (or the whole shell) is torn
        down — on shutdown, or in tests. Qt then raises "Signal source has been
        deleted" from a pool thread, where nothing can catch it. Swallow exactly
        that: the result has no one left to reach.
        """
        try:
            signal.emit(*payload)
        except RuntimeError:
            log.debug("Το αποτέλεσμα αγνοήθηκε: ο παραλήπτης έχει καταστραφεί")


#: In-flight jobs, kept alive on purpose. ``QThreadPool.start()`` owns the
#: QRunnable on the C++ side, but nothing holds the Python object — so its
#: ``_Signals`` companion could be garbage-collected *before* the worker emits,
#: and the result vanished silently (a page that randomly "never loads"). We
#: drop each job only once it has reported back.
_INFLIGHT: set[_Job] = set()


def _run(fn: Callable[[], Any], on_ok: Callable[[Any], None], on_err: Callable[[str], None]) -> None:
    job = _Job(fn)
    _INFLIGHT.add(job)
    job.signals.ok.connect(on_ok)
    job.signals.err.connect(on_err)
    job.signals.done.connect(lambda: _INFLIGHT.discard(job))
    QThreadPool.globalInstance().start(job)


#: The e-Τιμολόγιο sections, as (key, label). Sections with a native page are
#: marked and open in-app; the rest still open app.php#<key> in the browser
#: against the *same* backend until they are ported in a later phase.
#: Every section is now native — nothing falls back to the browser.
#: (key, label, description, icon) — the description is the tile's subtitle.
_SECTIONS = [
    ("issue", "Έκδοση", "Νέο παραστατικό", "edit"),
    ("documents", "Παραστατικά", "Αναζήτηση, εκτύπωση, ZIP", "pdf"),
    ("customers", "Πελάτες", "Λίστα & καρτέλες", "clients"),
    ("bulk", "Μαζική έκδοση", "Παρτίδα παραστατικών", "import"),
    ("credit", "Ακύρωση/Πιστωτικό", "Συσχετιζόμενο πιστωτικό", "cancel"),
    ("drafts", "Πρόχειρα", "Αποθηκευμένα προσχέδια", "restore"),
    ("products", "Είδη", "Κατάλογος ειδών", "folder"),
    ("series", "Σειρές", "Αρίθμηση παραστατικών", "filter"),
    ("payments", "Πληρωμές", "Ταμείο & extrait τράπεζας", "income"),
    ("stats", "Στατιστικά", "Τζίρος ανά τύπο", "stats"),
    ("schedule", "Προγραμματισμός", "Αυτόματες εκδόσεις", "schedule"),
    ("notifications", "Ειδοποιήσεις", "Ροή εκδόσεων", "bell"),
    ("settings", "Ρυθμίσεις", "Κωδικός, 2FA, email", "settings"),
    ("admin", "Διαχείριση", "Χρήστες & ρόλοι", "key"),
]
_NATIVE = {key for key, _label, _desc, _icon in _SECTIONS}


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
        self._documents = DocumentsPage(lambda: self._client, _run)
        self._schedule = SchedulePage(lambda: self._client, _run)
        self._notifications = NotificationsPage(lambda: self._client, _run)
        self._settings = SettingsPage(lambda: self._client, _run)
        self._admin = AdminPage(lambda: self._client, _run)

        self._customers.go_back.connect(lambda: self._stack.setCurrentWidget(self._home))
        self._customers.open_card.connect(self._show_card)
        self._card.go_back.connect(lambda: self._stack.setCurrentWidget(self._customers))
        self._notifications.unread_changed.connect(
            lambda n: ui.set_tile_value(self._kpi_unread, str(n))
        )
        self._settings.mode_change_requested.connect(self._switch_backend)
        self._drafts.open_in_issue.connect(self._edit_draft)
        #: Section key → page, used for both navigation and construction.
        self._pages = {
            "issue": self._issue, "credit": self._credit, "bulk": self._bulk,
            "customers": self._customers, "products": self._products,
            "series": self._series, "drafts": self._drafts,
            "payments": self._payments, "stats": self._stats,
            "documents": self._documents, "schedule": self._schedule,
            "notifications": self._notifications, "settings": self._settings,
            "admin": self._admin,
        }
        for page in self._pages.values():
            if page is not self._customers:
                page.go_back.connect(lambda: self._stack.setCurrentWidget(self._home))

        for w in (self._status, self._login, self._home, self._card, *self._pages.values()):
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
        # Οθόνη σύνδεσης ΜΟΝΟ όταν υπάρχει πραγματικός server. Στην τοπική
        # λειτουργία ο κωδικός παράγεται από την ίδια την εφαρμογή και δεν τον
        # ξέρει κανείς — το να ζητάμε από τον χρήστη να πατήσει «Σύνδεση» σε
        # προσυμπληρωμένη φόρμα δεν προστατεύει τίποτα, απλώς προσθέτει ένα βήμα
        # σε κάθε άνοιγμα.
        if self._service.mode() == "offline":
            self._login_hint.hide()
            email, password = self._service.bootstrap_credentials()
            self._set_status("Σύνδεση…")
            _run(
                lambda: self._client.login(email, password),
                self._after_login,
                self._login_failed_offline,
            )
            return
        self._login_hint.hide()
        self._show_login()

    def _login_failed_offline(self, msg: str) -> None:
        """Η αυτόματη τοπική σύνδεση απέτυχε — δείχνουμε τη φόρμα ως διέξοδο."""
        self._login_err.setText(
            f"Η τοπική σύνδεση απέτυχε: {msg}\n"
            "Δοκιμάστε ξανά ή επανεκκινήστε την εφαρμογή."
        )
        email, password = self._service.bootstrap_credentials()
        self._email.setText(email)
        self._password.setText(password)
        self._stack.setCurrentWidget(self._login)

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

        logo = QLabel()
        logo.setPixmap(logo_pixmap(56, etimologio=True))
        logo.setFixedSize(56, 56)
        logo.setScaledContents(True)
        outer.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("e-Τιμολόγιο Pro")
        title.setStyleSheet("font-size:20px;font-weight:800;")
        outer.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("Σύνδεση στον λογαριασμό σας")
        subtitle.setObjectName("muted")
        outer.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addSpacing(10)

        self._login_hint = QLabel("")
        self._login_hint.setObjectName("hint")
        self._login_hint.setWordWrap(True)
        self._login_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._login_hint.setMaximumWidth(360)
        self._login_hint.hide()
        outer.addWidget(self._login_hint, 0, Qt.AlignmentFlag.AlignHCenter)

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
        self._login_err.setStyleSheet(f"color:{CURRENT.bad};")
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
        """The e-Τιμολόγιο home, laid out like the Downloader's control panel:
        a header card (who/company/mode), KPI tiles, then a grid of launchers."""
        page, box = ui.page()

        header_card, header = ui.card()
        topbar = QHBoxLayout()
        self._who = QLabel("")
        self._who.setStyleSheet("font-size:16px;font-weight:700;")
        topbar.addWidget(self._who)
        topbar.addStretch(1)
        topbar.addWidget(ui.muted("Εταιρία:"))
        self._accounts = QComboBox()
        self._accounts.setMinimumWidth(260)
        self._accounts.currentIndexChanged.connect(self._account_changed)
        topbar.addWidget(self._accounts)
        self._mode_label = ui.muted("")
        topbar.addWidget(self._mode_label)
        topbar.addWidget(ui.button("Έξοδος", self._do_logout, icon_name="lock"))
        header.addLayout(topbar)
        box.addWidget(header_card)

        # KPI row — filled from the cached statistics, so it paints instantly.
        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self._kpi_docs = ui.stat_tile("—", "Παραστατικά μήνα")
        self._kpi_turnover = ui.stat_tile("—", "Καθαρός τζίρος μήνα")
        self._kpi_unread = ui.stat_tile("—", "Νέες ειδοποιήσεις")
        for tile in (self._kpi_docs, self._kpi_turnover, self._kpi_unread):
            kpis.addWidget(tile, 1)
        box.addLayout(kpis)

        # Launcher tiles, three per row like the Downloader's home.
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, (key, label, description, icon_name) in enumerate(_SECTIONS):
            tile = ui.nav_tile(
                label, description, icon_name,
                lambda k=key: self._open_section(k),
            )
            grid.addWidget(tile, index // 3, index % 3)
        box.addLayout(grid)
        box.addStretch(1)
        return page

    def _refresh_home_kpis(self) -> None:
        """Fill the KPI tiles from the cached snapshots (no AADE round-trip)."""
        if self._client is None:
            return

        def stats_ok(data: dict) -> None:
            ui.set_tile_value(self._kpi_docs, str(data.get("total_count", 0)))
            ui.set_tile_value(
                self._kpi_turnover, f"{fmt_money(parse_money(data.get('total_value')))} €"
            )

        _run(lambda: self._client.statistics("month", cached=True), stats_ok, lambda m: None)
        _run(
            self._client.notif_count,
            lambda n: ui.set_tile_value(self._kpi_unread, str(n)),
            lambda m: None,
        )

    def _enter_home(self) -> None:
        self._mode_label.setText(
            "backend: τοπικό (offline)" if self._service.mode() == "offline" else "backend: server"
        )
        _run(self._client.me, self._fill_home, lambda m: None)
        _run(self._client.accounts, self._fill_accounts, lambda m: None)
        self._stack.setCurrentWidget(self._home)
        self._refresh_home_kpis()
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

    #: Sections that arrive already populated; the rest load on demand.
    #: Η Έκδοση ΔΕΝ είναι εδώ: χρειάζεται το πελατολόγιο και τις σειρές, τα
    #: οποία φορτώνει μία φορά η δική της refresh().
    # Σελίδες που δεν πρέπει να τραβήξουν δεδομένα μόλις ανοίξουν. Άδειασε: το
    # `refresh()` της Μαζικής φέρνει μόνο τις σειρές και του Πιστωτικού μόνο το
    # πελατολόγιο — και χωρίς αυτά οι επιλογείς τους θα ήταν άδειοι. Η ακριβή
    # αναζήτηση παραστατικών στο Πιστωτικό μένει πίσω από κουμπί.
    _NO_AUTOLOAD: set[str] = set()

    def open_section(self, key: str) -> None:
        """Navigate from outside (the side menu). Ignored until logged in."""
        if key == "home":
            if self._client is not None:
                self._stack.setCurrentWidget(self._home)
                self._refresh_home_kpis()
            return
        self._open_section(key)

    def _open_section(self, key: str) -> None:
        if self._client is None:
            return
        page = self._pages.get(key)
        if page is None:
            # Not ported (should not happen — every section is native now); fall
            # back to the web UI against the same backend.
            base = self._client.base_url()
            vat = self._accounts.currentData()
            url = f"{base}/app.php" + (f"?account={vat}" if vat else "") + f"#{key}"
            QDesktopServices.openUrl(QUrl(url))
            return
        if key == "settings":
            page.show_mode(self._service.mode(), self._service.server_url())
        self._stack.setCurrentWidget(page)
        if key not in self._NO_AUTOLOAD and hasattr(page, "refresh"):
            page.refresh()

    # --- native navigation -------------------------------------------------
    def _show_customers(self) -> None:
        self._stack.setCurrentWidget(self._customers)
        self._customers.refresh()

    def _show_card(self, customer: dict) -> None:
        self._card.set_customer(customer)
        self._stack.setCurrentWidget(self._card)

    def _edit_draft(self, draft: dict) -> None:
        """Ανοίγει ένα πρόχειρο στην Έκδοση για συνέχεια.

        Το ``temp_id`` περνά στη φόρμα, ώστε η αποθήκευση να ΕΝΗΜΕΡΩΣΕΙ το ίδιο
        πρόχειρο αντί να φτιάξει δεύτερο.
        """
        self.open_section("issue")
        self._issue.load_draft(draft)

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

    def _switch_backend(self, mode: str, server_url: str) -> None:
        """Move between the bundled local PHP and the shared server, live.

        Stops whatever is running, rewrites the stored mode and re-enters the
        normal startup path — so the user lands on the login (server) or is
        auto-logged in (offline) without restarting the application.
        """
        self._service.stop()
        self._service.set_mode(mode, server_url)
        self._client = None
        self._started = False
        self._set_status(
            "Σύνδεση στον server…" if mode == "thin" else "Εκκίνηση τοπικού backend…"
        )
        self.start()

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
