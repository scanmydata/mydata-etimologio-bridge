"""Native Ακύρωση / Πιστωτικό: issue a correlated credit note by original MARK.

In myDATA you never delete an issued document — you cancel it with a correlated
credit note that references the original MARK. Same three modes as Έκδοση
(πρόχειρο / προεπισκόπηση / έκδοση).
"""

from __future__ import annotations

import base64
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import ui
from .base import ROW_ROLE, EtimPage, fmt_money, parse_money
from .pickers import customer_picker

#: Στήλες του πίνακα παραστατικών προς πίστωση.
_INV_COLS: list[tuple[str, str]] = [
    ("Ημ/νία", "issue_date"),
    ("Τύπος", "type"),
    ("Σειρά/ΑΑ", "_series_aa"),
    ("Πελάτης", "_buyer"),
    ("Καθαρή", "net_value"),
    ("Σύνολο", "total"),
    ("ΜΑΡΚ", "mark"),
]


class CreditNotePage(EtimPage):
    """Cancel an invoice via a correlated credit note."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._temp_id = ""
        self._buyer_vat = ""
        self._invoices: list[dict[str, Any]] = []
        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Ακύρωση / Πιστωτικό")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        box.addLayout(top)
        box.addWidget(ui.page_hint(
            "Ακύρωση ή μερική πίστωση εκδοθέντος παραστατικού. Διάλεξέ το από τη λίστα — το ΜΑΡΚ δεν πληκτρολογείται."))

        note = QLabel(
            "Διάλεξε το παραστατικό από τη λίστα. Πλήρης αξία = ακύρωση, "
            "μικρότερη αξία = μερική πίστωση. Ο τύπος (5.1 ή 11.4) επιλέγεται αυτόματα."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        box.addWidget(note)

        # --- αναζήτηση παραστατικών ----------------------------------------
        search = QHBoxLayout()
        self._customer = customer_picker(placeholder="Πελάτης (προαιρετικό)…")
        self._customer.picked.connect(self._picked_customer)
        search.addWidget(QLabel("Πελάτης:"))
        search.addWidget(self._customer, 2)
        year = date.today().year
        self._from = QDateEdit(QDate(year, 1, 1))
        self._to = QDateEdit(QDate.currentDate())
        for field in (self._from, self._to):
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd/MM/yyyy")
        search.addWidget(QLabel("Από:"))
        search.addWidget(self._from)
        search.addWidget(QLabel("Έως:"))
        search.addWidget(self._to)
        find = QPushButton("Αναζήτηση")
        find.clicked.connect(self.load_invoices)
        search.addWidget(find)
        box.addLayout(search)

        self._table = QTableWidget(0, len(_INV_COLS))
        self._table.setHorizontalHeaderLabels([h for h, _ in _INV_COLS])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.doubleClicked.connect(lambda *_: self._pick_selected())
        box.addWidget(self._table, 1)
        # Ταξινόμηση και φίλτρα, με τα νεότερα πρώτα: το παραστατικό που θέλει
        # κανείς να ακυρώσει είναι σχεδόν πάντα πρόσφατο.
        self._filter = ui.make_sortable(
            self._table, "credit/invoices", default_column=0,
            filter_columns=list(range(len(_INV_COLS))),
        )

        pick_row = QHBoxLayout()
        pick_row.addStretch(1)
        pick = QPushButton("Επιλογή για πίστωση →")
        pick.setObjectName("primary")
        pick.clicked.connect(self._pick_selected)
        pick_row.addWidget(pick)
        box.addLayout(pick_row)

        form = QFormLayout()
        # Το ΜΑΡΚ μένει ορατό για διαφάνεια αλλά δεν πληκτρολογείται: ήταν
        # 15ψήφιος αριθμός στο χέρι, για μη αναστρέψιμη ενέργεια.
        self._mark = QLineEdit()
        self._mark.setReadOnly(True)
        self._mark.setPlaceholderText("επίλεξε παραστατικό από τη λίστα")
        self._reason = QLineEdit()
        self._amount = QLineEdit()
        self._amount.setPlaceholderText("κενό = πλήρης ακύρωση")
        form.addRow("ΜΑΡΚ *", self._mark)
        form.addRow("Αιτιολογία", self._reason)
        form.addRow("Καθαρή αξία πιστωτικού", self._amount)
        box.addLayout(form)

        actions = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("muted")
        actions.addWidget(self._status)
        actions.addStretch(1)
        draft = QPushButton("Αποθήκευση πρόχειρου")
        draft.clicked.connect(self._draft)
        preview = QPushButton("Προεπισκόπηση")
        preview.clicked.connect(self._preview)
        issue = QPushButton("Έκδοση πιστωτικού")
        issue.setObjectName("danger")
        issue.clicked.connect(self._issue)
        for b in (draft, preview, issue):
            actions.addWidget(b)
        box.addLayout(actions)

    # --- φόρτωση & επιλογή παραστατικού ------------------------------------
    def refresh(self) -> None:
        """Φέρνει το πελατολόγιο για τον επιλογέα (τα παραστατικά με το κουμπί).

        Η αναζήτηση παραστατικών δεν τρέχει αυτόματα: είναι κλήση προς την ΑΑΔΕ
        και ο χρήστης συνήθως θέλει πρώτα να στενέψει το διάστημα.
        """
        client = self.client()
        if client is None or self._customer.rows():
            return
        self._run(
            client.customers,
            lambda data: self._customer.set_rows(
                data.get("customers") or data.get("rows") or []
            ),
            lambda _m: None,
        )

    def _picked_customer(self, row: dict[str, Any]) -> None:
        self._buyer_vat = str(row.get("vat") or row.get("afm") or "")
        self.load_invoices()

    def load_invoices(self) -> None:
        client = self.client()
        if client is None:
            return
        self._status.setText("Αναζήτηση παραστατικών…")
        vat = self._buyer_vat
        date_from = self._from.date().toString("dd/MM/yyyy")
        date_to = self._to.date().toString("dd/MM/yyyy")
        self._run(
            lambda: client.search_invoices(
                buyer_vat=vat, date_from=date_from, date_to=date_to
            ),
            self._fill_invoices,
            self._failed,
        )

    def _fill_invoices(self, data: dict[str, Any]) -> None:
        # Χωρίς ΜΑΡΚ δεν υπάρχει τι να πιστωθεί — τα πρόχειρα δεν ανήκουν εδώ.
        rows = [r for r in data.get("invoices", []) if r.get("mark")]
        self._invoices = rows
        # Η ταξινόμηση κλείνει όσο γεμίζει ο πίνακας, και κάθε γραμμή κουβαλά τη
        # θέση της στα δεδομένα: αλλιώς μετά από ταξινόμηση θα πιστωνόταν άλλο
        # παραστατικό από αυτό που βλέπει ο χρήστης.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = {
                **row,
                "_series_aa": f"{row.get('series', '')} / {row.get('aa', '')}",
                "_buyer": f"{row.get('buyer_name', '')} ({row.get('buyer_vat', '')})".strip(),
            }
            for c, (header, key) in enumerate(_INV_COLS):
                text = str(values.get(key, ""))
                if header == "Ημ/νία":
                    item = ui.date_cell(text)
                elif header in ("Καθαρή", "Σύνολο"):
                    item = ui.money_cell(text)
                else:
                    item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(ROW_ROLE, r)
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)
        self._status.setText(
            f"{len(rows)} παραστατικά." if rows else "Δεν βρέθηκαν παραστατικά στο διάστημα."
        )

    def _pick_selected(self) -> None:
        item = self._table.item(self._table.currentRow(), 0)
        index = item.data(ROW_ROLE) if item is not None else None
        if index is None:
            index = self._table.currentRow()
        index = int(index)
        if not (0 <= index < len(self._invoices)):
            self._status.setText("Διάλεξε πρώτα ένα παραστατικό.")
            return
        self.pick_invoice(self._invoices[index])

    def pick_invoice(self, row: dict[str, Any]) -> None:
        """Φορτώνει ένα παραστατικό στη φόρμα πίστωσης, με προσυμπληρωμένο ποσό."""
        self._temp_id = ""
        self._mark.setText(str(row.get("mark") or ""))
        net = parse_money(row.get("net_value"))
        self._amount.setText(f"{net:.2f}" if net else "")
        self._status.setText(
            f"Επιλέχθηκε ΜΑΡΚ {row.get('mark')} · καθαρή {fmt_money(net)} €. "
            "Μείωσε το ποσό για μερική πίστωση."
        )

    def _kwargs(self) -> dict | None:
        mark = self._mark.text().strip()
        if not mark:
            self._status.setText("Διάλεξε παραστατικό από τη λίστα.")
            return None
        return {
            "cancel_mark": mark,
            "reason": self._reason.text().strip(),
            "amount": parse_money(self._amount.text()),
            "temp_id": self._temp_id,
        }

    def _draft(self) -> None:
        client = self.client()
        kwargs = self._kwargs()
        if client is None or kwargs is None:
            return
        self._status.setText("Αποθήκευση πρόχειρου…")
        self._run(lambda: client.credit_note(**kwargs), self._after_draft, self._failed)

    def _after_draft(self, result: dict) -> None:
        if result.get("success"):
            self._temp_id = str(result.get("temp_id", "") or self._temp_id)
            self._status.setText(f"Πρόχειρο πιστωτικό αποθηκεύτηκε (temp_id={self._temp_id}).")
        else:
            self._failed(result.get("error", "Αποτυχία."))

    def _preview(self) -> None:
        client = self.client()
        kwargs = self._kwargs()
        if client is None or kwargs is None:
            return
        self._status.setText("Δημιουργία προεπισκόπησης…")
        self._run(
            lambda: client.credit_note(preview=True, **kwargs),
            self._after_preview,
            self._failed,
        )

    def _after_preview(self, result: dict) -> None:
        self._temp_id = str(result.get("temp_id", "") or self._temp_id)
        b64 = result.get("pdf_b64")
        if b64:
            path = Path(tempfile.gettempdir()) / f"etim_credit_{self._temp_id or 'draft'}.pdf"
            path.write_bytes(base64.b64decode(b64))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self._status.setText("Άνοιξε η προεπισκόπηση (PDF).")
        else:
            self._status.setText(result.get("preview_error", "Η προεπισκόπηση απέτυχε."))

    def _issue(self) -> None:
        client = self.client()
        kwargs = self._kwargs()
        if client is None or kwargs is None:
            return
        if QMessageBox.question(
            self, "Έκδοση πιστωτικού",
            "Θα εκδοθεί συσχετιζόμενο πιστωτικό στην ΑΑΔΕ και θα λάβει ΜΑΡΚ. Συνέχεια;",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._status.setText("Έκδοση…")
        self._run(lambda: client.credit_note(live=True, **kwargs), self._after_issue, self._failed)

    def _after_issue(self, result: dict) -> None:
        if result.get("success") and result.get("mark"):
            QMessageBox.information(
                self, "Επιτυχής έκδοση",
                f"Το πιστωτικό εκδόθηκε.\nΜΑΡΚ: {result.get('mark')}\n"
                f"Σύνολο: {fmt_money(parse_money(result.get('amount_total')))} €",
            )
            self.reset()
        else:
            self._failed(result.get("error", "Η έκδοση απέτυχε."))

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    def reset(self) -> None:
        self._temp_id = ""
        self._mark.clear()
        self._reason.clear()
        self._amount.clear()
        self._status.setText("")
        # Το ακυρωμένο παραστατικό δεν πρέπει να μείνει επιλέξιμο.
        self.load_invoices()
