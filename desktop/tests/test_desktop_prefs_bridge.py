"""Οι ρυθμίσεις του ΠΡΟΓΡΑΜΜΑΤΟΣ μέσα στη σελίδα του e-Τιμολόγιο.

Το UI του e-Τιμολόγιο είναι το ``app.php`` μέσα σε ενσωματωμένο browser, οπότε
«εκκίνηση στο tray» και «έλεγχος για ενημερώσεις» ζουν σε δύο κόσμους ταυτόχρονα:
το κουμπί είναι HTML, η ρύθμιση είναι Qt. Τα δύο άκρα της γέφυρας σπάνε
ανεξάρτητα και σιωπηλά — μια μετονομασία στη μία πλευρά αφήνει την άλλη να
καλεί κάτι που δεν υπάρχει, χωρίς κανένα σφάλμα.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
VENDORED_APP_PHP = REPO / "desktop" / "backend" / "etimologio" / "app.php"
ISS = Path(__file__).resolve().parents[1] / "installer" / "timologio.iss"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


# --- η πλευρά της σελίδας ---------------------------------------------------
def test_page_offers_the_desktop_only_settings(page: str) -> None:
    """Το panel υπάρχει, και ΜΟΝΟ στην ενσωματωμένη εφαρμογή.

    Στον browser δεν έχει τι να ρυθμίσει: δεν υπάρχει tray και οι ενημερώσεις
    είναι δουλειά του server.
    """
    start = page.index('<strong>🖥️ Εφαρμογή υπολογιστή</strong>')
    guard = page.rindex("<?php if ($__embedded): ?>", 0, start)
    assert page.index("<?php endif; ?>", start) > start
    assert guard < start
    assert 'id="dtTray"' in page
    assert "dtCheckUpdates()" in page


def test_page_and_shell_agree_on_the_bridge_names(page: str) -> None:
    """Τα ονόματα είναι συμβόλαιο ανάμεσα σε PHP/JS και Python."""
    from timologio.etimologio import webshell

    source = Path(webshell.__file__).read_text(encoding="utf-8")
    assert "window.etimHost" in page and "window.etimHost=c.objects.etimHost" in source
    assert 'registerObject("etimHost"' in source
    for call in ("setStartMinimized", "checkUpdates"):
        assert f"h.{call}(" in page, f"η σελίδα δεν καλεί το {call}"
        assert f"def {call}(" in source, f"το κέλυφος δεν εκθέτει το {call}"
    assert "applyDesktopPrefs" in page and "applyDesktopPrefs" in source


def test_vendored_copy_is_in_sync() -> None:
    """Δύο αντίγραφα του ίδιου αρχείου· το πακέτο κουβαλά το vendored."""
    assert VENDORED_APP_PHP.read_bytes() == APP_PHP.read_bytes()


# --- η πλευρά του Qt --------------------------------------------------------
def test_host_slots_emit_the_signals() -> None:
    pytest.importorskip("PySide6.QtWebEngineCore")
    from timologio.etimologio.webshell import _Host

    host = _Host()
    seen: list[object] = []
    host.start_minimized_changed.connect(seen.append)
    host.update_check_requested.connect(lambda: seen.append("updates"))

    host.setStartMinimized(True)
    host.checkUpdates()
    assert seen == [True, "updates"]


def test_main_window_routes_the_bridge_to_the_existing_handlers() -> None:
    """Μία ρύθμιση, δύο οθόνες: ο διακόπτης του πίνακα ελέγχου ακολουθεί."""
    from timologio.gui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")
    assert "start_minimized_changed" in source and "update_check_requested" in source
    body = source[source.index("def _on_start_minimized_requested"):]
    assert "control.set_start_minimized(value)" in body
    assert "control.check_updates()" in source


# --- η γραμμή κατάστασης ----------------------------------------------------
def test_client_counts_never_reach_the_chooser_screen() -> None:
    """Το «168 πελάτες · 62 διαθέσιμοι…» είναι έννοια της Λήψης.

    Η λίστα φορτώνει ΜΕΤΑ την εκκίνηση, ενώ στην οθόνη είναι ακόμη ο επιλογέας
    εφαρμογής: έγραφε από πάνω και καθόταν κάτω-κάτω, μιλώντας για εφαρμογή που
    ο χρήστης δεν είχε καν διαλέξει.
    """
    from timologio.gui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")
    assert "χωρίς κλειδί API · " in source
    counts = source[source.index("χωρίς κλειδί API · ") - 400:source.index("χωρίς κλειδί API · ")]
    assert "_set_counts_status(" in counts
    guard = source[source.index("def _set_counts_status"):]
    assert '("etimologio", "launcher")' in guard


def test_chooser_names_the_downloader_and_shows_a_readable_version() -> None:
    """Η αρχική οθόνη λέει «Timologio Downloader» και η έκδοση διαβάζεται."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel

    from timologio.gui.launcher import Launcher
    from timologio.gui.theme import CURRENT

    _ = QApplication.instance() or QApplication([])
    launcher = Launcher("1.2.3")
    titles = [w.text() for w in launcher.findChildren(QLabel)]
    assert "Timologio Downloader" in titles
    assert "Λήψη Παραστατικών" not in titles

    version = launcher._version_label
    assert version is not None and version.text() == "έκδοση 1.2.3"
    # Ήταν objectName «muted» στο μέγεθος του σώματος: μόλις που διαβαζόταν.
    assert version.objectName() != "muted"
    assert CURRENT.txt in version.styleSheet()


# --- το εικονίδιο της συντόμευσης -------------------------------------------
def test_shortcuts_carry_the_scanmydata_icon() -> None:
    """Τα Windows κρατούν επίμονη μνήμη εικονιδίων ανά συντόμευση."""
    script = ISS.read_text(encoding="utf-8-sig")
    assert 'DestName: "ScanmyDataSuite.ico"' in script
    icons = script[script.index("[Icons]"):script.index("[Registry]")]
    for line in icons.splitlines():
        if "{#AppExeName}" in line:
            assert 'IconFilename: "{app}\\ScanmyDataSuite.ico"' in line, line
