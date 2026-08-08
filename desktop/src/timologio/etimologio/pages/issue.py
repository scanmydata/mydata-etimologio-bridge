"""Native Έκδοση (invoice editor): customer, lines, taxes, draft/preview/issue.

The page owns no issuance logic — it collects a customer, a list of lines and a
document type, and hands them to ``EtimologioClient.issue_invoice`` in one of
three modes (πρόχειρο / προεπισκόπηση / έκδοση). Totals shown here are a live
preview; the bridge recomputes the authoritative amounts myDATA receives.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base import EtimPage, fmt_money, parse_money

#: Income document types (code → label), the subset a business issues day to day.
INVOICE_TYPES: list[tuple[str, str]] = [
    ("20", "2.1 Παροχή Υπηρεσιών"),
    ("1", "1.1 Τιμολόγιο Πώλησης"),
    ("2", "1.2 Πώληση Ενδοκοινοτική"),
    ("3", "1.3 Πώληση Τρίτες Χώρες"),
    ("21", "2.2 Ενδοκοινοτική Παροχή"),
    ("22", "2.3 Παροχή Τρίτων Χωρών"),
    ("30", "3.1 Τίτλος Κτήσης"),
    ("55", "8.1 Ενοίκια / Έσοδο"),
    ("57", "11.1 ΑΛΠ"),
    ("58", "11.2 ΑΠΥ"),
    ("59", "11.3 Απλοποιημένο Τιμολόγιο"),
]

#: Payment methods (code → label).
PAYMENT_METHODS: list[tuple[int, str]] = [
    (3, "Μετρητά"),
    (1, "Επαγγ. λογ. πληρωμών ημεδαπής"),
    (5, "Επί πιστώσει"),
    (4, "Επιταγή"),
    (7, "POS / e-POS"),
]

VAT_RATES = ["24", "13", "6", "0"]

#: Editor columns.
_COLS = ["Περιγραφή / Κωδικός", "Ποσότητα", "Τιμή μον.", "ΦΠΑ %", "Έκπτ. %", "Καθαρή", "Σύνολο"]
_DESC, _QTY, _PRICE, _RATE, _DISC, _NET, _TOTAL = range(7)


def line_amounts(qty: float, price: float, rate: float, disc_pct: float) -> tuple[float, float, float]:
    """(net, vat, total) for one line — mirrors the bridge's buildInvoiceLine."""
    if qty <= 0:
        qty = 1.0
    gross = round(price * qty, 2)
    disc = round(gross * disc_pct / 100.0, 2) if disc_pct > 0 else 0.0
    if disc > gross:
        disc = gross
    net = round(gross - disc, 2)
    vat = round(net * rate / 100.0, 2)
    return net, vat, round(net + vat, 2)


class IssuePage(EtimPage):
    """Compose and issue an invoice natively."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._temp_id = ""
        self._guard = False
        box = QVBoxLayout(self)

        top = QHBoxLayout()
        back = QPushButton("←")
        back.setToolTip("Πίσω")
        back.setFixedWidth(36)
        back.clicked.connect(self.go_back.emit)
        top.addWidget(back)
        title = QLabel("Έκδοση παραστατικού")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        new = QPushButton("Νέο")
        new.setToolTip("Καθαρισμός φόρμας")
        new.clicked.connect(self.reset)
        top.addWidget(new)
        box.addLayout(top)

        # --- header: type / series / payment -------------------------------
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

        # --- customer ------------------------------------------------------
        cust = QFormLayout()
        afm_row = QHBoxLayout()
        self._afm = QLineEdit()
        self._afm.setPlaceholderText("ΑΦΜ (κενό = ιδιώτης/λιανική)")
        afm_row.addWidget(self._afm)
        fetch = QPushButton("Άντληση")
        fetch.setToolTip("Συμπλήρωση στοιχείων από τους πελάτες")
        fetch.clicked.connect(self._fetch_customer)
        afm_row.addWidget(fetch)
        cust.addRow("ΑΦΜ", afm_row)
        self._name = QLineEdit()
        self._address = QLineEdit()
        self._city = QLineEdit()
        self._zip = QLineEdit()
        cust.addRow("Επωνυμία", self._name)
        cust.addRow("Διεύθυνση", self._address)
        cust.addRow("Πόλη", self._city)
        cust.addRow("Τ.Κ.", self._zip)
        box.addLayout(cust)

        # --- lines ---------------------------------------------------------
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(_DESC, 260)
        self._table.itemChanged.connect(self._on_item_changed)
        box.addWidget(self._table, 1)

        line_btns = QHBoxLayout()
        add = QPushButton("+ Γραμμή")
        add.clicked.connect(lambda: self.add_line())
        rem = QPushButton("− Γραμμή")
        rem.clicked.connect(self._remove_line)
        line_btns.addWidget(add)
        line_btns.addWidget(rem)
        line_btns.addStretch(1)
        self._totals = QLabel("Καθαρή: 0,00 €   ΦΠΑ: 0,00 €   Σύνολο: 0,00 €")
        self._totals.setStyleSheet("font-weight:600;")
        line_btns.addWidget(self._totals)
        box.addLayout(line_btns)

        # --- notes + actions ----------------------------------------------
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Σημειώσεις (προαιρετικό)")
        box.addWidget(self._notes)

        actions = QHBoxLayout()
        self._status = QLabel("")
        self._status.setStyleSheet("color:#93a4bd;")
        actions.addWidget(self._status)
        actions.addStretch(1)
        draft = QPushButton("Αποθήκευση πρόχειρου")
        draft.clicked.connect(self._save_draft)
        preview = QPushButton("Προεπισκόπηση")
        preview.clicked.connect(self._preview)
        issue = QPushButton("Έκδοση")
        issue.setObjectName("danger")
        issue.clicked.connect(self._issue)
        for b in (draft, preview, issue):
            actions.addWidget(b)
        box.addLayout(actions)

        self.add_line()

    # --- line editing ------------------------------------------------------
    def add_line(self, desc: str = "", qty: str = "1", price: str = "0", rate: str = "24", disc: str = "0") -> None:
        self._guard = True
        r = self._table.rowCount()
        self._table.insertRow(r)
        for col, val in ((_DESC, desc), (_QTY, qty), (_PRICE, price), (_RATE, rate), (_DISC, disc)):
            self._table.setItem(r, col, QTableWidgetItem(val))
        for col in (_NET, _TOTAL):
            item = QTableWidgetItem("0,00")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, col, item)
        self._guard = False
        self._recompute()

    def _remove_line(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            r = self._table.rowCount() - 1
        if r >= 0:
            self._table.removeRow(r)
        self._recompute()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._guard or item.column() in (_NET, _TOTAL):
            return
        self._recompute()

    def _recompute(self) -> None:
        self._guard = True
        net_sum = vat_sum = total_sum = 0.0
        for r in range(self._table.rowCount()):
            qty = parse_money(self._cell(r, _QTY))
            price = parse_money(self._cell(r, _PRICE))
            rate = parse_money(self._cell(r, _RATE))
            disc = parse_money(self._cell(r, _DISC))
            net, vat, total = line_amounts(qty, price, rate, disc)
            self._table.item(r, _NET).setText(fmt_money(net))
            self._table.item(r, _TOTAL).setText(fmt_money(total))
            net_sum += net
            vat_sum += vat
            total_sum += total
        self._totals.setText(
            f"Καθαρή: {fmt_money(net_sum)} €   ΦΠΑ: {fmt_money(vat_sum)} €   "
            f"Σύνολο: {fmt_money(total_sum)} €"
        )
        self._guard = False

    def _cell(self, r: int, c: int) -> str:
        item = self._table.item(r, c)
        return item.text() if item else ""

    # --- collect + actions -------------------------------------------------
    def collect_lines(self) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for r in range(self._table.rowCount()):
            code = self._cell(r, _DESC).strip()
            qty = parse_money(self._cell(r, _QTY))
            price = parse_money(self._cell(r, _PRICE))
            rate = parse_money(self._cell(r, _RATE))
            disc = parse_money(self._cell(r, _DISC))
            if not code and price == 0:
                continue
            line: dict[str, Any] = {
                "code": code or "Είδος",
                "qty": qty or 1,
                "price": price,
                # The bridge expects the rate as a FRACTION (0.24), not a percent;
                # send it explicitly so the issued VAT matches what the UI shows.
                "rate": round(rate / 100.0, 4),
            }
            if disc > 0:
                line["disc"] = disc
            lines.append(line)
        return lines

    def _customer_fields(self) -> dict[str, Any]:
        return {
            "afm": self._afm.text().strip(),
            "name": self._name.text().strip(),
            "address": self._address.text().strip(),
            "city": self._city.text().strip(),
            "zip_code": self._zip.text().strip(),
        }

    def _issue_kwargs(self) -> dict[str, Any] | None:
        lines = self.collect_lines()
        if not lines:
            self._status.setText("Πρόσθεσε τουλάχιστον μία γραμμή.")
            return None
        return {
            "lines": lines,
            "invoice_type": self._type.currentData(),
            "series": self._series.text().strip() or "A",
            "payment": int(self._payment.currentData()),
            "notes": self._notes.text().strip(),
            "temp_id": self._temp_id,
            **self._customer_fields(),
        }

    def _fetch_customer(self) -> None:
        client = self.client()
        afm = self._afm.text().strip()
        if client is None or not afm:
            return
        self._status.setText("Άντληση στοιχείων…")

        def fill(data: dict) -> None:
            rows = data.get("customers") or data.get("rows") or []
            if not rows:
                self._status.setText("Δεν βρέθηκε πελάτης με αυτό το ΑΦΜ.")
                return
            row = rows[0]
            self._name.setText(str(row.get("name", "")))
            self._address.setText(str(row.get("address", "")))
            self._city.setText(str(row.get("city", "")))
            self._status.setText("Συμπληρώθηκαν τα στοιχεία πελάτη.")

        self._run(lambda: client.customers(vat=afm), fill, lambda m: self._status.setText(f"Σφάλμα: {m}"))

    def _save_draft(self) -> None:
        client = self.client()
        kwargs = self._issue_kwargs()
        if client is None or kwargs is None:
            return
        self._status.setText("Αποθήκευση πρόχειρου…")
        self._run(lambda: client.issue_invoice(**kwargs), self._after_draft, self._failed)

    def _after_draft(self, result: dict) -> None:
        if result.get("success"):
            self._temp_id = str(result.get("temp_id", "") or self._temp_id)
            self._status.setText(
                f"Πρόχειρο αποθηκεύτηκε (temp_id={self._temp_id}). "
                f"Σύνολο {fmt_money(parse_money(result.get('amount_total')))} €."
            )
        else:
            self._failed(result.get("error", "Αποτυχία αποθήκευσης."))

    def _preview(self) -> None:
        client = self.client()
        kwargs = self._issue_kwargs()
        if client is None or kwargs is None:
            return
        self._status.setText("Δημιουργία προεπισκόπησης…")
        self._run(
            lambda: client.issue_invoice(preview=True, **kwargs),
            self._after_preview,
            self._failed,
        )

    def _after_preview(self, result: dict) -> None:
        self._temp_id = str(result.get("temp_id", "") or self._temp_id)
        b64 = result.get("pdf_b64")
        if b64:
            path = Path(tempfile.gettempdir()) / f"etim_preview_{self._temp_id or 'draft'}.pdf"
            path.write_bytes(base64.b64decode(b64))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self._status.setText("Άνοιξε η προεπισκόπηση (PDF).")
        else:
            self._status.setText(result.get("preview_error", "Η προεπισκόπηση απέτυχε."))

    def _issue(self) -> None:
        client = self.client()
        kwargs = self._issue_kwargs()
        if client is None or kwargs is None:
            return
        confirm = QMessageBox.question(
            self,
            "Οριστική έκδοση",
            "Το παραστατικό θα υποβληθεί στην ΑΑΔΕ και θα λάβει ΜΑΡΚ. Συνέχεια;",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._status.setText("Έκδοση…")
        self._run(lambda: client.issue_invoice(live=True, **kwargs), self._after_issue, self._failed)

    def _after_issue(self, result: dict) -> None:
        if result.get("success") and result.get("mark"):
            mark = result.get("mark")
            QMessageBox.information(
                self, "Επιτυχής έκδοση",
                f"Το παραστατικό εκδόθηκε.\nΜΑΡΚ: {mark}\n"
                f"Σύνολο: {fmt_money(parse_money(result.get('amount_total')))} €",
            )
            self.reset()
        else:
            self._failed(result.get("error", "Η έκδοση απέτυχε."))

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    def reset(self) -> None:
        self._temp_id = ""
        self._afm.clear()
        self._name.clear()
        self._address.clear()
        self._city.clear()
        self._zip.clear()
        self._notes.clear()
        self._table.setRowCount(0)
        self.add_line()
        self._status.setText("")
