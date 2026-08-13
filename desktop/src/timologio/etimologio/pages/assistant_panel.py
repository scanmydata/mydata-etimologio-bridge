"""Το παράθυρο του ψηφιακού βοηθού — κουβέντα, κουμπιά, μικρόφωνο.

Ζει ως παιδί του κελύφους, κάτω δεξιά, όπως το πλωτό panel του web: ακολουθεί
το μέγεθος του παραθύρου χωρίς δικό μας κώδικα θέσης και δεν μένει ποτέ ορφανό
πάνω από άλλο παράθυρο.

Ό,τι *αποφασίζει* ζει στο :mod:`timologio.etimologio.assistant` (χωρίς Qt)· εδώ
μένει μόνο η εμφάνιση και η εκτέλεση: πλοήγηση, διάλογοι, ετοιμασία πρόχειρου.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..assistant import Assistant, DraftSpec, Reply
from . import ui

#: Διαστάσεις του panel — αρκετό για μια παράγραφο βοήθειας χωρίς να σκεπάζει
#: τη σελίδα από κάτω.
_WIDTH = 380
_HEIGHT = 460
_MARGIN = 18


class AssistantPanel(QFrame):
    """Η επιφάνεια συνομιλίας. Οι ενέργειες βγαίνουν ως σήματα.

    QFrame και όχι QWidget επίτηδες: ο κανόνας του θέματος είναι ``QFrame#card``,
    οπότε ένα σκέτο QWidget με το ίδιο όνομα δεν έπαιρνε φόντο — και η σελίδα
    από κάτω φαινόταν μέσα από το panel (φάνηκε στο offscreen render).
    """

    #: Άνοιγμα ενότητας («issue», «drafts», …).
    navigate = Signal(str)
    #: Άνοιγμα διαλόγου: («customer»|«product», prefill).
    open_dialog = Signal(str, dict)
    #: Ετοιμασία πρόχειρου από εντολή — ο παραλήπτης είναι η Έκδοση.
    prepare_draft = Signal(object)
    #: Ασύγχρονο ερώτημα προς το backend («stats:year», «notifications»).
    fetch_requested = Signal(str)

    def __init__(
        self,
        host: QWidget,
        *,
        data_dir: Path,
        customers: Callable[[], list[dict[str, Any]]],
        products: Callable[[], list[dict[str, Any]]],
    ) -> None:
        super().__init__(host)
        self._host = host
        self._data_dir = Path(data_dir)
        self._assistant = Assistant(customers, products)
        self._voice = None          # φτιάχνεται με το πρώτο πάτημα του μικροφώνου

        self.setObjectName("card")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("🤖  Βοηθός")
        title.setStyleSheet("font-weight:700;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(ui.button("✕", self.hide, tip="Κλείσιμο (Esc)"))
        box.addLayout(head)

        self._log_box = QVBoxLayout()
        self._log_box.setSpacing(6)
        self._log_box.addStretch(1)
        log_holder = QWidget()
        log_holder.setLayout(self._log_box)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(log_holder)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        box.addWidget(self._scroll, 1)

        # Τα κουμπιά συντόμευσης της τελευταίας απάντησης.
        self._choices = QHBoxLayout()
        self._choices.setSpacing(6)
        box.addLayout(self._choices)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Γράψε ή πες μια εντολή…")
        self._input.returnPressed.connect(self.submit)
        row.addWidget(self._input, 1)
        self._mic = ui.button("🎤", self._toggle_mic, tip="Φωνητική εντολή")
        self._mic.setFixedWidth(38)
        row.addWidget(self._mic)
        row.addWidget(ui.button("Στείλε", self.submit, kind="primary"))
        box.addLayout(row)

        self.setFixedSize(_WIDTH, _HEIGHT)
        self.hide()
        host.installEventFilter(self)

    # --- εμφάνιση -----------------------------------------------------------
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.reposition()
        self.show()
        self.raise_()
        self._input.setFocus()
        if self._log_box.count() <= 1:
            self.say(
                "Γεια! Πες μου π.χ. «έκδοση τιμολογίου στον 802576637 καθαρή αξία 100 "
                "με παρακράτηση 20%», «νέος πελάτης», «πήγαινε στα πρόχειρα» ή «βοήθεια».\n"
                "Αποθηκεύω πάντα ΠΡΟΧΕΙΡΟ — ΜΑΡΚ παίρνει το παραστατικό μόνο όταν "
                "πατήσεις εσύ το κόκκινο «Οριστική Έκδοση»."
            )

    def reposition(self) -> None:
        rect = self._host.rect()
        self.move(
            max(_MARGIN, rect.width() - _WIDTH - _MARGIN),
            max(_MARGIN, rect.height() - _HEIGHT - _MARGIN),
        )

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self._host and event.type() is QEvent.Type.Resize and self.isVisible():
            self.reposition()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    # --- κουβέντα -----------------------------------------------------------
    def _bubble(self, text: str, mine: bool) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Τα λόγια του βοηθού είναι το κύριο περιεχόμενο του panel — όχι
        # δευτερεύον κείμενο· «muted» τα έκανε δυσανάγνωστα. Η ηχώ του χρήστη
        # παίρνει το χρώμα τονισμού και στοιχίζεται δεξιά, ώστε να ξεχωρίζει
        # ποιος είπε τι χωρίς εικονίδια.
        label.setObjectName("hint" if mine else "")
        label.setAlignment(
            Qt.AlignmentFlag.AlignRight if mine else Qt.AlignmentFlag.AlignLeft
        )
        self._log_box.insertWidget(self._log_box.count() - 1, label)
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def say(self, text: str) -> None:
        """Μήνυμα του βοηθού."""
        self._bubble(text, mine=False)

    def _clear_choices(self) -> None:
        while self._choices.count():
            item = self._choices.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # --- είσοδος ------------------------------------------------------------
    def submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.ask(text)

    def ask(self, text: str) -> None:
        """Στέλνει μια εντολή στον βοηθό, σαν να την πληκτρολόγησε ο χρήστης."""
        self._bubble(text, mine=True)
        self.apply(self._assistant.handle(text))

    def report(self, kind: str, data: Any) -> None:
        """Το αποτέλεσμα ενός ``fetch_requested``."""
        self.apply(self._assistant.report(kind, data))

    def apply(self, reply: Reply) -> None:
        """Εκτελεί μια απάντηση: λόγια, πλοήγηση, διάλογος ή πρόχειρο."""
        self._clear_choices()
        if reply.say:
            self.say(reply.say)
        for label, command in reply.choices:
            self._choices.addWidget(ui.button(label, lambda c=command: self.ask(c)))
        if reply.navigate:
            self.navigate.emit(reply.navigate)
        if reply.dialog:
            self.open_dialog.emit(reply.dialog, dict(reply.prefill))
        if reply.fetch:
            self.fetch_requested.emit(reply.fetch)
        if reply.draft is not None:
            self.prepare_draft.emit(reply.draft)
        # Το panel χάνει την εστίαση όταν αλλάζει σελίδα από κάτω· χωρίς αυτό ο
        # χρήστης έπρεπε να ξανακάνει κλικ στο πεδίο για κάθε επόμενη εντολή.
        if self.isVisible():
            self.raise_()
            self._input.setFocus()

    # --- φωνή ---------------------------------------------------------------
    def _toggle_mic(self) -> None:
        if self._voice is None:
            from ..voice import VoiceInput

            self._voice = VoiceInput(self._data_dir, self)
            self._voice.heard.connect(self._heard)
            self._voice.failed.connect(self.say)
            self._voice.listening_changed.connect(self._mic_state)
        self._voice.toggle()

    def _heard(self, text: str) -> None:
        # Μιλάμε πάντα μέσα από το ίδιο μονοπάτι με το πληκτρολόγιο: ό,τι
        # ακούστηκε φαίνεται στην κουβέντα πριν εκτελεστεί, ώστε ο χρήστης να
        # δει τι κατάλαβε η αναγνώριση.
        if text.strip():
            self.ask(text.strip())

    def _mic_state(self, listening: bool) -> None:
        self._mic.setText("⏹" if listening else "🎤")
        self._mic.setToolTip("Ακούω… (πάτα για τερματισμό)" if listening else "Φωνητική εντολή")

    def shutdown(self) -> None:
        if self._voice is not None:
            self._voice.stop()


__all__ = ["AssistantPanel", "DraftSpec"]
