"""Native Πελάτες (customers) page: search, list, create, open card."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import ui
from .base import ROW_ROLE, EtimPage, cached_then_live

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
    """Create a customer — επιχείρηση με ΑΦΜ ή ιδιώτης.

    The two are genuinely different records at the ΑΑΔΕ, not one form with an
    optional field: a customer with a VAT number is registered through the
    Taxisnet lookup, while an ιδιώτης is created locally and needs ονοματεπώνυμο,
    πόλη and ΤΚ. Filing a taxpayer as an ιδιώτης drops the VAT number, turns
    their invoices into retail receipts, and nothing says so until the ΑΑΔΕ
    rejects a Τιμολόγιο — hence the explicit choice.
    """

    def __init__(self, parent=None, *, vat: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Νέος πελάτης")
        self.setMinimumWidth(420)
        box = QVBoxLayout(self)

        self._tabs = QTabWidget()
        box.addWidget(self._tabs)

        # --- επιχείρηση με ΑΦΜ --------------------------------------------
        biz = QWidget()
        biz_form = QFormLayout(biz)
        self.vat = QLineEdit(vat)
        self.vat.setPlaceholderText("9 ψηφία")
        self.vat.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,9}")))
        biz_form.addRow("ΑΦΜ *", self.vat)
        note = QLabel(
            "Τα στοιχεία αντλούνται από το Taxisnet και ο πελάτης καταχωρείται "
            "στο e-timologio αν δεν υπάρχει ήδη."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        biz_form.addRow(note)
        self._tabs.addTab(biz, "Με ΑΦΜ (Taxisnet)")

        # --- ιδιώτης --------------------------------------------------------
        person = QWidget()
        p_form = QFormLayout(person)
        self.name = QLineEdit()
        self.address = QLineEdit()
        self.city = QLineEdit()
        self.zip = QLineEdit()
        self.job = QLineEdit("ΙΔΙΩΤΗΣ")
        self.email = QLineEdit()
        self.phone1 = QLineEdit()
        p_form.addRow("Ονοματεπώνυμο *", self.name)
        p_form.addRow("Διεύθυνση", self.address)
        p_form.addRow("Πόλη *", self.city)
        p_form.addRow("Τ.Κ. *", self.zip)
        p_form.addRow("Επάγγελμα", self.job)
        p_form.addRow("Email", self.email)
        p_form.addRow("Τηλέφωνο", self.phone1)
        self._tabs.addTab(person, "Ιδιώτης (χωρίς ΑΦΜ)")

        self._error = QLabel("")
        self._error.setObjectName("hint")
        self._error.setWordWrap(True)
        box.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        if vat:
            self._tabs.setCurrentIndex(0)

    def is_personal(self) -> bool:
        return self._tabs.currentIndex() == 1

    def _accept(self) -> None:
        if self.is_personal():
            for field, message in (
                (self.name, "Δώσε ονοματεπώνυμο."),
                (self.city, "Δώσε πόλη."),
                (self.zip, "Δώσε Τ.Κ."),
            ):
                if not field.text().strip():
                    self._error.setText(message)
                    field.setFocus()
                    return
        elif not re.fullmatch(r"\d{9}", self.vat.text().strip()):
            self._error.setText("Το ΑΦΜ πρέπει να έχει 9 ψηφία.")
            self.vat.setFocus()
            return
        self.accept()

    def fields(self) -> dict[str, Any]:
        """Exactly the keyword arguments the matching client call expects."""
        if self.is_personal():
            return {
                "name": self.name.text().strip(),
                "address": self.address.text().strip(),
                "city": self.city.text().strip(),
                "zip_code": self.zip.text().strip(),
                "job_description": self.job.text().strip() or "ΙΔΙΩΤΗΣ",
                "email": self.email.text().strip(),
                "phone1": self.phone1.text().strip(),
            }
        return {"vat": self.vat.text().strip()}


class EditCustomerDialog(QDialog):
    """Επεξεργασία υπάρχοντος πελάτη.

    Το ΑΦΜ/κωδικός είναι το κλειδί και δεν αλλάζει — αλλιώς θα δημιουργούσε
    δεύτερη εγγραφή αντί να ενημερώσει την υπάρχουσα.
    """

    def __init__(self, parent=None, *, row: dict[str, Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Επεξεργασία πελάτη")
        self.setMinimumWidth(400)
        self._vat = _cust_value(row, "vat")
        self._code = _cust_value(row, "code")

        form = QFormLayout(self)
        key = QLineEdit(self._vat or self._code)
        key.setReadOnly(True)
        form.addRow("ΑΦΜ / Κωδικός", key)

        self.name = QLineEdit(_cust_value(row, "name"))
        self.address = QLineEdit(_cust_value(row, "address"))
        self.city = QLineEdit(_cust_value(row, "city"))
        self.zip = QLineEdit(_cust_value(row, "zip"))
        self.email = QLineEdit(_cust_value(row, "email"))
        self.phone1 = QLineEdit(_cust_value(row, "phone1"))
        form.addRow("Επωνυμία", self.name)
        form.addRow("Διεύθυνση", self.address)
        form.addRow("Πόλη", self.city)
        form.addRow("Τ.Κ.", self.zip)
        form.addRow("Email", self.email)
        form.addRow("Τηλέφωνο", self.phone1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def fields(self) -> dict[str, Any]:
        return {
            "vat": self._vat,
            "code": "" if self._vat else self._code,
            "name": self.name.text().strip(),
            "address": self.address.text().strip(),
            "city": self.city.text().strip(),
            "zip_code": self.zip.text().strip(),
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
        edit_btn = QPushButton("Επεξεργασία")
        edit_btn.clicked.connect(self._edit_customer)
        top.addWidget(edit_btn)
        del_btn = QPushButton("Διαγραφή")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_customer)
        top.addWidget(del_btn)
        box.addLayout(top)
        box.addWidget(ui.page_hint(
            "Έξυπνη αναζήτηση και διαχείριση πελατολογίου. Διπλό κλικ ανοίγει την καρτέλα του πελάτη."))

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
        # Ταξινόμηση, μετακινούμενες στήλες που θυμούνται πλάτη, και φίλτρα ανά
        # στήλη — η ίδια υποδομή με τους πίνακες του Downloader.
        self._filter = ui.make_sortable(
            self._table, "customers", filter_columns=list(range(len(_COLS)))
        )

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
        if not term:
            # Χωρίς όρο αναζήτησης είναι «όλο το πελατολόγιο» — ακριβώς το
            # snapshot που κρατά η τοπική cache. Ο πίνακας ήταν άδειος για ~6
            # δευτερόλεπτα σε κάθε άνοιγμα της σελίδας, χωρίς κανέναν λόγο.
            cached_then_live(
                self._run, client, "customers", lambda: client.sync("customers"),
                lambda rows, from_cache: self._fill(
                    {"customers": rows, "_from_cache": from_cache}
                ),
                self._failed,
            )
            return
        # A digits-only term is almost certainly an ΑΦΜ; else a name.
        kwargs = {"vat": term} if term.isdigit() and len(term) >= 8 else {"name": term}
        self._run(lambda: client.customers(**kwargs), self._fill, self._failed)

    def rows(self) -> list[dict[str, Any]]:
        """Το φορτωμένο πελατολόγιο — το δανείζεται η Καρτέλα για τον επιλογέα."""
        return list(self._rows)

    def _fill(self, data: dict[str, Any]) -> None:
        rows = data.get("customers")
        if rows is None:
            rows = data.get("rows", [])
        self._rows = list(rows)
        # Η ταξινόμηση κλείνει όσο γεμίζει ο πίνακας: αλλιώς κάθε setItem
        # ξαναταξινομεί και οι γραμμές μπερδεύονται με τα _rows.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, (_, key) in enumerate(_COLS):
                item = QTableWidgetItem(_cust_value(row, key))
                if c == 0:
                    item.setData(ROW_ROLE, r)
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)
        self._status.setText(f"{len(self._rows)} πελάτες")

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    # --- actions -----------------------------------------------------------
    def _selected_row(self) -> dict[str, Any] | None:
        # Μέσω του δείκτη γραμμής: μετά από ταξινόμηση η οπτική σειρά δεν είναι
        # η σειρά φόρτωσης, και η «Διαγραφή» θα έσβηνε άλλον πελάτη.
        item = self._table.item(self._table.currentRow(), 0)
        if item is None:
            return None
        index = item.data(ROW_ROLE)
        index = self._table.currentRow() if index is None else int(index)
        return self._rows[index] if 0 <= index < len(self._rows) else None

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
        personal = dialog.is_personal()
        self._status.setText("Αποθήκευση πελάτη…")
        call = (
            (lambda: client.create_personal_customer(**fields))
            if personal
            else (lambda: client.lookup_afm(fields["vat"]))
        )
        self._run(call, self._created, self._failed)

    def _edit_customer(self) -> None:
        client = self.client()
        row = self._selected_row()
        if client is None or row is None:
            return
        dialog = EditCustomerDialog(self, row=row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self._status.setText("Ενημέρωση πελάτη…")
        self._run(lambda: client.update_customer(**fields), self._created, self._failed)

    def _delete_customer(self) -> None:
        client = self.client()
        row = self._selected_row()
        if client is None or row is None:
            return
        name = _cust_value(row, "name")
        code = _cust_value(row, "code")
        vat = _cust_value(row, "vat")
        if not (code or vat):
            self._status.setText("Ο πελάτης δεν έχει κωδικό ούτε ΑΦΜ — δεν διαγράφεται.")
            return
        if QMessageBox.question(
            self, "Διαγραφή πελάτη",
            f"Διαγραφή του πελάτη «{name}»;\n\nΤα ήδη εκδοθέντα παραστατικά του "
            "δεν επηρεάζονται — παραμένουν στην ΑΑΔΕ.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._status.setText("Διαγραφή πελάτη…")
        self._run(
            lambda: client.delete_customer(code=code, vat=vat), self._created, self._failed
        )

    def _created(self, result: dict[str, Any]) -> None:
        # Το Taxisnet lookup δεν επιστρέφει πάντα `success`· αν γύρισε πελάτη,
        # η καταχώρηση έγινε.
        if result.get("success") or result.get("customer") or result.get("info"):
            self._status.setText("Ο πελάτης αποθηκεύτηκε.")
            self.refresh()
        else:
            self._status.setText(result.get("error", "Αποτυχία αποθήκευσης."))
