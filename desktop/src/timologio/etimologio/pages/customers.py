"""Native Πελάτες (customers) page: search, list, create, open card."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base import EtimPage

#: Column order for the customers table: (header, source key).
_COLS: list[tuple[str, str]] = [
    ("Κωδικός", "code"),
    ("ΑΦΜ", "vat"),
    ("Επωνυμία", "name"),
    ("Πόλη", "city"),
    ("Διεύθυνση", "address"),
]


def _cust_value(row: dict[str, Any], key: str) -> str:
    """Read a field defensively — cache rows and live rows differ slightly."""
    if key == "vat":
        return str(row.get("vat") or row.get("afm") or row.get("vatNumber") or "")
    if key == "name":
        return str(row.get("name") or row.get("fullName") or row.get("customer_name") or "")
    if key == "code":
        return str(row.get("code") or row.get("customer_code") or "")
    return str(row.get(key) or "")


class NewCustomerDialog(QDialog):
    """Minimal create-customer form (ιδιώτης by default)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Νέος πελάτης")
        self.setMinimumWidth(380)
        form = QFormLayout(self)

        self.name = QLineEdit()
        self.vat = QLineEdit()
        self.vat.setPlaceholderText("προαιρετικό για ιδιώτη")
        self.address = QLineEdit()
        self.city = QLineEdit()
        self.zip = QLineEdit()
        self.doy = QLineEdit("ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ")
        self.email = QLineEdit()
        self.phone1 = QLineEdit()
        form.addRow("Επωνυμία *", self.name)
        form.addRow("ΑΦΜ", self.vat)
        form.addRow("Διεύθυνση", self.address)
        form.addRow("Πόλη", self.city)
        form.addRow("Τ.Κ.", self.zip)
        form.addRow("ΔΟΥ", self.doy)
        form.addRow("Email", self.email)
        form.addRow("Τηλέφωνο", self.phone1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        self.accept()

    def fields(self) -> dict[str, Any]:
        return {
            "name": self.name.text().strip(),
            "vat": self.vat.text().strip(),
            "address": self.address.text().strip(),
            "city": self.city.text().strip(),
            "zip": self.zip.text().strip(),
            "doy": self.doy.text().strip(),
            "email": self.email.text().strip(),
            "phone1": self.phone1.text().strip(),
        }


class CustomersPage(EtimPage):
    """Search + list customers; open a customer's card; create a customer."""

    #: Emitted with the selected customer row when the user opens its card.
    open_card = Signal(dict)
    #: Emitted when the user asks to leave the page.
    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        top = QHBoxLayout()
        back = QPushButton("←")
        back.setToolTip("Πίσω")
        back.setFixedWidth(36)
        back.clicked.connect(self.go_back.emit)
        top.addWidget(back)
        title = QLabel("Πελάτες")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Αναζήτηση με επωνυμία ή ΑΦΜ…")
        self._search.setMinimumWidth(240)
        self._search.returnPressed.connect(self.refresh)
        top.addWidget(self._search)
        search_btn = QPushButton("Αναζήτηση")
        search_btn.clicked.connect(self.refresh)
        top.addWidget(search_btn)
        new_btn = QPushButton("Νέος πελάτης")
        new_btn.clicked.connect(self._new_customer)
        top.addWidget(new_btn)
        box.addLayout(top)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels([h for h, _ in _COLS])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(lambda *_: self._open_selected())
        box.addWidget(self._table, 1)

        bottom = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("muted")
        bottom.addWidget(self._status)
        bottom.addStretch(1)
        open_btn = QPushButton("Άνοιγμα καρτέλας")
        open_btn.clicked.connect(self._open_selected)
        bottom.addWidget(open_btn)
        box.addLayout(bottom)

        self._rows: list[dict[str, Any]] = []

    # --- data --------------------------------------------------------------
    def set_search(self, text: str) -> None:
        self._search.setText(text)

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        term = self._search.text().strip()
        self._status.setText("Φόρτωση…")
        # A digits-only term is almost certainly an ΑΦΜ; else a name.
        kwargs = {"vat": term} if term.isdigit() and len(term) >= 8 else {"name": term}
        self._run(lambda: client.customers(**kwargs), self._fill, self._failed)

    def _fill(self, data: dict[str, Any]) -> None:
        rows = data.get("customers")
        if rows is None:
            rows = data.get("rows", [])
        self._rows = list(rows)
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, (_, key) in enumerate(_COLS):
                self._table.setItem(r, c, QTableWidgetItem(_cust_value(row, key)))
        self._status.setText(f"{len(self._rows)} πελάτες")

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    # --- actions -----------------------------------------------------------
    def _selected_row(self) -> dict[str, Any] | None:
        idx = self._table.currentRow()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self.open_card.emit(row)

    def _new_customer(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewCustomerDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self._status.setText("Αποθήκευση πελάτη…")
        self._run(
            lambda: client.create_customer(**fields),
            self._created,
            self._failed,
        )

    def _created(self, result: dict[str, Any]) -> None:
        if result.get("success"):
            self._status.setText("Ο πελάτης αποθηκεύτηκε.")
            self.refresh()
        else:
            self._status.setText(result.get("error", "Αποτυχία αποθήκευσης."))
