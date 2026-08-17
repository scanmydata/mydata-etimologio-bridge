"""Εταιρείες: ο κατάλογος των πελατών ενός λογιστικού γραφείου.

Η εφαρμογή ξεκίνησε ως «μία εταιρεία, η δική μου»: η μόνη διαχείριση ήταν ένα
«＋» δίπλα στον επιλογέα, χωρίς λίστα, χωρίς επεξεργασία και **χωρίς διαγραφή**.
Ένα γραφείο όμως δεν έχει μία εταιρεία — έχει δεκάδες, και η καθημερινή δουλειά
είναι να μπαινοβγαίνει σε αυτές.

Η σελίδα δείχνει όλες τις καταχωρημένες εταιρείες με τον χρήστη στον οποίο
ανήκουν, και δίνει: άνοιγμα (αλλαγή ενεργής εταιρείας), προσθήκη, επεξεργασία
στοιχείων/κλειδιών, και οριστική διαγραφή. Κάθε αλλαγή ενημερώνει αμέσως τον
επιλογέα της μπάρας — χωρίς επανεκκίνηση.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)

from . import ui
from .base import ListPage


class EditCompanyDialog(QDialog):
    """Στοιχεία μιας καταχωρημένης εταιρείας.

    Το subscription key δεν επιστρέφεται ποτέ από το backend (σκόπιμα), οπότε το
    πεδίο ανοίγει **κενό** και γράφεται μόνο αν το συμπληρώσεις — αλλιώς θα
    έσβηνε το αποθηκευμένο κλειδί με κάθε αλλαγή ετικέτας.
    """

    def __init__(self, parent=None, *, row: dict[str, Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Στοιχεία εταιρείας")
        self.setMinimumWidth(460)
        self.account_id = int(row.get("id") or 0)

        form = QFormLayout(self)
        self.vat = QLineEdit(str(row.get("vat") or ""))
        self.label = QLineEdit(str(row.get("label") or ""))
        self.username = QLineEdit(str(row.get("username") or ""))
        self.subkey = QLineEdit()
        self.subkey.setPlaceholderText("κενό = μένει το αποθηκευμένο κλειδί")
        form.addRow("ΑΦΜ", self.vat)
        form.addRow("Επωνυμία / ετικέτα", self.label)
        form.addRow("Username", self.username)
        form.addRow("Subscription key", self.subkey)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Άκυρο")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._original_subkey = str(row.get("subkey") or "")

    def fields(self) -> dict[str, Any]:
        return {
            "vat": self.vat.text().strip(),
            "label": self.label.text().strip(),
            "username": self.username.text().strip(),
            "subkey": self.subkey.text().strip() or self._original_subkey,
        }


class CompaniesPage(ListPage):
    """Όλες οι εταιρείες της εγκατάστασης, με άνοιγμα/προσθήκη/διαγραφή."""

    #: Ζητά από το κέλυφος να κάνει ενεργή αυτή την εταιρεία.
    open_company = Signal(str)
    #: Κάτι άλλαξε — ο επιλογέας της μπάρας πρέπει να ξαναχτιστεί.
    accounts_changed = Signal()

    _COLS = [
        ("ΑΦΜ", "vat"),
        ("Επωνυμία", "label"),
        ("Username", "username"),
        ("Χρήστης", "owner_email"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Εταιρείες", columns=self._COLS,
            rows_key="accounts", stretch_col=1, parent=parent,
            subtitle="Οι εταιρείες που διαχειρίζεσαι. Διπλό κλικ ανοίγει την εταιρεία.",
        )
        for widget in (
            ui.button("Άνοιγμα", self._open_selected, kind="primary", icon_name="check",
                      tip="Κάνε αυτή την εταιρεία ενεργή"),
            ui.button("Προσθήκη", self._add, icon_name="add_client"),
            ui.button("Επεξεργασία", self._edit, icon_name="edit"),
            ui.button("Διαγραφή", self._delete, kind="danger", icon_name="delete"),
        ):
            self.toolbar.insertWidget(self.toolbar.count() - 1, widget)
        self.table.doubleClicked.connect(lambda *_: self._open_selected())

    def fetch(self, client: Any) -> dict[str, Any]:
        return client.admin_accounts()

    # --- ενέργειες ----------------------------------------------------------
    def _open_selected(self) -> None:
        row = self.selected_row()
        if row is None:
            self.status.setText("Διάλεξε πρώτα εταιρεία.")
            return
        vat = str(row.get("vat") or "")
        if vat:
            self.open_company.emit(vat)

    def _add(self) -> None:
        client = self.client()
        if client is None:
            return
        from .company import AddCompanyDialog

        dialog = AddCompanyDialog(self, client=client, run=self._run)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.refresh()
        self.accounts_changed.emit()

    def _edit(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            self.status.setText("Διάλεξε πρώτα εταιρεία.")
            return
        dialog = EditCompanyDialog(self, row=row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.fields()
        account_id = int(row.get("id") or 0)
        self.status.setText("Αποθήκευση…")
        self._run(
            lambda: client.admin_update_account(account_id, **fields),
            self._after_write, self._failed,
        )

    def _delete(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            self.status.setText("Διάλεξε πρώτα εταιρεία.")
            return
        label = str(row.get("label") or row.get("vat") or "")
        if QMessageBox.question(
            self, "Διαγραφή εταιρείας",
            f"Διαγραφή της «{label}»;\n\nΤα κλειδιά ΑΑΔΕ της σβήνονται και δεν "
            "ανακτώνται. Τα παραστατικά στην ΑΑΔΕ δεν επηρεάζονται.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        account_id = int(row.get("id") or 0)
        self.status.setText("Διαγραφή…")
        self._run(
            lambda: client.admin_delete_account(account_id),
            self._after_write, self._failed,
        )

    def _after_write(self, result: dict[str, Any]) -> None:
        if not result.get("success"):
            self._failed(result.get("error", "Αποτυχία."))
            return
        self.refresh()
        # Ο επιλογέας της μπάρας ενημερώνεται ΤΩΡΑ — όχι στην επόμενη εκκίνηση.
        self.accounts_changed.emit()


__all__ = ["CompaniesPage", "EditCompanyDialog"]
