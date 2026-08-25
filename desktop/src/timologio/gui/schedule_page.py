"""Χρονοπρογραμματισμός λήψης — δική του σελίδα.

Ζούσε ως τρίτο κουτί μέσα στον Πίνακα ελέγχου, ανάμεσα στις συνδέσεις δικτύου
και στις ρυθμίσεις φακέλου. Δύο πράγματα δεν δούλευαν εκεί, και τα δύο για τον
ίδιο λόγο — **δεν χωρούσε**:

* σε παράθυρο που δεν ήταν πλήρους οθόνης, οι επεξηγήσεις κόβονταν στη μέση και
  τα χειριστήρια έβγαιναν εκτός πλαισίου·
* το «μόνο οι επιλεγμένοι» δεν είχε πού να δείξει ΠΟΙΟΙ. Ο χρήστης το διάλεγε
  και δεν έβλεπε λίστα πουθενά: η επιλογή γινόταν σιωπηλά από τα τσεκαρισμένα
  κουτάκια μιας άλλης οθόνης, που μπορεί να μην είχε ανοίξει ποτέ.

Εδώ η λίστα είναι μπροστά σου και ανήκει στο πρόγραμμα: ό,τι τσεκάρεις εδώ
είναι ό,τι θα κατέβει, ανεξάρτητα από το τι είναι επιλεγμένο αλλού.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..schedule import DAY_NAMES, SyncSchedule


class SchedulePage(QWidget):
    """Ώρα, ημέρες και ΠΟΙΟΙ πελάτες."""

    schedule_changed = Signal(object)   # SyncSchedule
    run_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: (ΑΦΜ, επωνυμία) όσων έχουν κλειδί API. Τους δίνει το παράθυρο.
        self._clients: list[tuple[str, str]] = []
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Ολόκληρη η σελίδα κυλά. Σε ύψος παραθύρου 700px τα κουτιά χωρούν ίσα
        # ίσα· σε 600 δεν χωρούσαν, και ό,τι περίσσευε απλώς κοβόταν.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        title = QLabel("⏰ Χρονοπρογραμματισμός λήψης")
        title.setObjectName("h1")
        root.addWidget(title)

        intro = QLabel(
            "Ο λογιστής κατεβάζει τα ίδια πράγματα κάθε πρωί για τους ίδιους "
            "πελάτες. Η λήψη κρατά λεπτά και τρώει το δίκτυο· η φυσική της ώρα "
            "είναι πριν ανοίξει το γραφείο."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        intro.setProperty("help_line", True)
        root.addWidget(intro)

        root.addWidget(self._when_box())
        root.addWidget(self._who_box(), 1)
        root.addWidget(self._state_box())
        body.setLayout(root)

    # ------------------------------------------------------------------ UI
    def _when_box(self) -> QWidget:
        box = QGroupBox("Πότε")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        from .widgets import ToggleSwitch

        self.chk_enabled = ToggleSwitch("Αυτόματη λήψη παραστατικών")
        self.chk_enabled.setToolTip(
            "Η λήψη ξεκινά μόνη της την ώρα που ορίζεις, για τους πελάτες που "
            "έχουν κλειδί API"
        )
        self.chk_enabled.toggled.connect(self._emit)
        layout.addWidget(self.chk_enabled)

        when = QHBoxLayout()
        when.setSpacing(8)
        when.addWidget(QLabel("Ώρα:"))
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.time.setFixedWidth(90)
        self.time.timeChanged.connect(self._emit)
        when.addWidget(self.time)
        when.addStretch(1)
        layout.addLayout(when)

        # Οι ημέρες σε δική τους γραμμή που **αναδιπλώνεται**: επτά κουτάκια
        # δίπλα στην ώρα δεν χωρούν σε στενό παράθυρο, και έβγαιναν έξω.
        days_label = QLabel("Ημέρες:")
        layout.addWidget(days_label)
        days = QHBoxLayout()
        days.setSpacing(6)
        self.days: list[QCheckBox] = []
        for name in DAY_NAMES:
            day = QCheckBox(name)
            day.setToolTip("Καμία επιλεγμένη ημέρα σημαίνει «κάθε μέρα»")
            day.toggled.connect(self._emit)
            self.days.append(day)
            days.addWidget(day)
        days.addStretch(1)
        layout.addLayout(days)
        return box

    def _who_box(self) -> QWidget:
        box = QGroupBox("Ποιοι πελάτες")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItem("Όλοι με κλειδί API", "all")
        self.scope.addItem("Μόνο οι επιλεγμένοι", "selected")
        self.scope.currentIndexChanged.connect(self._scope_changed)
        row.addWidget(self.scope)
        row.addStretch(1)
        self.btn_refresh = QPushButton("↻ Ανανέωση λίστας")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_requested)
        row.addWidget(self.btn_refresh)
        layout.addLayout(row)

        self.picker = QWidget()
        picker = QVBoxLayout(self.picker)
        picker.setContentsMargins(0, 4, 0, 0)
        picker.setSpacing(6)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Αναζήτηση ΑΦΜ ή επωνυμίας…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        tools.addWidget(self.search, 1)
        for text, value in (("Όλους", True), ("Κανέναν", False)):
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self._check_visible(v))
            tools.addWidget(button)
        picker.addLayout(tools)

        self.list = QListWidget()
        self.list.setMinimumHeight(160)
        self.list.itemChanged.connect(self._emit)
        picker.addWidget(self.list, 1)

        self.count = QLabel("")
        self.count.setObjectName("muted")
        picker.addWidget(self.count)
        layout.addWidget(self.picker, 1)

        note = QLabel(
            "Πελάτης χωρίς κλειδί API δεν συμμετέχει ποτέ — δεν εμφανίζεται καν "
            "σε αυτή τη λίστα. Η επιλογή ανήκει στο πρόγραμμα: δεν αλλάζει από "
            "τα τσεκαρισμένα κουτάκια της οθόνης «Λήψη»."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        note.setProperty("help_line", True)
        layout.addWidget(note)
        return box

    def _state_box(self) -> QWidget:
        box = QGroupBox("Κατάσταση")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.state = QLabel("")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)

        row = QHBoxLayout()
        self.btn_now = QPushButton("▶ Λήψη τώρα")
        self.btn_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_now.setToolTip("Τρέχει αμέσως ό,τι θα έτρεχε το πρόγραμμα")
        self.btn_now.clicked.connect(self.run_requested)
        row.addWidget(self.btn_now)
        row.addStretch(1)
        layout.addLayout(row)

        note = QLabel(
            "Η λήψη τρέχει μέσα στην εφαρμογή, οπότε το πρόγραμμα ισχύει όσο "
            "αυτή είναι ανοιχτή — γι' αυτό υπάρχει η «Εκκίνηση στο tray» στον "
            "Πίνακα ελέγχου. Ραντεβού που χάθηκε επειδή ο υπολογιστής ήταν "
            "κλειστός εκτελείται μόλις ανοίξει, την ίδια μέρα και μία φορά."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        note.setProperty("help_line", True)
        layout.addWidget(note)
        return box

    # --------------------------------------------------------------- λίστα
    def set_clients(self, clients) -> None:
        """Οι πελάτες με κλειδί API, ως (ΑΦΜ, επωνυμία)."""
        chosen = set(self.selected_vats())
        self._clients = [(str(v), str(n or v)) for v, n in clients]
        self._loading = True
        try:
            self.list.clear()
            for vat, name in self._clients:
                item = QListWidgetItem(f"{name}  ·  {vat}")
                item.setData(Qt.ItemDataRole.UserRole, vat)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if vat in chosen else Qt.CheckState.Unchecked
                )
                self.list.addItem(item)
        finally:
            self._loading = False
        self._filter(self.search.text())

    def _items(self):
        return (self.list.item(i) for i in range(self.list.count()))

    def selected_vats(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self._items()
            if item.checkState() == Qt.CheckState.Checked
        )

    def _filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        shown = 0
        for item in self._items():
            hit = not needle or needle in item.text().lower()
            item.setHidden(not hit)
            shown += hit
        picked = len(self.selected_vats())
        total = self.list.count()
        self.count.setText(
            f"{picked} από {total} επιλεγμένοι"
            + (f" · {shown} στη λίστα" if needle else "")
        )

    def _check_visible(self, value: bool) -> None:
        """«Όλους»/«Κανέναν» αφορά ΟΣΟΥΣ ΦΑΙΝΟΝΤΑΙ.

        Με ενεργό φίλτρο, ένα «Όλους» που τσέκαρε και τους κρυμμένους θα ήταν
        παγίδα: βλέπεις τρεις, κατεβάζεις τριακόσιους.
        """
        self._loading = True
        try:
            state = Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
            for item in self._items():
                if not item.isHidden():
                    item.setCheckState(state)
        finally:
            self._loading = False
        self._emit()

    def _scope_changed(self, *_args) -> None:
        self.picker.setVisible(str(self.scope.currentData() or "all") == "selected")
        self._emit()

    # ----------------------------------------------------------- κατάσταση
    def schedule(self) -> SyncSchedule:
        days = frozenset(i for i, box in enumerate(self.days) if box.isChecked())
        return SyncSchedule(
            enabled=self.chk_enabled.isChecked(),
            at=self.time.time().toString("HH:mm"),
            days=days,
            scope=str(self.scope.currentData() or "all"),
            vats=self.selected_vats(),
        )

    def set_schedule(self, schedule: SyncSchedule) -> None:
        """Δείχνει αποθηκευμένο πρόγραμμα, χωρίς να το ξαναεκπέμψει."""
        self._loading = True
        widgets = [self.chk_enabled, self.time, self.scope, *self.days]
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.chk_enabled.setChecked(schedule.enabled)
            self.time.setTime(QTime.fromString(schedule.at, "HH:mm"))
            for index, box in enumerate(self.days):
                box.setChecked(index in schedule.days)
            position = self.scope.findData(schedule.scope)
            self.scope.setCurrentIndex(max(0, position))
            wanted = set(schedule.vats)
            for item in self._items():
                item.setCheckState(
                    Qt.CheckState.Checked
                    if str(item.data(Qt.ItemDataRole.UserRole)) in wanted
                    else Qt.CheckState.Unchecked
                )
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._loading = False
        self.picker.setVisible(schedule.scope == "selected")
        self._filter(self.search.text())
        self.show_state(schedule)

    def show_state(self, schedule: SyncSchedule, last_run=None) -> None:
        text = schedule.describe()
        if schedule.scope == "selected":
            count = len(schedule.vats)
            text += f"\nΕπιλεγμένοι: {count}" if count else "\nΚανένας επιλεγμένος — δεν θα κατέβει τίποτα."
        upcoming = schedule.next_run(datetime.now(), last_run)
        if upcoming is not None:
            text += f"\nΕπόμενη: {upcoming:%d/%m/%Y %H:%M}"
        self.state.setText(text)

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        self._filter(self.search.text())
        self.schedule_changed.emit(self.schedule())
