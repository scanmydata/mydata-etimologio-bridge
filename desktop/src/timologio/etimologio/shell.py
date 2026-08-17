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
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..gui.icons import logo_pixmap
from ..gui.theme import CURRENT
from ..gui.widgets import add_reveal
from .client import EtimologioClient
from .pages import (
    AdminPage,
    BulkPage,
    CompaniesPage,
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
from .pages.assistant_panel import AssistantPanel
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
    # Η καρτέλα είναι ενότητα, όχι υποσέλιδο των Πελατών: στο web έχει δική της
    # εγγραφή στο μενού («📇 Καρτέλα»), εδώ έφτανες μόνο με διπλό κλικ.
    ("card", "Καρτέλα", "Κίνηση & υπόλοιπο πελάτη", "csv"),
    # Το γραφείο δουλεύει ΠΟΛΛΕΣ εταιρείες: ο κατάλογός τους είναι ενότητα, όχι
    # ένα «＋» δίπλα σε ένα dropdown.
    ("companies", "Εταιρείες", "Πελάτες του γραφείου", "network"),
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
#: Κλειδί → ετικέτα, για τη γραμμή θέσης της μόνιμης μπάρας.
_SECTION_LABELS = {key: label for key, label, _desc, _icon in _SECTIONS}


class EtimologioShell(QWidget):
    """Self-contained e-Τιμολόγιο Pro surface, embeddable as one page."""

    def __init__(self, data_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = EtimologioService(data_dir)
        self._client: EtimologioClient | None = None
        self._started = False
        #: Set by focus_customer() before login; replayed once home is reached.
        self._pending_focus_vat = ""

        #: Ιστορικό πλοήγησης — το ← γύριζε πάντα στην αρχική, ό,τι κι αν είχε
        #: προηγηθεί, οπότε από μια Καρτέλα έχανες τη λίστα πελατών.
        self._history: list[str] = []

        self._stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        # Μόνιμη μπάρα εταιρείας πάνω από ΟΛΕΣ τις σελίδες — όπως ο ενεργός
        # πελάτης στον Downloader. Ήταν κρυμμένη μέσα στην αρχική, οπότε από
        # οποιαδήποτε σελίδα δεν φαινόταν σε ποια εταιρεία δουλεύεις.
        self._topbar = self._build_company_bar()
        root.addWidget(self._topbar)
        root.addWidget(self._stack)

        self._status = self._build_status_page()
        self._login = self._build_login_page()
        self._home = self._build_home_page()

        # Native pages (Phase 1). They read the live client lazily via the
        # accessor, so they can be built before login completes.
        self._customers = CustomersPage(lambda: self._client, _run)
        self._companies = CompaniesPage(lambda: self._client, _run)
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

        # Κάθε ← περνά από το ιστορικό, ώστε να γυρίζει εκεί από όπου ήρθε ο
        # χρήστης — όχι πάντα στην αρχική.
        self._customers.open_card.connect(self._show_card)
        self._card.credit_requested.connect(self._credit_from_card)
        self._companies.open_company.connect(self._switch_company)
        self._companies.accounts_changed.connect(self._load_accounts)
        self._notifications.unread_changed.connect(self.set_unread)
        self._settings.mode_change_requested.connect(self._switch_backend)
        self._drafts.open_in_issue.connect(self._edit_draft)
        #: Section key → page, used for both navigation and construction.
        self._pages = {
            "issue": self._issue, "credit": self._credit, "bulk": self._bulk,
            "customers": self._customers, "card": self._card,
            "companies": self._companies,
            "products": self._products,
            "series": self._series, "drafts": self._drafts,
            "payments": self._payments, "stats": self._stats,
            "documents": self._documents, "schedule": self._schedule,
            "notifications": self._notifications, "settings": self._settings,
            "admin": self._admin,
        }
        for page in self._pages.values():
            page.go_back.connect(self.go_back)

        # --- ο ψηφιακός βοηθός ---------------------------------------------
        # Ζει πάνω από όλες τις σελίδες, σαν το πλωτό panel του web. Διαβάζει
        # πελάτες και είδη από την Έκδοση (που τα φορτώνει ούτως ή άλλως), ώστε
        # να μην υπάρχει δεύτερο αντίγραφο του πελατολογίου.
        self._assistant = AssistantPanel(
            self,
            data_dir=self._service.data_dir,
            customers=self._issue.known_customers,
            products=self._issue.known_products,
        )
        self._assistant.navigate.connect(self.open_section)
        self._assistant.open_dialog.connect(self._assistant_dialog)
        self._assistant.prepare_draft.connect(self._assistant_draft)
        self._assistant.fetch_requested.connect(self._assistant_fetch)
        self._issue.assistant_said.connect(self._assistant.say)
        shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.toggle_assistant)

        # Alt+← και Esc: η ίδια πλοήγηση με το κουμπί, χωρίς ποντίκι. Το Esc
        # κλείνει πρώτα τον βοηθό — αλλιώς το panel θα έμενε ανοιχτό ενώ η
        # σελίδα από κάτω άλλαζε.
        for sequence, slot in (
            (QKeySequence("Alt+Left"), self.go_back),
            (QKeySequence(Qt.Key.Key_Escape), self._escape),
            (QKeySequence("Ctrl+K"), self.open_palette),
        ):
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        for w in (self._status, self._login, self._home, *self._pages.values()):
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
        # Πρώτα το μικρόφωνο: το νήμα της αναγνώρισης πρέπει να σταματήσει πριν
        # καταστραφούν τα widget του, αλλιώς κρέμεται το κλείσιμο.
        self._assistant.shutdown()
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
        self._password = add_reveal(QLineEdit())
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

    # --- μόνιμη μπάρα εταιρείας --------------------------------------------
    def _build_company_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 6, 14, 6)
        row.setSpacing(8)

        # Κανονικό κουμπί με εικονίδιο και ετικέτα, όπως το «Πελάτες» της
        # προβολής παραστατικών. Η γλυφή «←» σε κουμπί πλάτους 38 έβγαινε
        # μικροσκοπική δίπλα στα υπόλοιπα κουμπιά της μπάρας.
        self._back_btn = ui.button("Πίσω", self.go_back, icon_name="back",
                                   tip="Επιστροφή στην προηγούμενη σελίδα (Alt+←)")
        row.addWidget(self._back_btn)
        self._crumb = QLabel("")
        self._crumb.setStyleSheet("font-weight:600;")
        row.addWidget(self._crumb)
        row.addStretch(1)

        row.addWidget(ui.muted("Εταιρία:"))
        self._accounts = QComboBox()
        self._accounts.setMinimumWidth(260)
        self._accounts.currentIndexChanged.connect(self._account_changed)
        row.addWidget(self._accounts)
        row.addWidget(ui.button("＋", self._add_company, tip="Προσθήκη εταιρείας ΑΑΔΕ"))
        self._mode_label = ui.muted("")
        row.addWidget(self._mode_label)
        # Καμπανάκι: ο αριθμός των αδιάβαστων ήταν ορατός μόνο στην αρχική, οπότε
        # μια έκδοση που έγινε ενώ δούλευες αλλού περνούσε απαρατήρητη.
        self._bell = ui.button("🔔", lambda: self.open_section("notifications"),
                               tip="Ειδοποιήσεις")
        self._bell.setFixedWidth(52)
        row.addWidget(self._bell)
        row.addWidget(ui.button("🔍", self.open_palette, tip="Αναζήτηση (Ctrl+K)"))
        row.addWidget(ui.button("🤖 Βοηθός", self.toggle_assistant, tip="Ψηφιακός βοηθός (Ctrl+B)"))
        row.addWidget(ui.button("Έξοδος", self._do_logout, icon_name="lock"))
        bar.hide()          # φαίνεται μόλις γίνει η σύνδεση
        return bar

    def _add_company(self) -> None:
        """Καταχώρηση λογαριασμού ΑΑΔΕ χωρίς να φύγει ο χρήστης από την εφαρμογή.

        Χωρίς αυτό μια καθαρή εγκατάσταση συνδεόταν ως master με μηδέν εταιρείες
        και κάθε σελίδα γύριζε άδεια, χωρίς καμία διέξοδο μέσα από το UI.
        """
        if self._client is None:
            return
        from .pages.company import AddCompanyDialog

        dialog = AddCompanyDialog(self, client=self._client, run=_run)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._load_accounts()

    # --- πλοήγηση με ιστορικό ----------------------------------------------
    def go_back(self) -> None:
        """Επιστροφή εκεί από όπου ήρθε ο χρήστης, όχι πάντα στην αρχική."""
        if self._history:
            self.open_section(self._history.pop(), remember=False)
            return
        self._show_home()

    def _show_home(self) -> None:
        self._stack.setCurrentWidget(self._home)
        self._crumb.setText("Αρχική")
        self._back_btn.setEnabled(False)
        self._refresh_home_kpis()

    # --- home page ---------------------------------------------------------
    def _build_home_page(self) -> QWidget:
        """The e-Τιμολόγιο home, laid out like the Downloader's control panel:
        a header card (who/company/mode), KPI tiles, then a grid of launchers."""
        page, box = ui.page()

        # Ο επιλογέας εταιρείας ζει πλέον στη μόνιμη μπάρα· εδώ μένει μόνο ο
        # χαιρετισμός.
        header_card, header = ui.card()
        topbar = QHBoxLayout()
        self._who = QLabel("")
        self._who.setStyleSheet("font-size:16px;font-weight:700;")
        topbar.addWidget(self._who)
        topbar.addStretch(1)
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
        _run(self._client.notif_count, self.set_unread, lambda m: None)

    def _enter_home(self) -> None:
        self._mode_label.setText(
            "backend: τοπικό (offline)" if self._service.mode() == "offline" else "backend: server"
        )
        _run(self._client.me, self._fill_home, lambda m: None)
        self._load_accounts()
        self._topbar.show()
        self._history.clear()
        self._show_home()
        self._apply_pending_focus()

    def _load_accounts(self) -> None:
        if self._client is not None:
            _run(self._client.accounts, self._fill_accounts, lambda m: None)

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
        self._card.set_account(str(self._accounts.currentData() or ""))

    def _account_changed(self, _index: int) -> None:
        if self._client is None:
            return
        vat = self._accounts.currentData()
        if not vat:
            return
        self._client.set_account(str(vat))
        # Η Καρτέλα θυμάται τον τελευταίο πελάτη **ανά εταιρεία**.
        self._card.set_account(str(vat))
        # Οι σελίδες κρατούν φορτωμένα δεδομένα της ΠΡΟΗΓΟΥΜΕΝΗΣ εταιρείας — το
        # πελατολόγιο της Έκδοσης, οι σειρές της Μαζικής, οι πελάτες του
        # Πιστωτικού. Χωρίς ακύρωση, ο χρήστης τιμολογούσε σε πελάτη που δεν
        # ανήκει στην επιλεγμένη εταιρεία.
        for page in self._pages.values():
            invalidate = getattr(page, "invalidate", None)
            if callable(invalidate):
                invalidate()
        current = self._stack.currentWidget()
        if current is not self._home and hasattr(current, "refresh"):
            current.refresh()
        self._refresh_home_kpis()

    #: Sections that arrive already populated; the rest load on demand.
    #: Η Έκδοση ΔΕΝ είναι εδώ: χρειάζεται το πελατολόγιο και τις σειρές, τα
    #: οποία φορτώνει μία φορά η δική της refresh().
    # Σελίδες που δεν πρέπει να τραβήξουν δεδομένα μόλις ανοίξουν. Άδειασε: το
    # `refresh()` της Μαζικής φέρνει μόνο τις σειρές και του Πιστωτικού μόνο το
    # πελατολόγιο — και χωρίς αυτά οι επιλογείς τους θα ήταν άδειοι. Η ακριβή
    # αναζήτηση παραστατικών στο Πιστωτικό μένει πίσω από κουμπί.
    #: Η Καρτέλα δεν ανανεώνεται αυτόματα από το ``_open_section``: όταν την
    #: ανοίγει ένας πελάτης (Πελάτες, παλέτα), το ``set_customer`` φορτώνει ήδη
    #: την κίνηση — δύο κλήσεις ledger για το ίδιο πράγμα.
    _NO_AUTOLOAD: set[str] = {"card"}

    def open_section(self, key: str, *, remember: bool = True) -> None:
        """Navigate from outside (the side menu). Ignored until logged in."""
        if key == "home":
            if self._client is not None:
                self._history.clear()
                self._show_home()
            return
        self._open_section(key, remember=remember)
        # Από το μενού η Καρτέλα ανοίγει χωρίς πελάτη: γεμίζει τον επιλογέα και
        # ζητά επιλογή, αντί να μένει κενή σαν χαλασμένη.
        if key == "card" and self._client is not None:
            self._card.refresh()

    def _open_section(self, key: str, *, remember: bool = True) -> None:
        if self._client is None:
            return
        if remember:
            current = self._current_key()
            if current and current != key:
                self._history.append(current)
        self._crumb.setText(_SECTION_LABELS.get(key, ""))
        self._back_btn.setEnabled(True)
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

    # --- καμπανάκι & παλέτα -------------------------------------------------
    def set_unread(self, count: int) -> None:
        """Ο αριθμός των αδιάβαστων, πάνω στο καμπανάκι."""
        number = int(count or 0)
        self._bell.setText(f"🔔 {number}" if number else "🔔")
        self._bell.setToolTip(
            f"{number} νέες ειδοποιήσεις" if number else "Ειδοποιήσεις"
        )
        ui.set_tile_value(self._kpi_unread, str(number))

    def open_palette(self) -> None:
        """Ctrl+K: μία γραμμή για πελάτη ή ενότητα."""
        if self._client is None:
            return
        from .pages.palette import CommandPalette

        palette = CommandPalette(
            self, sections=[(k, label) for k, label, _d, _i in _SECTIONS],
            get_client=lambda: self._client, run=_run,
        )
        palette.open_section.connect(self.open_section)
        palette.open_customer.connect(self._show_card)
        palette.exec()

    # --- ψηφιακός βοηθός ----------------------------------------------------
    def toggle_assistant(self) -> None:
        """Ανοίγει/κλείνει τον βοηθό. Χωρίς σύνδεση δεν έχει τι να κάνει."""
        if self._client is None:
            return
        # Ο βοηθός διαβάζει το πελατολόγιο και τον κατάλογο ειδών της Έκδοσης —
        # αν ο χρήστης δεν άνοιξε ποτέ την Έκδοση, δεν έχουν φορτωθεί ακόμη.
        self._issue.refresh()
        self._assistant.toggle()

    def _escape(self) -> None:
        if self._assistant.isVisible():
            self._assistant.hide()
            return
        self.go_back()

    def _assistant_dialog(self, kind: str, prefill: dict) -> None:
        self.open_section("issue")
        if kind == "customer":
            self._issue.open_new_customer(prefill)
        elif kind == "product":
            self._issue.open_new_product(prefill)

    def _assistant_draft(self, spec) -> None:
        self.open_section("issue")
        self._issue.prepare_draft(spec)

    def _assistant_fetch(self, kind: str) -> None:
        """Τα δύο ερωτήματα που κάνει ο βοηθός στο backend."""
        if self._client is None:
            return
        client = self._client
        if kind == "notifications":
            _run(
                client.notif_count,
                lambda n: self._assistant.report(kind, n),
                lambda msg: self._assistant.say(f"Δεν μπόρεσα να δω τις ειδοποιήσεις: {msg}"),
            )
            return
        if kind.startswith("stats"):
            period = kind.partition(":")[2] or "year"
            _run(
                lambda: client.statistics(period),
                lambda data: self._assistant.report(kind, data),
                lambda msg: self._assistant.say(f"Δεν μπόρεσα να φέρω στατιστικά: {msg}"),
            )

    # --- βοήθεια ------------------------------------------------------------
    def page(self, key: str):
        """Η σελίδα ενός κλειδιού — το χρησιμοποιεί η ξενάγηση για στόχους."""
        return self._pages.get(key)

    def start_tour(self) -> None:
        from ..gui.tour import Tour
        from .help import tour_steps

        if self._client is None:
            return
        Tour(self, tour_steps(self)).start()

    def open_manual(self) -> None:
        """Ανοίγει το εγχειρίδιο, και **λέει** αν δεν τα κατάφερε.

        Το «δεν λειτουργεί το εγχειρίδιο» ήταν σιωπηλή αποτυχία: το PDF
        χτιζόταν κανονικά, αλλά το άνοιγμα γινόταν με `QDesktopServices` και,
        αν αυτό δεν έπιανε, δεν εμφανιζόταν τίποτα — ούτε μήνυμα, ούτε
        καταγραφή. Ο Downloader ανοίγει τα δικά του αρχεία με `os.startfile`
        και δουλεύει· ίδιος δρόμος τώρα (`ui.open_file`).
        """
        from .help import ensure_manual

        # Στον φάκελο δεδομένων, όχι δίπλα στο εκτελέσιμο: το Program Files δεν
        # είναι εγγράψιμο για απλό χρήστη.
        try:
            path = ensure_manual(self._service.data_dir)
        except Exception as exc:  # noqa: BLE001 — κάθε αποτυχία πρέπει να φαίνεται
            log.exception("Το εγχειρίδιο δεν δημιουργήθηκε")
            QMessageBox.warning(
                self, "Εγχειρίδιο",
                f"Το εγχειρίδιο δεν μπόρεσε να ανοίξει.\n\n{exc}",
            )
            return
        ui.open_file(path, self)

    def _current_key(self) -> str:
        """Το κλειδί της σελίδας που φαίνεται τώρα ('' για αρχική/καρτέλα)."""
        current = self._stack.currentWidget()
        for key, page in self._pages.items():
            if page is current:
                return key
        return ""

    # --- native navigation -------------------------------------------------
    def _show_customers(self) -> None:
        self._stack.setCurrentWidget(self._customers)
        self._customers.refresh()

    def _show_card(self, customer: dict) -> None:
        """Άνοιγμα της Καρτέλας με συγκεκριμένο πελάτη (από Πελάτες ή παλέτα)."""
        # Το πελατολόγιο ταξιδεύει μαζί όταν υπάρχει: ο διάλογος «+ Πληρωμή»
        # της καρτέλας άνοιγε με άδειο επιλογέα πελάτη. Αν λείπει, η καρτέλα το
        # φορτώνει μόνη της (load_customers).
        rows = self._customers.rows()
        if rows:
            self._card.set_customers(rows)
        self._open_section("card")
        self._card.set_customer(customer)

    def _switch_company(self, vat: str) -> None:
        """«Άνοιγμα» από τη σελίδα Εταιρειών: αλλάζει ενεργή εταιρεία και φεύγει.

        Περνά από τον ίδιο επιλογέα της μπάρας, ώστε να τρέξει το ένα και
        μοναδικό `_account_changed` — αυτό ακυρώνει τα δεδομένα της
        προηγούμενης εταιρείας σε κάθε σελίδα.
        """
        index = self._accounts.findData(str(vat))
        if index < 0:
            return
        if index == self._accounts.currentIndex():
            self._account_changed(index)      # ίδια εταιρεία: απλή ανανέωση
        else:
            self._accounts.setCurrentIndex(index)
        self._show_home()

    def _credit_from_card(self, invoice: dict) -> None:
        """«↩ Ακύρωση» από την Καρτέλα → Πιστωτικό με το παραστατικό έτοιμο."""
        self.open_section("credit")
        self._credit.pick_invoice(invoice)

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
