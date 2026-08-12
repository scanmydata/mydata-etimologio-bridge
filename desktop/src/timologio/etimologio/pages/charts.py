"""Γραφήματα ζωγραφισμένα με QPainter.

Το QtCharts μένει εκτός του πακέτου (το ίδιο και τα matplotlib/numpy): θα
πρόσθετε δεκάδες MB στον installer για δύο γραφήματα. Δύο widget με ``paintEvent``
κάνουν τη δουλειά και ακολουθούν το θέμα, γιατί διαβάζουν τα χρώματα από το
``theme.CURRENT`` σε κάθε βάψιμο — άρα αλλάζουν μαζί με το light/dark.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...gui.theme import CURRENT

#: Απόχρωση ανά φέτα. Παράγονται από το accent του θέματος ώστε η παλέτα να
#: παραμένει συνεπής σε φωτεινό και σκοτεινό.
_HUE_STEPS = (0, 34, 68, 102, 136, 170, 204, 238, 272, 306)


def slice_colour(index: int) -> QColor:
    base = QColor(CURRENT.accent)
    hue = (base.hue() + _HUE_STEPS[index % len(_HUE_STEPS)]) % 360
    saturation = max(90, base.saturation())
    value = base.value()
    # Εναλλάξ πιο ανοιχτό/σκούρο, ώστε γειτονικές φέτες να ξεχωρίζουν και σε
    # ασπρόμαυρη εκτύπωση.
    if index % 2:
        value = min(255, int(value * 1.18))
    return QColor.fromHsv(hue, saturation, value)


class _ChartBase(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, float]] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        """``[(ετικέτα, αξία)]`` — μηδενικά και αρνητικά αγνοούνται."""
        self._data = [(str(label), float(value)) for label, value in data if float(value) > 0]
        self.update()

    def _empty(self, painter: QPainter, message: str = "Χωρίς δεδομένα") -> None:
        painter.setPen(QPen(QColor(CURRENT.muted)))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, message)


class PieChart(_ChartBase):
    """Κατανομή τζίρου ανά τύπο παραστατικού."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._data:
            self._empty(painter)
            return

        total = sum(value for _label, value in self._data)
        side = min(self.height() - 16, self.width() * 0.45)
        box = QRectF(8, (self.height() - side) / 2, side, side)

        start = 90 * 16  # ξεκινά στις 12 η ώρα, δεξιόστροφα
        for index, (_label, value) in enumerate(self._data):
            span = int(-360 * 16 * value / total)
            painter.setBrush(slice_colour(index))
            painter.setPen(QPen(QColor(CURRENT.panel), 2))
            painter.drawPie(box, start, span)
            start += span

        # --- υπόμνημα ------------------------------------------------------
        legend_x = box.right() + 18
        y = box.top()
        font = QFont(painter.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 0.5))
        painter.setFont(font)
        step = painter.fontMetrics().height() + 6
        for index, (label, value) in enumerate(self._data):
            if y + step > self.height():
                break
            painter.setBrush(slice_colour(index))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(legend_x, y + 3, 10, 10))
            painter.setPen(QPen(QColor(CURRENT.txt)))
            share = value / total * 100
            painter.drawText(
                QRectF(legend_x + 16, y, self.width() - legend_x - 20, step),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{label} — {share:.1f}%",
            )
            y += step


class BarChart(_ChartBase):
    """Οριζόντιες ράβδοι με το μερίδιο κάθε τύπου."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(140)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._data:
            self._empty(painter)
            return

        biggest = max(value for _label, value in self._data)
        metrics = painter.fontMetrics()
        row_h = metrics.height() + 10
        label_w = min(
            self.width() * 0.35,
            max(metrics.horizontalAdvance(label) for label, _ in self._data) + 12,
        )
        y = 4.0
        for index, (label, value) in enumerate(self._data):
            if y + row_h > self.height():
                break
            painter.setPen(QPen(QColor(CURRENT.txt)))
            painter.drawText(
                QRectF(0, y, label_w - 8, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                label,
            )
            track = self.width() - label_w - 8
            width = max(2.0, track * value / biggest)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(CURRENT.line))
            painter.drawRoundedRect(QRectF(label_w, y + 4, track, row_h - 12), 4, 4)
            painter.setBrush(slice_colour(index))
            painter.drawRoundedRect(QRectF(label_w, y + 4, width, row_h - 12), 4, 4)
            y += row_h


def breakdown_series(rows: list[dict[str, Any]], *, top: int = 8) -> list[tuple[str, float]]:
    """Μετατρέπει το ``breakdown`` των στατιστικών σε σειρά για τα γραφήματα.

    Πάνω από ``top`` τύπους η πίτα γίνεται δυσανάγνωστη, οπότε η ουρά μαζεύεται
    σε «Λοιπά» αντί να κοπεί — αλλιώς τα ποσοστά δεν θα άθροιζαν στο 100%.
    """
    from .base import parse_money

    series = [
        (str(row.get("type") or "—"), parse_money(row.get("value")))
        for row in rows
    ]
    series = [(label, value) for label, value in series if value > 0]
    series.sort(key=lambda item: item[1], reverse=True)
    if len(series) > top:
        rest = sum(value for _label, value in series[top:])
        series = series[:top] + [("Λοιπά", rest)]
    return series
