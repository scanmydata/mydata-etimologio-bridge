"""Παλέτα εντολών (Ctrl+K): πελάτης ή ενότητα, με ένα πληκτρολόγιο.

Το web έχει μόνο αναζήτηση πελάτη· εδώ η ίδια γραμμή βρίσκει **και** ενότητες,
γιατί σε εφαρμογή υπολογιστή με δεκατέσσερις σελίδες το «πού ήταν οι σειρές;»
είναι συχνότερο από το «ποιος ήταν ο πελάτης;».

Η αναζήτηση πελάτη περνά από το backend (με μικρή παύση, όπως στο web), οι
ενότητες φιλτράρονται τοπικά — δεν έχει νόημα ερώτημα δικτύου για μια λίστα
δεκατεσσάρων σταθερών λέξεων.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ..assistant import normalize
from .base import RunFn

#: Καθυστέρηση πριν φύγει ερώτημα στο backend, σε ms.
_DELAY_MS = 300

#: Ο ρόλος όπου κάθε γραμμή κρατά τι είναι: ("section", key) ή ("customer", row).
_PAYLOAD = int(Qt.ItemDataRole.UserRole) + 11


class CommandPalette(QDialog):
    """Μία γραμμή αναζήτησης πάνω από όλα. Εκπέμπει τι διάλεξε ο χρήστης."""

    open_section = Signal(str)
    open_customer = Signal(dict)

    def __init__(
        self,
        parent,
        *,
        sections: list[tuple[str, str]],
        get_client: Callable[[], Any],
        run: RunFn,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Αναζήτηση")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._sections = sections
        self._get_client = get_client
        self._run = run

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Πελάτης (επωνυμία ή ΑΦΜ) ή ενότητα…")
        self.input.textEdited.connect(self._typed)
        self.input.returnPressed.connect(self._accept_current)
        box.addWidget(self.input)

        self.results = QListWidget()
        self.results.setMinimumHeight(260)
        self.results.itemActivated.connect(self._chose)
        self.results.itemClicked.connect(self._chose)
        box.addWidget(self.results, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_DELAY_MS)
        self._timer.timeout.connect(self._search_customers)
        self._fill_sections("")

    # --- πληκτρολόγιο -------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Τα βελάκια οδηγούν τη λίστα ενώ η εστίαση μένει στο πεδίο — αλλιώς θα
        # έπρεπε να πατήσει κανείς Tab για να διαλέξει.
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.results.count():
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            row = (self.results.currentRow() + step) % self.results.count()
            self.results.setCurrentRow(row)
            return
        super().keyPressEvent(event)

    # --- αποτελέσματα -------------------------------------------------------
    def _typed(self, text: str) -> None:
        self._fill_sections(text)
        self._timer.stop()
        if len(text.strip()) >= 2:
            self._timer.start()

    def _fill_sections(self, text: str) -> None:
        needle = normalize(text.strip())
        self.results.clear()
        for key, label in self._sections:
            if needle and needle not in normalize(label):
                continue
            self._add(f"→  {label}", "Ενότητα", ("section", key))
        if self.results.count():
            self.results.setCurrentRow(0)

    def _search_customers(self) -> None:
        client = self._get_client()
        term = self.input.text().strip()
        if client is None or not term:
            return
        kwargs = {"vat": term} if term.isdigit() and len(term) >= 6 else {"name": term}
        self._run(lambda: client.customers(**kwargs), self._add_customers, lambda _m: None)

    def _add_customers(self, data: dict[str, Any]) -> None:
        rows = data.get("customers") or data.get("rows") or []
        for row in rows[:12]:
            name = str(row.get("name") or row.get("customer_name") or "")
            vat = str(row.get("vat") or row.get("afm") or "")
            city = str(row.get("city") or "")
            detail = " · ".join(p for p in (f"ΑΦΜ {vat}" if vat else "", city) if p)
            self._add(f"👤  {name}", detail, ("customer", row))
        if self.results.count() and self.results.currentRow() < 0:
            self.results.setCurrentRow(0)

    def _add(self, text: str, detail: str, payload: tuple[str, Any]) -> None:
        item = QListWidgetItem(f"{text}\n{detail}" if detail else text)
        item.setData(_PAYLOAD, payload)
        self.results.addItem(item)

    # --- επιλογή ------------------------------------------------------------
    def _accept_current(self) -> None:
        item = self.results.currentItem() or self.results.item(0)
        if item is not None:
            self._chose(item)

    def _chose(self, item: QListWidgetItem) -> None:
        payload = item.data(_PAYLOAD)
        if not payload:
            return
        kind, value = payload
        self.accept()
        if kind == "section":
            self.open_section.emit(value)
        else:
            self.open_customer.emit(value)
