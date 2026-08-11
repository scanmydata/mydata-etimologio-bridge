"""Shared plumbing for the native e-Τιμολόγιο pages."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: Injected worker: ``run(fn, on_ok, on_err)`` runs ``fn`` off the UI thread and
#: delivers the result on the main thread. The shell passes its ``QThreadPool``
#: helper; tests pass a synchronous stub.
RunFn = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[str], None]], None]

#: Zero-arg accessor for the live client (may be ``None`` before login).
ClientFn = Callable[[], Any]

_MONEY_RE = re.compile(r"[^0-9,.\-]")


def parse_money(value: Any) -> float:
    """Parse a Greek-formatted money string (``1.234,56 €``) to a float.

    Returns ``0.0`` for blanks or garbage — totals must never raise while a
    table is being filled from whatever the AADE HTML scrape produced.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = _MONEY_RE.sub("", str(value or "")).strip()
    if not text:
        return 0.0
    # Greek grouping: dot = thousands, comma = decimals. Drop dots, comma→dot.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def fmt_money(value: float) -> str:
    """Format a float as ``1.234,56`` (Greek grouping) for display."""
    return f"{value:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


class EtimPage(QWidget):
    """Base for a native page: gives access to the client and the worker."""

    def __init__(
        self,
        get_client: ClientFn,
        run: RunFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_client = get_client
        self._run = run

    def client(self) -> Any:
        return self._get_client()


class ListPage(EtimPage):
    """A back-bar + toolbar + table + status list page.

    Subclasses set ``columns``/``rows_key``, implement :meth:`fetch`, and add
    their own buttons to ``self.toolbar`` (a ``QHBoxLayout``). The table, refresh,
    row access and status line are handled here.
    """

    go_back = Signal()

    def __init__(
        self,
        get_client: ClientFn,
        run: RunFn,
        *,
        title: str,
        columns: list[tuple[str, str]],
        rows_key: str,
        stretch_col: int = -1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(get_client, run, parent)
        self._columns = columns
        self._rows_key = rows_key
        self._rows: list[dict[str, Any]] = []

        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)
        self.toolbar = QHBoxLayout()
        back = QPushButton("←")
        back.setToolTip("Πίσω")
        back.setFixedWidth(36)
        back.clicked.connect(self.go_back.emit)
        self.toolbar.addWidget(back)
        label = QLabel(title)
        label.setStyleSheet("font-size:16px;font-weight:600;")
        self.toolbar.addWidget(label)
        self.toolbar.addStretch(1)
        refresh = QPushButton("Ανανέωση")
        refresh.clicked.connect(self.refresh)
        self.toolbar.addWidget(refresh)
        box.addLayout(self.toolbar)

        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([h for h, _ in columns])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        if stretch_col >= 0:
            self.table.horizontalHeader().setSectionResizeMode(
                stretch_col, QHeaderView.ResizeMode.Stretch
            )
        box.addWidget(self.table, 1)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        box.addWidget(self.status)
        self._box = box

    # subclasses override -------------------------------------------------
    def fetch(self, client: Any) -> dict[str, Any]:
        raise NotImplementedError

    # shared --------------------------------------------------------------
    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        self.status.setText("Φόρτωση…")
        self._run(lambda: self.fetch(client), self._fill, self._failed)

    def _fill(self, data: dict[str, Any]) -> None:
        self._rows = list(data.get(self._rows_key, []))
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, (_, key) in enumerate(self._columns):
                self.table.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))
        self.status.setText(f"{len(self._rows)} εγγραφές")

    def _failed(self, msg: str) -> None:
        self.status.setText(f"Σφάλμα: {msg}")

    def selected_row(self) -> dict[str, Any] | None:
        idx = self.table.currentRow()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None
