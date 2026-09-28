"""Εκκίνηση που δεν σκάει, και αυτόματη εκκίνηση που όντως ξεκινά — και στα Windows 10.

* **«sqlite3.OperationalError: disk I/O error».** Η εφαρμογή δεν άνοιγε
  «κάποιες φορές». Φταίει το shared memory του WAL (αρχείο `-shm`): antivirus
  που το κρατά τη στιγμή της εκκίνησης, φάκελος που συγχρονίζεται στο cloud, ή
  `-shm` ξεχασμένο από βίαιο κλείσιμο. Τώρα η σύνδεση ξαναδοκιμάζει, πετά το
  ξεχασμένο `-shm` (ΠΟΤΕ το `-wal`, που κρατά δεδομένα) και τελικά πέφτει σε
  journal χωρίς shared memory. Αν πάλι δεν ανοίξει, ο χρήστης βλέπει τι να
  κάνει — όχι stack trace.

* **Αυτόματη εκκίνηση.** Ρυθμιζόταν ΜΟΝΟ στην εγκατάσταση, και κάθε ενημέρωση
  την ξανάγραφε από τις προτάσεις του ρόλου. Το «Εκκίνηση στο tray» χωρίς αυτήν
  δεν ξεκινά τίποτα. Στα Windows 10/11 η Διαχείριση εργασιών βάζει «βέτο» σε
  ξεχωριστό κλειδί αντί να σβήνει την καταχώρηση.

* **Windows 10.** Το εικονίδιο του tray δεν έχει πού να μπει όσο ο explorer
  στήνει τη γραμμή εργασιών· κρυβόμαστε μόνο όταν μπει.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from timologio import config, db

REPO = Path(__file__).resolve().parents[2]
ISS = REPO / "desktop" / "installer" / "timologio.iss"
ENTRY = REPO / "desktop" / "entry.py"
MAIN_WINDOW = REPO / "desktop" / "src" / "timologio" / "gui" / "main_window.py"

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="μόνο στα Windows")


# ===========================================================================
# 1. Η βάση που «δεν ανοίγει»
# ===========================================================================
def test_cloud_folders_skip_wal(tmp_path: Path):
    cloud = tmp_path / "OneDrive - Γραφείο" / "ScanmyData"
    conn = db.init_db(cloud / "t.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "truncate"
    finally:
        conn.close()
    assert db.is_cloud_synced(Path(r"C:\Users\x\Dropbox\a.db"))
    assert db.is_cloud_synced(Path("/home/x/Google Drive/a.db"))
    assert not db.is_cloud_synced(tmp_path / "data" / "a.db")


def test_retry_survives_a_transient_io_error(tmp_path: Path, monkeypatch):
    """Το antivirus κρατά το αρχείο μία στιγμή — η δεύτερη απόπειρα περνά."""
    real = sqlite3.connect
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return real(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", flaky)
    conn = db.connect(tmp_path / "t.db")
    try:
        assert calls["n"] == 2
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_last_attempt_drops_shared_memory(tmp_path: Path, monkeypatch):
    """Όταν το WAL δεν γίνεται με τίποτα, ανοίγουμε με rollback journal."""
    real = sqlite3.connect
    seen: list[str] = []

    class Guard(sqlite3.Connection):
        def execute(self, sql, *args):  # type: ignore[override]
            if sql.startswith("PRAGMA journal_mode"):
                seen.append(sql)
                if "WAL" in sql:
                    raise sqlite3.OperationalError("disk I/O error")
            return super().execute(sql, *args)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: real(*a, factory=Guard, **k))
    conn = db.connect(tmp_path / "t.db")
    try:
        assert any("TRUNCATE" in sql for sql in seen)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "truncate"
    finally:
        conn.close()


def test_stale_shm_goes_but_the_wal_never_does(tmp_path: Path):
    db_path = tmp_path / "t.db"
    db_path.write_bytes(b"")
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    wal.write_bytes(b"data")
    shm.write_bytes(b"junk")
    assert db._drop_stale_shm(db_path) is True
    assert not shm.exists()
    assert wal.read_bytes() == b"data"       # τα δεδομένα δεν τα αγγίζουμε ΠΟΤΕ


def test_a_dead_database_explains_itself(tmp_path: Path, monkeypatch):
    def dead(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sqlite3, "connect", dead)
    with pytest.raises(db.DatabaseUnavailable) as err:
        db.connect(tmp_path / "t.db")
    text = str(err.value)
    for hint in ("OneDrive", "antivirus", "δικτυακός φάκελος", "t.db"):
        assert hint in text


def test_startup_dialog_shows_the_explanation_not_the_traceback():
    src = ENTRY.read_text(encoding="utf-8")
    assert 'known = type(exc).__name__ == "DatabaseUnavailable"' in src
    assert "str(exc) if known else" in src
    assert "box.setDetailedText(detail)" in src


# ===========================================================================
# 2. Αυτόματη εκκίνηση με τα Windows
# ===========================================================================
def test_autostart_command_is_quoted():
    command = config.autostart_command()
    assert command.startswith('"') and command.count('"') >= 2
    assert str(Path(sys.executable)) in command


@windows_only
def test_autostart_round_trip(monkeypatch):
    """Γράφεται, διαβάζεται, σβήνεται — σε δικό μας κλειδί, όχι στο αληθινό Run."""
    import winreg

    test_path = r"Software\scanmydata\TimologioDownloaderTest\Run"
    approved = r"Software\scanmydata\TimologioDownloaderTest\Approved"
    monkeypatch.setattr(config, "_RUN_PATH", test_path)
    monkeypatch.setattr(config, "_APPROVED_PATH", approved)
    try:
        assert config.load_autostart() is False
        config.save_autostart(True)
        assert config.load_autostart() is True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_path) as key:
            value, _ = winreg.QueryValueEx(key, config._RUN_NAME)
        assert value == config.autostart_command()

        # Βέτο της Διαχείρισης εργασιών: η καταχώρηση υπάρχει αλλά δεν ισχύει.
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, approved) as key:
            winreg.SetValueEx(key, config._RUN_NAME, 0, winreg.REG_BINARY,
                              bytes([3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
        assert config.autostart_vetoed() is True
        assert config.load_autostart() is False
        # Ρητό «ναι» από την εφαρμογή σηκώνει το βέτο.
        config.save_autostart(True)
        assert config.autostart_vetoed() is False
        assert config.load_autostart() is True

        config.save_autostart(False)
        assert config.load_autostart() is False
    finally:
        for path in (test_path, approved):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass


@windows_only
def test_refresh_rewrites_a_stale_path(monkeypatch):
    import winreg

    test_path = r"Software\scanmydata\TimologioDownloaderTest\Run"
    monkeypatch.setattr(config, "_RUN_PATH", test_path)
    monkeypatch.setattr(config, "_APPROVED_PATH", test_path + "Approved")
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, test_path) as key:
            winreg.SetValueEx(key, config._RUN_NAME, 0, winreg.REG_SZ,
                              r'"C:\Old\Gone\TimologioDownloader.exe"')
        assert config.refresh_autostart() is True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_path) as key:
            value, _ = winreg.QueryValueEx(key, config._RUN_NAME)
        assert value == config.autostart_command()
        assert config.refresh_autostart() is False      # τίποτα να ξαναγραφτεί
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, test_path)
        except OSError:
            pass


def test_tray_switch_also_turns_on_autostart():
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    fn = src[src.index("def _on_start_minimized(self, value: bool)"):]
    fn = fn[:fn.index("def _on_autostart")]
    assert "if value and not load_autostart():" in fn
    assert "self._on_autostart(True)" in fn
    assert "refresh_autostart()" in src
    assert "self.control.autostart_changed.connect(self._on_autostart)" in src


def test_control_panel_exposes_the_switch():
    src = (REPO / "desktop" / "src" / "timologio" / "gui" / "control_panel.py").read_text(
        encoding="utf-8"
    )
    assert "autostart_changed = Signal(bool)" in src
    assert 'ToggleSwitch("Αυτόματη εκκίνηση με τα Windows")' in src
    assert "def set_autostart(self, value: bool, vetoed: bool = False)" in src
    assert "Διαχείριση εργασιών" in src


# ===========================================================================
# 3. Windows 10
# ===========================================================================
def test_installer_declares_windows_10():
    src = ISS.read_text(encoding="utf-8-sig")
    assert "MinVersion=10.0.17763" in src


def test_update_keeps_the_startup_choices():
    src = ISS.read_text(encoding="utf-8-sig")
    assert "HasExistingInstall: Boolean;" in src
    assert "if TrayFromCommandLine or HasExistingInstall then" in src
    assert "HasExistingInstall := True;" in src
    # Η αλήθεια για την αυτόματη εκκίνηση είναι η καταχώρηση των Windows.
    assert "'Software\\Microsoft\\Windows\\CurrentVersion\\Run',\n" \
           "                         'TimologioDownloader', V) and (V <> '') then" in src
    assert "Flags: deletevalue; Check: not WantsAutostart" in src
    assert "StartupApproved\\Run" in src


def test_window_hides_only_when_the_tray_is_really_there():
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    assert "QTimer.singleShot(0, self._hide_to_tray_if_possible)" in src
    fn = src[src.index("def _hide_to_tray_if_possible"):src.index("def _ensure_tray_visible")]
    assert "QSystemTrayIcon.isSystemTrayAvailable() and self.tray.isVisible()" in fn
    assert "self._hide_when_tray_ready = True" in fn
    retry = src[src.index("def _ensure_tray_visible"):src.index("def _on_start_minimized")]
    assert "tray.show()" in retry and "self._tray_tries <= 10" in retry
