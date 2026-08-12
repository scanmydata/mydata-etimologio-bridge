"""Native Έκδοση (invoice editor): customer, lines, taxes, draft/preview/issue.

The page owns no issuance logic — it collects a customer, a list of lines and a
document type, and hands them to ``EtimologioClient.issue_invoice`` in one of
three modes (πρόχειρο / προεπισκόπηση / έκδοση). Totals shown here are a live
preview; the bridge recomputes the authoritative amounts myDATA receives.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..codes import (  # noqa: F401 — re-exported for the pages that already import from here
    INVOICE_TYPES,
    PAYMENT_METHODS,
    VAT_RATES,
    series_for_type,
    type_label,
)
from .base import EtimPage, fmt_money, parse_money
from .catalog import NewProductDialog
from .customers import NewCustomerDialog
from .dialogs import (
    DEDUCTING_TYPES,
    NEW_DEDUCTION,
    TAX_TYPES,
    ScheduleDialog,
    TaxDialog,
    tax_signed_total,
)
from .pickers import customer_picker, product_picker

#: Πόσο περιμένουμε μετά το τελευταίο πλήκτρο πριν ρωτήσουμε το Taxisnet.
#: Ίδιο με το web — αρκετά ώστε να μη φύγει ερώτημα σε κάθε ψηφίο.
AFM_LOOKUP_DELAY_MS = 400

_WIZARD_KEY = "etimologio/issue_wizard_seen"


def _wizard_seen() -> bool:
    return bool(QSettings().value(_WIZARD_KEY, False, type=bool))


def _mark_wizard_seen() -> None:
    QSettings().setValue(_WIZARD_KEY, True)

#: Editor columns.
_COLS = ["Περιγραφή / Κωδικός", "Ποσότητα", "Τιμή μον.", "ΦΠΑ %", "Έκπτ. %", "Καθαρή", "Σύνολο"]
_DESC, _QTY, _PRICE, _RATE, _DISC, _NET, _TOTAL = range(7)

#: Columns of the taxes/withholdings table.
_TAX_COLS = ["Είδος", "Κατηγορία", "Ποσό (€)", "Σημ."]

#: myDATA vatCategory id → ποσοστό, για να συμπληρώνεται το ΦΠΑ από τον κατάλογο.
_VAT_PERCENT: dict[str, str] = {
    "1": "24", "2": "13", "3": "6", "4": "17", "5": "9", "6": "4", "7": "0", "8": "0",
}


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
        self._loaded = False
        self._customers: list[dict[str, Any]] = []
        self._products: list[dict[str, Any]] = []
        self._categories: list[dict[str, Any]] = []
        self._all_series: list[dict[str, Any]] = []
        #: ``None`` = δεν έχουν ζητηθεί ακόμη από την ΑΑΔΕ.
        self._tax_categories: dict[str, Any] | None = None
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
        # Η σειρά είναι λίστα και όχι ελεύθερο κείμενο: το e-timologio δέχεται
        # μόνο σειρές που έχουν ήδη δημιουργηθεί για ΤΟΝ ΣΥΓΚΕΚΡΙΜΕΝΟ τύπο, και
        # μια πληκτρολογημένη ανύπαρκτη σειρά απορριπτόταν στο τέλος — αφού ο
        # χρήστης είχε συμπληρώσει όλο το παραστατικό.
        self._series = QComboBox()
        self._series.setMinimumWidth(110)
        head.addWidget(QLabel("Σειρά:"))
        head.addWidget(self._series)
        self._payment = QComboBox()
        for code, label in PAYMENT_METHODS:
            self._payment.addItem(label, code)
        head.addWidget(QLabel("Πληρωμή:"))
        head.addWidget(self._payment, 1)
        box.addLayout(head)
        self._type.currentIndexChanged.connect(self._fill_series)

        self._series_warn = QLabel("")
        self._series_warn.setObjectName("hint")
        self._series_warn.setWordWrap(True)
        self._series_warn.hide()
        box.addWidget(self._series_warn)

        # --- οδηγός πρώτης χρήσης ------------------------------------------
        # Inline γραμμή, όχι modal: διαλέγει τον τύπο για λογαριασμό του χρήστη
        # («τιμολόγιο» ή «απόδειξη») και μετά φεύγει για πάντα.
        self._wizard = QWidget()
        wiz = QHBoxLayout(self._wizard)
        wiz.setContentsMargins(0, 0, 0, 0)
        wiz.addWidget(QLabel("Ο πελάτης είναι:"))
        pro = QPushButton("Επαγγελματίας")
        pro.clicked.connect(lambda: self._wizard_pick("pro"))
        idiot = QPushButton("Ιδιώτης")
        idiot.clicked.connect(lambda: self._wizard_pick("idiot"))
        skip = QPushButton("Παράλειψη")
        skip.setObjectName("linkButton")
        skip.clicked.connect(lambda: self._wizard_pick(""))
        for button in (pro, idiot, skip):
            wiz.addWidget(button)
        wiz.addStretch(1)
        self._wizard.setVisible(not _wizard_seen())
        box.addWidget(self._wizard)

        # --- customer ------------------------------------------------------
        cust = QFormLayout()
        # Η λίστα ανοίγει με το κλικ, όχι μόνο με πληκτρολόγηση, και η πρώτη
        # γραμμή φτιάχνει πελάτη επί τόπου — όπως στο web. Το παλιό QComboBox με
        # completer απαιτούσε να ξέρεις τι να γράψεις για να δεις οτιδήποτε.
        self._picker = customer_picker()
        self._picker.picked.connect(self._picked_customer)
        self._picker.create_requested.connect(self._new_customer)
        cust.addRow("Πελάτης", self._picker)

        afm_row = QHBoxLayout()
        self._afm = QLineEdit()
        self._afm.setPlaceholderText("ΑΦΜ (κενό = ιδιώτης/λιανική)")
        self._afm.textEdited.connect(self._afm_typed)
        afm_row.addWidget(self._afm)
        fetch = QPushButton("Άντληση")
        fetch.setToolTip("Συμπλήρωση στοιχείων από το Taxisnet")
        fetch.clicked.connect(self._fetch_customer)
        afm_row.addWidget(fetch)
        cust.addRow("ΑΦΜ", afm_row)
        # Το lookup ξεκινά μόνο του μόλις συμπληρωθούν 9 ψηφία, με μικρή παύση
        # ώστε να μη φύγει ερώτημα σε κάθε πλήκτρο.
        self._afm_timer = QTimer(self)
        self._afm_timer.setSingleShot(True)
        self._afm_timer.setInterval(AFM_LOOKUP_DELAY_MS)
        self._afm_timer.timeout.connect(self._fetch_customer)
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
        tax_btn = QPushButton("💶 Φόρος / Κράτηση")
        tax_btn.setToolTip("Παρακρατούμενοι φόροι, τέλη και κρατήσεις")
        tax_btn.clicked.connect(self._add_tax)
        line_btns.addWidget(tax_btn)
        line_btns.addStretch(1)
        box.addLayout(line_btns)

        # --- φόροι / κρατήσεις ---------------------------------------------
        # Ο client στέλνει ήδη `taxes`· αυτό που έλειπε ήταν ο τρόπος να τα
        # συμπληρώσει κανείς χωρίς να πάει στο web.
        self._taxes: list[dict[str, Any]] = []
        self._tax_table = QTableWidget(0, len(_TAX_COLS))
        self._tax_table.setHorizontalHeaderLabels(_TAX_COLS)
        self._tax_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tax_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tax_table.verticalHeader().setVisible(False)
        self._tax_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._tax_table.setMaximumHeight(120)
        self._tax_table.hide()
        self._tax_table.doubleClicked.connect(lambda *_: self._remove_tax())
        box.addWidget(self._tax_table)

        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        self._totals = QLabel("Καθαρή: 0,00 €   ΦΠΑ: 0,00 €   Σύνολο: 0,00 €")
        self._totals.setStyleSheet("font-weight:600;")
        totals_row.addWidget(self._totals)
        box.addLayout(totals_row)

        # --- notes + actions ----------------------------------------------
        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Σημειώσεις (προαιρετικό)")
        box.addWidget(self._notes)

        actions = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("muted")
        actions.addWidget(self._status)
        actions.addStretch(1)
        draft = QPushButton("Αποθήκευση πρόχειρου")
        draft.clicked.connect(self._save_draft)
        preview = QPushButton("Προεπισκόπηση")
        preview.clicked.connect(self._preview)
        schedule = QPushButton("⏰ Προγραμματισμός")
        schedule.setToolTip("Έκδοση αργότερα, αυτόματα")
        schedule.clicked.connect(self._schedule)
        issue = QPushButton("Έκδοση")
        issue.setObjectName("danger")
        issue.clicked.connect(self._issue)
        for b in (draft, preview, schedule, issue):
            actions.addWidget(b)
        box.addLayout(actions)

        self.add_line()

    # --- line editing ------------------------------------------------------
    def add_line(self, desc: str = "", qty: str = "1", price: str = "0", rate: str = "24", disc: str = "0") -> None:
        self._guard = True
        r = self._table.rowCount()
        self._table.insertRow(r)
        # Η περιγραφή είναι επιλογέας ειδών, όχι ελεύθερο κείμενο: ο κωδικός που
        # φεύγει στην ΑΑΔΕ πρέπει να υπάρχει στον κατάλογο, αλλιώς το είδος
        # καταχωρείται χωρίς χαρακτηρισμό.
        picker = product_picker()
        picker.setText(desc)
        picker.set_rows(self._products)
        picker.picked.connect(lambda row, row_index=r: self._picked_product(row_index, row))
        picker.create_requested.connect(lambda text, row_index=r: self._new_product(row_index, text))
        self._table.setCellWidget(r, _DESC, picker)
        for col, val in ((_QTY, qty), (_PRICE, price), (_RATE, rate), (_DISC, disc)):
            self._table.setItem(r, col, QTableWidgetItem(val))
        for col in (_NET, _TOTAL):
            item = QTableWidgetItem("0,00")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, col, item)
        self._guard = False
        self._recompute()

    def _line_picker(self, row: int):
        return self._table.cellWidget(row, _DESC)

    def _picked_product(self, row: int, product: dict[str, Any]) -> None:
        """Συμπληρώνει τιμή και ΦΠΑ από τον κατάλογο.

        Η τιμή μπαίνει **μόνο αν το πεδίο είναι ακόμη κενό/μηδέν** — αλλιώς μια
        χειροκίνητη τιμή θα σβηνόταν κάθε φορά που ο χρήστης ξαναδιαλέγει είδος.
        """
        price = str(product.get("unit_price") or product.get("price") or "").strip()
        if price and parse_money(self._cell(row, _PRICE)) == 0:
            item = self._table.item(row, _PRICE)
            if item is not None:
                item.setText(price)
        rate = _VAT_PERCENT.get(str(product.get("vat_category") or product.get("vat") or ""))
        if rate is not None:
            item = self._table.item(row, _RATE)
            if item is not None:
                item.setText(rate)
        self._recompute()

    def _new_product(self, row: int, typed: str) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewProductDialog(self, categories=self._categories, code=typed)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        code = fields["product_code"]

        def created(result: dict) -> None:
            if not result.get("success"):
                self._failed(result.get("error", "Αποτυχία δημιουργίας είδους."))
                return
            self._status.setText(f"Το είδος {code} δημιουργήθηκε.")
            picker = self._line_picker(row)
            if picker is not None:
                picker.setText(code)
            self._reload_products()

        self._status.setText("Δημιουργία είδους…")
        self._run(lambda: client.create_product(**fields), created, self._failed)

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
        plus, minus = tax_signed_total(self._taxes)
        text = (
            f"Καθαρή: {fmt_money(net_sum)} €   ΦΠΑ: {fmt_money(vat_sum)} €   "
            f"Σύνολο: {fmt_money(total_sum)} €"
        )
        if plus or minus:
            # Τα τέλη προστίθενται, οι παρακρατήσεις/κρατήσεις αφαιρούνται — και
            # το πληρωτέο είναι αυτό που τελικά ζητά ο επιτηδευματίας.
            text += (
                f"   Τέλη: +{fmt_money(plus)} €   Κρατήσεις: −{fmt_money(minus)} €"
                f"   Πληρωτέο: {fmt_money(total_sum + plus - minus)} €"
            )
        self._totals.setText(text)
        self._guard = False

    def _cell(self, r: int, c: int) -> str:
        if c == _DESC:
            picker = self._line_picker(r)
            return picker.text() if picker is not None else ""
        item = self._table.item(r, c)
        return item.text() if item else ""

    # --- φόροι / κρατήσεις -------------------------------------------------
    def net_total(self) -> float:
        """Καθαρή αξία όλων των γραμμών — η βάση για τα ποσοστά παρακράτησης."""
        total = 0.0
        for r in range(self._table.rowCount()):
            net, _vat, _sum = line_amounts(
                parse_money(self._cell(r, _QTY)),
                parse_money(self._cell(r, _PRICE)),
                parse_money(self._cell(r, _RATE)),
                parse_money(self._cell(r, _DISC)),
            )
            total += net
        return total

    def _add_tax(self) -> None:
        client = self.client()
        if client is None:
            return
        if self._tax_categories is None:
            self._status.setText("Φόρτωση κατηγοριών φόρου…")
            self._run(client.tax_categories, self._got_tax_categories, self._failed)
            return
        self._open_tax_dialog()

    def _got_tax_categories(self, data: dict[str, Any]) -> None:
        self._tax_categories = {k: v for k, v in data.items() if isinstance(v, list)}
        self._status.setText("")
        self._open_tax_dialog()

    def _open_tax_dialog(self) -> None:
        dialog = TaxDialog(
            self._tax_categories or {},
            net_total=self.net_total(),
            invoice_type=str(self._type.currentData() or ""),
            parent=self,
        )
        result = dialog.exec()
        if result == NEW_DEDUCTION:
            self._create_deduction()
            return
        if result != QDialog.DialogCode.Accepted:
            return
        self._taxes.append(dialog.tax())
        self._render_taxes()

    def _create_deduction(self) -> None:
        client = self.client()
        if client is None:
            return
        name, ok = QInputDialog.getText(self, "Νέα κράτηση", "Ονομασία κράτησης:")
        if not ok or not name.strip():
            return

        def created(result: dict) -> None:
            if not result.get("success"):
                self._failed(result.get("error", "Αποτυχία δημιουργίας κράτησης."))
                return
            # Ο κατάλογος ξαναφορτώνεται ώστε η νέα κράτηση να είναι επιλέξιμη.
            self._tax_categories = None
            self._add_tax()

        self._status.setText("Δημιουργία κράτησης…")
        self._run(lambda: client.create_deduction(name.strip()), created, self._failed)

    def _remove_tax(self) -> None:
        row = self._tax_table.currentRow()
        if 0 <= row < len(self._taxes):
            del self._taxes[row]
            self._render_taxes()

    def _render_taxes(self) -> None:
        self._tax_table.setRowCount(len(self._taxes))
        for r, tax in enumerate(self._taxes):
            kind = dict(TAX_TYPES).get(int(tax.get("type") or 0), "")
            sign = "−" if int(tax.get("type") or 0) in DEDUCTING_TYPES else "+"
            cells = (
                kind,
                str(tax.get("label") or tax.get("category") or ""),
                f"{sign} {fmt_money(float(tax.get('amount') or 0))}",
                str(tax.get("notes") or ""),
            )
            for c, text in enumerate(cells):
                self._tax_table.setItem(r, c, QTableWidgetItem(text))
        self._tax_table.setVisible(bool(self._taxes))
        self._tax_table.setToolTip("Διπλό κλικ σε γραμμή για αφαίρεση")
        self._recompute()

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
            "series": str(self._series.currentData() or self._series.currentText() or "A"),
            "payment": int(self._payment.currentData()),
            "notes": self._notes.text().strip(),
            "temp_id": self._temp_id,
            "taxes": [
                {k: t[k] for k in ("type", "category", "amount", "notes") if k in t}
                for t in self._taxes
            ],
            **self._customer_fields(),
        }

    # --- φόρτωση πελατολογίου & σειρών --------------------------------------
    def refresh(self) -> None:
        """Φέρνει πελάτες, είδη και σειρές μία φορά, όταν ανοίγει η σελίδα."""
        client = self.client()
        if client is None or self._loaded:
            return
        self._loaded = True
        self._status.setText("Φόρτωση πελατών, ειδών και σειρών…")
        quiet = lambda _m: self._status.setText("")  # noqa: E731
        self._run(client.customers, self._fill_customers, quiet)
        self._run(client.series, self._got_series, quiet)
        self._run(client.products, self._got_products, quiet)
        self._run(client.product_categories, self._got_categories, quiet)

    def invalidate(self) -> None:
        """Ξεχνά τα φορτωμένα δεδομένα — καλείται όταν αλλάζει εταιρεία.

        Χωρίς αυτό ο επιλογέας κρατούσε το πελατολόγιο της **προηγούμενης**
        εταιρείας, οπότε ο χρήστης τιμολογούσε σε πελάτη που δεν της ανήκει.
        """
        self._loaded = False
        self._customers = []
        self._products = []
        self._categories = []
        self._all_series = []
        self._tax_categories = None
        self._picker.set_rows([])
        self.refresh()

    def _fill_customers(self, data: dict[str, Any]) -> None:
        rows = data.get("customers") or data.get("rows") or []
        self._customers = list(rows)
        self._picker.set_rows(self._customers)
        self._status.setText(f"{len(self._customers)} πελάτες διαθέσιμοι.")

    def _got_products(self, data: dict[str, Any]) -> None:
        self._products = list(data.get("products") or data.get("rows") or [])
        for r in range(self._table.rowCount()):
            picker = self._line_picker(r)
            if picker is not None:
                picker.set_rows(self._products)

    def _got_categories(self, data: dict[str, Any]) -> None:
        self._categories = list(
            data.get("categories") or data.get("product_categories") or data.get("rows") or []
        )

    def _reload_products(self) -> None:
        client = self.client()
        if client is not None:
            self._run(client.products, self._got_products, lambda _m: None)

    def _picked_customer(self, row: dict[str, Any]) -> None:
        self._afm.setText(str(row.get("vat") or row.get("afm") or ""))
        self._name.setText(str(row.get("name") or row.get("customer_name") or ""))
        self._address.setText(str(row.get("address") or ""))
        self._city.setText(str(row.get("city") or ""))
        self._zip.setText(str(row.get("zip") or ""))

    def _new_customer(self, typed: str) -> None:
        """«➕ Νέος πελάτης…» — φτιάχνει και επιλέγει τον πελάτη επί τόπου."""
        client = self.client()
        if client is None:
            return
        prefill = typed if typed.isdigit() and len(typed) == 9 else ""
        dialog = NewCustomerDialog(self, vat=prefill)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        personal = dialog.is_personal()

        def created(result: dict) -> None:
            row = result.get("customer") or result.get("info") or {}
            if not (result.get("success") or row):
                self._failed(result.get("error", "Αποτυχία δημιουργίας πελάτη."))
                return
            if not personal:
                row = {**row, "vat": row.get("vat") or fields.get("vat", "")}
            else:
                row = {**fields, "vat": ""}
                row["zip"] = fields.get("zip_code", "")
            self._picked_customer(row)
            self._picker.setText(str(row.get("name") or ""))
            self._status.setText("Ο πελάτης δημιουργήθηκε και επιλέχθηκε.")
            self._run(client.customers, self._fill_customers, lambda _m: None)

        self._status.setText("Δημιουργία πελάτη…")
        call = (
            (lambda: client.create_personal_customer(**fields))
            if personal
            else (lambda: client.lookup_afm(fields["vat"]))
        )
        self._run(call, created, self._failed)

    def _got_series(self, data: dict[str, Any]) -> None:
        self._all_series = list(data.get("series", []))
        self._fill_series()

    def _fill_series(self) -> None:
        """Δείχνει μόνο τις σειρές που ανήκουν στον επιλεγμένο τύπο."""
        code = str(self._type.currentData() or "")
        label = type_label(code)
        matching = series_for_type(self._all_series, code)
        self._series.clear()
        for s in matching:
            self._series.addItem(str(s.get("series_code", "")), str(s.get("series_code", "")))
        if matching:
            self._series_warn.hide()
        else:
            self._series.addItem("A", "A")
            self._series_warn.setText(
                f"⚠ Δεν υπάρχει σειρά για «{label}». Δημιουργήστε μία από τις "
                "Σειρές, αλλιώς η ΑΑΔΕ θα απορρίψει την έκδοση."
            )
            self._series_warn.show()

    def _wizard_pick(self, who: str) -> None:
        """Διαλέγει τον πρώτο τύπο που ταιριάζει και κλείνει τον οδηγό.

        Ψάχνει μόνο ανάμεσα στους τύπους που έχουν ενεργή σειρά — αλλιώς ο
        οδηγός θα οδηγούσε σε τύπο που η ΑΑΔΕ θα απέρριπτε.
        """
        self._wizard.hide()
        _mark_wizard_seen()
        if not who:
            return
        pattern = r"λιανικ|απόδειξη|ΑΛΠ|ΑΠΥ" if who == "idiot" else r"τιμολ"
        for index in range(self._type.count()):
            code = str(self._type.itemData(index) or "")
            if not series_for_type(self._all_series, code):
                continue
            if re.search(pattern, self._type.itemText(index), re.IGNORECASE):
                self._type.setCurrentIndex(index)
                return
        self._status.setText(
            "Δεν υπάρχει σειρά για αυτόν τον τύπο — δημιούργησέ τη από τις Σειρές."
        )

    def _afm_typed(self, text: str) -> None:
        """Ξεκινά την άντληση μόλις σταματήσει η πληκτρολόγηση σε 9 ψηφία."""
        self._afm_timer.stop()
        if text.strip().isdigit() and len(text.strip()) == 9:
            self._afm_timer.start()

    def _fetch_customer(self) -> None:
        client = self.client()
        afm = self._afm.text().strip()
        if client is None or not (afm.isdigit() and len(afm) == 9):
            return
        self._status.setText("Άντληση στοιχείων από το Taxisnet…")

        def fill(data: dict) -> None:
            row = data.get("customer") or data.get("info") or data
            name = str(row.get("name") or row.get("customer_name") or "")
            if not name:
                self._status.setText("Δεν βρέθηκαν στοιχεία για αυτό το ΑΦΜ.")
                return
            self._name.setText(name)
            self._address.setText(str(row.get("address") or ""))
            self._city.setText(str(row.get("city") or ""))
            self._zip.setText(str(row.get("zip") or ""))
            self._status.setText("Συμπληρώθηκαν τα στοιχεία πελάτη.")

        self._run(lambda: client.lookup_afm(afm), fill, lambda m: self._status.setText(f"Σφάλμα: {m}"))

    # --- προγραμματισμός ---------------------------------------------------
    def _schedule(self) -> None:
        """Βάζει το παραστατικό σε ουρά αντί να το εκδώσει τώρα.

        Το ``schedule_job`` υπήρχε γραμμένο στον client αλλά δεν το καλούσε
        κανείς, οπότε η σελίδα «Προγραμματισμός» ήταν πάντα άδεια.
        """
        client = self.client()
        kwargs = self._issue_kwargs()
        if client is None or kwargs is None:
            return
        summary = (
            f"{self._type.currentText()} · σειρά {kwargs['series']} · "
            f"{self._name.text().strip() or self._afm.text().strip() or 'χωρίς πελάτη'} · "
            f"{fmt_money(self.net_total())} € καθαρή"
        )
        dialog = ScheduleDialog(summary, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = {k: v for k, v in kwargs.items() if k != "temp_id"}
        payload["live"] = 1
        self._status.setText("Καταχώρηση εργασίας…")
        self._run(
            lambda: client.schedule_job(
                payload,
                dialog.run_at(),
                title=dialog.title.text().strip() or summary,
                kind="invoice",
                recurrence=str(dialog.recurrence.currentData() or "none"),
            ),
            self._after_schedule,
            self._failed,
        )

    def _after_schedule(self, result: dict) -> None:
        if result.get("success"):
            self._status.setText("Η εργασία προγραμματίστηκε — δες τη στον Προγραμματισμό.")
        else:
            self._failed(result.get("error", "Ο προγραμματισμός απέτυχε."))

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
        self._picker.clear()
        self._afm.clear()
        self._name.clear()
        self._address.clear()
        self._city.clear()
        self._zip.clear()
        self._notes.clear()
        self._taxes.clear()
        self._render_taxes()
        self._table.setRowCount(0)
        self.add_line()
        self._status.setText("")
