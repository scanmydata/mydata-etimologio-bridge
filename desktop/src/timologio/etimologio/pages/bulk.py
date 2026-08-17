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
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..codes import INVOICE_TYPES, PAYMENT_METHODS, series_for_type, type_label
from . import ui
from .base import EtimPage, cached_then_live, parse_money
from .pickers import customer_picker, customer_vat_picker, product_picker

_COLS = ["ΑΦΜ", "Επωνυμία", "Περιγραφή", "Ποσότητα", "Τιμή", "ΦΠΑ %", "Αποτέλεσμα"]
_AFM, _NAME, _DESC, _QTY, _PRICE, _RATE, _RESULT = range(7)

#: myDATA vatCategory id → ποσοστό, ώστε η επιλογή είδους να συμπληρώνει ΦΠΑ.
_VAT_PERCENT: dict[str, str] = {
    "1": "24", "2": "13", "3": "6", "4": "17", "5": "9", "6": "4", "7": "0", "8": "0",
}


class BulkPage(EtimPage):
    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._loaded = False
        self._all_series: list[dict[str, Any]] = []
        self._customers: list[dict[str, Any]] = []
        self._products: list[dict[str, Any]] = []
        self._categories: list[dict[str, Any]] = []
        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Μαζική έκδοση")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        box.addLayout(top)
        box.addWidget(ui.page_hint(
            "Πολλά παραστατικά μαζί: κοινός τύπος, σειρά και τρόπος πληρωμής, μία γραμμή ανά πελάτη."))

        head = QHBoxLayout()
        self._type = QComboBox()
        for code, label in INVOICE_TYPES:
            self._type.addItem(label, code)
        head.addWidget(QLabel("Τύπος παραστατικού:"))
        head.addWidget(self._type, 2)
        # Η σειρά ήταν ελεύθερο κείμενο με προεπιλογή «A». Μια σειρά που δεν
        # υπάρχει για τον συγκεκριμένο τύπο δεν απορρίπτει μία γραμμή — απορρίπτει
        # ΟΛΟΚΛΗΡΗ την παρτίδα, αφού έχει συμπληρωθεί.
        self._series = QComboBox()
        self._series.setMinimumWidth(110)
        head.addWidget(QLabel("Σειρά:"))
        head.addWidget(self._series)
        self._payment = QComboBox()
        for code, label in PAYMENT_METHODS:
            self._payment.addItem(label, code)
        head.addWidget(QLabel("Τρόπος πληρωμής:"))
        head.addWidget(self._payment, 1)
        self._lang = QComboBox()
        for code, label in (("el", "Ελληνικά"), ("en", "English")):
            self._lang.addItem(label, code)
        head.addWidget(QLabel("Γλώσσα:"))
        head.addWidget(self._lang)
        box.addLayout(head)
        self._type.currentIndexChanged.connect(self._fill_series)

        self._series_warn = QLabel("")
        self._series_warn.setObjectName("hint")
        self._series_warn.setWordWrap(True)
        self._series_warn.hide()
        box.addWidget(self._series_warn)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setColumnWidth(_NAME, 200)
        self._table.setColumnWidth(_DESC, 200)
        box.addWidget(self._table, 1)

        row_btns = QHBoxLayout()
        add = QPushButton("➕ Γραμμή")
        add.clicked.connect(lambda: self.add_row())
        rem = QPushButton("➖ Γραμμή")
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
        draft = QPushButton("💾 Δημιουργία προχείρων (όλα)")
        draft.clicked.connect(lambda: self._run_bulk(live=False))
        issue = QPushButton("📤 Οριστική έκδοση όλων (ΜΑΡΚ)")
        issue.setObjectName("danger")
        issue.clicked.connect(lambda: self._run_bulk(live=True))
        actions.addWidget(draft)
        actions.addWidget(issue)
        box.addLayout(actions)

        self.add_row()

    # --- σειρές, πελάτες, είδη ---------------------------------------------
    def refresh(self) -> None:
        """Φέρνει σειρές, πελάτες και είδη μία φορά — τα θέλουν οι επιλογείς."""
        client = self.client()
        if client is None or self._loaded:
            return
        self._loaded = True
        quiet = lambda _m: self._status.setText("")  # noqa: E731
        # Cache πρώτα, ΑΑΔΕ από πίσω — ίδιο μοτίβο με την Έκδοση. Οι τρεις
        # επιλογείς έμεναν άδειοι ~10 δευτερόλεπτα σε κάθε άνοιγμα.
        for kind, key, handler in (
            ("series", "series", self._got_series),
            ("customers", "customers", self._got_customers),
            ("products", "products", self._got_products),
        ):
            cached_then_live(
                self._run, client, kind,
                (lambda k=kind: client.sync(k)),
                (lambda rows, _fc, k=key, h=handler: h({k: rows})),
                quiet,
            )
        self._run(client.product_categories, self._got_categories, quiet)

    def invalidate(self) -> None:
        """Ξεχνά τα φορτωμένα δεδομένα — καλείται όταν αλλάζει εταιρεία."""
        self._loaded = False
        self._all_series = []
        self._customers = []
        self._products = []
        self._categories = []
        self._spread_rows()
        self.refresh()

    def _fill_types(self) -> None:
        """Ξαναγεμίζει το «Τύπος» από τον ενεργό κατάλογο, κρατώντας την επιλογή.

        Ο κατάλογος αντικαθίσταται από τον ζωντανό της ΑΑΔΕ όταν τον φέρει η
        Έκδοση· η Μαζική χτίζεται μια φορά, οπότε πρέπει να ξαναδιαβάσει.
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

    def _got_series(self, data: dict[str, Any]) -> None:
        self._all_series = list(data.get("series", []))
        self._fill_types()
        self._fill_series()

    def _got_customers(self, data: dict[str, Any]) -> None:
        self._customers = list(data.get("customers") or data.get("rows") or [])
        self._spread_rows()

    def _got_products(self, data: dict[str, Any]) -> None:
        self._products = list(data.get("products") or data.get("rows") or [])
        self._spread_rows()

    def _got_categories(self, data: dict[str, Any]) -> None:
        self._categories = list(
            data.get("categories") or data.get("product_categories") or data.get("rows") or []
        )

    def _spread_rows(self) -> None:
        """Δίνει τα φορτωμένα δεδομένα σε κάθε επιλογέα που υπάρχει ήδη."""
        for r in range(self._table.rowCount()):
            for column, rows in (
                (_AFM, self._customers), (_NAME, self._customers), (_DESC, self._products)
            ):
                picker = self._table.cellWidget(r, column)
                if picker is not None:
                    picker.set_rows(rows)

    def _fill_series(self) -> None:
        code = str(self._type.currentData() or "")
        matching = series_for_type(self._all_series, code)
        self._series.clear()
        for s in matching:
            self._series.addItem(str(s.get("series_code", "")), str(s.get("series_code", "")))
        if matching:
            self._series_warn.hide()
            return
        self._series.addItem("A", "A")
        self._series_warn.setText(
            f"⚠ Δεν υπάρχει σειρά για «{type_label(code)}». Δημιουργήστε μία από τις "
            "Σειρές — αλλιώς η ΑΑΔΕ θα απορρίψει ΟΛΗ την παρτίδα."
        )
        self._series_warn.show()

    def add_row(self, afm="", name="", desc="", qty="1", price="0", rate="24") -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        # ΑΦΜ, Επωνυμία και Περιγραφή είναι επιλογείς, όχι ελεύθερο κείμενο: σε
        # μια παρτίδα 200 γραμμών, ένα πληκτρολογημένο ΑΦΜ ή ένας κωδικός είδους
        # που δεν υπάρχει απορρίπτεται από την ΑΑΔΕ αφού συμπληρωθούν όλα.
        vat_picker = customer_vat_picker()
        name_picker = customer_picker(placeholder="Επωνυμία…")
        item_picker = product_picker(placeholder="Είδος…")
        vat_picker.setText(afm)
        name_picker.setText(name)
        item_picker.setText(desc)
        for picker, column in (
            (vat_picker, _AFM), (name_picker, _NAME), (item_picker, _DESC)
        ):
            picker.set_rows(self._products if column == _DESC else self._customers)
            self._table.setCellWidget(r, column, picker)
        for picker in (vat_picker, name_picker):
            picker.picked.connect(lambda row, i=r: self._picked_customer(i, row))
            picker.create_requested.connect(lambda text, i=r: self._new_customer(i, text))
        item_picker.picked.connect(lambda row, i=r: self._picked_product(i, row))
        item_picker.create_requested.connect(lambda text, i=r: self._new_product(i, text))
        for col, val in ((_QTY, qty), (_PRICE, price), (_RATE, rate)):
            self._table.setItem(r, col, QTableWidgetItem(val))
        self._table.setItem(r, _RESULT, QTableWidgetItem(""))

    # --- επιλογή πελάτη / είδους -------------------------------------------
    def _picker_at(self, row: int, column: int):
        return self._table.cellWidget(row, column)

    def _picked_customer(self, row: int, customer: dict[str, Any]) -> None:
        """Μία επιλογή συμπληρώνει **και** το ΑΦΜ **και** την επωνυμία."""
        vat = str(customer.get("vat") or customer.get("afm") or "")
        name = str(customer.get("name") or customer.get("customer_name") or "")
        for column, value in ((_AFM, vat), (_NAME, name)):
            picker = self._picker_at(row, column)
            if picker is not None:
                picker.setText(value)

    def _picked_product(self, row: int, product: dict[str, Any]) -> None:
        """Ο κωδικός στη στήλη, και τιμή/ΦΠΑ από τον κατάλογο αν λείπουν."""
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

    def _new_customer(self, row: int, typed: str) -> None:
        client = self.client()
        if client is None:
            return
        from .customers import NewCustomerDialog

        prefill = typed if typed.isdigit() and len(typed) == 9 else ""
        dialog = NewCustomerDialog(self, vat=prefill)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        personal = dialog.is_personal()

        def created(result: dict[str, Any]) -> None:
            created_row = result.get("customer") or result.get("info") or {}
            if not (result.get("success") or created_row):
                self._failed(result.get("error", "Αποτυχία δημιουργίας πελάτη."))
                return
            if personal:
                created_row = {**fields, "vat": ""}
            else:
                created_row = {**created_row, "vat": created_row.get("vat") or fields.get("vat", "")}
            self._picked_customer(row, created_row)
            self._status.setText("Ο πελάτης δημιουργήθηκε και μπήκε στη γραμμή.")
            self._run(client.customers, self._got_customers, lambda _m: None)

        self._status.setText("Δημιουργία πελάτη…")
        call = (
            (lambda: client.create_personal_customer(**fields))
            if personal
            else (lambda: client.lookup_afm(fields["vat"]))
        )
        self._run(call, created, self._failed)

    def _new_product(self, row: int, typed: str) -> None:
        client = self.client()
        if client is None:
            return
        from .catalog import NewProductDialog

        dialog = NewProductDialog(self, categories=self._categories, code=typed)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        code = fields["product_code"]

        def created(result: dict[str, Any]) -> None:
            if not result.get("success"):
                self._failed(result.get("error", "Αποτυχία δημιουργίας είδους."))
                return
            picker = self._picker_at(row, _DESC)
            if picker is not None:
                picker.setText(code)
            self._status.setText(f"Το είδος {code} δημιουργήθηκε.")
            self._run(client.products, self._got_products, lambda _m: None)

        self._status.setText("Δημιουργία είδους…")
        self._run(lambda: client.create_product(**fields), created, self._failed)

    def _remove_row(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            r = self._table.rowCount() - 1
        if r >= 0:
            self._table.removeRow(r)

    def _cell(self, r: int, c: int) -> str:
        # Οι τρεις πρώτες στήλες είναι widget (επιλογείς), όχι κελιά κειμένου.
        picker = self._table.cellWidget(r, c)
        if picker is not None:
            return picker.text().strip()
        item = self._table.item(r, c)
        return item.text().strip() if item else ""

    def build_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        inv_type = self._type.currentData()
        series = str(self._series.currentData() or self._series.currentText() or "A")
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
                "issue_lang": str(self._lang.currentData() or "el"),
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
