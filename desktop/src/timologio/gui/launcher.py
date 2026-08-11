"""Η αρχική οθόνη: διάλεξε εφαρμογή.

Το πρόγραμμα είναι δύο εφαρμογές σε ένα εκτελέσιμο. Χωρίς αυτή την οθόνη
άνοιγε κατευθείαν στη Λήψη Παραστατικών και το e-Τιμολόγιο έμοιαζε με «καρτέλα»
κάπου μέσα — ενώ είναι ισότιμο πρόγραμμα. Η επιλογή γίνεται εδώ και αλλάζει
ανά πάσα στιγμή από το πλαϊνό μενού.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import icon, logo_pixmap
from .theme import CURRENT


class _Card(QPushButton):
    """Μεγάλη κάρτα επιλογής — λογότυπο, τίτλος, περιγραφή."""

    def __init__(self, title: str, subtitle: str, lines: list[str], pixmap) -> None:
        super().__init__()
        self.setObjectName("tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(330, 260)

        box = QVBoxLayout(self)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(pixmap)
        logo.setFixedSize(52, 52)
        logo.setScaledContents(True)
        box.addWidget(logo)

        name = QLabel(title)
        name.setStyleSheet("font-size:18px;font-weight:800;")
        box.addWidget(name)

        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        box.addWidget(sub)

        line = QFrame()
        line.setObjectName("line")
        box.addWidget(line)

        for text in lines:
            item = QLabel("•  " + text)
            item.setObjectName("muted")
            item.setWordWrap(True)
            box.addWidget(item)
        box.addStretch(1)


class Launcher(QWidget):
    """Δύο κάρτες: Λήψη Παραστατικών ή e-Τιμολόγιο Pro."""

    chosen = Signal(str)   # "downloader" | "etimologio"

    def __init__(self, version: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 30)
        root.setSpacing(6)
        root.addStretch(1)

        title = QLabel("Τι θέλετε να κάνετε;")
        title.setStyleSheet("font-size:22px;font-weight:800;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(title)

        hint = QLabel("Μπορείτε να αλλάξετε εφαρμογή όποτε θέλετε, από το πλαϊνό μενού.")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(hint)
        root.addSpacing(18)

        cards = QHBoxLayout()
        cards.setSpacing(18)
        cards.addStretch(1)

        downloader = _Card(
            "Λήψη Παραστατικών",
            "Μαζική λήψη των παραστατικών των πελατών σας από το myDATA.",
            ["Πολλοί πελάτες, μία λήψη",
             "Αρχειοθέτηση PDF ανά ΑΦΜ και μήνα",
             "Εξαγωγή σε Excel/CSV"],
            logo_pixmap(52),
        )
        downloader.clicked.connect(lambda: self.chosen.emit("downloader"))
        cards.addWidget(downloader)

        etimologio = _Card(
            "e-Τιμολόγιο Pro",
            "Έκδοση και διαχείριση παραστατικών πάνω στο e-τιμολόγιο της ΑΑΔΕ.",
            ["Έκδοση, ακύρωση, μαζική έκδοση",
             "Πελάτες, καρτέλες, πληρωμές",
             "Μαζική εκτύπωση και εξαγωγή ZIP"],
            logo_pixmap(52, etimologio=True),
        )
        etimologio.clicked.connect(lambda: self.chosen.emit("etimologio"))
        cards.addWidget(etimologio)

        cards.addStretch(1)
        root.addLayout(cards)
        root.addStretch(2)

        if version:
            foot = QLabel(f"έκδοση {version}")
            foot.setObjectName("muted")
            foot.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            root.addWidget(foot)

    def restyle(self) -> None:
        """Ξαναβάφει τα λογότυπα μετά από αλλαγή θέματος."""
        for label in self.findChildren(QLabel):
            if label.pixmap() and not label.pixmap().isNull():
                label.setPixmap(
                    logo_pixmap(52, etimologio=label.property("etim") is True)
                )
        # Τα εικονίδια των καρτών ακολουθούν το χρώμα τόνου του νέου θέματος.
        _ = icon("etimologio", CURRENT.accent)
