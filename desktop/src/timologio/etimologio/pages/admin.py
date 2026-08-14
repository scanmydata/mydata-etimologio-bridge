"""Native Διαχείριση: users, roles and email invitations (staff only)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)

from . import ui
from .base import ListPage

#: Roles the accountant can hand out.
ROLES: list[tuple[str, str]] = [
    ("editor", "Λογιστής (όλες οι εταιρείες)"),
    ("business", "Επιχείρηση (δικές της εταιρείες)"),
    ("master", "Διαχειριστής"),
]
_ROLE_LABELS = dict(ROLES)


class InviteDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Πρόσκληση μέλους")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.email = QLineEdit()
        self.email.setPlaceholderText("name@example.com")
        self.role = QComboBox()
        for code, label in ROLES:
            self.role.addItem(label, code)
        form.addRow("Email *", self.email)
        form.addRow("Ρόλος", self.role)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Αποστολή")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(
            lambda: self.accept() if "@" in self.email.text() else self.email.setFocus()
        )
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class AdminPage(ListPage):
    """User list with role changes, activation and invitations."""

    _COLS = [
        ("Email", "email"),
        ("Επωνυμία", "business_name"),
        ("Ρόλος", "role_label"),
        ("Κατάσταση", "status"),
        ("Εγγραφή", "created_at"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Διαχείριση", columns=self._COLS,
            rows_key="users", stretch_col=1, parent=parent,
            subtitle="Χρήστες, ρόλοι και λογαριασμοί ΑΑΔΕ ανά επιχείρηση.",
        )
        for widget in (
            ui.button("Πρόσκληση μέλους", self._invite, kind="primary", icon_name="add_client"),
            ui.button("Αλλαγή ρόλου", self._change_role, icon_name="edit"),
            ui.button("Ενεργοποίηση", lambda: self._set_status("active"), icon_name="check"),
            ui.button("Απενεργοποίηση", lambda: self._set_status("disabled"), kind="danger", icon_name="cancel"),
            ui.button("Διαγραφή χρήστη", self._delete_user, kind="danger", icon_name="delete",
                      tip="Οριστική διαγραφή, μαζί με τις εταιρείες του"),
        ):
            self.toolbar.insertWidget(self.toolbar.count() - 1, widget)

    def fetch(self, client: Any) -> dict[str, Any]:
        data = client.admin_users()
        for row in data.get("users", []):
            row["role_label"] = _ROLE_LABELS.get(str(row.get("role", "")), row.get("role", ""))
        return data

    def _invite(self) -> None:
        client = self.client()
        if client is None:
            return
        dialog = InviteDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        email = dialog.email.text().strip()
        role = dialog.role.currentData()
        self.status.setText("Αποστολή πρόσκλησης…")
        self._run(lambda: client.admin_invite(email, role), self._after_invite, self._failed)

    def _after_invite(self, result: dict) -> None:
        if not result.get("success"):
            self._failed(result.get("error", "Η πρόσκληση απέτυχε."))
            return
        # With email off, the backend hands back the link for manual delivery.
        link = result.get("invite_url") or result.get("link") or ""
        if link:
            QMessageBox.information(
                self, "Πρόσκληση",
                "Η πρόσκληση δημιουργήθηκε. Δεν στάλθηκε email — στείλε τον σύνδεσμο:\n\n" + link,
            )
        else:
            QMessageBox.information(self, "Πρόσκληση", "Η πρόσκληση στάλθηκε με email.")
        self.refresh()

    def _change_role(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Αλλαγή ρόλου")
        form = QFormLayout(dialog)
        combo = QComboBox()
        for code, label in ROLES:
            combo.addItem(label, code)
        index = combo.findData(str(row.get("role", "")))
        if index >= 0:
            combo.setCurrentIndex(index)
        form.addRow(f"Ρόλος για {row.get('email', '')}", combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        user_id, role = row.get("id"), combo.currentData()
        self._run(lambda: client.admin_set_role(user_id, role), self._after_write, self._failed)

    def _set_status(self, status: str) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        user_id = row.get("id")
        self._run(lambda: client.admin_set_status(user_id, status), self._after_write, self._failed)

    def _delete_user(self) -> None:
        """Οριστική διαγραφή — η απενεργοποίηση κρατά τη γραμμή για πάντα.

        Λέει ΠΟΣΕΣ εταιρείες φεύγουν μαζί: τα κλειδιά ΑΑΔΕ που είναι δεμένα
        στον χρήστη σβήνονται μαζί του και δεν ανακτώνται.
        """
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            self.status.setText("Διάλεξε πρώτα χρήστη.")
            return
        user_id = row.get("id")
        email = str(row.get("email", ""))
        companies = len(client.admin_user_accounts(int(user_id)).get("accounts", []))
        extra = (f"\n\nΜαζί του διαγράφονται {companies} εταιρείες με τα "
                 "κλειδιά ΑΑΔΕ τους.") if companies else ""
        if QMessageBox.question(
            self, "Διαγραφή χρήστη",
            f"Οριστική διαγραφή του «{email}»;{extra}\n\nΗ ενέργεια δεν αναιρείται.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Διαγραφή…")
        self._run(lambda: client.admin_delete_user(user_id), self._after_write, self._failed)

    def _after_write(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Αποτυχία."))
