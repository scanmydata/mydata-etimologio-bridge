"""0.4.45 — εκτύπωση: ο οριζόντιος προσανατολισμός της προεπισκόπησης δεν
χάνεται στον διάλογο των Windows, και «Εμπρός-πίσω» με κάθε παραστατικό σε
δικό του φύλλο. Ημερομηνίες: τα ημερολόγια μένουν μέσα στην ενεργή χρήση."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QSettings  # noqa: E402
from PySide6.QtGui import QPageLayout, QPainter, QPdfWriter  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from timologio.gui import printing  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "timologio"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pdf(path: Path, pages: int) -> Path:
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    for i in range(pages):
        if i:
            writer.newPage()
        painter.drawText(100, 100, f"σελίδα {i + 1}")
    painter.end()
    return path


def _prefs(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


# ===========================================================================
# Εμπρός-πίσω
# ===========================================================================
def test_each_document_starts_on_its_own_sheet():
    # Δισέλιδο + μονοσέλιδο + μονοσέλιδο.
    assert printing.layout_pages([2, 1, 1], duplex=True) == [
        (0, 0), (0, 1), (1, 0), None, (2, 0)]
    # Δύο μονοσέλιδα: δύο φύλλα, όχι το ένα στην πλάτη του άλλου.
    assert printing.layout_pages([1, 1], duplex=True) == [(0, 0), None, (1, 0)]
    # Τρισέλιδο στο τέλος: καμία περιττή λευκή.
    assert printing.layout_pages([3], duplex=True) == [(0, 0), (0, 1), (0, 2)]
    # Μονή όψη: καμία λευκή.
    assert printing.layout_pages([2, 1, 1], duplex=False) == [
        (0, 0), (0, 1), (1, 0), (2, 0)]


class _WindowsDialog:
    """Ο διάλογος των Windows: ξαναγράφει τις ρυθμίσεις με τις προεπιλογές του
    οδηγού (κατακόρυφο) — εδώ τυπώνει σε PDF για να μετρηθεί το αποτέλεσμα."""

    out: Path
    duplex = QPrinter.DuplexMode.DuplexNone
    answer = QDialog.DialogCode.Accepted

    def __init__(self, printer: QPrinter, parent=None) -> None:
        self.printer = printer

    def setWindowTitle(self, _t): ...

    def exec(self):
        self.printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        self.printer.setOutputFileName(str(self.out))
        self.printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        self.printer.setDuplex(self.duplex)
        return self.answer


class _DuplexPrinter(QPrinter):
    """Ο PDF «εκτυπωτής» αγνοεί το duplex· εδώ το κρατάμε όπως ένας πραγματικός."""

    def __init__(self) -> None:
        super().__init__()
        self._duplex = QPrinter.DuplexMode.DuplexNone

    def setDuplex(self, mode) -> None:  # noqa: N802
        self._duplex = mode

    def duplex(self):
        return self._duplex


def _job(app, tmp_path, counts, prefs=None):
    docs = []
    for i, n in enumerate(counts):
        doc = QPdfDocument()
        doc.load(str(_pdf(tmp_path / f"d{i}.pdf", n)))
        docs.append(doc)
    return printing.PrintJob(docs, prefs or _prefs(tmp_path))


def _printed(path: Path) -> QPdfDocument:
    doc = QPdfDocument()
    doc.load(str(path))
    return doc


def test_landscape_from_the_preview_survives_the_windows_dialog(app, tmp_path, monkeypatch):
    _WindowsDialog.out = tmp_path / "out.pdf"
    monkeypatch.setattr(printing, "QPrintDialog", _WindowsDialog)
    job = _job(app, tmp_path, [1])
    printer = QPrinter()
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)   # η προεπισκόπηση
    assert job.print_to(printer)
    out = _printed(_WindowsDialog.out)
    size = out.pagePointSize(0)
    assert size.width() > size.height(), "τυπώθηκε κατακόρυφα"
    assert _prefs(tmp_path).value("print/landscape", type=bool) is True
    job.close()


def test_duplex_from_our_switch_inserts_the_blanks(app, tmp_path, monkeypatch):
    _WindowsDialog.out = tmp_path / "out.pdf"
    monkeypatch.setattr(printing, "QPrintDialog", _WindowsDialog)
    job = _job(app, tmp_path, [2, 1, 1])
    job.duplex = True
    printer = _DuplexPrinter()
    assert job.print_to(printer)
    assert printer.duplex() == QPrinter.DuplexMode.DuplexAuto
    assert _printed(_WindowsDialog.out).pageCount() == 5      # 2 + 1 + λευκή + 1
    assert _prefs(tmp_path).value("print/duplex", type=bool) is True
    job.close()


def test_duplex_chosen_in_windows_is_also_smart(app, tmp_path, monkeypatch):
    """Ο εκτυπωτής τυπώνει εμπρός-πίσω από προεπιλογή: δύο μονοσέλιδα
    πρέπει να βγουν σε δύο φύλλα."""
    _WindowsDialog.out = tmp_path / "out.pdf"
    monkeypatch.setattr(printing, "QPrintDialog", _WindowsDialog)
    monkeypatch.setattr(_WindowsDialog, "duplex", QPrinter.DuplexMode.DuplexLongSide)
    job = _job(app, tmp_path, [1, 1])
    printer = _DuplexPrinter()
    assert job.print_to(printer)
    assert _printed(_WindowsDialog.out).pageCount() == 3
    assert printer.duplex() == QPrinter.DuplexMode.DuplexAuto
    job.close()


def test_single_sided_prints_exactly_the_pages(app, tmp_path, monkeypatch):
    _WindowsDialog.out = tmp_path / "out.pdf"
    monkeypatch.setattr(printing, "QPrintDialog", _WindowsDialog)
    job = _job(app, tmp_path, [2, 1, 1])
    assert job.print_to(QPrinter())
    assert _printed(_WindowsDialog.out).pageCount() == 4
    job.close()


def test_cancel_prints_nothing(app, tmp_path, monkeypatch):
    _WindowsDialog.out = tmp_path / "never.pdf"
    monkeypatch.setattr(printing, "QPrintDialog", _WindowsDialog)
    monkeypatch.setattr(_WindowsDialog, "answer", QDialog.DialogCode.Rejected)
    job = _job(app, tmp_path, [1])
    assert job.print_to(QPrinter()) is False
    assert not _WindowsDialog.out.exists()
    job.close()


def test_the_preview_has_our_print_and_duplex_buttons(app, tmp_path):
    job = _job(app, tmp_path, [1, 1])
    printer = QPrinter()
    dialog = QPrintPreviewDialog(printer)
    printing._fix_toolbar_icons(dialog)
    _toolbar, native = printing._native_print_action(dialog)
    duplex, act = printing._install_print_controls(dialog, printer, job, lambda: None)
    assert not native.isVisible()
    assert act.text() == "Εκτύπωση" and duplex.isCheckable()
    duplex.setChecked(True)
    assert job.duplex is True and job.slots() == [(0, 0), None, (1, 0)]
    dialog.deleteLater()
    job.close()


def test_the_choices_are_remembered(app, tmp_path):
    prefs = _prefs(tmp_path)
    prefs.setValue("print/duplex", True)
    prefs.setValue("print/landscape", True)
    job = _job(app, tmp_path, [1], prefs)
    assert job.duplex and job.landscape
    job.close()


# ===========================================================================
# Ημερολόγια μέσα στη χρήση
# ===========================================================================
def test_sync_dates_stay_inside_the_fiscal_year(app):
    from timologio.gui.sync_page import SyncPage

    page = SyncPage(QSettings("scanmydata-test", "sync45"))
    page.set_fiscal_year(2025)
    for edit in (page.date_from, page.date_to):
        assert edit.minimumDate() == QDate(2025, 1, 1)
        assert edit.maximumDate() == QDate(2025, 12, 31)
    # Μήνας/τρίμηνο μετρούν από σήμερα: μόνο στην τρέχουσα χρήση.
    assert not page._preset_buttons["month"].isEnabled()
    page.set_fiscal_year(date.today().year)
    assert page._preset_buttons["month"].isEnabled()
    assert page.date_to.maximumDate() == QDate(date.today().year, 12, 31)
    page.close()


def test_previous_year_changes_the_active_year(app):
    from timologio.gui.sync_page import SyncPage

    page = SyncPage(QSettings("scanmydata-test", "sync45"))
    page.set_fiscal_year(2026)
    asked: list[int] = []
    page.fiscal_year_requested.connect(asked.append)
    page._apply_preset("prev_year")
    assert asked == [2025]
    page.close()


def test_documents_dates_follow_the_year(app, tmp_path):
    from timologio.config import Settings
    from timologio.gui.documents_view import DocumentsView

    view = DocumentsView(Settings(data_dir=tmp_path), _prefs(tmp_path))
    view.set_year(2024)
    assert view.date_from.minimumDate() == QDate(2024, 1, 1)
    assert view.date_to.maximumDate() == QDate(2024, 12, 31)
    view.set_year(None)
    assert view.date_from.minimumDate() == QDate(2000, 1, 1)
    view.close()


def test_the_main_window_switches_the_year_for_the_preset():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "self.sync_page.fiscal_year_requested.connect(" in src


def test_the_manual_explains_it():
    manual = (SRC / "gui" / "manual.py").read_text(encoding="utf-8")
    assert "Εμπρός-πίσω" in manual and "οριζόντιο" in manual
