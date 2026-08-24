"""Πίνακας ελέγχου: ποιος είναι συνδεδεμένος και τι ακριβώς συμβαίνει.

Σε ένα γραφείο με server και τερματικά, οι ερωτήσεις που προκύπτουν στην πράξη
είναι πάντα οι ίδιες τρεις: «είμαι συνδεδεμένος;», «ποιος άλλος δουλεύει τώρα;»
και «γιατί μου λέει ότι τρέχει ήδη λήψη;». Μέχρι τώρα καμία δεν είχε απάντηση
μέσα από την εφαρμογή — ο χρήστης μάντευε από το αν έβλεπε πελάτες ή όχι.

Ο πίνακας ανανεώνεται μόνος του, αλλά ο έλεγχος σύνδεσης γίνεται μόνο όταν
ζητηθεί: αγγίζει το δίκτυο και σε χαλασμένο share μπλοκάρει για δευτερόλεπτα.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTime, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import presence, sharing, updates
from ..config import ROLE_LABELS_EL
from ..db import is_network_path
from ..locking import SyncLock
from ..schedule import DAY_NAMES, SyncSchedule
from . import updater
from .icons import icon
from .theme import CURRENT
from .widgets import ToggleSwitch

#: Κάθε πόσο ξαναζωγραφίζεται η λίστα συνδέσεων.
REFRESH_MS = 10_000


def _dot(online: bool) -> str:
    return "🟢" if online else "⚪"


class _BrowserProbeWorker(QObject):
    """Δοκιμάζει τους browsers για headless λειτουργία, εκτός GUI thread.

    Το άνοιγμα browser είναι αργό και μπλοκάρει· εδώ τρέχει σε δικό του thread
    και επιστρέφει τα αποτελέσματα ως απλή λίστα από πλειάδες.
    """

    done = Signal(list)  # list[(name, ok, detail)]
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            from ..download import headless

            results = [
                (p.name, p.ok, p.detail) for p in headless.probe_browsers()
            ]
            self.done.emit(results)
        except Exception as exc:  # noqa: BLE001 — να μη σκάει σιωπηλά το thread
            self.failed.emit(str(exc))


class ControlPanel(QWidget):
    """Σελίδα «Πίνακας ελέγχου» μέσα στο κύριο παράθυρο."""

    #: Ο χρήστης άλλαξε το «εκκίνηση στο tray».
    start_minimized_changed = Signal(bool)
    #: Ζητήθηκε επανέλεγχος σύνδεσης (το κύριο παράθυρο ξαναφορτώνει τη λίστα).
    reconnect_requested = Signal()
    #: Ο χρήστης πείραξε τον χρονοπρογραμματισμό της λήψης.
    schedule_changed = Signal(object)
    #: «Λήψη τώρα» από τον χρονοπρογραμματισμό.
    schedule_run_requested = Signal()
    #: Το e-Τιμολόγιο να δουλέψει σε server (url) ή τοπικά (κενό url).

    def __init__(
        self,
        *,
        data_dir: Path,
        db_path: Path,
        role: str,
        version: str,
        conn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._db_path = db_path
        self._role = role
        self._version = version
        self._conn = conn
        #: Οι πελάτες του προγράμματος όταν είναι «μόνο οι επιλεγμένοι».
        #: Τους κρατά το κύριο παράθυρο (εκεί ζει η λίστα) και τους περνά εδώ.
        self._sched_vats: tuple[str, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        root.addWidget(self._header())
        root.addWidget(self._identity_box())
        root.addWidget(self._peers_box(), 1)
        root.addWidget(self._schedule_box())
        root.addWidget(self._settings_box())

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()
        # Χωριστά από το refresh: κάθε έλεγχος ξεκινά PowerShell, που δεν αξίζει
        # να τρέχει κάθε δέκα δευτερόλεπτα για κάτι που αλλάζει σπάνια.
        QTimer.singleShot(0, self._refresh_share_state)

    # ------------------------------------------------------------------ UI
    def _header(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(icon("network", CURRENT.accent, 24).pixmap(24, 24))
        row.addWidget(mark)

        title = QLabel("Πίνακας ελέγχου")
        title.setObjectName("h1")
        row.addWidget(title)
        row.addStretch()

        self.btn_browser = QPushButton("Δοκιμή browser")
        self.btn_browser.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browser.setToolTip(
            "Δοκιμάζει τους εγκατεστημένους browsers (Edge/Chrome) σε αόρατη\n"
            "λειτουργία, όπως τους χρησιμοποιεί η αυτόματη λήψη «μόνο online».\n"
            "Δείχνει αν θα δουλέψει στο μηχάνημά σας."
        )
        self.btn_browser.clicked.connect(self.test_browsers)
        row.addWidget(self.btn_browser)

        self.btn_updates = QPushButton("Έλεγχος για ενημερώσεις")
        self.btn_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_updates.setToolTip(
            "Ρωτά το GitHub αν υπάρχει νεότερη έκδοση. Δεν κατεβαίνει τίποτα "
            "αυτόματα."
        )
        self.btn_updates.clicked.connect(self.check_updates)
        row.addWidget(self.btn_updates)

        self.btn_check = QPushButton("Έλεγχος σύνδεσης")
        self.btn_check.setObjectName("primary")
        self.btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check.setToolTip(
            "Ελέγχει τον φάκελο, το δικαίωμα εγγραφής και τη βάση, ένα προς ένα"
        )
        self.btn_check.clicked.connect(self.run_check)
        row.addWidget(self.btn_check)
        return holder

    # -------------------------------------------------------- ενημερώσεις
    def check_updates(self) -> None:
        """Χειροκίνητος έλεγχος (κουμπί). Δίνει πάντα απάντηση, ακόμη κι όταν
        είμαστε ενημερωμένοι — αλλιώς ο χρήστης δεν ξέρει αν έγινε ο έλεγχος."""
        self.btn_updates.setEnabled(False)
        self.btn_updates.setText("Έλεγχος…")

        self._upd_thread = QThread(self)
        self._upd_worker = updater.CheckWorker(self._version)
        self._upd_worker.moveToThread(self._upd_thread)
        self._upd_thread.started.connect(self._upd_worker.run)
        self._upd_worker.ok.connect(self._on_update_result)
        self._upd_worker.failed.connect(self._on_update_failed)
        self._upd_thread.start()

    def _stop_upd_thread(self) -> None:
        thread = getattr(self, "_upd_thread", None)
        if thread is not None:
            thread.quit()
            thread.wait(3000)
        self._upd_thread = None
        self._upd_worker = None
        self.btn_updates.setEnabled(True)
        self.btn_updates.setText("Έλεγχος για ενημερώσεις")

    def _on_update_result(self, info) -> None:
        self._stop_upd_thread()
        if info.is_newer:
            updater.Updater(self.window()).offer(info)
        else:
            QMessageBox.information(
                self, "Ενημερωμένο",
                f"Έχετε την τελευταία έκδοση (<b>{info.current}</b>).",
            )

    def _on_update_failed(self, detail: str) -> None:
        self._stop_upd_thread()
        QMessageBox.warning(
            self, "Δεν ολοκληρώθηκε ο έλεγχος",
            "Δεν ήταν δυνατή η σύνδεση στο GitHub για έλεγχο ενημερώσεων.<br><br>"
            "Ελέγξτε τη σύνδεσή σας στο internet και δοκιμάστε ξανά, ή δείτε "
            f'απευθείας τη <a href="{updates.RELEASES_URL}">σελίδα εκδόσεων</a>.'
            f"<br><br><span style='color:gray'>{detail[:200]}</span>",
        )

    # ------------------------------------------------------- δοκιμή browser
    def test_browsers(self) -> None:
        """Χειροκίνητη δοκιμή των browsers για headless (κουμπί).

        Τρέχει σε δικό του thread γιατί ανοίγει πραγματικούς browsers και αργεί.
        """
        self.btn_browser.setEnabled(False)
        self.btn_browser.setText("Δοκιμή…")

        self._probe_thread = QThread(self)
        self._probe_worker = _BrowserProbeWorker()
        self._probe_worker.moveToThread(self._probe_thread)
        self._probe_thread.started.connect(self._probe_worker.run)
        self._probe_worker.done.connect(self._on_browser_probe_done)
        self._probe_worker.failed.connect(self._on_browser_probe_failed)
        self._probe_thread.start()

    def _stop_probe_thread(self) -> None:
        thread = getattr(self, "_probe_thread", None)
        if thread is not None:
            thread.quit()
            thread.wait(3000)
        self._probe_thread = None
        self._probe_worker = None
        self.btn_browser.setEnabled(True)
        self.btn_browser.setText("Δοκιμή browser")

    def _on_browser_probe_done(self, results: list) -> None:
        self._stop_probe_thread()
        if not results:
            QMessageBox.warning(
                self, "Δοκιμή browser",
                "Δεν βρέθηκε Microsoft Edge ή Google Chrome στον υπολογιστή.\n\n"
                "Η αυτόματη λήψη «μόνο online» χρειάζεται έναν από τους δύο. Το "
                "Edge υπάρχει προεγκατεστημένο σε κάθε Windows 10/11 — αν λείπει, "
                "εγκαταστήστε Edge ή Chrome, ή χρησιμοποιήστε «Μέσω του browser "
                "μου».",
            )
            return
        lines = [
            f"{'✓' if ok else '✗'} <b>{name}</b> — {detail}"
            for name, ok, detail in results
        ]
        any_ok = any(ok for _, ok, _ in results)
        color = CURRENT.ok if any_ok else CURRENT.bad
        head = (
            "Η αυτόματη λήψη «μόνο online» θα δουλέψει."
            if any_ok else
            "Κανένας browser δεν απέδωσε PDF."
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information if any_ok else QMessageBox.Icon.Warning)
        box.setWindowTitle("Δοκιμή browser")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f'<div style="color:{color};"><b>{head}</b></div><br>'
            + "<br>".join(lines)
        )
        box.exec()

    def _on_browser_probe_failed(self, detail: str) -> None:
        self._stop_probe_thread()
        QMessageBox.warning(
            self, "Δοκιμή browser",
            f"Η δοκιμή δεν ολοκληρώθηκε.\n\n{detail[:300]}",
        )

    def _identity_box(self) -> QWidget:
        box = QGroupBox("Αυτός ο υπολογιστής")
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)

        self._rows: dict[str, QLabel] = {}
        for index, name in enumerate(
            ["Ρόλος", "Όνομα υπολογιστή", "Φάκελος δεδομένων", "Βάση", "Κατάσταση λήψης"]
        ):
            key = QLabel(name)
            key.setObjectName("muted")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(key, index, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, index, 1)
            self._rows[name] = value

        self.health = QLabel("")
        self.health.setWordWrap(True)
        self.health.setVisible(False)
        grid.addWidget(self.health, len(self._rows), 0, 1, 2)
        return box

    def _peers_box(self) -> QWidget:
        box = QGroupBox("Συνδέσεις")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        hint = QLabel(
            "Κάθε υπολογιστής που ανοίγει την εφαρμογή γράφει την παρουσία του "
            "στη βάση. «Ενεργός» σημαίνει ότι έδωσε σημείο ζωής το τελευταίο "
            "ενάμισι λεπτό."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["", "Υπολογιστής", "Ρόλος", "Έκδοση", "Τελευταία δραστηριότητα"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        return box

    def _schedule_box(self) -> QWidget:
        """Αυτόματη λήψη σε ώρα που δεν ενοχλεί.

        Ο λογιστής κατεβάζει τα ίδια πράγματα κάθε πρωί για τους ίδιους πελάτες.
        Η λήψη κρατά λεπτά και τρώει το δίκτυο· η φυσική της ώρα είναι πριν
        ανοίξει το γραφείο.
        """
        box = QGroupBox("Χρονοπρογραμματισμός λήψης")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.chk_schedule = ToggleSwitch("Αυτόματη λήψη παραστατικών")
        self.chk_schedule.setToolTip(
            "Η λήψη ξεκινά μόνη της την ώρα που ορίζεις, για τους πελάτες που "
            "έχουν κλειδί API"
        )
        self.chk_schedule.toggled.connect(self._emit_schedule)
        layout.addWidget(self.chk_schedule)

        when = QHBoxLayout()
        when.addWidget(QLabel("Ώρα:"))
        self.sched_time = QTimeEdit()
        self.sched_time.setDisplayFormat("HH:mm")
        self.sched_time.setFixedWidth(90)
        self.sched_time.timeChanged.connect(self._emit_schedule)
        when.addWidget(self.sched_time)
        when.addSpacing(12)
        when.addWidget(QLabel("Ημέρες:"))
        # Κενή επιλογή = κάθε μέρα. Το λέει και το «Σύνοψη» από κάτω, ώστε να μη
        # χρειάζεται να το μαντέψει κανείς.
        self.sched_days: list[QCheckBox] = []
        for index, name in enumerate(DAY_NAMES):
            day = QCheckBox(name)
            day.setToolTip("Καμία επιλεγμένη ημέρα σημαίνει «κάθε μέρα»")
            day.toggled.connect(self._emit_schedule)
            self.sched_days.append(day)
            when.addWidget(day)
        when.addStretch(1)
        layout.addLayout(when)

        who = QHBoxLayout()
        who.addWidget(QLabel("Πελάτες:"))
        self.sched_scope = QComboBox()
        self.sched_scope.addItem("Όλοι με κλειδί API", "all")
        self.sched_scope.addItem("Μόνο οι επιλεγμένοι", "selected")
        self.sched_scope.setToolTip(
            "«Οι επιλεγμένοι» = όσοι είναι τσεκαρισμένοι στη λίστα πελατών τη "
            "στιγμή που πατάς «Αποθήκευση». Πελάτης χωρίς κλειδί δεν συμμετέχει "
            "ποτέ."
        )
        self.sched_scope.currentIndexChanged.connect(self._emit_schedule)
        who.addWidget(self.sched_scope)
        self.btn_sched_now = QPushButton("Λήψη τώρα")
        self.btn_sched_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sched_now.setToolTip("Τρέχει αμέσως ό,τι θα έτρεχε το πρόγραμμα")
        self.btn_sched_now.clicked.connect(self.schedule_run_now)
        who.addWidget(self.btn_sched_now)
        who.addStretch(1)
        layout.addLayout(who)

        self.sched_state = QLabel("")
        self.sched_state.setWordWrap(True)
        self.sched_state.setObjectName("muted")
        layout.addWidget(self.sched_state)

        note = QLabel(
            "Η λήψη τρέχει μέσα στην εφαρμογή, οπότε το πρόγραμμα ισχύει όσο "
            "αυτή είναι ανοιχτή — γι' αυτό υπάρχει η «Εκκίνηση στο tray» "
            "παρακάτω. Ραντεβού που χάθηκε επειδή ο υπολογιστής ήταν κλειστός "
            "εκτελείται μόλις ανοίξει, την ίδια μέρα."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        note.setProperty("help_line", True)
        layout.addWidget(note)
        return box

    # --- πρόγραμμα: κατάσταση ↔ widgets ------------------------------------
    def schedule(self) -> SyncSchedule:
        """Ό,τι δείχνουν τώρα τα χειριστήρια."""
        days = frozenset(i for i, box in enumerate(self.sched_days) if box.isChecked())
        return SyncSchedule(
            enabled=self.chk_schedule.isChecked(),
            at=self.sched_time.time().toString("HH:mm"),
            days=days,
            scope=str(self.sched_scope.currentData() or "all"),
            vats=self._sched_vats,
        )

    def set_schedule(self, schedule: SyncSchedule) -> None:
        """Δείχνει ένα αποθηκευμένο πρόγραμμα, χωρίς να το ξαναεκπέμψει."""
        self._sched_vats = tuple(schedule.vats)
        widgets = [self.chk_schedule, self.sched_time, self.sched_scope, *self.sched_days]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.chk_schedule.setChecked(schedule.enabled)
            self.sched_time.setTime(QTime.fromString(schedule.at, "HH:mm"))
            for index, box in enumerate(self.sched_days):
                box.setChecked(index in schedule.days)
            position = self.sched_scope.findData(schedule.scope)
            self.sched_scope.setCurrentIndex(max(0, position))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self.show_schedule_state(schedule)

    def show_schedule_state(self, schedule: SyncSchedule, last_run=None) -> None:
        text = schedule.describe()
        upcoming = schedule.next_run(datetime.now(), last_run)
        if upcoming is not None:
            text += f"\nΕπόμενη: {upcoming:%d/%m/%Y %H:%M}"
        self.sched_state.setText(text)

    def _emit_schedule(self, *_args) -> None:
        self.schedule_changed.emit(self.schedule())


    def schedule_run_now(self) -> None:
        """Τρέχει ΤΩΡΑ ό,τι θα έτρεχε το πρόγραμμα (χωρίς να αλλάξει την ώρα)."""
        self.schedule_run_requested.emit()
    def _settings_box(self) -> QWidget:
        box = QGroupBox("Ρυθμίσεις δικτύου")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.chk_tray = ToggleSwitch("Εκκίνηση στο tray")
        self.chk_tray.setToolTip(
            "Η εφαρμογή ξεκινά χωρίς παράθυρο, ως εικονίδιο δίπλα στο ρολόι"
        )
        self.chk_tray.toggled.connect(self.start_minimized_changed.emit)
        layout.addWidget(self.chk_tray)

        note = QLabel(
            "Χρήσιμο στον server: μένει ανοιχτός ώστε ο φάκελος να είναι "
            "διαθέσιμος στα τερματικά, χωρίς να πιάνει χώρο στην επιφάνεια "
            "εργασίας. Διπλό κλικ στο εικονίδιο τον επαναφέρει."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        # Κοινή χρήση: μόνο όπου ο φάκελος είναι όντως εδώ. Ένα τερματικό δεν
        # μοιράζει τον φάκελο του server — τον χρησιμοποιεί.
        if self._role != "terminal":
            layout.addSpacing(6)
            share_row = QHBoxLayout()
            self.btn_share = QPushButton("Κοινή χρήση φακέλου…")
            self.btn_share.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_share.setToolTip(
                "Κάνει τον φάκελο προσβάσιμο από τα τερματικά του γραφείου"
            )
            self.btn_share.clicked.connect(self.open_share_dialog)
            share_row.addWidget(self.btn_share)

            self.share_state = QLabel("")
            self.share_state.setWordWrap(True)
            self.share_state.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            share_row.addWidget(self.share_state, 1)
            layout.addLayout(share_row)

        # Φάκελος λήψεων: ισχύει για κάθε PDF/ZIP που κατεβάζει το e-Τιμολόγιο.
        layout.addSpacing(10)
        dl_row = QHBoxLayout()
        dl_label = QLabel("Φάκελος λήψεων:")
        dl_row.addWidget(dl_label)
        self.dl_state = QLabel("")
        self.dl_state.setWordWrap(True)
        self.dl_state.setObjectName("muted")
        self.dl_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dl_row.addWidget(self.dl_state, 1)
        self.btn_dl = QPushButton("Αλλαγή…")
        self.btn_dl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dl.setToolTip(
            "Τα παραστατικά και οι καρτέλες αποθηκεύονται εδώ χωρίς να ρωτηθείς"
        )
        self.btn_dl.clicked.connect(self.choose_download_dir)
        dl_row.addWidget(self.btn_dl)
        self.btn_dl_clear = QPushButton("Να με ρωτά")
        self.btn_dl_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dl_clear.clicked.connect(lambda: self._set_download_dir(None))
        dl_row.addWidget(self.btn_dl_clear)
        layout.addLayout(dl_row)
        self._refresh_download_dir()
        return box

    # ------------------------------------------------------------ λήψεις
    def choose_download_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from .. import config

        current = config.load_download_dir() or (Path.home() / "Downloads")
        chosen = QFileDialog.getExistingDirectory(
            self, "Φάκελος λήψεων", str(current)
        )
        if chosen:
            self._set_download_dir(Path(chosen))

    def _set_download_dir(self, path: Path | None) -> None:
        from .. import config

        config.save_download_dir(path)
        self._refresh_download_dir()

    def _refresh_download_dir(self) -> None:
        from .. import config

        current = config.load_download_dir()
        self.dl_state.setText(
            str(current) if current else "(ερωτάται κάθε φορά)"
        )
        self.btn_dl_clear.setEnabled(current is not None)

    def open_share_dialog(self) -> None:
        from .share_dialog import ShareDialog

        dialog = ShareDialog(self._data_dir, self._has_master_password(), self)
        dialog.exec()
        self._refresh_share_state()

    def _has_master_password(self) -> bool:
        """Ώστε το παράθυρο να προειδοποιήσει πριν εκθέσει κλειδιά στο δίκτυο."""
        try:
            from ..crypto import is_protected

            return is_protected(self._data_dir / ".enckey")
        except Exception:  # pragma: no cover - η προειδοποίηση δεν πρέπει να σκάει
            return False

    def _refresh_share_state(self) -> None:
        if self._role == "terminal" or not hasattr(self, "share_state"):
            return
        share = sharing.find_share_for(self._data_dir)
        if share:
            self.share_state.setText(
                f'<span style="color:{CURRENT.ok};">✓ Κοινόχρηστος ως</span> '
                f"<b>{share.unc}</b>"
            )
            self.btn_share.setText("Ρυθμίσεις κοινής χρήσης…")
        else:
            self.share_state.setText(
                f'<span style="color:{CURRENT.muted};">Δεν είναι κοινόχρηστος — '
                "τα τερματικά δεν μπορούν να συνδεθούν.</span>"
                if self._role == "server"
                else ""
            )
            self.btn_share.setText("Κοινή χρήση φακέλου…")

    # -------------------------------------------------------------- δεδομένα
    def set_start_minimized(self, value: bool) -> None:
        """Χωρίς blockSignals θα γραφόταν ξανά η ίδια τιμή στο registry."""
        self.chk_tray.blockSignals(True)
        self.chk_tray.setChecked(value)
        self.chk_tray.blockSignals(False)

    def refresh(self) -> None:
        self._refresh_identity()
        self._refresh_peers()

    def _refresh_identity(self) -> None:
        self._rows["Ρόλος"].setText(ROLE_LABELS_EL.get(self._role, self._role))
        self._rows["Όνομα υπολογιστή"].setText(
            f"{presence.host_name()}\\{presence.user_name()}"
        )
        self._rows["Φάκελος δεδομένων"].setText(str(self._data_dir))

        if self._db_path.exists():
            size_mb = self._db_path.stat().st_size / (1024 * 1024)
            where = "δικτυακός φάκελος" if is_network_path(self._db_path) else "τοπικός δίσκος"
            self._rows["Βάση"].setText(f"{size_mb:.1f} MB · {where}")
        else:
            self._rows["Βάση"].setText("Δεν βρέθηκε")

        info = SyncLock(self._data_dir).read_info()
        if info:
            self._rows["Κατάσταση λήψης"].setText(
                f"Εκτελείται λήψη από «{info.holder}» (από {info.since})"
            )
        else:
            self._rows["Κατάσταση λήψης"].setText("Καμία λήψη σε εξέλιξη")

    def _refresh_peers(self) -> None:
        peers = presence.list_peers(self._conn)
        self.table.setRowCount(len(peers))
        for row, peer in enumerate(peers):
            label = peer.label + (" (αυτός ο υπολογιστής)" if peer.is_self else "")
            values = [
                _dot(peer.online),
                label,
                ROLE_LABELS_EL.get(peer.role, peer.role).split(" (")[0],
                peer.version or "—",
                f"{peer.ago_el()} · {peer.last_seen_local()}",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if not peer.online:
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, column, item)

    # ---------------------------------------------------------------- έλεγχος
    def run_check(self) -> None:
        self.btn_check.setEnabled(False)
        try:
            health = presence.check_connection(self._data_dir, self._db_path)
        finally:
            self.btn_check.setEnabled(True)

        lines = [
            f"{'✓' if check.ok else '✗'} <b>{check.name}</b> — {check.detail}"
            for check in health.checks
        ]
        color = CURRENT.ok if health.ok else CURRENT.bad
        head = (
            "Η σύνδεση λειτουργεί."
            if health.ok
            else "Υπάρχει πρόβλημα σύνδεσης."
        )
        self.health.setText(
            f'<div style="color:{color};"><b>{head}</b></div>'
            + "<br>".join(lines)
        )
        self.health.setVisible(True)
        if health.ok:
            self.reconnect_requested.emit()
