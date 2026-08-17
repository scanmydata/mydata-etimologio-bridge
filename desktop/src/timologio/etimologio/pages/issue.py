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

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
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
    set_live_types,
    type_label,
)
from . import ui
from .base import EtimPage, cached_then_live, fmt_money, parse_money
from .catalog import NewProductDialog
from .customers import NewCustomerDialog
from .dialogs import (
    DEDUCTING_TYPES,
    NEW_DEDUCTION,
    TAX_TYPES,
    ScheduleDialog,
    TaxDialog,
    rate_from_label,
    tax_signed_total,
)
from .pickers import customer_picker, product_picker

#: Πόσο περιμένουμε μετά το τελευταίο πλήκτρο πριν ρωτήσουμε το Taxisnet.
#: Ίδιο με το web — αρκετά ώστε να μη φύγει ερώτημα σε κάθε ψηφίο.
AFM_LOOKUP_DELAY_MS = 400

# Ο οδηγός ΔΕΝ «απομνημονεύεται» πια: το web τον δείχνει σε κάθε νέο
# παραστατικό, ενώ εδώ εμφανιζόταν μία φορά στη ζωή της εγκατάστασης και μετά
# δεν ξαναγύριζε ποτέ — γι' αυτό «δεν υπάρχει σύστημα επιλογής τι θα εκδώσεις».

#: Η τιμή που σημαίνει «➕ Νέα σειρά…» μέσα στο dropdown σειράς.
_NEW_SERIES = "__new_series"

#: Editor columns.
#: Ίδια σειρά στηλών με το web (`#iLines`): η έκπτωση ΠΡΙΝ τον ΦΠΑ, γιατί έτσι
#: εφαρμόζεται και στον υπολογισμό. Το «Καθαρή» είναι δική μας προσθήκη.
_COLS = ["Περιγραφή / Κωδικός", "Ποσότητα", "Τιμή μον.", "Έκπτ. %", "ΦΠΑ %", "Καθαρή", "Σύνολο"]
_DESC, _QTY, _PRICE, _DISC, _RATE, _NET, _TOTAL = range(7)

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
    #: Τι να πει ο βοηθός όταν τελειώσει η ετοιμασία πρόχειρου.
    assistant_said = Signal(str)

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
        title = QLabel("Έκδοση παραστατικού")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        new = QPushButton("🆕 Νέο")
        new.setToolTip("Καθαρισμός φόρμας")
        new.clicked.connect(self.reset)
        top.addWidget(new)
        box.addLayout(top)
        box.addWidget(ui.page_hint(
            "Έκδοση τιμολογίων και αποδείξεων στην ΑΑΔΕ. Το «Πρόχειρο» δεν στέλνει τίποτα — ΜΑΡΚ δίνει μόνο η «Έκδοση»."))

        # --- header: type / series / payment -------------------------------
        head = QHBoxLayout()
        self._type = QComboBox()
        self._fill_types()
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
        # Γλώσσα παραστατικού: υπήρχε μόνο στο web, οπότε από την εφαρμογή
        # υπολογιστή δεν γινόταν να εκδοθεί αγγλικό τιμολόγιο — ο client δεχόταν
        # ήδη `lang`, απλώς δεν το ρωτούσε κανείς.
        self._lang = QComboBox()
        for code, label in (("el", "Ελληνικά"), ("en", "English")):
            self._lang.addItem(label, code)
        head.addWidget(QLabel("Γλώσσα:"))
        head.addWidget(self._lang)
        box.addLayout(head)
        self._type.currentIndexChanged.connect(self._fill_series)
        self._series.currentIndexChanged.connect(self._series_changed)

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
        self._wizard_label = QLabel("Τι θέλεις να εκδώσεις;")
        wiz.addWidget(self._wizard_label)
        # Βήμα 1: είδος παραστατικού. Βήμα 2: τι είναι ο πελάτης. Το web ρωτά
        # και τα δύο και τα ξαναρωτά σε κάθε νέο παραστατικό — ο οδηγός εδώ
        # εμφανιζόταν **μία φορά στη ζωή της εγκατάστασης** και μετά ποτέ.
        self._wizard_buttons: list[QPushButton] = []
        for text, choice in (
            ("🧾 Τιμολόγιο / Απόδειξη", "invoice"),
            ("🚚 Δελτίο αποστολής", "delivery"),
            ("🏢 Επαγγελματίας", "pro"),
            ("👤 Ιδιώτης", "idiot"),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, c=choice: self._wizard_pick(c))
            wiz.addWidget(button)
            self._wizard_buttons.append(button)
        skip = QPushButton("Παράλειψη")
        skip.setObjectName("linkButton")
        skip.clicked.connect(lambda: self._wizard_pick(""))
        wiz.addWidget(skip)
        self._again = QPushButton("↺ Αλλαγή επιλογής")
        self._again.setObjectName("linkButton")
        self._again.setToolTip("Άλλαξε τύπο παραστατικού / πελάτη")
        self._again.clicked.connect(self.start_wizard)
        wiz.addWidget(self._again)
        wiz.addStretch(1)
        box.addWidget(self._wizard)
        self.start_wizard()

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
        # Ο επιλογέας είδους είναι ολόκληρο widget μέσα στο κελί και είναι
        # ΨΗΛΟΤΕΡΟΣ από την προεπιλεγμένη γραμμή: το κάτω μέρος του κοβόταν και
        # η γραμμή έμοιαζε μισοσχεδιασμένη. Το ύψος βγαίνει από το ίδιο το
        # widget, όχι από σταθερά, ώστε να αντέχει άλλη γραμματοσειρά ή DPI.
        self._table.verticalHeader().setDefaultSectionSize(
            max(30, product_picker().sizeHint().height() + 8)
        )
        box.addWidget(self._table, 1)

        line_btns = QHBoxLayout()
        add = QPushButton("➕ Γραμμή")
        add.clicked.connect(lambda: self.add_line())
        rem = QPushButton("➖ Γραμμή")
        rem.clicked.connect(self._remove_line)
        line_btns.addWidget(add)
        line_btns.addWidget(rem)
        tax_btn = QPushButton("💶 Φόρος/Κράτηση")
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
        self._notes.setPlaceholderText("Σχόλια / Παρατηρήσεις (προαιρετικό)")
        box.addWidget(self._notes)

        actions = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("muted")
        actions.addWidget(self._status)
        actions.addStretch(1)
        draft = QPushButton("💾 Αποθήκευση πρόχειρου")
        draft.clicked.connect(self._save_draft)
        # Διπλό «&&»: το Qt διαβάζει το μονό «&» ως mnemonic και το κουμπί έγραφε
        # «Αποθήκευση _Προεπισκόπηση».
        preview = QPushButton("💾👁 Αποθήκευση && Προεπισκόπηση")
        preview.clicked.connect(self._preview)
        schedule = QPushButton("⏰ Προγραμματισμός")
        schedule.setToolTip("Έκδοση αργότερα, αυτόματα")
        schedule.clicked.connect(self._schedule)
        issue = QPushButton("📤 Οριστική Έκδοση στην ΑΑΔΕ (ΜΑΡΚ)")
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
        self._table.resizeRowToContents(r)
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

    def _new_product(self, row: int, typed: str, defaults: dict[str, Any] | None = None) -> None:
        client = self.client()
        if client is None:
            return
        dialog = NewProductDialog(self, categories=self._categories, code=typed)
        # Ο βοηθός ξέρει περιγραφή και τιμή από την πρόταση του χρήστη· τα
        # συμπληρώνει ώστε να μένουν μόνο κατηγορία και ΦΠΑ.
        for field, widget in (("description", dialog.description), ("price", dialog.unit_price)):
            value = str((defaults or {}).get(field) or "")
            if value:
                widget.setText(value)
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
            # «Κρατήσεις» σκέτο ήταν λάθος όνομα: στο ίδιο ποσό μπαίνουν και οι
            # παρακρατήσεις φόρου. Ίδια διατύπωση με το web.
            text += (
                f"   Τέλη: +{fmt_money(plus)} €   "
                f"Παρακρατήσεις / Κρατήσεις: −{fmt_money(minus)} €"
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
            "lang": str(self._lang.currentData() or "el"),
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
        """Φέρνει πελάτες, είδη και σειρές, με την cache πρώτα.

        Χωρίς την cache, ο επιλογέας πελάτη έμενε άδειος ~4 δευτερόλεπτα μετά το
        άνοιγμα της σελίδας — και όποιος τον άνοιγε σε εκείνο το διάστημα έβλεπε
        μόνο το «➕ Νέος πελάτης…».
        """
        client = self.client()
        if client is None or self._loaded:
            return
        self._loaded = True
        self._picker.set_loading(True)
        self._status.setText("Φόρτωση πελατών, ειδών και σειρών…")
        # Το ζωντανό βήμα είναι το `sync`: φέρνει τα ίδια δεδομένα ΚΑΙ γράφει το
        # snapshot, ώστε το επόμενο άνοιγμα να είναι ακαριαίο.
        cached_then_live(self._run, client, "customers",
                         lambda: client.sync("customers"),
                         self._fill_customers, self._load_failed)
        # Ο κατάλογος τύπων ΠΡΩΤΑ: οι σειρές ταιριάζουν πάνω του, και χωρίς
        # αυτόν μένουμε στους 11 χειρόγραφους τύπους αντί για τους 24 της ΑΑΔΕ.
        cached_then_live(self._run, client, "invtypes", lambda: client.sync("invtypes"),
                         self._got_types, lambda _m: None)
        cached_then_live(self._run, client, "series", lambda: client.sync("series"),
                         self._got_series, self._load_failed)
        cached_then_live(self._run, client, "products", lambda: client.sync("products"),
                         self._got_products, self._load_failed)
        self._run(client.product_categories, self._got_categories, lambda _m: None)

    def _load_failed(self, message: str) -> None:
        """Ένα αποτυχημένο φόρτωμα ΔΕΝ σβήνεται σιωπηλά.

        Πριν, κάθε σφάλμα κατέληγε σε καθαρή γραμμή κατάστασης και άδειο
        dropdown — και ο χρήστης δεν είχε τρόπο να μάθει ότι φταίει π.χ. ένας
        λογαριασμός ΑΑΔΕ που δεν έχει ρυθμιστεί (το backend απαντά 409).
        """
        self._picker.set_loading(False)
        self._status.setText(f"Τα δεδομένα δεν φορτώθηκαν: {message}")

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

    def _fill_customers(self, rows: list[dict[str, Any]], from_cache: bool = False) -> None:
        self._customers = list(rows)
        self._picker.set_loading(False)
        self._picker.set_rows(self._customers)
        note = " (τοπικά)" if from_cache else ""
        self._status.setText(f"{len(self._customers)} πελάτες διαθέσιμοι{note}.")

    def _got_products(self, rows: list[dict[str, Any]], _from_cache: bool = False) -> None:
        self._products = list(rows)
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

    def _fill_types(self) -> None:
        """(Ξανα)γεμίζει το «Τύπος», κρατώντας ό,τι είχε επιλεγεί.

        Ο κατάλογος τύπων έρχεται από την ΑΑΔΕ (24 τύποι) και αντικαθιστά τον
        χειρόγραφο πίνακα των 11 — αλλιώς μια ενεργή σειρά όπως το «9.3 Δελτίο
        Αποστολής» δεν έχει τύπο να διαλέξεις για να την εκδώσεις.
        """
        current = str(self._type.currentData() or "")
        self._type.blockSignals(True)
        self._type.clear()
        for code, label in INVOICE_TYPES:
            self._type.addItem(label, code)
        index = self._type.findData(current) if current else -1
        if index >= 0:
            self._type.setCurrentIndex(index)
        self._type.blockSignals(False)

    def _got_types(self, rows: list[dict[str, Any]], _from_cache: bool = False) -> None:
        if set_live_types(rows):
            self._fill_types()
            self._mark_types_without_series()
            self._fill_series()

    def _got_series(self, rows: list[dict[str, Any]], _from_cache: bool = False) -> None:
        self._all_series = list(rows)
        self._mark_types_without_series()
        self._select_type_with_series()
        self._fill_series()

    def _select_type_with_series(self) -> None:
        """Αν ο επιλεγμένος τύπος δεν έχει σειρά, πάει στον πρώτο που έχει.

        Η φόρμα άνοιγε στον πρώτο τύπο του πίνακα ό,τι κι αν είχε ο λογαριασμός.
        Όποιος δεν εκδίδει «2.1» έβλεπε «— χωρίς σειρά» και άδειο δεύτερο
        dropdown: ακριβώς η εικόνα του «δεν επιλέγεται τίποτα».
        """
        if not self._all_series:
            return
        code = str(self._type.currentData() or "")
        if code and series_for_type(self._all_series, code):
            return
        for index in range(self._type.count()):
            if series_for_type(self._all_series, str(self._type.itemData(index) or "")):
                self._type.setCurrentIndex(index)
                return

    def _mark_types_without_series(self) -> None:
        """Σημειώνει στην ετικέτα ποιοι τύποι δεν έχουν σειρά.

        Το web δείχνει μόνο όσους έχουν· εμείς κρατάμε όλη τη λίστα, αλλά πρέπει
        να φαίνεται **πριν** συμπληρωθεί το παραστατικό ότι ο τύπος δεν είναι
        εκδόσιμος.
        """
        self._type.blockSignals(True)
        for index in range(self._type.count()):
            code = str(self._type.itemData(index) or "")
            base = type_label(code) or self._type.itemText(index)
            has = bool(series_for_type(self._all_series, code))
            self._type.setItemText(index, base if has else f"{base}  — χωρίς σειρά")
        self._type.blockSignals(False)

    def _fill_series(self) -> None:
        """Δείχνει μόνο τις σειρές που ανήκουν στον επιλεγμένο τύπο."""
        code = str(self._type.currentData() or "")
        label = type_label(code)
        matching = series_for_type(self._all_series, code)
        self._series.blockSignals(True)
        self._series.clear()
        for s in matching:
            description = str(s.get("description") or "").strip()
            text = str(s.get("series_code", ""))
            self._series.addItem(
                f"{text} — {description}" if description else text, text
            )
        # ΚΑΜΙΑ επινοημένη σειρά «A» όταν δεν υπάρχει καμία: η ΑΑΔΕ δέχεται μόνο
        # σειρές που έχουν δημιουργηθεί, οπότε η προεπιλογή αυτή οδηγούσε σε
        # σίγουρη απόρριψη — αφού είχε συμπληρωθεί όλο το παραστατικό.
        # «Νέα σειρά» μέσα στο ίδιο dropdown, όπως στο web: αλλιώς πρέπει να
        # φύγεις στη σελίδα Σειρές και να γυρίσεις πίσω με άδεια φόρμα.
        self._series.addItem("➕  Νέα σειρά…", _NEW_SERIES)
        self._series.blockSignals(False)
        if matching:
            self._series_warn.hide()
        else:
            self._series_warn.setText(
                f"⚠ Δεν υπάρχει σειρά για «{label}». Φτιάξε μία από το ίδιο "
                "dropdown («➕ Νέα σειρά…»), αλλιώς η ΑΑΔΕ θα απορρίψει την έκδοση."
            )
            self._series_warn.show()

    def _series_changed(self) -> None:
        """«➕ Νέα σειρά…»: τη φτιάχνει επί τόπου και την επιλέγει."""
        if str(self._series.currentData() or "") != _NEW_SERIES:
            return
        client = self.client()
        code = str(self._type.currentData() or "")
        if client is None:
            self._fill_series()
            return
        from .catalog import NewSeriesDialog

        dialog = NewSeriesDialog(self, invoice_type=code)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._fill_series()
            return
        fields = dialog.fields()

        def created(result: dict[str, Any]) -> None:
            if not result.get("success"):
                self._failed(result.get("error", "Η σειρά δεν δημιουργήθηκε."))
                self._fill_series()
                return
            self._status.setText(f"Η σειρά {fields['series_code']} δημιουργήθηκε.")
            self._run(
                client.series,
                lambda data: self._after_new_series(data, fields["series_code"]),
                self._failed,
            )

        self._status.setText("Δημιουργία σειράς…")
        self._run(lambda: client.create_series(**fields), created, self._failed)

    def _after_new_series(self, data: dict[str, Any], series_code: str) -> None:
        self._got_series(list(data.get("series", [])))
        index = self._series.findData(series_code)
        if index >= 0:
            self._series.setCurrentIndex(index)

    def start_wizard(self) -> None:
        """Δείχνει το πρώτο βήμα: τι είδος παραστατικού."""
        self._wizard_step = "kind"
        self._sync_wizard()

    def _sync_wizard(self) -> None:
        """Ποια κουμπιά φαίνονται σε κάθε βήμα."""
        kind = self._wizard_step == "kind"
        self._wizard_label.setText(
            "Τι θέλεις να εκδώσεις;" if kind else "Ο πελάτης είναι:"
        )
        for button, step in zip(
            self._wizard_buttons, ("kind", "kind", "who", "who"), strict=True
        ):
            button.setVisible((step == "kind") == kind)
        self._again.setVisible(not kind)
        self._wizard.setVisible(True)

    def _wizard_pick(self, who: str) -> None:
        """Διαλέγει τον πρώτο τύπο που ταιριάζει και προχωρά τον οδηγό.

        Ψάχνει μόνο ανάμεσα στους τύπους που έχουν ενεργή σειρά — αλλιώς ο
        οδηγός θα οδηγούσε σε τύπο που η ΑΑΔΕ θα απέρριπτε.
        """
        if who == "invoice":                       # βήμα 1 → βήμα 2
            self._wizard_step = "who"
            self._sync_wizard()
            return
        if who == "delivery":
            self._wizard.hide()
            self._pick_type(r"δελτίο αποστολ")
            self._status.setText(
                "Δελτίο αποστολής: τα στοιχεία διακίνησης (όχημα, διευθύνσεις) "
                "συμπληρώνονται προς το παρόν από τη web εφαρμογή."
            )
            return
        self._wizard.hide()
        if not who:
            return
        pattern = r"λιανικ|απόδειξη|ΑΛΠ|ΑΠΥ" if who == "idiot" else r"τιμολ"
        self._pick_type(pattern)

    def _pick_type(self, pattern: str) -> None:
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
            if name:
                self._apply_customer_details(row)
                return
            # Το `afm` endpoint επιβεβαιώνει/καταχωρεί τον πελάτη αλλά επιστρέφει
            # μόνο `{status, code, vat}` — τα στοιχεία τα δίνει το πελατολόγιο.
            # Χωρίς αυτό το δεύτερο βήμα, επωνυμία και διεύθυνση έμεναν κενές.
            if not data.get("success"):
                self._status.setText("Δεν βρέθηκαν στοιχεία για αυτό το ΑΦΜ.")
                return
            self._run(lambda: client.customers(vat=afm), fill_from_list, quiet)

        def fill_from_list(data: dict) -> None:
            rows = data.get("customers") or data.get("rows") or []
            match = next(
                (r for r in rows if str(r.get("vat") or r.get("afm") or "") == afm), None
            )
            if match is None:
                self._status.setText("Ο πελάτης καταχωρήθηκε — συμπλήρωσε τα στοιχεία.")
                return
            self._apply_customer_details(match)

        quiet = lambda m: self._status.setText(f"Σφάλμα: {m}")  # noqa: E731
        self._run(lambda: client.lookup_afm(afm), fill, quiet)

    def _apply_customer_details(self, row: dict[str, Any]) -> None:
        self._name.setText(str(row.get("name") or row.get("customer_name") or ""))
        self._address.setText(str(row.get("address") or ""))
        self._city.setText(str(row.get("city") or ""))
        self._zip.setText(str(row.get("zip") or ""))
        self._status.setText("Συμπληρώθηκαν τα στοιχεία πελάτη.")

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
            ui.open_file(path, self)
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

    def load_draft(self, draft: dict[str, Any]) -> None:
        """Φορτώνει ένα αποθηκευμένο πρόχειρο για συνέχεια.

        Κρατάμε το ``temp_id`` ώστε η επόμενη αποθήκευση να ενημερώσει το ίδιο
        πρόχειρο — αλλιώς κάθε άνοιγμα άφηνε πίσω του ένα ακόμη διπλότυπο.
        """
        self.reset()
        self._temp_id = str(draft.get("temp_id") or "")
        vat = str(draft.get("buyer_vat") or "")
        if vat:
            self._afm.setText(vat)
            match = next(
                (c for c in self._customers if str(c.get("vat") or "") == vat), None
            )
            if match is not None:
                self._picked_customer(match)
                self._picker.setText(str(match.get("name") or ""))
        series = str(draft.get("series") or "")
        if series:
            index = self._series.findData(series)
            if index >= 0:
                self._series.setCurrentIndex(index)
        self._status.setText(
            f"Άνοιξε το πρόχειρο {self._temp_id[:8]}… — συμπλήρωσε τις γραμμές και αποθήκευσε."
        )

    # --- ο ψηφιακός βοηθός ---------------------------------------------------
    # Ο βοηθός δεν μιλά στο backend μόνος του: ζητά από ΑΥΤΗ τη σελίδα να
    # ετοιμάσει πρόχειρο. Έτσι υπάρχει ένα μόνο σημείο που στέλνει παραστατικά —
    # και είναι φανερό ότι η διαδρομή του βοηθού τελειώνει σε `issue_invoice`
    # χωρίς `live`, δηλαδή χωρίς ΜΑΡΚ.

    def known_customers(self) -> list[dict[str, Any]]:
        return list(self._customers)

    def known_products(self) -> list[dict[str, Any]]:
        return list(self._products)

    def open_new_customer(self, prefill: dict[str, Any] | None = None) -> None:
        data = prefill or {}
        self._new_customer(str(data.get("vat") or data.get("name") or ""))

    def open_new_product(self, prefill: dict[str, Any] | None = None) -> None:
        data = prefill or {}
        if self._table.rowCount() == 0:
            self.add_line()
        self._new_product(0, "", defaults=data)

    def prepare_draft(self, spec: Any) -> None:
        """Γεμίζει τη φόρμα από εντολή του βοηθού και αποθηκεύει **πρόχειρο**.

        Ποτέ οριστική έκδοση: δεν υπάρχει διαδρομή από εδώ προς ``live=True``.
        """
        client = self.client()
        if client is None:
            self.assistant_said.emit("Δεν υπάρχει σύνδεση με το backend.")
            return
        self.reset()
        # Αν ο τύπος που είναι επιλεγμένος δεν έχει σειρά, τον διαλέγουμε όπως ο
        # οδηγός: ο πρώτος «τιμολόγιο» (ή «απόδειξη» για ιδιώτη) που ΕΧΕΙ σειρά.
        # Αλλιώς το πρόχειρο θα έφευγε με σειρά «A», που δεν υπάρχει.
        if not series_for_type(self._all_series, str(self._type.currentData() or "")):
            self._wizard_pick("idiot" if getattr(spec, "retail", False) else "pro")
        vat = str(getattr(spec, "vat", "") or "")
        name = str(getattr(spec, "name", "") or "")
        self._afm.setText(vat)
        self._name.setText(name)
        self._picker.setText(name or vat)

        code = str(getattr(spec, "code", "") or "")
        price = getattr(spec, "price", None)
        qty = getattr(spec, "qty", 1) or 1
        self._table.setRowCount(0)
        self.add_line(desc=code, qty=f"{float(qty):g}", price=f"{float(price or 0):g}")
        product = next(
            (p for p in self._products if str(p.get("code") or p.get("product_code") or "") == code),
            None,
        )
        if product is not None:
            self._picked_product(0, product)
            # Η τιμή της εντολής υπερισχύει του καταλόγου: ο χρήστης την είπε ρητά.
            if price:
                item = self._table.item(0, _PRICE)
                if item is not None:
                    item.setText(f"{float(price):g}")
                self._recompute()

        match = next(
            (c for c in self._customers if str(c.get("vat") or c.get("afm") or "") == vat), None
        )
        if match is not None:
            self._picked_customer(match)
            self._picker.setText(str(match.get("name") or vat))
            self._assistant_taxes(spec)
            return
        if vat.isdigit() and len(vat) == 9:
            # Άγνωστο ΑΦΜ: το αντλούμε από το Taxisnet ΠΡΙΝ αποθηκεύσουμε, αλλιώς
            # το πρόχειρο θα έφευγε χωρίς επωνυμία και διεύθυνση.
            self.assistant_said.emit("Αντλώ τα στοιχεία του πελάτη…")
            self._run(
                lambda: client.customers(vat=vat),
                lambda data: self._assistant_customer(data, vat, spec),
                lambda msg: self._assistant_taxes(spec),
            )
            return
        self._assistant_taxes(spec)

    def _assistant_customer(self, data: dict[str, Any], vat: str, spec: Any) -> None:
        rows = data.get("customers") or data.get("rows") or []
        match = next((r for r in rows if str(r.get("vat") or r.get("afm") or "") == vat), None)
        if match is not None:
            self._picked_customer(match)
            self._picker.setText(str(match.get("name") or vat))
        self._assistant_taxes(spec)

    def _assistant_taxes(self, spec: Any) -> None:
        """Προσθέτει την παρακράτηση, αν ζητήθηκε — και μετά αποθηκεύει."""
        pct = getattr(spec, "withholding_pct", None)
        client = self.client()
        if not pct or client is None:
            self._assistant_save()
            return
        if self._tax_categories is None:

            def got(data: dict[str, Any]) -> None:
                self._tax_categories = {k: v for k, v in data.items() if isinstance(v, list)}
                self._assistant_taxes(spec)

            self._run(
                client.tax_categories,
                got,
                lambda msg: self._assistant_save(f"⚠ Οι κατηγορίες φόρου δεν ήρθαν: {msg}."),
            )
            return
        rows = (self._tax_categories or {}).get("withheld", []) or []
        target = next(
            (r for r in rows if abs(rate_from_label(str(r.get("label", ""))) * 100 - float(pct)) < 0.01),
            None,
        )
        if target is None:
            self._assistant_save(
                f"⚠ Δεν βρήκα κατηγορία παρακράτησης {float(pct):g}% — πρόσθεσέ τη "
                "από το «💶 Φόρος / Κράτηση»."
            )
            return
        amount = round(self.net_total() * float(pct) / 100.0, 2)
        self._taxes.append(
            {
                "type": 1,
                "category": str(target.get("code", "")),
                "amount": amount,
                "notes": "",
                "label": str(target.get("label", "")),
            }
        )
        self._render_taxes()
        self._assistant_save()

    def _assistant_save(self, warning: str = "") -> None:
        client = self.client()
        kwargs = self._issue_kwargs()
        if client is None or kwargs is None:
            self.assistant_said.emit(
                "Χρειάζεται είδος και τιμή — συμπλήρωσέ τα στη φόρμα και πάτα «Πρόχειρο»."
            )
            return

        def done(result: dict) -> None:
            self._after_draft(result)
            if result.get("success"):
                self.assistant_said.emit(
                    (warning + "\n" if warning else "")
                    + f"✔ Το πρόχειρο ετοιμάστηκε ({self._temp_id[:8]}…). Έλεγξέ το εδώ ή "
                    "στα «Πρόχειρα» και έκδωσέ το χειροκίνητα."
                )
            else:
                self.assistant_said.emit(
                    "Το πρόχειρο δεν αποθηκεύτηκε: "
                    + str(result.get("error", "άγνωστο σφάλμα"))
                )

        self._status.setText("Αποθήκευση πρόχειρου…")
        # Χωρίς `live`: ο βοηθός δεν εκδίδει ποτέ οριστικά.
        self._run(
            lambda: client.issue_invoice(**kwargs),
            done,
            lambda msg: self.assistant_said.emit(f"Σφάλμα: {msg}"),
        )

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
        self.start_wizard()
