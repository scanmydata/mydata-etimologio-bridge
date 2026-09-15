"""Timologio Downloader: ζουμ προεπισκόπησης που δουλεύει, και Χρονοπρογραμματισμός.

* **Έτοιμες τιμές ζουμ χωρίς αποτέλεσμα.** Το Qt γράφει «400,0%» με την
  ελληνική υποδιαστολή αλλά το ξαναδιαβάζει με ``toFloat`` (τελεία): η ανάγνωση
  αποτύγχανε σιωπηλά και το ζουμ έμενε 1.0. Επαληθεύτηκε: πριν 1.0, μετά 4.0.
* **Ctrl+ροδέλα.** Η προεπισκόπηση του Qt δεν το υποστηρίζει καθόλου.
* **Πελάτες του προγράμματος** με αλφαβητική σειρά (χωρίς τόνους/κεφαλαία).
* **Σκοτεινό θέμα:** τα κουτιά είχαν το native γκρι περίγραμμα, αόρατο.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QGraphicsView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def greek(app):
    from PySide6.QtCore import QLocale

    from timologio.gui import i18n

    saved = QLocale()
    t = i18n.install(app)
    yield app
    app.removeTranslator(t)
    QLocale.setDefault(saved)


def _dialog():
    from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog, QPrintPreviewWidget

    from timologio.gui import printing

    printer = QPrinter()
    dialog = QPrintPreviewDialog(printer)
    dialog.paintRequested.connect(lambda _p: None)
    printing._fix_toolbar_icons(dialog)
    printing._fix_zoom(dialog)
    dialog._printer = printer  # noqa: SLF001
    return dialog, dialog.findChild(QPrintPreviewWidget), dialog.findChild(QComboBox)


def test_parse_zoom_accepts_comma_and_dot():
    from timologio.gui.printing import _parse_zoom

    assert _parse_zoom("400,0%") == pytest.approx(4.0)
    assert _parse_zoom("12.5%") == pytest.approx(0.125)
    assert _parse_zoom(" 80 ") == pytest.approx(0.8)
    assert _parse_zoom("5000%") == pytest.approx(10.0)
    assert _parse_zoom("abc") is None


def test_preset_zoom_changes_the_preview(greek):
    dialog, preview, combo = _dialog()
    try:
        idx = combo.findText("400,0%")
        assert idx >= 0, [combo.itemText(i) for i in range(combo.count())]
        combo.setCurrentIndex(idx)
        combo.textActivated.emit(combo.itemText(idx))
        assert preview.zoomFactor() == pytest.approx(4.0)
        assert combo.currentText() == "400,0%"
    finally:
        dialog.deleteLater()


def test_ctrl_wheel_zooms(greek):
    dialog, preview, combo = _dialog()
    try:
        view = dialog.findChild(QGraphicsView)
        before = preview.zoomFactor()

        def wheel(dy, mods):
            ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, dy),
                             Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(view.viewport(), ev)

        wheel(120, Qt.KeyboardModifier.ControlModifier)
        up = preview.zoomFactor()
        assert up > before
        wheel(-120, Qt.KeyboardModifier.ControlModifier)
        assert preview.zoomFactor() < up
        # Χωρίς Ctrl η ροδέλα απλώς κυλά.
        now = preview.zoomFactor()
        wheel(120, Qt.KeyboardModifier.NoModifier)
        assert preview.zoomFactor() == pytest.approx(now)
    finally:
        dialog.deleteLater()


def test_schedule_clients_are_alphabetical(app):
    from timologio.gui.schedule_page import SchedulePage

    page = SchedulePage()
    page.set_clients([("999", "Ωμέγα ΑΕ"), ("111", "αλφα ΟΕ"), ("333", ""),
                      ("555", "Έψιλον ΙΚΕ"), ("222", "Βήτα")])
    rows = [page.list.item(i).text() for i in range(page.list.count())]
    assert rows == ["111 — αλφα ΟΕ", "222 — Βήτα", "555 — Έψιλον ΙΚΕ", "999 — Ωμέγα ΑΕ", "333"]


def test_dark_theme_draws_group_and_list_borders():
    from timologio.gui import theme

    qss = theme.build(theme.DARK)
    group = qss[qss.index("QGroupBox {{".replace("{{", "{")):]
    assert f"border: 1px solid {theme.DARK.line}" in group[:200]
    assert "QGroupBox::title" in qss
    assert "QListWidget#scheduleClients {" in qss
    src = (theme.__file__).replace("theme.py", "schedule_page.py")
    with open(src, encoding="utf-8") as fh:
        assert 'self.list.setObjectName("scheduleClients")' in fh.read()
