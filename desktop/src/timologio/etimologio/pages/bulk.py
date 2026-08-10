"""Native Μαζική έκδοση: issue many one-line documents in a batch.

A shared header (type/series/payment) applies to every row; each row is one
customer + one line. Default action saves drafts; "Μαζική έκδοση" issues for
real. Per-row results are written back into the table.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base import EtimPage, parse_money
from .issue import INVOICE_TYPES, PAYMENT_METHODS

_COLS = ["ΑΦΜ", "Επωνυμία", "Περιγραφή", "Ποσότητα", "Τιμή", "ΦΠΑ %", "Αποτέλεσμα"]
_AFM, _NAME, _DESC, _QTY, _PRICE, _RATE, _RESULT = range(7)


class BulkPage(EtimPage):
    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        box = QVBoxLayout(self)

        top = QHBoxLayout()
        back = QPushButton("←")
        back.setFixedWidth(36)
        back.setToolTip("Πίσω")
        back.clicked.connect(self.go_back.emit)
        top.addWidget(back)
        title = QLabel("Μαζική έκδοση")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        box.addLayout(top)

        head = QHBoxLayout()
        self._type = QComboBox()
        for code, label in INVOICE_TYPES:
            self._type.addItem(label, code)
        head.addWidget(QLabel("Τύπος:"))
        head.addWidget(self._type, 2)
        self._series = QLineEdit("A")
        self._series.setFixedWidth(56)
        head.addWidget(QLabel("Σειρά:"))
        head.addWidget(self._series)
        self._payment = QComboBox()
        for code, label in PAYMENT_METHODS:
            self._payment.addItem(label, code)
        head.addWidget(QLabel("Πληρωμή:"))
        head.addWidget(self._payment, 1)
        box.addLayout(head)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setColumnWidth(_NAME, 200)
        self._table.setColumnWidth(_DESC, 200)
        box.addWidget(self._table, 1)

        row_btns = QHBoxLayout()
        add = QPushButton("+ Γραμμή")
        add.clicked.connect(lambda: self.add_row())
        rem = QPushButton("− Γραμμή")
        rem.clicked.connect(self._remove_row)
        row_btns.addWidget(add)
        row_btns.addWidget(rem)
        row_btns.addStretch(1)
        self._status = QLabel("")
        self._status.setObjectName("muted")
        row_btns.addWidget(self._status)
        box.addLayout(row_btns)

        actions = QHBoxLayout()
        actions.addStretch(1)
        draft = QPushButton("Αποθήκευση πρόχειρων")
        draft.clicked.connect(lambda: self._run_bulk(live=False))
        issue = QPushButton("Μαζική έκδοση")
        issue.setObjectName("danger")
        issue.clicked.connect(lambda: self._run_bulk(live=True))
        actions.addWidget(draft)
        actions.addWidget(issue)
        box.addLayout(actions)

        self.add_row()

    def add_row(self, afm="", name="", desc="", qty="1", price="0", rate="24") -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        for col, val in ((_AFM, afm), (_NAME, name), (_DESC, desc), (_QTY, qty), (_PRICE, price), (_RATE, rate)):
            self._table.setItem(r, col, QTableWidgetItem(val))
        self._table.setItem(r, _RESULT, QTableWidgetItem(""))

    def _remove_row(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            r = self._table.rowCount() - 1
        if r >= 0:
            self._table.removeRow(r)

    def _cell(self, r: int, c: int) -> str:
        item = self._table.item(r, c)
        return item.text().strip() if item else ""

    def build_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        inv_type = self._type.currentData()
        series = self._series.text().strip() or "A"
        payment = int(self._payment.currentData())
        for r in range(self._table.rowCount()):
            desc = self._cell(r, _DESC)
            price = parse_money(self._cell(r, _PRICE))
            if not desc and price == 0:
                continue
            rate = parse_money(self._cell(r, _RATE))
            items.append({
                "afm": self._cell(r, _AFM),
                "name": self._cell(r, _NAME),
                "type": inv_type,
                "series": series,
                "payment": payment,
                "lines": [{
                    "code": desc or "Είδος",
                    "qty": parse_money(self._cell(r, _QTY)) or 1,
                    "price": price,
                    "rate": round(rate / 100.0, 4),
                }],
                "_row": r,
            })
        return items

    def _run_bulk(self, *, live: bool) -> None:
        client = self.client()
        if client is None:
            return
        items = self.build_items()
        if not items:
            self._status.setText("Πρόσθεσε τουλάχιστον μία έγκυρη γραμμή.")
            return
        rows_by_index = [it.pop("_row") for it in items]
        if live and QMessageBox.question(
            self, "Μαζική έκδοση",
            f"Θα εκδοθούν {len(items)} παραστατικά στην ΑΑΔΕ (ΜΑΡΚ). Συνέχεια;",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._status.setText("Επεξεργασία παρτίδας…")
        self._run(
            lambda: client.bulk_issue(items, live=live),
            lambda res: self._after_bulk(res, rows_by_index),
            self._failed,
        )

    def _after_bulk(self, result: dict, rows_by_index: list[int]) -> None:
        results = result.get("results", [])
        ok = 0
        for res in results:
            idx = res.get("index", -1)
            if not (0 <= idx < len(rows_by_index)):
                continue
            table_row = rows_by_index[idx]
            if res.get("success"):
                ok += 1
                text = f"✓ ΜΑΡΚ {res['mark']}" if res.get("mark") else f"✓ πρόχειρο {res.get('temp_id', '')[:8]}"
            else:
                text = f"✗ {res.get('error', 'σφάλμα')}"
            self._table.setItem(table_row, _RESULT, QTableWidgetItem(text))
        self._status.setText(f"Ολοκληρώθηκε: {ok}/{len(results)} επιτυχή.")

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")
