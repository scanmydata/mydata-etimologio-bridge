"""Native Καρτέλα πελάτη: μία ενιαία κίνηση χρέωσης/πίστωσης με τρέχον υπόλοιπο.

Η καρτέλα χτίζεται από το ``ledger`` του backend, που ενώνει τα εκδοθέντα
παραστατικά με τις τοπικές πληρωμές σε **μία** χρονολογική σειρά. Δύο ξεχωριστές
καρτέλες («Παραστατικά» / «Πληρωμές») δεν είναι καρτέλα: το υπόλοιπο μετά από
κάθε κίνηση — αυτό που ζητά ο λογιστής — δεν φαίνεται πουθενά.

Δύο παγίδες που έκαναν τις καρτέλες να βγαίνουν **κενές** και λύθηκαν:

* Το προεπιλεγμένο διάστημα ήταν «φέτος». Σε πραγματικό λογαριασμό, 11 στους 12
  πελάτες είχαν παραστατικά μόνο παλαιότερα — δηλαδή άδεια καρτέλα. Η προεπιλογή
  είναι πλέον **όλη η ιστορία**.
* Το φίλτρο ΑΦΜ αγοραστή της ΑΑΔΕ αγνοείται σιωπηλά για τις ΑΠΥ· το φιλτράρισμα
  γίνεται τώρα στο backend (βλ. ``buildLedger``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from ...gui.printing import print_pdfs
from ..bulkpdf import export_zip, fetch_pdfs
from ..codes import PAYMENT_LABELS
from ..ledgerpdf import build_ledger_pdf, entries_from
from . import ui
from .base import EtimPage, fmt_date, fmt_money, parse_money
from .customers import _cust_value

#: Οι στήλες της ενιαίας κίνησης.
_COLS: list[str] = ["Ημ/νία", "Κίνηση", "Χρέωση", "Πίστωση", "Υπόλοιπο"]
_DATE, _LABEL, _DEBIT, _CREDIT, _BALANCE = range(5)

#: Payment method codes → labels. Kept as an alias so the pages that already
#: import ``_METHODS`` from here keep working; the table itself lives in
#: ``codes.py`` so Έκδοση, Μαζική και Πληρωμές cannot drift apart again.
_METHODS = PAYMENT_LABELS

#: Προκαθορισμένα διαστήματα. Το «Όλα» είναι πρώτο **και** προεπιλογή: μια
#: καρτέλα χωρίς ιστορικό δεν είναι καρτέλα.
_PERIODS: list[tuple[str, int]] = [
    ("Όλα", 0),
    ("Φέτος", 1),
    ("Πέρσι", 2),
    ("Τελευταίοι 12 μήνες", 3),
]

#: Από πότε ψάχνουμε όταν ζητηθεί «Όλα». Το e-timologio δεν έχει παραστατικά
#: πριν από τη λειτουργία του myDATA.
_EPOCH = QDate(2019, 1, 1)


class CustomerCard(EtimPage):
    """Ενιαία καρτέλα ενός πελάτη: κίνηση, υπόλοιπο, πληρωμές, εκτυπώσεις."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._customer: dict[str, Any] = {}
        self._entries: list[dict[str, Any]] = []
        self._customers: list[dict[str, Any]] = []
        self._totals = {"invoiced": 0.0, "paid": 0.0, "balance": 0.0, "opening": 0.0}

        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        top = QHBoxLayout()
        self._title = QLabel("Καρτέλα πελάτη")
        self._title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(self._title)
        top.addStretch(1)
        # «Εκτύπωση καρτέλας» τυπώνει την ΚΑΡΤΕΛΑ. Έτυπωνε τα PDF των
        # παραστατικών, που είναι εντελώς άλλο πράγμα — και υπάρχει ήδη δικό του
        # κουμπί δίπλα.
        top.addWidget(ui.button("Εκτύπωση καρτέλας", self.print_ledger, kind="primary",
                                icon_name="printer",
                                tip="Προεπισκόπηση & εκτύπωση της κίνησης (χρεώσεις/πιστώσεις)"))
        top.addWidget(ui.button("PDF καρτέλας", self.export_ledger_pdf, icon_name="pdf",
                                tip="Αποθήκευση της κίνησης σε PDF"))
        top.addWidget(ui.button("Εκτύπωση παραστατικών", self.print_all, icon_name="pdf",
                                tip="Τα PDF όλων των παραστατικών του πελάτη από την ΑΑΔΕ"))
        top.addWidget(ui.button("Εξαγωγή ZIP", self.export_all, icon_name="folder",
                                tip="Πακετάρει τα PDF των παραστατικών σε ένα ZIP"))
        top.addWidget(ui.button("Ανανέωση", self.refresh, icon_name="refresh"))
        box.addLayout(top)

        period = QHBoxLayout()
        self._period = QComboBox()
        for label, code in _PERIODS:
            self._period.addItem(label, code)
        self._period.currentIndexChanged.connect(self._period_changed)
        period.addWidget(QLabel("Διάστημα:"))
        period.addWidget(self._period)
        year = date.today().year
        self._from = QDateEdit(QDate(year, 1, 1))
        self._to = QDateEdit(QDate.currentDate())
        for field in (self._from, self._to):
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd/MM/yyyy")
        period.addWidget(QLabel("Από:"))
        period.addWidget(self._from)
        period.addWidget(QLabel("Έως:"))
        period.addWidget(self._to)
        period.addWidget(ui.button("Φόρτωση", self.refresh))
        period.addWidget(ui.button("+ Πληρωμή", self._new_payment, icon_name="income",
                                   tip="Καταχώρηση είσπραξης για αυτόν τον πελάτη"))
        period.addStretch(1)
        box.addLayout(period)
        self._period_changed()          # εφαρμόζει το «Όλα»

        self._summary = QLabel("")
        self._summary.setObjectName("muted")
        box.addWidget(self._summary)

        self._table = ui.table(_COLS, stretch=_LABEL)
        self._table.horizontalHeader().setSectionResizeMode(
            _LABEL, QHeaderView.ResizeMode.Stretch
        )
        self._table.doubleClicked.connect(lambda *_: self._open_entry())
        self._table.setToolTip(
            "Διπλό κλικ: παραστατικό → άνοιγμα PDF · πληρωμή → διαγραφή"
        )
        box.addWidget(self._table, 1)
        self._filter = ui.make_sortable(
            self._table, "card/entries", filter_columns=[_DATE, _LABEL]
        )

        self._status = QLabel("")
        self._status.setObjectName("muted")
        box.addWidget(self._status)

    # --- διάστημα -----------------------------------------------------------
    def _period_changed(self) -> None:
        code = int(self._period.currentData() or 0)
        today = QDate.currentDate()
        if code == 0:                                   # Όλα
            self._from.setDate(_EPOCH)
            self._to.setDate(today.addYears(1))
        elif code == 1:                                 # Φέτος
            self._from.setDate(QDate(today.year(), 1, 1))
            self._to.setDate(today)
        elif code == 2:                                 # Πέρσι
            self._from.setDate(QDate(today.year() - 1, 1, 1))
            self._to.setDate(QDate(today.year() - 1, 12, 31))
        else:                                           # Τελευταίοι 12 μήνες
            self._from.setDate(today.addMonths(-12))
            self._to.setDate(today)

    # --- data --------------------------------------------------------------
    def set_customer(self, customer: dict[str, Any]) -> None:
        self._customer = dict(customer or {})
        name = _cust_value(self._customer, "name")
        vat = _cust_value(self._customer, "vat")
        self._title.setText(f"Καρτέλα: {name}" if name else "Καρτέλα πελάτη")
        self._summary.setText(f"ΑΦΜ: {vat}" if vat else "")
        self.refresh()

    def set_customers(self, rows: list[dict[str, Any]]) -> None:
        """Το πελατολόγιο, για τον επιλογέα του διαλόγου πληρωμής."""
        self._customers = list(rows or [])

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        vat = _cust_value(self._customer, "vat")
        if not vat:
            self._status.setText(
                "Ο πελάτης δεν έχει ΑΦΜ (λιανική) — η ΑΑΔΕ δεν δίνει κίνηση χωρίς ΑΦΜ."
            )
            self._table.setRowCount(0)
            return
        self._status.setText("Φόρτωση κίνησης…")
        date_from = self._from.date().toString("dd/MM/yyyy")
        date_to = self._to.date().toString("dd/MM/yyyy")
        # Μία κλήση αντί για δύο: το backend ενώνει παραστατικά και πληρωμές και
        # υπολογίζει το τρέχον υπόλοιπο με σωστή σειρά ακόμη και όταν πληρωμή και
        # τιμολόγιο πέφτουν την ίδια ημέρα.
        self._run(
            lambda: client.ledger(vat, date_from=date_from, date_to=date_to),
            self._fill,
            self._failed,
        )

    def _fill(self, data: dict[str, Any]) -> None:
        self._entries = list(data.get("entries", []))
        self._totals = {
            "invoiced": parse_money(data.get("total_invoiced")),
            "paid": parse_money(data.get("total_paid")),
            "balance": parse_money(data.get("balance")),
            "opening": parse_money(data.get("opening_balance")),
        }
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._entries))
        for r, entry in enumerate(self._entries):
            debit = parse_money(entry.get("debit"))
            credit = parse_money(entry.get("credit"))
            cells = (
                ui.date_cell(str(entry.get("date", ""))),
                ui.cell(self._label(entry)),
                ui.money_cell(fmt_money(debit) if debit else ""),
                ui.money_cell(fmt_money(credit) if credit else ""),
                ui.money_cell(fmt_money(parse_money(entry.get("balance")))),
            )
            for c, item in enumerate(cells):
                if c in (_DEBIT, _CREDIT, _BALANCE):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)
        self._table.sortItems(_DATE, Qt.SortOrder.AscendingOrder)
        self._done()

    def _label(self, entry: dict[str, Any]) -> str:
        if str(entry.get("kind")) == "payment":
            parts = [
                "Πληρωμή",
                _METHODS.get(str(entry.get("method") or ""), ""),
                str(entry.get("notes") or ""),
            ]
        else:
            series, aa = entry.get("series"), entry.get("aa")
            parts = [
                str(entry.get("type") or "Παραστατικό"),
                f"Σειρά {series} Αρ. {aa}" if series else "",
                f"ΜΑΡΚ {entry.get('mark')}" if entry.get("mark") else "",
            ]
        return " · ".join(p for p in parts if p)

    def _done(self) -> None:
        opening = self._totals["opening"]
        self._status.setText(f"{len(self._entries)} κινήσεις")
        self._summary.setText(
            f"ΑΦΜ: {_cust_value(self._customer, 'vat')}    ·    "
            + (f"Αρχικό υπόλοιπο: {fmt_money(opening)} €    ·    " if opening else "")
            + f"Χρεώσεις: {fmt_money(self._totals['invoiced'])} €    ·    "
            f"Πιστώσεις: {fmt_money(self._totals['paid'])} €    ·    "
            f"Υπόλοιπο: {fmt_money(self._totals['balance'])} €"
        )

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    # --- γραμμές ------------------------------------------------------------
    def entry_at(self, table_row: int) -> dict[str, Any] | None:
        """Η κίνηση μιας ΟΠΤΙΚΗΣ γραμμής — ο πίνακας ταξινομείται."""
        item = self._table.item(table_row, _DATE)
        if item is None:
            return None
        # Το ταίριασμα γίνεται με ημερομηνία+υπόλοιπο, που είναι μοναδικά ανά
        # γραμμή στην κίνηση· ο δείκτης θέσης δεν επιβιώνει την ταξινόμηση.
        key = (item.text(), self._table.item(table_row, _BALANCE).text())
        for entry in self._entries:
            if (fmt_date(entry.get("date")), fmt_money(parse_money(entry.get("balance")))) == key:
                return entry
        return None

    def invoice_rows(self) -> list[dict[str, Any]]:
        """Οι κινήσεις-παραστατικά, στη μορφή που θέλει η λήψη PDF."""
        rows = []
        for entry in self._entries:
            if str(entry.get("kind")) == "payment" or not entry.get("mark"):
                continue
            rows.append({
                "mark": entry.get("mark", ""),
                "issue_date": fmt_date(entry.get("date")),
                "series": entry.get("series", ""),
                "aa": entry.get("aa", ""),
                "type": entry.get("type", ""),
                "total": entry.get("debit", 0),
            })
        return rows

    def _open_entry(self) -> None:
        entry = self.entry_at(self._table.currentRow())
        if entry is None:
            return
        if str(entry.get("kind")) == "payment":
            self._delete_payment(entry)
            return
        mark = str(entry.get("mark") or "")
        if not mark:
            return
        client = self.client()
        if client is None:
            return
        row = next((r for r in self.invoice_rows() if r["mark"] == mark), None)
        self._status.setText("Λήψη PDF…")
        self._run(
            lambda: fetch_pdfs(client, [row]),
            lambda result: self._after_fetch(result, mode="open"),
            self._failed,
        )

    # --- payments ----------------------------------------------------------
    def _new_payment(self) -> None:
        client = self.client()
        if client is None:
            return
        vat = _cust_value(self._customer, "vat")
        if not vat:
            return
        from .payments import NewPaymentDialog

        dialog = NewPaymentDialog(self)
        # Ο επιλογέας έμενε άδειος: ο διάλογος άνοιγε χωρίς πελατολόγιο, οπότε
        # δεν μπορούσες να αλλάξεις πελάτη μέσα από την καρτέλα.
        dialog.set_customers(self._customers)
        dialog.vat.setText(vat)
        dialog.name.setText(_cust_value(self._customer, "name"))
        dialog.customer.setText(_cust_value(self._customer, "name"))
        # Προτείνουμε το ανοιχτό υπόλοιπο — ο συνηθέστερος σκοπός της είσπραξης.
        balance = self._totals["balance"]
        if balance > 0:
            dialog.amount.setText(f"{balance:.2f}")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        self._status.setText("Καταχώρηση πληρωμής…")
        self._run(lambda: client.add_payment(**fields), lambda _r: self.refresh(), self._failed)

    def _delete_payment(self, entry: dict[str, Any]) -> None:
        client = self.client()
        payment_id = entry.get("payment_id") or entry.get("id")
        if client is None or not payment_id:
            return
        if QMessageBox.question(
            self, "Διαγραφή πληρωμής",
            f"Διαγραφή της πληρωμής {fmt_money(parse_money(entry.get('credit')))} € "
            f"({fmt_date(entry.get('date'))});",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: client.delete_payment(payment_id), lambda _r: self.refresh(), self._failed)

    # --- ledger PDF --------------------------------------------------------
    def ledger_entries(self) -> list[dict[str, Any]]:
        """Οι κινήσεις στη μορφή που ζωγραφίζει το PDF."""
        return [
            {
                "date": fmt_date(entry.get("date")),
                "label": self._label(entry),
                "debit": parse_money(entry.get("debit")),
                "credit": parse_money(entry.get("credit")),
            }
            for entry in self._entries
        ]

    def _ledger_pdf(self, path: Path) -> Path:
        return build_ledger_pdf(
            path,
            customer={
                "name": _cust_value(self._customer, "name") or "ΠΕΛΑΤΗΣ",
                "vat": _cust_value(self._customer, "vat"),
                "address": _cust_value(self._customer, "address"),
                "city": _cust_value(self._customer, "city"),
            },
            entries=self.ledger_entries(),
            period=(
                self._from.date().toString("dd/MM/yyyy"),
                self._to.date().toString("dd/MM/yyyy"),
            ),
        )

    def _default_name(self, suffix: str) -> Path:
        name = _cust_value(self._customer, "name") or "ΠΕΛΑΤΗΣ"
        vat = _cust_value(self._customer, "vat")
        safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()[:40]
        return Path.home() / f"ΚΑΡΤΕΛΑ {vat} {safe}{suffix}"

    def export_ledger_pdf(self) -> None:
        """Η καρτέλα ως PDF — η κίνηση, όχι τα PDF των παραστατικών."""
        if not self._entries:
            QMessageBox.information(self, "Καρτέλα", "Η καρτέλα δεν έχει κινήσεις.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Αποθήκευση καρτέλας", str(self._default_name(".pdf")), "PDF (*.pdf)"
        )
        if not path:
            return
        self._ledger_pdf(Path(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        self._status.setText(f"Η καρτέλα αποθηκεύτηκε: {Path(path).name}")

    def print_ledger(self) -> None:
        """Προεπισκόπηση εκτύπωσης της κίνησης, με τον διάλογο του Downloader."""
        if not self._entries:
            QMessageBox.information(self, "Καρτέλα", "Η καρτέλα δεν έχει κινήσεις.")
            return
        from ..bulkpdf import cache_dir

        vat = _cust_value(self._customer, "vat") or "καρτέλα"
        path = self._ledger_pdf(cache_dir() / f"ΚΑΡΤΕΛΑ {vat}.pdf")
        print_pdfs([path], self)

    # --- bulk print / ZIP for this customer's documents --------------------
    def _fetch_card_pdfs(self, mode: str) -> None:
        client = self.client()
        if client is None:
            return
        rows = self.invoice_rows()
        if not rows:
            QMessageBox.information(
                self, "Καρτέλα", "Η καρτέλα δεν έχει παραστατικά με ΜΑΡΚ για εκτύπωση."
            )
            return
        self._status.setText(f"Λήψη {len(rows)} PDF από την ΑΑΔΕ…")
        self._run(
            lambda: fetch_pdfs(client, rows),
            lambda result: self._after_fetch(result, mode=mode),
            self._failed,
        )

    def print_all(self) -> None:
        self._fetch_card_pdfs("print")

    def export_all(self) -> None:
        self._fetch_card_pdfs("zip")

    def _after_fetch(self, result, *, mode: str) -> None:
        paths, errors = result
        note = f"\n\n{len(errors)} δεν κατέβηκαν." if errors else ""
        if not paths:
            self._status.setText("Κανένα PDF δεν κατέβηκε.")
            return
        self._status.setText(f"{len(paths)} PDF έτοιμα.")
        if mode == "open":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[0])))
            return
        if mode == "print":
            print_pdfs(paths, self)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Εξαγωγή {len(paths)} PDF σε ZIP",
            str(self._default_name(".zip")), "ZIP (*.zip)",
        )
        if not path:
            return
        added = export_zip(paths, Path(path))
        QMessageBox.information(
            self, "Η εξαγωγή ολοκληρώθηκε", f"{added} αρχεία -> {Path(path).name}{note}"
        )


__all__ = ["CustomerCard", "entries_from"]
