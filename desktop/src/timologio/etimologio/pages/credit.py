"""Native Ακύρωση / Πιστωτικό: issue a correlated credit note by original MARK.

In myDATA you never delete an issued document — you cancel it with a correlated
credit note that references the original MARK. Same three modes as Έκδοση
(πρόχειρο / προεπισκόπηση / έκδοση).
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .base import EtimPage, fmt_money, parse_money


class CreditNotePage(EtimPage):
    """Cancel an invoice via a correlated credit note."""

    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._temp_id = ""
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
        title = QLabel("Ακύρωση / Πιστωτικό")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        box.addLayout(top)

        note = QLabel(
            "Η ακύρωση εκδίδει συσχετιζόμενο πιστωτικό που αναφέρεται στο ΜΑΡΚ του "
            "αρχικού παραστατικού. Άφησε το ποσό κενό για πλήρη ακύρωση."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        box.addWidget(note)

        form = QFormLayout()
        self._mark = QLineEdit()
        self._mark.setPlaceholderText("ΜΑΡΚ αρχικού παραστατικού")
        self._reason = QLineEdit()
        self._amount = QLineEdit()
        self._amount.setPlaceholderText("κενό = πλήρης ακύρωση")
        form.addRow("ΜΑΡΚ *", self._mark)
        form.addRow("Αιτιολογία", self._reason)
        form.addRow("Ποσό (μερικό)", self._amount)
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
        box.addStretch(1)

    def _kwargs(self) -> dict | None:
        mark = self._mark.text().strip()
        if not mark:
            self._status.setText("Συμπλήρωσε το ΜΑΡΚ του αρχικού παραστατικού.")
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
