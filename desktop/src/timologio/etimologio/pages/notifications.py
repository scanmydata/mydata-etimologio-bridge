"""Native Ειδοποιήσεις: the issuance feed the accountant/admin watches."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal

from . import ui
from .base import ListPage, fmt_money, parse_money


class NotificationsPage(ListPage):
    """Issuance feed with read/unread handling."""

    #: Emitted with the unread count after every refresh, so the shell can badge.
    unread_changed = Signal(int)

    _COLS = [
        ("Ημ/νία", "created_at"),
        ("Παραστατικό", "doc_label"),
        ("Σειρά/ΑΑ", "series_aa"),
        ("ΜΑΡΚ", "mark"),
        ("Πελάτης", "buyer_name"),
        ("Ποσό", "amount"),
        ("Χρήστης", "actor_email"),
    ]

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(
            get_client, run, title="Ειδοποιήσεις", columns=self._COLS,
            rows_key="items", stretch_col=4, parent=parent,
        )
        self.toolbar.insertWidget(
            self.toolbar.count() - 1,
            ui.button("Σήμανση όλων ως αναγνωσμένων", self._read_all, icon_name="check"),
        )

    def fetch(self, client: Any) -> dict[str, Any]:
        data = client.notifications()
        for row in data.get("items", []):
            series, aa = row.get("series", ""), row.get("aa", "")
            row["series_aa"] = f"{series}/{aa}" if series or aa else ""
            amount = row.get("amount_total")
            row["amount"] = f"{fmt_money(parse_money(amount))} €" if amount is not None else ""
            if not row.get("doc_label"):
                row["doc_label"] = row.get("doc_type", "")
        return data

    def _fill(self, data: dict[str, Any]) -> None:
        super()._fill(data)
        rows = data.get("items", [])
        unread = sum(1 for r in rows if not int(r.get("is_read", 0) or 0))
        # Unread rows read bolder, the same cue the Downloader uses for new items.
        for r, row in enumerate(rows):
            if int(row.get("is_read", 0) or 0):
                continue
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is not None:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
        self.status.setText(f"{len(rows)} ειδοποιήσεις · {unread} μη αναγνωσμένες")
        self.unread_changed.emit(unread)

    def _read_all(self) -> None:
        client = self.client()
        if client is None:
            return
        self._run(client.mark_all_read, lambda _r: self.refresh(), self._failed)
