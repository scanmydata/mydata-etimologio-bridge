"""Native catalog pages: Είδη (products) and Σειρές (numbering series)."""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from ..codes import INVOICE_TYPES
from .base import ListPage

#: Product VAT category codes (label → code) — myDATA vatCategory ids.
VAT_CATEGORIES: list[tuple[str, str]] = [
    ("24%", "1"),
    ("13%", "2"),
    ("6%", "3"),
    ("9%", "5"),
    ("0%", "7"),
    ("Απαλλασσόμενο", "8"),
]

#: Είδος γραμμής. Το e-timologio ξεχωρίζει αγαθά από υπηρεσίες — τα δελτία
#: αποστολής δέχονται μόνο αγαθά, και οι παρακρατήσεις μόνο υπηρεσίες.
PRODUCT_TYPES: list[tuple[str, str]] = [
    ("2", "Υπηρεσία"),
    ("1", "Αγαθό"),
]

#: Μονάδες μέτρησης (κωδικός → ετικέτα).
UNITS: list[tuple[str, str]] = [
    ("1", "Τεμάχιο"),
    ("2", "Κιλό"),
    ("3", "Λίτρο"),
    ("4", "Μέτρο"),
    ("7", "Άλλο"),
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
    """Δημιουργία/επεξεργασία είδους.

    Η **κατηγορία είναι υποχρεωτική**: χωρίς αυτήν το e-timologio απαντά
    «The value '' is invalid» — μήνυμα που δεν λέει τίποτα στον χρήστη, οπότε το
    πιάνουμε εδώ.
    """

    def __init__(
        self,
        parent=None,
        *,
        categories: list[dict[str, Any]] | None = None,
        code: str = "",
        row: dict[str, Any] | None = None,
    ) -> None:
        editing = row is not None
        super().__init__("Επεξεργασία είδους" if editing else "Νέο είδος", parent)
        row = row or {}

        self.code = QLineEdit(str(row.get("product_code") or code))
        # Ο κωδικός είναι το κλειδί — αν αλλάξει στο edit, φτιάχνεται δεύτερο είδος.
        self.code.setReadOnly(editing)
        self.type = QComboBox()
        for value, label in PRODUCT_TYPES:
            self.type.addItem(label, value)
        self.description = QLineEdit(str(row.get("description") or ""))
        self.category = QComboBox()
        self.category.addItem("— επιλέξτε —", "")
        for cat in categories or []:
            name = str(cat.get("name") or cat.get("category_name") or "")
            self.category.addItem(name, name)
        self.unit_price = QLineEdit(str(row.get("unit_price") or "0"))
        self.vat = QComboBox()
        for label, value in VAT_CATEGORIES:
            self.vat.addItem(label, value)
        self.unit = QComboBox()
        for value, label in UNITS:
            self.unit.addItem(label, value)

        self.form.addRow("Κωδικός *", self.code)
        self.form.addRow("Είδος", self.type)
        self.form.addRow("Περιγραφή *", self.description)
        self.form.addRow("Κατηγορία *", self.category)
        self.form.addRow("Τιμή μον.", self.unit_price)
        self.form.addRow("ΦΠΑ", self.vat)
        self.form.addRow("Μον. μέτρησης", self.unit)

        self._error = QLabel("")
        self._error.setObjectName("hint")
        self._error.setWordWrap(True)
        self.form.addRow(self._error)

        current = str(row.get("category") or "")
        if current:
            index = self.category.findData(current)
            if index >= 0:
                self.category.setCurrentIndex(index)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)
        self._editing = editing

    def is_editing(self) -> bool:
        return self._editing

    def _accept(self) -> None:
        for field, message in (
            (self.code, "Δώσε κωδικό είδους."),
            (self.description, "Δώσε περιγραφή."),
        ):
            if not field.text().strip():
                self._error.setText(message)
                field.setFocus()
                return
        if not self.category.currentData():
            self._error.setText(
                "Το e-timologio απαιτεί κατηγορία — χωρίς αυτήν η καταχώρηση απορρίπτεται."
            )
            self.category.setFocus()
            return
        self.accept()

    def fields(self) -> dict[str, Any]:
        return {
            "product_code": self.code.text().strip(),
            "description": self.description.text().strip(),
            "unit_price": self.unit_price.text().strip() or "0",
            "vat_category": self.vat.currentData(),
            "product_type": self.type.currentData(),
            "category": self.category.currentData(),
            # Οι υπηρεσίες δεν έχουν μονάδα μέτρησης.
            "unit": "" if self.type.currentData() == "2" else self.unit.currentData(),
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
            subtitle="Ο κατάλογος ειδών που τροφοδοτεί την Έκδοση. Η κατηγορία είναι υποχρεωτική για την ΑΑΔΕ.",
        )
        self._categories: list[dict[str, Any]] = []
        new = QPushButton("Νέο είδος")
        new.clicked.connect(self._new)
        edit = QPushButton("Επεξεργασία")
        edit.clicked.connect(self._edit)
        delete = QPushButton("Διαγραφή")
        delete.clicked.connect(self._delete)
        cats = QPushButton("🏷️ Κατηγορίες & χαρακτηρισμοί")
        cats.setToolTip("Ποιος χαρακτηρισμός εσόδου και κωδικός E3 ανά τύπο παραστατικού")
        cats.clicked.connect(self._open_categories)
        for button in (new, edit, delete, cats):
            self.toolbar.insertWidget(self.toolbar.count() - 1, button)
        self.table.doubleClicked.connect(lambda *_: self._edit())

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.products()

    def refresh(self) -> None:
        super().refresh()
        client = self.client()
        if client is not None and not self._categories:
            self._run(client.product_categories, self._got_categories, lambda _m: None)

    def _got_categories(self, data: dict[str, Any]) -> None:
        self._categories = list(
            data.get("categories") or data.get("product_categories") or data.get("rows") or []
        )

    def _open_categories(self) -> None:
        client = self.client()
        if client is None:
            return
        from .categories import CategoriesDialog

        CategoriesDialog(self, client=client, run=self._run).exec()
        # Οι κατηγορίες μπορεί να άλλαξαν — ο διάλογος ειδών πρέπει να τις δει.
        self._categories = []
        self.refresh()

    def _new(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewProductDialog(self, categories=self._categories)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self.status.setText("Αποθήκευση είδους…")
        self._run(lambda: client.create_product(**fields), self._after_write, self._failed)

    def _edit(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        dialog = NewProductDialog(self, categories=self._categories, row=row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        code = fields.pop("product_code")
        self.status.setText("Ενημέρωση είδους…")
        self._run(lambda: client.update_product(code, **fields), self._after_write, self._failed)

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
    def __init__(
        self,
        parent=None,
        *,
        row: dict[str, Any] | None = None,
        invoice_type: str = "",
    ) -> None:
        editing = row is not None
        super().__init__("Επεξεργασία σειράς" if editing else "Νέα σειρά", parent)
        row = row or {}
        self.type = QComboBox()
        for code, label in INVOICE_TYPES:
            self.type.addItem(label, code)
        self.code = QLineEdit(str(row.get("series_code") or ""))
        self.code.setMaxLength(10)
        self.code.setPlaceholderText("π.χ. Α, ΤΠΥ, ΔΑ")
        self.start_aa = QLineEdit(str(row.get("start_aa") or "1"))
        self.description = QLineEdit(str(row.get("description") or ""))
        self.form.addRow("Τύπος", self.type)
        self.form.addRow("Σειρά *", self.code)
        self.form.addRow("Επόμ. Α/Α", self.start_aa)
        self.form.addRow("Περιγραφή", self.description)
        self.add_buttons(self.code)

        # Ο κωδικός τύπου είναι το ασφαλές κλειδί — τον δίνει το backend ως
        # `invoice_type_code` και τον περνά η Έκδοση όταν ζητά νέα σειρά για τον
        # τύπο που δουλεύει ο χρήστης.
        wanted = str(invoice_type or row.get("invoice_type_code") or "")
        if wanted:
            index = self.type.findData(wanted)
            if index >= 0:
                self.type.setCurrentIndex(index)

        # Εφεδρεία για γραμμές που έχουν μόνο την ετικέτα («2.1 - Τιμολόγιο…»).
        current = "" if wanted else str(row.get("invoice_type") or "")
        if current:
            dotted = current.split(" ", 1)[0]
            for index in range(self.type.count()):
                if self.type.itemText(index).startswith(dotted):
                    self.type.setCurrentIndex(index)
                    break

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
            subtitle="Σειρές αρίθμησης ανά τύπο παραστατικού. Χωρίς σειρά, ο τύπος δεν εκδίδεται.",
        )
        new = QPushButton("Νέα σειρά")
        new.clicked.connect(self._new)
        edit = QPushButton("Επεξεργασία")
        edit.clicked.connect(self._edit)
        delete = QPushButton("Διαγραφή")
        delete.clicked.connect(self._delete)
        for button in (new, edit, delete):
            self.toolbar.insertWidget(self.toolbar.count() - 1, button)
        self.table.doubleClicked.connect(lambda *_: self._edit())

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

    def _edit(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        series_id = str(row.get("delete_id") or row.get("series_id") or "")
        if not series_id:
            self.status.setText("Η σειρά δεν έχει id — δεν μπορεί να ενημερωθεί.")
            return
        dialog = NewSeriesDialog(self, row=row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self.status.setText("Ενημέρωση σειράς…")
        self._run(
            lambda: client.update_series(series_id, **fields), self._after_write, self._failed
        )

    def _delete(self) -> None:
        """Διαγραφή — αλλά πρώτα ελέγχουμε ότι δεν έχει εκδοθεί τίποτα σε αυτήν.

        Χωρίς τον έλεγχο, μια σειρά με ιστορικό εξαφανίζεται από τη λίστα και η
        αρίθμηση σπάει· τα ήδη εκδοθέντα παραστατικά μένουν στην ΑΑΔΕ αλλά η
        επόμενη σειρά με το ίδιο όνομα ξεκινά από την αρχή.
        """
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        series_id = str(row.get("delete_id") or row.get("series_id") or "")
        code = str(row.get("series_code") or "")
        if not series_id:
            return
        self.status.setText("Έλεγχος αν η σειρά χρησιμοποιείται…")
        year = date.today().year
        self._run(
            lambda: client.search_invoices(
                series=code,
                date_from=f"01/01/{year - 5}",
                date_to=date.today().strftime("%d/%m/%Y"),
            ),
            lambda data: self._confirm_delete(series_id, code, data),
            # Αν ο έλεγχος αποτύχει δεν διαγράφουμε στα τυφλά.
            lambda msg: self.status.setText(
                f"Δεν έγινε ο έλεγχος χρήσης ({msg}) — η διαγραφή ακυρώθηκε."
            ),
        )

    def _confirm_delete(self, series_id: str, code: str, data: dict[str, Any]) -> None:
        client = self.client()
        if client is None:
            return
        used = [i for i in data.get("invoices", []) if str(i.get("series", "")) == code]
        if used:
            self.status.setText(
                f"Η σειρά «{code}» χρησιμοποιείται σε {len(used)} παραστατικά "
                "και δεν διαγράφεται."
            )
            QMessageBox.warning(
                self, "Η σειρά χρησιμοποιείται",
                f"Η σειρά «{code}» έχει {len(used)} εκδοθέντα παραστατικά.\n\n"
                "Η διαγραφή θα έσπαγε την αρίθμηση. Αν δεν τη χρειάζεσαι πια, "
                "άφησέ την και δημιούργησε νέα.",
            )
            return
        self.status.setText("")
        if QMessageBox.question(
            self, "Διαγραφή", f"Διαγραφή της σειράς «{code}»; Δεν έχει παραστατικά."
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: client.delete_series(series_id), self._after_write, self._failed)

    def _after_write(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))
