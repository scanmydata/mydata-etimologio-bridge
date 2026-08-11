"""Native Πληρωμές: local payment ledger + bank-statement import.

e-timologio keeps no payments, so these live bridge-side (encrypted, per company).
Two tabs: the current ledger (+ manual add), and a bank-statement import that
parses a file into candidate rows the user reviews before registering them.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .base import EtimPage, fmt_money, parse_money
from .card import _METHODS

_PAY_COLS = [("Ημ/νία", "pay_date"), ("Ποσό", "amount"), ("Τρόπος", "method"),
             ("Πελάτης", "customer_name"), ("ΑΦΜ", "customer_vat"), ("Σημειώσεις", "notes")]
_PREVIEW_COLS = ["Ημ/νία", "Περιγραφή", "Ποσό", "ΑΦΜ πελάτη", "Όνομα"]


class NewPaymentDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Νέα πληρωμή")
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        self.vat = QLineEdit()
        self.name = QLineEdit()
        self.amount = QLineEdit("0")
        self.method = QComboBox()
        for code, label in _METHODS.items():
            self.method.addItem(label, code)
        self.notes = QLineEdit()
        form.addRow("ΑΦΜ πελάτη", self.vat)
        form.addRow("Επωνυμία", self.name)
        form.addRow("Ποσό *", self.amount)
        form.addRow("Τρόπος", self.method)
        form.addRow("Σημειώσεις", self.notes)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(lambda: self.accept() if parse_money(self.amount.text()) > 0 else self.amount.setFocus())
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def fields(self) -> dict[str, Any]:
        return {
            "buyer_vat": self.vat.text().strip(),
            "customer_name": self.name.text().strip(),
            "pay_amount": parse_money(self.amount.text()),
            "pay_method": self.method.currentData(),
            "pay_notes": self.notes.text().strip(),
        }


class PaymentsPage(EtimPage):
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
        back.setFixedWidth(36)
        back.setToolTip("Πίσω")
        back.clicked.connect(self.go_back.emit)
        top.addWidget(back)
        title = QLabel("Πληρωμές")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        box.addLayout(top)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._ledger_tab(), "Πληρωμές")
        self._tabs.addTab(self._import_tab(), "Εισαγωγή από τράπεζα")
        box.addWidget(self._tabs, 1)

        self._status = QLabel("")
        self._status.setObjectName("muted")
        box.addWidget(self._status)

    # --- ledger tab --------------------------------------------------------
    def _ledger_tab(self):
        w = QVBoxLayout()
        bar = QHBoxLayout()
        new = QPushButton("Νέα πληρωμή")
        new.clicked.connect(self._new_payment)
        refresh = QPushButton("Ανανέωση")
        refresh.clicked.connect(self.refresh)
        bar.addWidget(new)
        bar.addWidget(refresh)
        bar.addStretch(1)
        w.addLayout(bar)
        self._pay_table = QTableWidget(0, len(_PAY_COLS))
        self._pay_table.setHorizontalHeaderLabels([h for h, _ in _PAY_COLS])
        self._pay_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pay_table.verticalHeader().setVisible(False)
        self._pay_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        w.addWidget(self._pay_table, 1)
        container = _wrap(w)
        return container

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        self._status.setText("Φόρτωση πληρωμών…")
        self._run(client.payments, self._fill_payments, self._failed)

    def _fill_payments(self, data: dict) -> None:
        rows = data.get("payments", [])
        self._pay_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (_, key) in enumerate(_PAY_COLS):
                if key == "method":
                    text = _METHODS.get(str(row.get("method", "")), str(row.get("method", "")))
                elif key == "amount":
                    text = fmt_money(parse_money(row.get("amount")))
                else:
                    text = str(row.get(key, ""))
                self._pay_table.setItem(r, c, QTableWidgetItem(text))
        self._status.setText(f"{len(rows)} πληρωμές")

    def _new_payment(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewPaymentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._status.setText("Αποθήκευση πληρωμής…")
        self._run(lambda: client.add_payment(**dialog.fields()), self._after_write, self._failed)

    def _after_write(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))

    # --- bank import tab ---------------------------------------------------
    def _import_tab(self):
        w = QVBoxLayout()
        bar = QHBoxLayout()
        openf = QPushButton("Άνοιγμα αρχείου τράπεζας…")
        openf.clicked.connect(self._open_bank_file)
        self._import_btn = QPushButton("Εισαγωγή ως πληρωμές")
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._do_import)
        bar.addWidget(openf)
        bar.addWidget(self._import_btn)
        bar.addStretch(1)
        w.addLayout(bar)
        hint = QLabel("Άνοιξε extrait (.xlsx/.csv). Συμπλήρωσε ΑΦΜ/όνομα πελάτη ανά γραμμή και εισήγαγε.")
        hint.setObjectName("muted")
        w.addWidget(hint)
        self._prev_table = QTableWidget(0, len(_PREVIEW_COLS))
        self._prev_table.setHorizontalHeaderLabels(_PREVIEW_COLS)
        self._prev_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        w.addWidget(self._prev_table, 1)
        return _wrap(w)

    def _open_bank_file(self) -> None:
        client = self.client()
        if client is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Επιλογή αρχείου τράπεζας", "", "Extrait (*.xlsx *.xls *.csv *.txt);;Όλα (*.*)"
        )
        if not path:
            return
        raw = Path(path).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        name = Path(path).name
        self._status.setText("Ανάλυση αρχείου…")
        self._run(
            lambda: client.bank_preview(b64, filename=name),
            self._fill_preview,
            self._failed,
        )

    def _fill_preview(self, data: dict) -> None:
        txs = data.get("transactions", [])
        self._prev_table.setRowCount(len(txs))
        for r, tx in enumerate(txs):
            self._prev_table.setItem(r, 0, QTableWidgetItem(str(tx.get("date", ""))))
            self._prev_table.setItem(r, 1, QTableWidgetItem(str(tx.get("description", ""))))
            self._prev_table.setItem(r, 2, QTableWidgetItem(fmt_money(parse_money(tx.get("amount")))))
            self._prev_table.setItem(r, 3, QTableWidgetItem(str(tx.get("customer_vat", ""))))
            self._prev_table.setItem(r, 4, QTableWidgetItem(str(tx.get("customer_name", ""))))
        self._import_btn.setEnabled(len(txs) > 0)
        self._status.setText(f"{len(txs)} κινήσεις — έλεγξε και εισήγαγε.")

    def _do_import(self) -> None:
        client = self.client()
        if client is None:
            return
        items: list[dict[str, Any]] = []
        for r in range(self._prev_table.rowCount()):
            amount = parse_money(self._prev_table.item(r, 2).text())
            if amount <= 0:
                continue  # only money-in rows become payments
            items.append({
                "pay_date": self._prev_table.item(r, 0).text().strip(),
                "notes": self._prev_table.item(r, 1).text().strip(),
                "amount": amount,
                "customer_vat": self._prev_table.item(r, 3).text().strip(),
                "customer_name": self._prev_table.item(r, 4).text().strip(),
                "method": 1,  # bank account
            })
        if not items:
            self._status.setText("Καμία θετική κίνηση προς εισαγωγή.")
            return
        self._status.setText(f"Εισαγωγή {len(items)} πληρωμών…")
        self._run(lambda: client.bank_import(items), self._after_import, self._failed)

    def _after_import(self, result: dict) -> None:
        ok = result.get("imported", result.get("ok", 0))
        self._status.setText(f"Εισήχθησαν {ok} πληρωμές.")
        self._prev_table.setRowCount(0)
        self._import_btn.setEnabled(False)
        self._tabs.setCurrentIndex(0)
        self.refresh()

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")


def _wrap(layout: QVBoxLayout) -> QWidget:
    """A tab page needs a widget, not a layout."""
    page = QWidget()
    page.setLayout(layout)
    return page
