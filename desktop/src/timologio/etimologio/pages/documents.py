"""Native Παραστατικά: search issued documents, then bulk print or export ZIP.

The gesture is the Downloader's: tick the rows you want, then «Μαζική εκτύπωση»
opens the same print preview, or «Εξαγωγή ZIP» packs their PDFs into one file.
The PDFs are pulled from e-timologio by MARK on demand (see ``bulkpdf``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...gui.printing import print_pdfs
from ...gui.widgets import GrDateEdit
from ..bulkpdf import export_zip, fetch_pdfs
from . import ui
from .base import EtimPage, fmt_money, parse_money

_COLS = ["", "Ημ/νία", "Τύπος", "Σειρά", "Α/Α", "ΜΑΡΚ", "ΑΦΜ", "Καθαρή", "Σύνολο"]
_CHECK, _DATE, _TYPE, _SERIES, _AA, _MARK, _VAT, _NET, _TOTAL = range(9)


class DocumentsPage(EtimPage):
    """Issued documents with multi-select, bulk print preview and ZIP export."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._rows: list[dict[str, Any]] = []
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(12)
        box.addLayout(ui.page_header("Παραστατικά", self.go_back.emit))

        # --- filters card --------------------------------------------------
        filters_card, filters = ui.card()
        row = QHBoxLayout()
        row.addWidget(ui.muted("Από:"))
        self._from = GrDateEdit(date(date.today().year, 1, 1))
        row.addWidget(self._from)
        row.addWidget(ui.muted("Έως:"))
        self._to = GrDateEdit(date.today())
        row.addWidget(self._to)
        row.addWidget(ui.muted("ΑΦΜ:"))
        self._vat = QLineEdit()
        self._vat.setPlaceholderText("αγοραστή (προαιρετικό)")
        self._vat.setFixedWidth(160)
        self._vat.returnPressed.connect(self.refresh)
        row.addWidget(self._vat)
        row.addWidget(ui.muted("Σειρά:"))
        self._series = QLineEdit()
        self._series.setFixedWidth(80)
        row.addWidget(self._series)
        row.addStretch(1)
        row.addWidget(ui.button("Αναζήτηση", self.refresh, kind="primary", icon_name="search"))
        filters.addLayout(row)
        box.addWidget(filters_card)

        # --- table ---------------------------------------------------------
        self._table = ui.table(_COLS, stretch=_TYPE, checkable=True)
        self._table.setColumnWidth(_CHECK, 34)
        box.addWidget(self._table, 1)

        # --- action bar ----------------------------------------------------
        actions = QHBoxLayout()
        actions.addWidget(ui.button("Επιλογή όλων", lambda: self._set_all(True), icon_name="check"))
        actions.addWidget(ui.button("Καμία", lambda: self._set_all(False), icon_name="cancel"))
        self._status = ui.muted("")
        actions.addWidget(self._status)
        actions.addStretch(1)
        actions.addWidget(
            ui.button("Μαζική εκτύπωση", self.print_selected, kind="primary",
                      icon_name="printer", tip="Προεπισκόπηση και εκτύπωση των επιλεγμένων")
        )
        actions.addWidget(
            ui.button("Εξαγωγή ZIP", self.export_selected, icon_name="folder",
                      tip="Πακετάρει τα PDF των επιλεγμένων σε ένα αρχείο ZIP")
        )
        box.addLayout(actions)

    # --- data --------------------------------------------------------------
    def set_customer_filter(self, vat: str) -> None:
        self._vat.setText(vat)

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        self._status.setText("Αναζήτηση…")
        kwargs = {
            "date_from": self._from.gr(),
            "date_to": self._to.gr(),
            "buyer_vat": self._vat.text().strip(),
            "series": self._series.text().strip(),
        }
        self._run(lambda: client.search_invoices(**kwargs), self._fill, self._failed)

    def _fill(self, data: dict[str, Any]) -> None:
        self._rows = list(data.get("invoices", []))
        self._table.setRowCount(len(self._rows))
        total = 0.0
        for r, row in enumerate(self._rows):
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, _CHECK, check)
            for col, key in (
                (_DATE, "issue_date"), (_TYPE, "type"), (_SERIES, "series"),
                (_AA, "aa"), (_MARK, "mark"), (_VAT, "buyer_vat"),
            ):
                self._table.setItem(r, col, QTableWidgetItem(str(row.get(key, ""))))
            self._table.setItem(r, _NET, QTableWidgetItem(str(row.get("net_value", ""))))
            self._table.setItem(r, _TOTAL, QTableWidgetItem(str(row.get("total", ""))))
            total += parse_money(row.get("total"))
        self._status.setText(f"{len(self._rows)} παραστατικά · σύνολο {fmt_money(total)} €")

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")

    # --- selection ---------------------------------------------------------
    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _CHECK)
            if item is not None:
                item.setCheckState(state)

    def selected_rows(self) -> list[dict[str, Any]]:
        """Ticked rows; if nothing is ticked, the highlighted row (if any)."""
        rows = [
            self._rows[r]
            for r in range(min(self._table.rowCount(), len(self._rows)))
            if (item := self._table.item(r, _CHECK)) is not None
            and item.checkState() == Qt.CheckState.Checked
        ]
        if rows:
            return rows
        current = self._table.currentRow()
        if 0 <= current < len(self._rows):
            return [self._rows[current]]
        return []

    # --- bulk actions ------------------------------------------------------
    def _gather(self, action: str):
        """Common preamble: check a selection exists, then fetch its PDFs."""
        client = self.client()
        rows = self.selected_rows()
        if client is None:
            return None
        if not rows:
            QMessageBox.information(
                self, action,
                "Δεν έχετε επιλέξει παραστατικά.\n\n"
                "Τσεκάρετε όσα θέλετε (ή πατήστε «Επιλογή όλων»).",
            )
            return None
        self._status.setText(f"Λήψη {len(rows)} PDF από την ΑΑΔΕ…")
        return client, rows

    def print_selected(self) -> None:
        gathered = self._gather("Μαζική εκτύπωση")
        if gathered is None:
            return
        client, rows = gathered
        self._run(
            lambda: fetch_pdfs(client, rows),
            lambda result: self._after_fetch(result, mode="print"),
            self._failed,
        )

    def export_selected(self) -> None:
        gathered = self._gather("Εξαγωγή ZIP")
        if gathered is None:
            return
        client, rows = gathered
        self._run(
            lambda: fetch_pdfs(client, rows),
            lambda result: self._after_fetch(result, mode="zip"),
            self._failed,
        )

    def _after_fetch(self, result, *, mode: str) -> None:
        paths, errors = result
        note = f"\n\n{len(errors)} δεν κατέβηκαν." if errors else ""
        if not paths:
            self._status.setText("Κανένα PDF δεν κατέβηκε.")
            QMessageBox.warning(self, "Χωρίς PDF", "Δεν κατέβηκε κανένα PDF." + note)
            return
        self._status.setText(f"{len(paths)} PDF έτοιμα.")
        if mode == "print":
            print_pdfs(paths, self)
            if errors:
                QMessageBox.information(self, "Μαζική εκτύπωση", f"{len(paths)} στην προεπισκόπηση.{note}")
            return
        default = Path.home() / f"ΠΑΡΑΣΤΑΤΙΚΑ {date.today():%Y-%m-%d}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Εξαγωγή {len(paths)} PDF σε ZIP", str(default), "ZIP (*.zip)"
        )
        if not path:
            return
        added = export_zip(paths, Path(path))
        QMessageBox.information(
            self, "Η εξαγωγή ολοκληρώθηκε", f"{added} αρχεία -> {Path(path).name}{note}"
        )
