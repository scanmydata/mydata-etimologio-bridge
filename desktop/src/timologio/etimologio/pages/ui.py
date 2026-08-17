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

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...gui.documents_view import SortableItem
from ...gui.icons import icon
from ...gui.table_filter import TableColumnFilter
from ...gui.theme import CURRENT
from ...gui.widgets import persist_header
from .base import date_key, fmt_date, parse_money


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


def page_hint(text: str) -> QLabel:
    """Η επεξηγηματική γραμμή κάτω από τον τίτλο μιας σελίδας.

    Το web έχει μία τέτοια κάτω από κάθε τίτλο (``<p class="sub">``, 36 συνολικά)
    και εκεί μαθαίνει ο χρήστης τι κάνει η σελίδα. Στο native έλειπαν εντελώς.
    Σημειώνονται με ``help_line`` ώστε ο διακόπτης «Βοηθητικά μηνύματα» να τις
    σβήνει μαζί με τα tooltips.
    """
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    label.setProperty("help_line", True)
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
    # Το ← ζει στη μόνιμη μπάρα του κελύφους, μία φορά για όλη την εφαρμογή.
    # Υπήρχαν τρία διαφορετικά στυλ βέλους σε τρεις σελίδες.
    bar = QHBoxLayout()
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


def cell(text: str, sort_key: object | None = None) -> QTableWidgetItem:
    """Κελί που ταξινομείται σωστά.

    Χωρίς αυτό, ένα ποσό «1.234,56» ταξινομείται λεξικογραφικά (το «9,00»
    βγαίνει μετά το «1.234,56») και μια ημερομηνία «01/12/2025» πριν από την
    «05/01/2026». Δίνουμε ρητό κλειδί και κρατάμε το κείμενο ανέπαφο.
    """
    if sort_key is None:
        return QTableWidgetItem(text)
    return SortableItem(text, sort_key)


def money_cell(text: str) -> QTableWidgetItem:
    return cell(text, parse_money(text))


def date_cell(text: str) -> QTableWidgetItem:
    """Ταξινόμηση κατά (έτος, μήνας, ημέρα) — δέχεται dd/MM/yyyy και ISO.

    Το κείμενο εμφανίζεται πάντα σε ελληνική μορφή: η καρτέλα ανακατεύει
    ημερομηνίες της ΑΑΔΕ με ημερομηνίες της τοπικής βάσης, και δύο μορφές στην
    ίδια στήλη είναι απλώς λάθος.
    """
    key = date_key(text)
    if key == (0, 0, 0):
        return cell(str(text or ""), str(text or ""))
    return cell(fmt_date(text), key)


def make_sortable(
    table: QTableWidget,
    key: str,
    *,
    default_column: int | None = None,
    default_order: Qt.SortOrder = Qt.SortOrder.DescendingOrder,
    filter_columns: list[int] | None = None,
) -> TableColumnFilter | None:
    """Ταξινόμηση, μετακινούμενες στήλες που θυμούνται πλάτη, και φίλτρα.

    Η ίδια υποδομή που χρησιμοποιεί ο Downloader — δεν χρησιμοποιούνταν πουθενά
    στο e-Τιμολόγιο, οπότε κανένας πίνακας δεν ταξινομούνταν.

    Ο δείκτης ταξινόμησης ορίζεται **ρητά**: με ενεργή ταξινόμηση το Qt ξεκινά
    από φθίνουσα στην πρώτη στήλη, οπότε το πελατολόγιο άνοιγε ανάποδα χωρίς να
    το έχει ζητήσει κανείς. Όποιος θέλει «τα νεότερα πρώτα» το λέει με
    ``default_column`` + φθίνουσα σειρά.

    Το «ταξινόμησε ο χρήστης» κρατιέται σε **δική μας** σημαία. Το
    ``restoreState`` επαναφέρει και τον δείκτη ταξινόμησης, οπότε το να το
    θεωρήσεις επιλογή του χρήστη σημαίνει ότι ένα απλό σύρσιμο στήλης κλείδωνε
    για πάντα τη φθίνουσα προεπιλογή του Qt.

    **Η σειρά των βημάτων μετράει.** Το φίλτρο στήλης ΑΝΤΙΚΑΘΙΣΤΑ την κεφαλίδα
    (``setHorizontalHeader``), οπότε ό,τι έχει επαναφέρει πριν το
    ``persist_header`` — πλάτη, σειρά στηλών, δείκτης ταξινόμησης — πετιέται
    μαζί με την παλιά κεφαλίδα. Οι πίνακες του Downloader φτιάχνουν το φίλτρο
    πρώτα, για ακριβώς αυτόν τον λόγο.
    """
    prefs = QSettings()
    sorted_key = f"etimologio/{key}/sorted"
    table.setSortingEnabled(True)
    column_filter = TableColumnFilter(table, filter_columns) if filter_columns else None
    persist_header(table, prefs, f"etimologio/{key}")
    header = table.horizontalHeader()
    if not bool(prefs.value(sorted_key, False, type=bool)):
        column = default_column if default_column is not None else 0
        order = default_order if default_column is not None else Qt.SortOrder.AscendingOrder
        header.setSortIndicator(column, order)
        table.sortItems(column, order)
    # Σύνδεση ΜΕΤΑ την προεπιλογή: αλλιώς η ίδια μας η κλήση θα καταγραφόταν ως
    # επιλογή του χρήστη.
    header.sortIndicatorChanged.connect(lambda *_: prefs.setValue(sorted_key, True))
    # Πλάτη στηλών στο περιεχόμενο, ΜΟΝΟ αν δεν υπάρχει αποθηκευμένο state:
    # με το προεπιλεγμένο πλάτος των 100px, «2.1 - Τιμολόγιο Παροχής Υπηρεσιών»
    # και «ΜΑΡΚ 400014370878566» έβγαιναν ως «2.1 - …» και «ΜΑΡΚ …» — ο πίνακας
    # φαινόταν άδειος ενώ ήταν απλώς στριμωγμένος. Αν ο χρήστης έχει σύρει
    # στήλες, σεβόμαστε ό,τι όρισε.
    # ΠΑΝΤΑ, όχι μόνο την πρώτη φορά: το `persist_header` γράφει state ακόμη κι
    # όταν δεν το ζήτησε ο χρήστης (το `sectionResized` πυροδοτείται και στην
    # πρώτη διάταξη), οπότε ένα «μόνο αν δεν υπάρχει state» δεν έτρεχε ποτέ και
    # οι στήλες έμεναν στα 100px με κομμένο περιεχόμενο.
    _autosize_columns(table)
    return column_filter


def _autosize_columns(table: QTableWidget) -> None:
    """Πλάτη στο περιεχόμενο μία φορά, και μετά ελεύθερα για τον χρήστη.

    Κρατά όποια στήλη ήταν ήδη σε Stretch (το «γεμάτο» κελί της σελίδας).
    """
    header = table.horizontalHeader()
    stretched = [
        c for c in range(table.columnCount())
        if header.sectionResizeMode(c) == QHeaderView.ResizeMode.Stretch
    ]

    def apply() -> None:
        table.resizeColumnsToContents()
        for c in range(table.columnCount()):
            # Μια πολύ μακριά περιγραφή δεν πρέπει να σπρώξει τις υπόλοιπες έξω.
            table.setColumnWidth(c, min(max(table.columnWidth(c) + 12, 70), 420))
        for c in stretched:
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

    apply()
    # Και μετά από κάθε γέμισμα: τα πλάτη βγαίνουν από το περιεχόμενο, που δεν
    # υπάρχει ακόμη όταν χτίζεται ο πίνακας.
    table.model().rowsInserted.connect(lambda *_: QTimer.singleShot(0, apply))


def page(*, margins: tuple[int, int, int, int] = (16, 14, 16, 14), spacing: int = 12):
    """A page widget + its vertical layout, with the Downloader's page padding."""
    widget = QWidget()
    box = QVBoxLayout(widget)
    box.setContentsMargins(*margins)
    box.setSpacing(spacing)
    return widget, box


def open_file(path, parent=None) -> bool:
    """Ανοίγει ένα ΤΟΠΙΚΟ αρχείο με την εφαρμογή του συστήματος.

    Γιατί όχι ``QDesktopServices.openUrl``: όλο το e-Τιμολόγιο το χρησιμοποιούσε
    για τοπικά αρχεία (εγχειρίδιο, PDF παραστατικών, PDF καρτέλας) και **αν
    αποτύγχανε δεν συνέβαινε τίποτα** — ούτε μήνυμα, ούτε καταγραφή. Ο χρήστης
    πατούσε «Εγχειρίδιο» ή «Άνοιγμα PDF» και η οθόνη έμενε ίδια, που διαβάζεται
    ως «η σελίδα δεν λειτουργεί».

    Ο Downloader — το κομμάτι που δουλεύει αποδεδειγμένα — ανοίγει αρχεία με
    ``os.startfile``. Ίδιος δρόμος εδώ, με το ``QDesktopServices`` ως εφεδρεία
    και **ρητό μήνυμα** όταν αποτύχουν και τα δύο.
    """
    import logging
    import os
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    log = logging.getLogger(__name__)
    target = _Path(path)
    if not target.exists():
        _open_failed(target, "Το αρχείο δεν βρέθηκε.", parent)
        return False
    try:
        if os.name == "nt":
            os.startfile(str(target))  # noqa: S606
        elif _sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True
    except OSError as exc:
        log.warning("Το άνοιγμα του %s απέτυχε: %s", target, exc)

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    if QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
        return True
    _open_failed(target, "Δεν υπάρχει εφαρμογή συσχετισμένη με αυτόν τον τύπο αρχείου.", parent)
    return False


def _open_failed(target, reason: str, parent) -> None:
    from PySide6.QtWidgets import QMessageBox

    QMessageBox.warning(
        parent, "Άνοιγμα αρχείου",
        f"{reason}\n\nΔιαδρομή:\n{target}",
    )
