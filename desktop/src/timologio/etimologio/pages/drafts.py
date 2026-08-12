"""Native Πρόχειρα (saved drafts): προβολή PDF, μαζική εκτύπωση/ZIP, διαγραφή.

Τα πρόχειρα είχαν μόνο «Διαγραφή» — δεν μπορούσες καν να τα δεις. Επειδή δεν
έχουν ΜΑΡΚ, το PDF τους έρχεται από το ``preview_temp`` και όχι από τη διαδρομή
των εκδοθέντων.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)

from ...gui.printing import print_pdfs
from ..bulkpdf import export_zip, fetch_draft_pdfs
from .base import ListPage


class DraftsPage(ListPage):
    """List, preview, print, export and delete drafts (πρόχειρα)."""

    #: Ζητά η σελίδα να ανοίξει ένα πρόχειρο στην Έκδοση.
    open_in_issue = Signal(dict)

    _COLS = [
        ("", "_check"),
        ("Ημ/νία", "save_date"),
        ("Τύπος", "type"),
        ("Σειρά", "series"),
        ("ΑΦΜ αγοραστή", "buyer_vat"),
        ("Κωδικός πρόχειρου", "temp_id"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Πρόχειρα", columns=self._COLS,
            rows_key="temp_invoices", stretch_col=2, parent=parent,
        )
        self.table.setColumnWidth(0, 34)
        self.table.doubleClicked.connect(lambda *_: self._preview_selected())

        buttons = (
            ("Όλα / κανένα", self._toggle_all, ""),
            ("Προεπισκόπηση", self._preview_selected, ""),
            ("Άνοιγμα σε Έκδοση", self._open_in_issue, ""),
            ("Εκτύπωση επιλεγμένων", lambda: self._bulk("print"), "primary"),
            ("Εξαγωγή ZIP", lambda: self._bulk("zip"), ""),
            ("Διαγραφή", self._delete, "danger"),
        )
        for text, slot, kind in buttons:
            button = QPushButton(text)
            if kind:
                button.setObjectName(kind)
            button.clicked.connect(slot)
            self.toolbar.insertWidget(self.toolbar.count() - 1, button)

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.temp_invoices()

    # --- επιλογή -----------------------------------------------------------
    def _fill(self, data: dict[str, Any]) -> None:
        super()._fill(data)
        for r in range(self.table.rowCount()):
            item = QTableWidgetItem()
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, item)

    def _toggle_all(self) -> None:
        # Αν έστω μία είναι ασημείωτη → σημειώνονται όλες· αλλιώς καθαρίζουν.
        rows = range(self.table.rowCount())
        any_unchecked = any(
            self.table.item(r, 0) is not None
            and self.table.item(r, 0).checkState() != Qt.CheckState.Checked
            for r in rows
        )
        state = Qt.CheckState.Checked if any_unchecked else Qt.CheckState.Unchecked
        for r in rows:
            item = self.table.item(r, 0)
            if item is not None:
                item.setCheckState(state)

    def checked_rows(self) -> list[dict[str, Any]]:
        """Τα σημειωμένα πρόχειρα — αν κανένα, το επιλεγμένο της λίστας."""
        picked = [
            row
            for r, row in enumerate(self._rows)
            if self.table.item(r, 0) is not None
            and self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if picked:
            return picked
        row = self.selected_row()
        return [row] if row is not None else []

    # --- ενέργειες ---------------------------------------------------------
    def _token(self, row: dict[str, Any]) -> str:
        return str(row.get("enc_id") or row.get("temp_id") or "")

    def _preview_selected(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        token = self._token(row)
        if not token:
            return
        self.status.setText("Λήψη PDF πρόχειρου…")
        self._run(
            lambda: fetch_draft_pdfs(client, [row]),
            lambda result: self._after_fetch(result, mode="open"),
            self._failed,
        )

    def _open_in_issue(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        self.open_in_issue.emit(row)

    def _bulk(self, mode: str) -> None:
        client = self.client()
        rows = self.checked_rows()
        if client is None:
            return
        if not rows:
            QMessageBox.information(self, "Πρόχειρα", "Σημείωσε πρώτα ένα ή περισσότερα πρόχειρα.")
            return
        self.status.setText(f"Λήψη {len(rows)} PDF…")
        self._run(
            lambda: fetch_draft_pdfs(client, rows),
            lambda result: self._after_fetch(result, mode=mode),
            self._failed,
        )

    def _after_fetch(self, result, *, mode: str) -> None:
        paths, errors = result
        if not paths:
            # Γνωστό: για κάποιους λογαριασμούς το `preview_temp` της ΑΑΔΕ απαντά
            # «Αδυναμία προεπισκόπησης» ακόμη και για έγκυρο πρόχειρο (ισχύει και
            # στο web). Δείχνουμε το πραγματικό μήνυμα και τη διέξοδο, αντί για
            # ένα σιωπηλό «τίποτα».
            detail = errors[0] if errors else "άγνωστο σφάλμα"
            self.status.setText(f"Το PDF δεν κατέβηκε: {detail}")
            QMessageBox.information(
                self, "Προεπισκόπηση πρόχειρου",
                f"Η ΑΑΔΕ δεν επέστρεψε PDF:\n\n{detail}\n\n"
                "Άνοιξε το πρόχειρο στην Έκδοση και πάτα «Προεπισκόπηση» — "
                "αυτή η διαδρομή δουλεύει.",
            )
            return
        note = f" ({len(errors)} απέτυχαν)" if errors else ""
        self.status.setText(f"{len(paths)} PDF έτοιμα{note}.")
        if mode == "open":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[0])))
            return
        if mode == "print":
            print_pdfs(paths, self)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Εξαγωγή {len(paths)} PDF σε ZIP",
            str(Path.home() / "ΠΡΟΧΕΙΡΑ.zip"), "ZIP (*.zip)",
        )
        if not path:
            return
        added = export_zip(paths, Path(path))
        QMessageBox.information(
            self, "Η εξαγωγή ολοκληρώθηκε", f"{added} αρχεία -> {Path(path).name}"
        )

    def _delete(self) -> None:
        client = self.client()
        rows = self.checked_rows()
        if client is None or not rows:
            return
        if QMessageBox.question(
            self, "Διαγραφή πρόχειρων",
            f"Διαγραφή {len(rows)} πρόχειρων;",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Διαγραφή…")
        targets = [(str(r.get("temp_id") or ""), str(r.get("seller_vat") or "")) for r in rows]

        def delete_all() -> dict[str, Any]:
            failed = 0
            for temp_id, seller in targets:
                if not temp_id:
                    continue
                if not client.delete_temp(temp_id, seller).get("success"):
                    failed += 1
            return {"success": failed == 0, "failed": failed}

        self._run(delete_all, self._after_delete, self._failed)

    def _after_delete(self, result: dict) -> None:
        if not result.get("success"):
            self.status.setText(f"{result.get('failed', 0)} πρόχειρα δεν διαγράφηκαν.")
        self.refresh()
