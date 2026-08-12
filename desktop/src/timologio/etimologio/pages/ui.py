"""Shared look-and-feel helpers so e-Τιμολόγιο matches the Downloader.

The app-wide stylesheet (``gui/theme.py``) already styles plain widgets; what it
keys off is **object names** (``card``, ``muted``, ``hint``, ``primary``,
``danger``, ``tile``, ``stat``…). These helpers build the same shapes the
Downloader pages use, so both halves of the product read as one app — and they
follow the theme when the user flips light/dark, because nothing here hardcodes
a colour.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...gui.icons import icon
from ...gui.theme import CURRENT


def muted(text: str = "") -> QLabel:
    """Secondary text (status lines, counts) in the theme's muted colour.

    Wraps by default: an unwrapped explanatory sentence reports a very wide
    sizeHint, which pushed the whole card past the right edge of the page
    instead of flowing onto a second line.
    """
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def hint(text: str = "") -> QLabel:
    """Accent-coloured helper text, as used under Downloader toolbars."""
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size:16px;font-weight:700;")
    return label


def card(*, spacing: int = 10, margins: tuple[int, int, int, int] = (14, 14, 14, 14)):
    """A rounded panel (``QFrame#card``) plus its layout — the Downloader's
    basic building block. Returns ``(frame, layout)``."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("line")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def button(
    text: str,
    on_click: Callable[[], None] | None = None,
    *,
    kind: str = "",
    icon_name: str = "",
    tip: str = "",
) -> QPushButton:
    """A themed button. ``kind`` is ``primary``/``danger``/``linkButton``/''."""
    btn = QPushButton(f"  {text}" if icon_name else text)
    if kind:
        btn.setObjectName(kind)
    if icon_name:
        colour = CURRENT.bad if kind == "danger" else CURRENT.muted
        btn.setIcon(icon(icon_name, colour))
    if tip:
        btn.setToolTip(tip)
    if on_click is not None:
        btn.clicked.connect(lambda *_: on_click())
    return btn


def page_header(text: str, on_back: Callable[[], None] | None = None) -> QHBoxLayout:
    """The standard page top bar: optional back arrow, then the page title.

    Callers keep adding widgets to the returned layout (it already ends with a
    stretch, so use ``insertWidget(layout.count() - 1, w)`` or just ``addWidget``
    for right-aligned tools).
    """
    bar = QHBoxLayout()
    if on_back is not None:
        back = QPushButton()
        back.setIcon(icon("back", CURRENT.muted))
        back.setToolTip("Πίσω")
        back.setFixedWidth(38)
        back.clicked.connect(lambda *_: on_back())
        bar.addWidget(back)
    bar.addWidget(title(text))
    bar.addStretch(1)
    return bar


def stat_tile(value: str, label: str) -> QFrame:
    """A KPI tile like the Downloader's control panel: big accent number + caption."""
    frame, box = card(spacing=2, margins=(14, 10, 14, 10))
    number = QLabel(value)
    number.setObjectName("stat")
    caption = QLabel(label)
    caption.setObjectName("statLabel")
    box.addWidget(number)
    box.addWidget(caption)
    frame._value = number  # type: ignore[attr-defined]  — so callers can update it
    return frame


def set_tile_value(tile: QFrame, value: str) -> None:
    getattr(tile, "_value").setText(value)


def nav_tile(label: str, description: str, icon_name: str, on_click: Callable[[], None]) -> QPushButton:
    """A large launcher tile (``QPushButton#tile``) — the Downloader's home look."""
    btn = QPushButton()
    btn.setObjectName("tile")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(74)
    btn.clicked.connect(lambda *_: on_click())

    row = QHBoxLayout(btn)
    row.setContentsMargins(14, 10, 14, 10)
    row.setSpacing(12)
    glyph = QLabel()
    glyph.setPixmap(icon(icon_name, CURRENT.accent).pixmap(26, 26))
    row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignVCenter)

    text = QVBoxLayout()
    text.setSpacing(1)
    name = QLabel(label)
    name.setStyleSheet("font-weight:600;")
    text.addWidget(name)
    text.addWidget(muted(description))
    row.addLayout(text, 1)
    return btn


def table(headers: list[str], *, stretch: int = -1, checkable: bool = False) -> QTableWidget:
    """A read-only, row-selecting table styled like the Downloader's lists."""
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    if not checkable:
        widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.verticalHeader().setVisible(False)
    widget.horizontalHeader().setHighlightSections(False)
    if stretch >= 0:
        from PySide6.QtWidgets import QHeaderView

        widget.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    return widget


def page(*, margins: tuple[int, int, int, int] = (16, 14, 16, 14), spacing: int = 12):
    """A page widget + its vertical layout, with the Downloader's page padding."""
    widget = QWidget()
    box = QVBoxLayout(widget)
    box.setContentsMargins(*margins)
    box.setSpacing(spacing)
    return widget, box
