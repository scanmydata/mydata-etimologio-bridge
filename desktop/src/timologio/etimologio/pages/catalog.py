"""Native catalog pages: Είδη (products) and Σειρές (numbering series)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from .base import ListPage
from .issue import INVOICE_TYPES

#: Product VAT category codes (label → code) — myDATA vatCategory ids.
VAT_CATEGORIES: list[tuple[str, str]] = [
    ("24%", "1"),
    ("13%", "2"),
    ("6%", "3"),
    ("0%", "7"),
]


class _Dialog(QDialog):
    """Small helper dialog with Save/Cancel and a required-field guard."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self.form = QFormLayout(self)

    def add_buttons(self, required: QLineEdit) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(lambda: self.accept() if required.text().strip() else required.setFocus())
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)


class NewProductDialog(_Dialog):
    def __init__(self, parent=None) -> None:
        super().__init__("Νέο είδος", parent)
        self.code = QLineEdit()
        self.description = QLineEdit()
        self.unit_price = QLineEdit("0")
        self.vat = QComboBox()
        for label, code in VAT_CATEGORIES:
            self.vat.addItem(label, code)
        self.unit = QLineEdit()
        self.form.addRow("Κωδικός *", self.code)
        self.form.addRow("Περιγραφή", self.description)
        self.form.addRow("Τιμή μον.", self.unit_price)
        self.form.addRow("ΦΠΑ", self.vat)
        self.form.addRow("Μον. μέτρησης", self.unit)
        self.add_buttons(self.code)

    def fields(self) -> dict[str, Any]:
        return {
            "product_code": self.code.text().strip(),
            "description": self.description.text().strip(),
            "unit_price": self.unit_price.text().strip() or "0",
            "vat_category": self.vat.currentData(),
            "unit": self.unit.text().strip(),
        }


class ProductsPage(ListPage):
    """List / create / delete items (είδη)."""

    _COLS = [
        ("Κωδικός", "product_code"),
        ("Περιγραφή", "description"),
        ("Τιμή", "unit_price"),
        ("ΦΠΑ", "vat"),
        ("Μον.", "measurement_unit"),
        ("Κατηγορία", "category"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Είδη", columns=self._COLS,
            rows_key="products", stretch_col=1, parent=parent,
        )
        new = QPushButton("Νέο είδος")
        new.clicked.connect(self._new)
        delete = QPushButton("Διαγραφή")
        delete.clicked.connect(self._delete)
        self.toolbar.insertWidget(self.toolbar.count() - 1, new)
        self.toolbar.insertWidget(self.toolbar.count() - 1, delete)

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.products()

    def _new(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewProductDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self.status.setText("Αποθήκευση είδους…")
        self._run(lambda: client.create_product(**fields), self._after_write, self._failed)

    def _delete(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        code = str(row.get("delete_code") or row.get("product_code") or "")
        if not code:
            return
        if QMessageBox.question(self, "Διαγραφή", f"Διαγραφή του είδους {code};") != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: client.delete_product(code), self._after_write, self._failed)

    def _after_write(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))


class NewSeriesDialog(_Dialog):
    def __init__(self, parent=None) -> None:
        super().__init__("Νέα σειρά", parent)
        self.type = QComboBox()
        for code, label in INVOICE_TYPES:
            self.type.addItem(label, code)
        self.code = QLineEdit()
        self.start_aa = QLineEdit("1")
        self.description = QLineEdit()
        self.form.addRow("Τύπος", self.type)
        self.form.addRow("Σειρά *", self.code)
        self.form.addRow("Επόμ. Α/Α", self.start_aa)
        self.form.addRow("Περιγραφή", self.description)
        self.add_buttons(self.code)

    def fields(self) -> dict[str, Any]:
        return {
            "invoice_type": self.type.currentData(),
            "code": self.code.text().strip(),
            "start_aa": self.start_aa.text().strip() or "1",
            "description": self.description.text().strip(),
        }


class SeriesPage(ListPage):
    """List / create / delete numbering series."""

    _COLS = [
        ("Τύπος", "invoice_type"),
        ("Σειρά", "series_code"),
        ("Επόμ. Α/Α", "start_aa"),
        ("Περιγραφή", "description"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Σειρές", columns=self._COLS,
            rows_key="series", stretch_col=3, parent=parent,
        )
        new = QPushButton("Νέα σειρά")
        new.clicked.connect(self._new)
        delete = QPushButton("Διαγραφή")
        delete.clicked.connect(self._delete)
        self.toolbar.insertWidget(self.toolbar.count() - 1, new)
        self.toolbar.insertWidget(self.toolbar.count() - 1, delete)

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.series()

    def _new(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewSeriesDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self.status.setText("Αποθήκευση σειράς…")
        self._run(lambda: client.create_series(**fields), self._after_write, self._failed)

    def _delete(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        series_id = str(row.get("delete_id") or row.get("series_id") or "")
        if not series_id:
            return
        if QMessageBox.question(self, "Διαγραφή", "Διαγραφή της σειράς;") != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: client.delete_series(series_id), self._after_write, self._failed)

    def _after_write(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))
