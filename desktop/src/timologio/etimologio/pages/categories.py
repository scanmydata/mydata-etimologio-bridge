"""Κατηγορίες ειδών και οι χαρακτηρισμοί τους (myDATA).

Κάθε είδος ανήκει σε μια κατηγορία, και η κατηγορία ορίζει **ανά τύπο
παραστατικού** τον χαρακτηρισμό εσόδου (π.χ. «Έσοδα από Παροχή Υπηρεσιών (1.3)»)
και τον κωδικό E3. Χωρίς αυτό το UI η κατηγορία μπορούσε μόνο να επιλεγεί — όχι
να δημιουργηθεί ούτε να αλλάξει — οπότε ένα καινούριο είδος σε καινούρια
δραστηριότητα απαιτούσε επίσκεψη στο web.

Ο κανόνας που επιβάλλει η ΑΑΔΕ: **ένας χαρακτηρισμός ανά τύπο παραστατικού**.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import ui

_TYPE, _CATEGORY, _CODE = range(3)
_ROW_COLS = ["Τύπος παραστατικού", "Κατηγορία εσόδου", "Κωδικός E3"]


def classification_summary(row: dict[str, Any]) -> str:
    """Μονογραμμή περίληψη των χαρακτηρισμών μιας κατηγορίας."""
    parts = []
    for cls in row.get("classifications") or []:
        label = str(cls.get("invoice_type_label") or cls.get("invoice_type") or "")
        parts.append(f"{label.split(' - ')[0]} → {cls.get('code', '')}")
    return "  ·  ".join(parts) or "— χωρίς χαρακτηρισμούς —"


class CategoryEditDialog(QDialog):
    """Δημιουργία/επεξεργασία κατηγορίας με τους χαρακτηρισμούς της.

    Οι δύο λίστες είναι αλυσιδωτές: ο τύπος παραστατικού καθορίζει ποιες
    κατηγορίες εσόδου επιτρέπονται, και η κατηγορία ποιους κωδικούς E3 — ακριβώς
    όπως τα δίνει το ``cls_options`` της ΑΑΔΕ.
    """

    def __init__(
        self,
        parent=None,
        *,
        invoice_types: list[dict[str, Any]],
        options_for: Any,
        row: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        editing = row is not None
        row = row or {}
        self.setWindowTitle("Επεξεργασία κατηγορίας" if editing else "Νέα κατηγορία")
        self.setMinimumWidth(720)
        self._invoice_types = invoice_types
        self._options_for = options_for      # callable: type code → cls_options dict
        self._category_id = str(row.get("category_id") or "")

        box = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Ονομασία *"))
        self.name = QLineEdit(str(row.get("name") or ""))
        # Η ονομασία είναι το κλειδί που κρατούν τα είδη — αλλάζοντάς την στο edit
        # θα δημιουργούσε δεύτερη κατηγορία και τα είδη θα έμεναν ορφανά.
        self.name.setReadOnly(editing)
        name_row.addWidget(self.name, 1)
        box.addLayout(name_row)

        self._table = QTableWidget(0, len(_ROW_COLS))
        self._table.setHorizontalHeaderLabels(_ROW_COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(_TYPE, 260)
        self._table.setColumnWidth(_CATEGORY, 220)
        box.addWidget(self._table, 1)

        buttons_row = QHBoxLayout()
        add = QPushButton("+ Χαρακτηρισμός")
        add.clicked.connect(lambda: self.add_row())
        remove = QPushButton("− Χαρακτηρισμός")
        remove.clicked.connect(self._remove_row)
        buttons_row.addWidget(add)
        buttons_row.addWidget(remove)
        buttons_row.addStretch(1)
        box.addLayout(buttons_row)

        self._error = ui.hint("")
        box.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        for cls in row.get("classifications") or []:
            self.add_row(
                str(cls.get("invoice_type") or ""),
                str(cls.get("category") or ""),
                str(cls.get("code") or ""),
            )
        if not self._table.rowCount():
            self.add_row()

    # --- γραμμές -----------------------------------------------------------
    def add_row(self, invoice_type: str = "", category: str = "", code: str = "") -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)

        types = QComboBox()
        for item in self._invoice_types:
            types.addItem(str(item.get("label") or ""), str(item.get("value") or ""))
        categories = QComboBox()
        codes = QComboBox()
        self._table.setCellWidget(r, _TYPE, types)
        self._table.setCellWidget(r, _CATEGORY, categories)
        self._table.setCellWidget(r, _CODE, codes)

        types.currentIndexChanged.connect(lambda *_: self._reload_categories(r))
        categories.currentIndexChanged.connect(lambda *_: self._reload_codes(r))

        if invoice_type:
            index = types.findData(invoice_type)
            if index >= 0:
                types.setCurrentIndex(index)
        self._reload_categories(r, keep=(category, code))

    def _remove_row(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            r = self._table.rowCount() - 1
        if r >= 0:
            self._table.removeRow(r)

    def _reload_categories(self, r: int, keep: tuple[str, str] = ("", "")) -> None:
        types = self._table.cellWidget(r, _TYPE)
        categories = self._table.cellWidget(r, _CATEGORY)
        if types is None or categories is None:
            return
        options = self._options_for(str(types.currentData() or ""))
        categories.blockSignals(True)
        categories.clear()
        for opt in options.get("categories") or []:
            categories.addItem(str(opt.get("title") or ""), str(opt.get("category") or ""))
        if keep[0]:
            index = categories.findData(keep[0])
            if index >= 0:
                categories.setCurrentIndex(index)
        categories.blockSignals(False)
        self._reload_codes(r, keep=keep[1])

    def _reload_codes(self, r: int, keep: str = "") -> None:
        types = self._table.cellWidget(r, _TYPE)
        categories = self._table.cellWidget(r, _CATEGORY)
        codes = self._table.cellWidget(r, _CODE)
        if types is None or categories is None or codes is None:
            return
        options = self._options_for(str(types.currentData() or ""))
        wanted = str(categories.currentData() or "")
        codes.clear()
        for opt in options.get("categories") or []:
            if str(opt.get("category") or "") != wanted:
                continue
            for code in opt.get("codes") or []:
                codes.addItem(
                    f"{code.get('code')} — {code.get('title')}", str(code.get("code") or "")
                )
        if keep:
            index = codes.findData(keep)
            if index >= 0:
                codes.setCurrentIndex(index)

    # --- αποτέλεσμα ---------------------------------------------------------
    def classifications(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in range(self._table.rowCount()):
            types = self._table.cellWidget(r, _TYPE)
            categories = self._table.cellWidget(r, _CATEGORY)
            codes = self._table.cellWidget(r, _CODE)
            if types is None or categories is None or codes is None:
                continue
            invoice_type = str(types.currentData() or "")
            category = str(categories.currentData() or "")
            code = str(codes.currentData() or "")
            if invoice_type and category and code:
                # Τα ονόματα των κλειδιών είναι δεσμευτικά: το backend αγνοεί
                # σιωπηλά όποια εγγραφή δεν έχει `invoice_type`/`category`, οπότε
                # λάθος όνομα δίνει κατηγορία με μηδέν χαρακτηρισμούς και
                # `success: true`.
                rows.append(
                    {"invoice_type": invoice_type, "category": category, "code": code}
                )
        return rows

    def fields(self) -> dict[str, Any]:
        return {
            "category_id": self._category_id,
            "name": self.name.text().strip(),
            "cls": self.classifications(),
        }

    def _accept(self) -> None:
        if not self.name.text().strip():
            self._error.setText("Δώσε ονομασία κατηγορίας.")
            self.name.setFocus()
            return
        rows = self.classifications()
        if not rows:
            self._error.setText("Πρόσθεσε τουλάχιστον έναν πλήρη χαρακτηρισμό.")
            return
        seen = [r["invoice_type"] for r in rows]
        duplicate = next((t for t in seen if seen.count(t) > 1), "")
        if duplicate:
            # Η ΑΑΔΕ δέχεται έναν χαρακτηρισμό ανά τύπο· ο δεύτερος θα σκότωνε
            # σιωπηλά τον πρώτο.
            label = next(
                (str(i.get("label")) for i in self._invoice_types
                 if str(i.get("value")) == duplicate), duplicate
            )
            self._error.setText(f"Δύο χαρακτηρισμοί για «{label}» — επιτρέπεται ένας ανά τύπο.")
            return
        self.accept()


class CategoriesDialog(QDialog):
    """Λίστα κατηγοριών με τους χαρακτηρισμούς τους, και προσθαφαίρεση."""

    def __init__(self, parent=None, *, client, run) -> None:
        super().__init__(parent)
        self.setWindowTitle("Κατηγορίες ειδών & χαρακτηρισμοί")
        self.setMinimumSize(860, 460)
        self._client = client
        self._run = run
        self._rows: list[dict[str, Any]] = []
        self._invoice_types: list[dict[str, Any]] = []
        #: cls_options ανά τύπο — στατικά, οπότε ζητούνται μία φορά.
        self._options: dict[str, dict[str, Any]] = {}

        box = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(ui.button("Ανανέωση", self.refresh))
        bar.addWidget(ui.button("Νέα κατηγορία", self._new, kind="primary"))
        bar.addWidget(ui.button("Επεξεργασία", self._edit))
        bar.addWidget(ui.button("Διαγραφή", self._delete, kind="danger"))
        bar.addStretch(1)
        box.addLayout(bar)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Κατηγορία", "Χαρακτηρισμοί"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 240)
        self._table.doubleClicked.connect(lambda *_: self._edit())
        box.addWidget(self._table, 1)

        self._status = ui.muted("")
        box.addWidget(self._status)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Κλείσιμο")
        close.rejected.connect(self.reject)
        box.addWidget(close)

        self.refresh()

    # --- δεδομένα ----------------------------------------------------------
    def refresh(self) -> None:
        self._status.setText("Φόρτωση κατηγοριών…")
        self._run(self._client.category_classifications, self._fill, self._failed)

    def _fill(self, data: dict[str, Any]) -> None:
        self._rows = list(data.get("categories") or data.get("rows") or [])
        self._invoice_types = list(data.get("invoice_types") or [])
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            self._table.setItem(r, 0, QTableWidgetItem(str(row.get("name") or "")))
            item = QTableWidgetItem(classification_summary(row))
            item.setToolTip(
                "\n".join(
                    f"{c.get('invoice_type_label', '')}: {c.get('category_title', '')} · "
                    f"{c.get('code_title', '')}"
                    for c in row.get("classifications") or []
                )
            )
            self._table.setItem(r, 1, item)
        self._status.setText(f"{len(self._rows)} κατηγορίες")

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    def _options_for(self, invoice_type: str) -> dict[str, Any]:
        """Σύγχρονη ανάκτηση (και cache) των επιλογών ενός τύπου.

        Καλείται από τα combo του διαλόγου, όπου δεν υπάρχει worker — αλλά το
        αποτέλεσμα είναι στατικό και το backend το κρατά ήδη σε cache, οπότε
        μετά την πρώτη φορά είναι στιγμιαίο.
        """
        if not invoice_type:
            return {}
        if invoice_type not in self._options:
            try:
                self._options[invoice_type] = self._client.classification_options(invoice_type)
            except Exception:  # noqa: BLE001 — άδειες λίστες αντί για crash
                self._options[invoice_type] = {}
        return self._options[invoice_type]

    # --- ενέργειες ----------------------------------------------------------
    def _selected(self) -> dict[str, Any] | None:
        index = self._table.currentRow()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _open(self, row: dict[str, Any] | None) -> None:
        if not self._invoice_types:
            self._status.setText("Δεν φορτώθηκαν οι τύποι παραστατικών — δοκίμασε ανανέωση.")
            return
        dialog = CategoryEditDialog(
            self, invoice_types=self._invoice_types,
            options_for=self._options_for, row=row,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self._status.setText("Αποθήκευση κατηγορίας…")
        self._run(
            lambda: self._client.save_category_classifications(**fields),
            self._after_write,
            self._failed,
        )

    def _new(self) -> None:
        self._open(None)

    def _edit(self) -> None:
        row = self._selected()
        if row is not None:
            self._open(row)

    def _delete(self) -> None:
        row = self._selected()
        if row is None:
            return
        category_id = str(row.get("category_id") or "")
        name = str(row.get("name") or "")
        if not category_id:
            self._status.setText("Η κατηγορία δεν έχει id — δεν διαγράφεται.")
            return
        if QMessageBox.question(
            self, "Διαγραφή κατηγορίας",
            f"Διαγραφή της κατηγορίας «{name}»;\n\n"
            "Τα είδη που την χρησιμοποιούν θα μείνουν χωρίς χαρακτηρισμό και "
            "η ΑΑΔΕ θα απορρίπτει την έκδοσή τους.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._status.setText("Διαγραφή…")
        self._run(
            lambda: self._client.delete_product_category(category_id),
            self._after_write,
            self._failed,
        )

    def _after_write(self, result: dict[str, Any]) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))
