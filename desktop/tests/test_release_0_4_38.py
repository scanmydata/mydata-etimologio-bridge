"""Τρία που «δεν δούλευαν» — και γιατί δεν τα έπιασαν τα προηγούμενα tests.

* **Δεξί κλικ στους Πελάτες.** Το `cell_menu_actions` είχε εισαχθεί ΜΕΣΑ στη
  μέθοδο που στήνει τον πίνακα, ενώ το μενού χτίζεται σε άλλη μέθοδο: NameError
  — και έπεφτε ΟΛΟΚΛΗΡΟ το μενού (επεξεργασία, διαγραφή, τα πάντα), όχι μόνο οι
  νέες ενέργειες. Τα tests της 0.4.37 δοκίμαζαν τη βοηθητική συνάρτηση, ποτέ τον
  πραγματικό χειριστή — γι' αυτό εδώ καλούνται οι ΙΔΙΟΙ οι χειριστές.

* **«Μόνο οι επιλεγμένοι πελάτες».** Το κουτάκι κρυβόταν όταν οι επιλεγμένοι δεν
  είχαν εκκρεμή — και έμοιαζε σαν να μην υπάρχει η δυνατότητα.

* **Φωτισμένη γραμμή μενού.** Άναβε μόνο όταν ΞΕΚΙΝΟΥΣΕ η λήψη, όχι με το
  πάτημα· όποιος ακύρωνε τον διάλογο δεν έβλεπε ποτέ τίποτα.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QMenu,
    QTableWidgetItem,
)

from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.models import Client, Direction, Document  # noqa: E402
from timologio.repo import upsert_client, upsert_document  # noqa: E402

SRC = Path(__file__).resolve().parents[2] / "desktop" / "src" / "timologio"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path: Path, monkeypatch):
    """Παράθυρο με δύο πελάτες και πραγματική ουρά εκκρεμών (2 και 4 PDF)."""
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    conn = init_db(tmp_path / "timologio.db")
    crypto = Crypto(tmp_path / ".enckey")
    for i, (vat, label) in enumerate([("803105689", "ΑΛΦΑ ΟΕ"), ("104836713", "ΒΗΤΑ ΑΕ")], 1):
        cid = upsert_client(conn, Client(vat=vat, label=label, mydata_user="u",
                                         mydata_key="k" * 32), crypto)
        for n in range(i * 2):
            upsert_document(conn, cid, Document(
                mark=f"{i}{n:03d}", invoice_type="1.1", issuer_vat="076762490",
                counter_vat=vat, net_value=1.0, vat_amount=0.0, total_value=1.0,
                issue_date="2026-08-28", direction=Direction.INCOMING,
                downloading_invoice_url=f"https://x.gr/{i}{n}"))
    conn.commit()
    conn.close()

    from timologio.gui.main_window import MainWindow

    # Καμία modal σύνοψη μέσα σε test: θα περίμενε για πάντα κάποιον να πατήσει ΟΚ.
    monkeypatch.setattr(MainWindow, "_show_sync_summary", lambda *a, **k: None)
    monkeypatch.setattr(MainWindow, "_notify_done", lambda *a, **k: None)
    win = MainWindow(force_show=True)
    yield win
    # Ένα νήμα που έμεινε ζωντανό κάνει την επόμενη κλήση να βγάλει το modal
    # «Εκτελείται ήδη» — και το επόμενο test κολλάει χωρίς να εξηγεί γιατί.
    win._teardown()
    win.close()


def _grab_menu(app, store: dict, key: str):
    def go() -> None:
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMenu) and widget.isVisible():
                store[key] = [a.text() for a in widget.actions() if a.text()]
                widget.close()

    return go


def _row_of(window, vat: str) -> int:
    for row in range(window.table.rowCount()):
        if window.table.item(row, 1).text() == vat:
            return row
    raise AssertionError(vat)


# ===========================================================================
# 1. Το μενού δεξιού κλικ ανοίγει ΠΡΑΓΜΑΤΙΚΑ
# ===========================================================================
def test_the_clients_menu_opens_with_old_and_new_actions(app, window):
    seen: dict[str, list[str]] = {}
    QTimer.singleShot(200, _grab_menu(app, seen, "clients"))
    window._context_menu(window.table.visualItemRect(window.table.item(0, 1)).center())
    labels = seen.get("clients", [])
    assert "Επεξεργασία…" in labels                       # ό,τι υπήρχε, υπάρχει
    assert any(a.startswith("Αντιγραφή «") for a in labels)
    assert "Αντιγραφή ολόκληρης της γραμμής" in labels
    assert any(a.startswith("Φίλτρο: ") for a in labels)


def test_the_sync_and_documents_menus_open(app, window):
    seen: dict[str, list[str]] = {}
    sync = window.sync_page
    sync.table.setRowCount(1)
    for col in range(sync.table.columnCount()):
        sync.table.setItem(0, col, QTableWidgetItem(f"κελί{col}"))
    QTimer.singleShot(200, _grab_menu(app, seen, "sync"))
    sync.table.customContextMenuRequested.emit(
        sync.table.visualItemRect(sync.table.item(0, 1)).center()
    )
    assert any(a.startswith("Αντιγραφή «") for a in seen.get("sync", []))

    docs = window.docs
    docs.table.setRowCount(1)
    for col in range(docs.table.columnCount()):
        docs.table.setItem(0, col, QTableWidgetItem(f"κ{col}"))
    QTimer.singleShot(200, _grab_menu(app, seen, "docs"))
    docs._table_context_menu(docs.table.visualItemRect(docs.table.item(0, 2)).center())
    assert any(a.startswith("Αντιγραφή «") for a in seen.get("docs", []))


def test_the_helper_is_imported_where_the_menu_is_built():
    """Τοπικό import σε ΑΛΛΗ μέθοδο = NameError τη στιγμή του δεξιού κλικ."""
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    head = src[:src.index("class MainWindow")]
    assert "from .table_filter import cell_menu_actions" in head
    build = src[src.index("self._client_col_filter = TableColumnFilter"):]
    build = build[:build.index("def ")]
    assert "cell_menu_actions" not in build


# ===========================================================================
# 2. Η επιλογή πελατών στη «Λήψη εκκρεμών»
# ===========================================================================
def _run_backlog(app, window, monkeypatch, *, accept=True, uncheck=False):
    """Τρέχει τον ΠΡΑΓΜΑΤΙΚΟ χειριστή με ψεύτικο worker και απαντά στον διάλογο."""
    import timologio.gui.main_window as mw
    from timologio.gui import workers

    captured: dict[str, object] = {}

    class FakeWorker(workers.SyncWorker):
        def __init__(self, vats, *a, **kw):
            captured["vats"] = list(vats)
            captured["backlog_only"] = kw.get("backlog_only")
            super().__init__(vats, *a, **kw)

        def run(self) -> None:
            self.finished.emit(True)

    monkeypatch.setattr(mw, "SyncWorker", FakeWorker)

    def answer() -> None:
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                box = widget.findChild(QCheckBox)
                captured["checkbox"] = (box.text(), box.isVisible(), box.isChecked(),
                                        box.isEnabled()) if box else None
                if uncheck and box is not None:
                    box.setChecked(False)
                buttons = widget.findChild(QDialogButtonBox)
                key = (QDialogButtonBox.StandardButton.Yes if accept
                       else QDialogButtonBox.StandardButton.Cancel)
                buttons.button(key).click()

    QTimer.singleShot(150, answer)
    window.on_download_backlog()
    # Μέχρι να τελειώσει το (ψεύτικο) νήμα: αλλιώς μένει «τρέχει κάτι» και το
    # επόμενο test βρίσκει modal αντί για διάλογο.
    for _ in range(50):
        app.processEvents()
        if window._thread is None:
            break
    return captured


def test_only_the_selected_client_is_downloaded(app, window, monkeypatch):
    window._toggle_checked({_row_of(window, "104836713")})
    assert window._checked == {"104836713"}
    got = _run_backlog(app, window, monkeypatch)
    label, visible, checked, enabled = got["checkbox"]
    assert "Μόνο οι επιλεγμένοι πελάτες (1)" in label and "4 PDF" in label
    assert visible and checked and enabled
    assert got["vats"] == ["104836713"]        # ΟΧΙ και οι δύο
    assert got["backlog_only"] is True


def test_a_highlighted_row_counts_as_selected(app, window, monkeypatch):
    window.table.selectRow(_row_of(window, "803105689"))
    window._on_selection(animate=False)
    assert not window._checked
    got = _run_backlog(app, window, monkeypatch)
    assert got["vats"] == ["803105689"]


def test_unticking_the_box_downloads_everyone(app, window, monkeypatch):
    window._toggle_checked({_row_of(window, "104836713")})
    got = _run_backlog(app, window, monkeypatch, uncheck=True)
    assert sorted(got["vats"]) == ["104836713", "803105689"]


def test_the_option_shows_even_when_the_selected_have_nothing_pending(app, window, monkeypatch):
    """Κρυμμένο κουτάκι = «δεν υπάρχει η δυνατότητα» για τον χρήστη."""
    window.conn.execute(
        "UPDATE documents SET status='downloaded' WHERE client_id="
        "(SELECT id FROM clients WHERE vat='104836713')"
    )
    window.conn.commit()
    window._toggle_checked({_row_of(window, "104836713")})
    got = _run_backlog(app, window, monkeypatch)
    label, visible, checked, enabled = got["checkbox"]
    assert "δεν έχουν εκκρεμή PDF" in label
    assert visible and not checked and not enabled
    assert got["vats"] == ["803105689"]        # κατεβαίνει η υπόλοιπη ουρά


# ===========================================================================
# 3. Η φωτισμένη γραμμή του μενού
# ===========================================================================
def test_the_menu_row_lights_on_click_and_clears_on_cancel(app, window, monkeypatch):
    button = window.menu.button("pending_pdf")
    assert not button.property("active")

    lit: list[bool] = []

    def answer() -> None:
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                lit.append(bool(button.property("active")))   # φωτισμένη ΟΣΟ ρωτά
                widget.findChild(QDialogButtonBox).button(
                    QDialogButtonBox.StandardButton.Cancel
                ).click()

    QTimer.singleShot(150, answer)
    window.on_download_backlog()
    app.processEvents()
    assert lit == [True]
    assert not button.property("active")        # ακύρωση = σβήνει


def test_nothing_pending_does_not_leave_the_row_lit(app, window, monkeypatch):
    window.conn.execute("UPDATE documents SET status='downloaded'")
    window.conn.commit()
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.information",
        staticmethod(lambda *a, **k: None),
    )
    window.on_download_backlog()
    assert not window.menu.button("pending_pdf").property("active")


def test_the_online_only_action_lights_up_too():
    src = (SRC / "gui" / "main_window.py").read_text(encoding="utf-8")
    fn = src[src.index("def on_download_viewer_only"):src.index("def _browser_profile_dir")]
    assert fn.index('self.menu.set_action_busy("online_pdf", True)') < fn.index("rows =") \
        if "rows =" in fn else True
    assert fn.count('self.menu.set_action_busy("online_pdf", False)') >= 3
