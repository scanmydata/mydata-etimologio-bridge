"""Διάλογοι που ανοίγουν μέσα από την Έκδοση — φόροι, είδος, προγραμματισμός.

Το native στέλνει ήδη `taxes` στο backend αλλά δεν είχε πουθενά UI για να τους
συμπληρώσει κανείς, οπότε κάθε παρακράτηση έπρεπε να μπει από το web. Εδώ είναι
η ίδια φόρμα με «Νέος Φόρος» του `app.php`, μαζί με τους δύο κανόνες που
κουβαλά: το αυτόματο ποσό από το ποσοστό της ετικέτας, και το πρόσημο.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTimeEdit,
    QVBoxLayout,
)

from ...gui.widgets import GrDateEdit
from ..codes import INVOICE_TYPES
from .base import fmt_money, parse_money

#: Είδη φόρου (κωδικός → ετικέτα), σταθερά όπως στο e-timologio.
TAX_TYPES: list[tuple[int, str]] = [
    (1, "Παρακρατούμενοι φόροι"),
    (2, "Τέλη"),
    (3, "Άλλοι φόροι"),
    (4, "Ψηφιακό Τέλος Συναλλαγής"),
    (5, "Κρατήσεις"),
]

#: Σε ποιο κλειδί της απάντησης ``tax_categories`` αντιστοιχεί κάθε είδος.
TAX_TYPE_KEY: dict[int, str] = {
    1: "withheld", 2: "fees", 3: "other", 4: "digital", 5: "deductions",
}

#: Τα είδη που ΑΦΑΙΡΟΥΝΤΑΙ από το πληρωτέο. Τα υπόλοιπα προστίθενται.
DEDUCTING_TYPES = frozenset({1, 5})

#: Τύποι παραστατικού που θεωρούνται παροχή υπηρεσιών — μόνο σε αυτούς
#: επιτρέπεται παρακράτηση φόρου.
_SERVICE_TYPES = frozenset({"20", "21", "22", "58", "59"})


def is_service_type(invoice_type: str) -> bool:
    code = str(invoice_type or "")
    if code in _SERVICE_TYPES:
        return True
    label = dict(INVOICE_TYPES).get(code, "")
    return bool(re.match(r"^(2\.|11\.[25])", label))


def rate_from_label(label: str) -> float:
    """Το ποσοστό που κρύβεται στην ετικέτα («… 3%») ως κλάσμα (0.03).

    Οι ετικέτες της ΑΑΔΕ γράφουν το ποσοστό μέσα στο κείμενο, οπότε το ποσό
    μπορεί να προϋπολογιστεί αντί να το βγάζει ο λογιστής με το χέρι.
    """
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(label or ""))
    if not match:
        return 0.0
    return float(match.group(1).replace(",", ".")) / 100.0


def tax_signed_total(taxes: list[dict[str, Any]]) -> tuple[float, float]:
    """(προσθήκες, αφαιρέσεις) από μια λίστα φόρων."""
    plus = minus = 0.0
    for tax in taxes:
        amount = float(tax.get("amount") or 0)
        if int(tax.get("type") or 0) in DEDUCTING_TYPES:
            minus += amount
        else:
            plus += amount
    return plus, minus


class TaxDialog(QDialog):
    """«Νέος Φόρος»: είδος, κατηγορία, ποσό, σημειώσεις."""

    def __init__(
        self,
        categories: dict[str, Any],
        *,
        net_total: float = 0.0,
        invoice_type: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Φόρος / Κράτηση / Τέλος")
        self.setMinimumWidth(430)
        self._categories = categories or {}
        self._net_total = net_total
        self._invoice_type = invoice_type
        #: Γεμίζει όταν ο χρήστης ζητήσει «➕ Νέα κράτηση…».
        self.new_deduction_name = ""

        box = QVBoxLayout(self)
        form = QFormLayout()
        box.addLayout(form)

        self.type = QComboBox()
        for code, label in TAX_TYPES:
            self.type.addItem(label, code)
        self.type.currentIndexChanged.connect(self._type_changed)
        form.addRow("Είδος φόρου", self.type)

        self.category = QComboBox()
        self.category.currentIndexChanged.connect(self._category_changed)
        form.addRow("Κατηγορία", self.category)

        self.amount = QLineEdit("0")
        form.addRow("Ποσό (€)", self.amount)

        self.notes = QLineEdit()
        form.addRow("Σημειώσεις", self.notes)

        self._hint = QLabel("")
        self._hint.setObjectName("muted")
        self._hint.setWordWrap(True)
        box.addWidget(self._hint)

        self._error = QLabel("")
        self._error.setObjectName("hint")
        self._error.setWordWrap(True)
        box.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Προσθήκη")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        self._type_changed()

    # --- reactions ---------------------------------------------------------
    def _current_type(self) -> int:
        return int(self.type.currentData() or 0)

    def _type_changed(self) -> None:
        kind = self._current_type()
        self._error.setText("")
        self._hint.setText("")
        if kind == 1 and not is_service_type(self._invoice_type):
            self._hint.setText("Η παρακράτηση φόρου αφορά μόνο παροχή υπηρεσιών.")

        rows = list(self._categories.get(TAX_TYPE_KEY.get(kind, ""), []) or [])
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("Επιλέξτε…", "")
        for row in rows:
            self.category.addItem(str(row.get("label", "")), str(row.get("code", "")))
        if kind == 5:
            # Μόνο οι κρατήσεις είναι δικές μας — τα υπόλοιπα τα ορίζει η ΑΑΔΕ.
            self.category.addItem("➕  Νέα κράτηση…", "__new")
        self.category.blockSignals(False)

    def _category_changed(self) -> None:
        code = str(self.category.currentData() or "")
        if code == "__new":
            self.new_deduction_name = ""
            self.done(_NEW_DEDUCTION)
            return
        rate = rate_from_label(self.category.currentText())
        if rate > 0 and self._net_total > 0:
            amount = round(self._net_total * rate, 2)
            # ΕΛΛΗΝΙΚΗ μορφή — την ίδια που διαβάζει το parse_money. Γραμμένο ως
            # «20.00», η τελεία διαβαζόταν ως διαχωριστικό χιλιάδων και το 20 €
            # γινόταν **2.000 €**: μια παρακράτηση 20% σε καθαρή 100 € έβγαζε
            # πληρωτέο −1.876 €.
            self.amount.setText(fmt_money(amount))
            self._hint.setText(
                f"Αυτόματο ποσό: {rate * 100:g}% × καθαρή {fmt_money(self._net_total)} € "
                f"= {fmt_money(amount)} € (μπορείς να το αλλάξεις)."
            )

    def _accept(self) -> None:
        kind = self._current_type()
        code = str(self.category.currentData() or "")
        amount = parse_money(self.amount.text())
        if kind == 1 and not is_service_type(self._invoice_type):
            self._error.setText("Παρακράτηση φόρου μόνο σε παροχή υπηρεσιών.")
            return
        if not code:
            self._error.setText("Επίλεξε κατηγορία.")
            return
        if amount <= 0:
            self._error.setText("Δώσε ποσό μεγαλύτερο του μηδενός.")
            self.amount.setFocus()
            return
        self.accept()

    # --- result ------------------------------------------------------------
    def tax(self) -> dict[str, Any]:
        return {
            "type": self._current_type(),
            "category": str(self.category.currentData() or ""),
            "amount": parse_money(self.amount.text()),
            "notes": self.notes.text().strip(),
            "label": self.category.currentText(),
        }


#: Ο κωδικός εξόδου που σημαίνει «ο χρήστης ζήτησε νέα κράτηση».
NEW_DEDUCTION = 42
_NEW_DEDUCTION = NEW_DEDUCTION


class ScheduleDialog(QDialog):
    """Πότε να εκδοθεί αυτόματα — ημερομηνία, ώρα, επανάληψη."""

    RECURRENCES: list[tuple[str, str]] = [
        ("none", "Καμία (μία φορά)"),
        ("daily", "Καθημερινά"),
        ("weekly", "Εβδομαδιαία"),
        ("monthly", "Μηνιαία"),
    ]

    def __init__(self, summary: str = "", *, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Προγραμματισμός έκδοσης")
        self.setMinimumWidth(400)
        box = QVBoxLayout(self)

        if summary:
            label = QLabel(summary)
            label.setObjectName("muted")
            label.setWordWrap(True)
            box.addWidget(label)

        form = QFormLayout()
        box.addLayout(form)

        tomorrow = date.today() + timedelta(days=1)
        self.date = GrDateEdit(tomorrow)
        form.addRow("Ημερομηνία", self.date)

        self.time = QTimeEdit(QTime(9, 0))
        self.time.setDisplayFormat("HH:mm")
        form.addRow("Ώρα", self.time)

        self.recurrence = QComboBox()
        for code, label_text in self.RECURRENCES:
            self.recurrence.addItem(label_text, code)
        form.addRow("Επανάληψη", self.recurrence)

        self.title = QLineEdit()
        self.title.setPlaceholderText("π.χ. Μηνιαίο τιμολόγιο συντήρησης")
        form.addRow("Περιγραφή", self.title)

        self._warn = QLabel("")
        self._warn.setObjectName("hint")
        self._warn.setWordWrap(True)
        box.addWidget(self._warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Προγραμματισμός")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def run_at(self) -> str:
        """``YYYY-MM-DD HH:MM`` — η μορφή που περιμένει το ``sched_add``."""
        return (
            f"{self.date.date().toString('yyyy-MM-dd')} "
            f"{self.time.time().toString('HH:mm')}"
        )

    def _accept(self) -> None:
        when = datetime.strptime(self.run_at(), "%Y-%m-%d %H:%M")
        if when < datetime.now():
            # Προειδοποίηση, όχι εμπόδιο: ο runner θα το εκτελέσει αμέσως.
            self._warn.setText("⚠ Η ώρα έχει περάσει — η εργασία θα τρέξει στην πρώτη ευκαιρία.")
        self.accept()
