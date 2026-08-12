"""Native Στατιστικά: turnover per document type, cached like every dataset.

Cache-first: on open (and on period change) the page renders the DB-cached
snapshot instantly (``cached=True``, no AADE), then fires a live refresh that
write-through updates the same cache. This is the same instant-then-sync pattern
the Downloader uses, and — because the cache lives in the bridge DB — it works
identically offline, on the thin client and on the VPS.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base import EtimPage, fmt_money, parse_money
from .charts import BarChart, PieChart, breakdown_series

PERIODS: list[tuple[str, str]] = [
    ("month", "Τρέχων μήνας"),
    ("preMonth", "Προηγούμενος μήνας"),
    ("year", "Έτος"),
]


class StatsPage(EtimPage):
    go_back = Signal()

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._live_loaded = False
        box = QVBoxLayout(self)
        # Ίδια περιθώρια με τις υπόλοιπες σελίδες: χωρίς αυτά οι ετικέτες
        # της φόρμας ακουμπούσαν στο πλαϊνό μενού και κόβονταν τα γράμματα.
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Στατιστικά")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(QLabel("Περίοδος:"))
        self._period = QComboBox()
        for code, label in PERIODS:
            self._period.addItem(label, code)
        self._period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self._period)
        refresh = QPushButton("Ανανέωση")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        box.addLayout(top)

        self._summary = QLabel("")
        self._summary.setStyleSheet("font-weight:600;margin:4px 0;")
        box.addWidget(self._summary)

        # Γραφήματα πάνω από τον πίνακα: η κατανομή διαβάζεται με μια ματιά, τα
        # ακριβή νούμερα μένουν από κάτω.
        charts = QHBoxLayout()
        self._pie = PieChart()
        self._bars = BarChart()
        charts.addWidget(self._pie, 1)
        charts.addWidget(self._bars, 1)
        box.addLayout(charts, 1)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Τύπος", "Πλήθος", "Καθαρή αξία"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        box.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setObjectName("muted")
        box.addWidget(self._status)

    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        period = self._period.currentData()
        self._live_loaded = False
        self._status.setText("Φόρτωση από cache…")
        # 1) instant cached render, 2) live write-through refresh.
        self._run(lambda: client.statistics(period, cached=True), self._fill_cached, lambda m: None)
        self._run(lambda: client.statistics(period), self._fill_live, self._failed)

    def _fill_cached(self, data: dict[str, Any]) -> None:
        if self._live_loaded:
            return  # live already won; don't overwrite with a stale snapshot
        if data.get("breakdown") or data.get("total_count"):
            self._render(data, live=False)

    def _fill_live(self, data: dict[str, Any]) -> None:
        self._live_loaded = True
        self._render(data, live=True)

    def _render(self, data: dict[str, Any], *, live: bool) -> None:
        rows = data.get("breakdown", [])
        series = breakdown_series(rows)
        self._pie.set_data(series)
        self._bars.set_data(series)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(str(row.get("type", ""))))
            self._table.setItem(r, 1, QTableWidgetItem(str(row.get("count", ""))))
            self._table.setItem(r, 2, QTableWidgetItem(fmt_money(parse_money(row.get("value")))))
        self._summary.setText(
            f"Πλήθος παραστατικών: {data.get('total_count', 0)}   ·   "
            f"Καθαρός τζίρος: {fmt_money(parse_money(data.get('total_value')))} €"
        )
        synced = data.get("synced_at", "")
        origin = "ζωντανά" if live else "από cache"
        self._status.setText(
            f"Ενημερώθηκε ({origin})" + (f" · τελευταίος συγχρονισμός: {synced}" if synced else "")
        )

    def _failed(self, msg: str) -> None:
        # Live failed — keep whatever the cache rendered.
        if not self._table.rowCount():
            self._status.setText(f"Σφάλμα: {msg}")
        else:
            self._status.setText(f"Εμφανίζονται δεδομένα cache (η ζωντανή ανανέωση απέτυχε: {msg})")
