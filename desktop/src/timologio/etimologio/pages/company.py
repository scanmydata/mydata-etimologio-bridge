"""Καταχώρηση εταιρείας ΑΑΔΕ μέσα από την εφαρμογή.

Χωρίς αυτό, μια καθαρή εγκατάσταση συνδεόταν ως master με **μηδέν εταιρείες**:
κάθε σελίδα γύριζε άδεια και δεν υπήρχε καμία διέξοδος μέσα από το UI — έπρεπε
να μπεις στο web ή να πειράξεις τη βάση.
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QRegularExpression, QTimer
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from . import ui

#: Καθυστέρηση πριν ρωτήσουμε το Taxisnet για την επωνυμία (ίδια με την Έκδοση).
NAME_LOOKUP_DELAY_MS = 400


class AddCompanyDialog(QDialog):
    """ΑΦΜ, ετικέτα, username και subscription key του e-timologio."""

    def __init__(self, parent=None, *, client, run) -> None:
        super().__init__(parent)
        self.setWindowTitle("Προσθήκη εταιρείας ΑΑΔΕ")
        self.setMinimumWidth(460)
        self._client = client
        self._run = run

        box = QVBoxLayout(self)
        form = QFormLayout()
        box.addLayout(form)

        self.vat = QLineEdit()
        self.vat.setPlaceholderText("9 ψηφία")
        self.vat.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,9}")))
        self.vat.textEdited.connect(self._vat_typed)
        self.label = QLineEdit()
        self.label.setPlaceholderText("συμπληρώνεται από το Taxisnet")
        self.username = QLineEdit()
        self.subkey = QLineEdit()
        # Το κλειδί δεν κρύβεται: ο λογιστής το αντιγράφει από το e-timologio και
        # πρέπει να μπορεί να δει ότι το επικόλλησε σωστά.
        self.subkey.setPlaceholderText("subscription key από το e-timologio")

        form.addRow("ΑΦΜ *", self.vat)
        form.addRow("Επωνυμία / ετικέτα", self.label)
        form.addRow("Username *", self.username)
        form.addRow("Subscription key *", self.subkey)

        box.addWidget(ui.muted(
            "Τα στοιχεία είναι αυτά που χρησιμοποιείς για να μπεις στο e-timologio "
            "της ΑΑΔΕ. Αποθηκεύονται κρυπτογραφημένα, τοπικά."
        ))
        self._error = ui.hint("")
        box.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Προσθήκη")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(NAME_LOOKUP_DELAY_MS)
        self._timer.timeout.connect(self._lookup_name)

    # --- επωνυμία από το Taxisnet ------------------------------------------
    def _vat_typed(self, text: str) -> None:
        self._timer.stop()
        if re.fullmatch(r"\d{9}", text.strip()):
            self._timer.start()

    def _lookup_name(self) -> None:
        vat = self.vat.text().strip()
        if not re.fullmatch(r"\d{9}", vat):
            return

        def fill(data: dict[str, Any]) -> None:
            name = str(data.get("name") or "")
            if name and not self.label.text().strip():
                self.label.setText(name)

        self._run(lambda: self._client.taxis_name(vat), fill, lambda _m: None)

    # --- αποθήκευση ---------------------------------------------------------
    def _accept(self) -> None:
        vat = self.vat.text().strip()
        if not re.fullmatch(r"\d{9}", vat):
            self._error.setText("Το ΑΦΜ πρέπει να έχει 9 ψηφία.")
            self.vat.setFocus()
            return
        for field, message in (
            (self.username, "Δώσε το username του e-timologio."),
            (self.subkey, "Δώσε το subscription key."),
        ):
            if not field.text().strip():
                self._error.setText(message)
                field.setFocus()
                return

        def done(result: dict[str, Any]) -> None:
            if result.get("success"):
                self.accept()
            else:
                self._error.setText(result.get("error", "Η προσθήκη απέτυχε."))

        def failed(msg: str) -> None:
            self._error.setText(f"Σφάλμα: {msg}")

        self._error.setText("Καταχώρηση…")
        self._run(self._add, done, failed)

    def _add(self) -> dict[str, Any]:
        """Βρίσκει τον master και συνδέει τον λογαριασμό σε αυτόν.

        Το `admin_add_account` θέλει `user_id`, και σε τοπική εγκατάσταση ο
        μοναδικός χρήστης είναι ο master που δημιουργήθηκε στο bootstrap.
        """
        users = self._client.admin_users().get("users", [])
        master = next((u for u in users if u.get("role") == "master"), None)
        if master is None:
            return {"success": False, "error": "Δεν βρέθηκε διαχειριστής."}
        return self._client.admin_add_account(
            int(master["id"]),
            vat=self.vat.text().strip(),
            label=self.label.text().strip() or self.vat.text().strip(),
            username=self.username.text().strip(),
            # Η παράμετρος λέγεται `subkey`· το `subscription_key` γίνεται
            # δεκτό από τη φόρμα και παράγει κλειδί μηδενικού μήκους, που
            # εμφανίζεται πολύ αργότερα ως σκέτο «Login failed».
            subkey=self.subkey.text().strip(),
        )
