"""Native Πρόχειρα (saved drafts) page: list + delete."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox, QPushButton

from .base import ListPage


class DraftsPage(ListPage):
    """List and delete drafts (πρόχειρα) saved in e-timologio."""

    _COLS = [
        ("Ημ/νία", "save_date"),
        ("Τύπος", "type"),
        ("Σειρά", "series"),
        ("ΑΦΜ αγοραστή", "buyer_vat"),
        ("Κωδικός πρόχειρου", "temp_id"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Πρόχειρα", columns=self._COLS,
            rows_key="temp_invoices", stretch_col=1, parent=parent,
        )
        delete = QPushButton("Διαγραφή")
        delete.clicked.connect(self._delete)
        self.toolbar.insertWidget(self.toolbar.count() - 1, delete)

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.temp_invoices()

    def _delete(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        temp_id = str(row.get("temp_id") or "")
        seller = str(row.get("seller_vat") or "")
        if not temp_id:
            return
        if QMessageBox.question(
            self, "Διαγραφή πρόχειρου", "Διαγραφή του επιλεγμένου πρόχειρου;"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Διαγραφή…")
        self._run(
            lambda: client.delete_temp(temp_id, seller),
            self._after_delete,
            self._failed,
        )

    def _after_delete(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία διαγραφής."))
