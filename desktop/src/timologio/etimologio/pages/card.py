"""Native Καρτέλα πελάτη: a customer's issued invoices + local payments + balance.

e-timologio has no ledger endpoint, so the card is reconstructed here: issued
documents come from ``search_invoices`` filtered by the buyer's ΑΦΜ, and payments
from the bridge-side local ledger (``list_payments``). The balance is
``Σύνολο τιμολογίων − Σύνολο πληρωμών``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from .base import EtimPage, fmt_money, parse_money
from .customers import _cust_value

_INV_COLS: list[tuple[str, str]] = [
    ("Ημ/νία", "issue_date"),
    ("Τύπος", "type"),
    ("Σειρά", "series"),
    ("Α/Α", "aa"),
    ("MARK", "mark"),
    ("Καθαρή", "net_value"),
    ("ΦΠΑ", "vat_value"),
    ("Σύνολο", "total"),
]

_PAY_COLS: list[tuple[str, str]] = [
    ("Ημ/νία", "pay_date"),
    ("Ποσό", "amount"),
    ("Τρόπος", "method"),
    ("MARK", "mark"),
    ("Σημειώσεις", "notes"),
]

#: Payment method codes → labels (subset the bridge uses).
_METHODS = {
    "1": "Επαγγ. λογ. τράπεζας",
    "2": "Επαγγ. λογ. τράπεζας αλλοδαπής",
    "3": "Μετρητά",
    "4": "Επιταγή",
    "5": "Επί πιστώσει",
    "6": "Web banking",
    "7": "POS / e-POS",
}


class CustomerCard(EtimPage):
    """Read-only ledger for a single customer."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._customer: dict[str, Any] = {}
        box = QVBoxLayout(self)

        top = QHBoxLayout()
        back = QPushButton("←")
        back.setToolTip("Πίσω στους πελάτες")
        back.setFixedWidth(36)
        back.clicked.connect(self.go_back.emit)
        top.addWidget(back)
        self._title = QLabel("Καρτέλα πελάτη")
        self._title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(self._title)
        top.addStretch(1)
        refresh = QPushButton("Ανανέωση")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        box.addLayout(top)

        self._summary = QLabel("")
        self._summary.setStyleSheet("color:#93a4bd;margin:2px 0 6px 0;")
        box.addWidget(self._summary)

        self._tabs = QTabWidget()
        self._invoices = self._make_table(_INV_COLS)
        self._payments = self._make_table(_PAY_COLS)
        self._tabs.addTab(self._invoices, "Παραστατικά")
        self._tabs.addTab(self._payments, "Πληρωμές")
        box.addWidget(self._tabs, 1)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#93a4bd;")
        box.addWidget(self._status)

        self._inv_total = 0.0
        self._pay_total = 0.0
        self._pending = 0

    def _make_table(self, cols: list[tuple[str, str]]) -> QTableWidget:
        table = QTableWidget(0, len(cols))
        table.setHorizontalHeaderLabels([h for h, _ in cols])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            len(cols) - 1, QHeaderView.ResizeMode.Stretch
        )
        return table

    # --- data --------------------------------------------------------------
    def set_customer(self, customer: dict[str, Any]) -> None:
        self._customer = dict(customer or {})
        name = _cust_value(self._customer, "name")
        vat = _cust_value(self._customer, "vat")
        self._title.setText(f"Καρτέλα: {name}" if name else "Καρτέλα πελάτη")
        self._summary.setText(f"ΑΦΜ: {vat}" if vat else "")
        self.refresh()

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        vat = _cust_value(self._customer, "vat")
        if not vat:
            self._status.setText("Ο πελάτης δεν έχει ΑΦΜ — δεν υπάρχει καρτέλα.")
            return
        self._inv_total = 0.0
        self._pay_total = 0.0
        self._pending = 2
        self._status.setText("Φόρτωση…")
        # e-timologio search needs a date range; default to the current year so
        # the card shows this year's history without the user picking dates.
        year = date.today().year
        date_from = f"01/01/{year}"
        date_to = date.today().strftime("%d/%m/%Y")
        self._run(
            lambda: client.search_invoices(
                buyer_vat=vat, date_from=date_from, date_to=date_to
            ),
            self._fill_invoices,
            self._failed,
        )
        self._run(lambda: client.payments(buyer_vat=vat), self._fill_payments, self._failed)

    def _fill_invoices(self, data: dict[str, Any]) -> None:
        rows = list(data.get("invoices", []))
        self._invoices.setRowCount(len(rows))
        total = 0.0
        for r, row in enumerate(rows):
            for c, (_, key) in enumerate(_INV_COLS):
                self._invoices.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))
            total += parse_money(row.get("total"))
        self._inv_total = total
        self._done()

    def _fill_payments(self, data: dict[str, Any]) -> None:
        rows = list(data.get("payments", []))
        self._payments.setRowCount(len(rows))
        total = 0.0
        for r, row in enumerate(rows):
            for c, (_, key) in enumerate(_PAY_COLS):
                if key == "method":
                    text = _METHODS.get(str(row.get("method", "")), str(row.get("method", "")))
                elif key == "amount":
                    text = fmt_money(parse_money(row.get("amount")))
                else:
                    text = str(row.get(key, ""))
                self._payments.setItem(r, c, QTableWidgetItem(text))
            total += parse_money(row.get("amount"))
        self._pay_total = total
        self._done()

    def _done(self) -> None:
        self._pending -= 1
        if self._pending > 0:
            return
        balance = self._inv_total - self._pay_total
        self._status.setText("")
        self._summary.setText(
            f"ΑΦΜ: {_cust_value(self._customer, 'vat')}    ·    "
            f"Τιμολόγια: {fmt_money(self._inv_total)} €    ·    "
            f"Πληρωμές: {fmt_money(self._pay_total)} €    ·    "
            f"Υπόλοιπο: {fmt_money(balance)} €"
        )

    def _failed(self, msg: str) -> None:
        self._pending = max(0, self._pending - 1)
        self._status.setText(f"Σφάλμα: {msg}")
