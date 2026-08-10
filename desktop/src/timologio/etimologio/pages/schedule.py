"""Native Προγραμματισμός: queued/automatic issuance jobs."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from . import ui
from .base import ListPage

_STATUS = {
    "pending": "Σε αναμονή",
    "done": "Ολοκληρώθηκε",
    "failed": "Απέτυχε",
    "cancelled": "Ακυρώθηκε",
    "running": "Εκτελείται",
}
_RECURRENCE = {
    "none": "Μία φορά",
    "daily": "Καθημερινά",
    "weekly": "Εβδομαδιαία",
    "monthly": "Μηνιαία",
}


class SchedulePage(ListPage):
    """List scheduled issuance jobs and cancel the pending ones."""

    _COLS = [
        ("Εκτέλεση", "run_at"),
        ("Τίτλος", "title"),
        ("Είδος", "kind"),
        ("Επανάληψη", "recurrence"),
        ("Κατάσταση", "status"),
        ("Τελευταία εκτέλεση", "last_run_at"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Προγραμματισμός", columns=self._COLS,
            rows_key="jobs", stretch_col=1, parent=parent,
        )
        self.toolbar.insertWidget(
            self.toolbar.count() - 1,
            ui.button("Ακύρωση εργασίας", self._cancel, kind="danger", icon_name="cancel"),
        )

    def fetch(self, client: Any) -> dict[str, Any]:
        data = client.scheduled_jobs()
        # The endpoint returns the list under `jobs`; normalise the labels so the
        # table reads in Greek rather than in raw status codes.
        for row in data.get("jobs", []):
            row["status"] = _STATUS.get(str(row.get("status", "")), row.get("status", ""))
            row["recurrence"] = _RECURRENCE.get(
                str(row.get("recurrence", "")), row.get("recurrence", "")
            )
        return data

    def _cancel(self) -> None:
        client = self.client()
        row = self.selected_row()
        if client is None or row is None:
            return
        if row.get("status") != _STATUS["pending"]:
            self.status.setText("Μόνο εργασίες σε αναμονή ακυρώνονται.")
            return
        if QMessageBox.question(
            self, "Ακύρωση", "Ακύρωση της προγραμματισμένης έκδοσης;"
        ) != QMessageBox.StandardButton.Yes:
            return
        job_id = row.get("id")
        self._run(lambda: client.cancel_job(job_id), self._after_cancel, self._failed)

    def _after_cancel(self, result: dict) -> None:
        if result.get("success"):
            self.refresh()
        else:
            self._failed(result.get("error", "Η ακύρωση απέτυχε."))
