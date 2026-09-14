"""Η ενημέρωση δεν βγάζει πια τον λογιστή από τον λογαριασμό του, ούτε ξεχνά ρυθμίσεις.

Τρεις αιτίες, όλες στην εκκίνηση — και κάθε ενημέρωση ξεκινά την εφαρμογή από την αρχή:

* **Προφίλ «ανώνυμης περιήγησης».** Στο Qt 6 το προεπιλεγμένο προφίλ του
  QtWebEngine δεν γράφει τίποτα στον δίσκο: cookies σύνδεσης και localStorage
  σβήνουν με το κλείσιμο. Επαληθεύτηκε με δύο διεργασίες: παλιό προφίλ →
  «uid=none | tour=null», νέο → «uid=42 | tour=1».
* **Τυχαία θύρα** σε κάθε εκκίνηση: το localStorage κρατιέται ανά θύρα.
* **Συνεδρίες PHP** στον Temp των Windows με όριο 24 λεπτών, και cookie
  «μέχρι να κλείσει ο browser».
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUTH_PHP = REPO / "auth.php"
SHELL_PY = REPO / "desktop" / "src" / "timologio" / "etimologio" / "webshell.py"
SERVICE_PY = REPO / "desktop" / "src" / "timologio" / "etimologio" / "service.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_shell_uses_a_named_persistent_profile():
    src = _read(SHELL_PY)
    fn = src[src.index("def persistent_profile():"):src.index("def webengine_available(")]
    assert "QWebEngineProfile(PROFILE_NAME, QApplication.instance())" in fn
    assert "ForcePersistentCookies" in fn
    assert "self._page = _Page(persistent_profile(), self)" in src
    assert "_Page(self._view.page().profile()" not in src


def test_persistent_profile_is_not_off_the_record():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import timologio.etimologio.webshell as ws

    saved_name, saved = ws.PROFILE_NAME, ws._PROFILE
    try:
        ws.PROFILE_NAME, ws._PROFILE = "etimtest-pytest", None
        prof = ws.persistent_profile()
        assert not prof.isOffTheRecord()
        assert prof.persistentStoragePath().replace("\\", "/").endswith("/QtWebEngine/etimtest-pytest")
        assert ws.persistent_profile() is prof           # ένα ανά διεργασία
        from PySide6.QtWebEngineCore import QWebEngineProfile

        assert prof.persistentCookiesPolicy() == QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    finally:
        ws.PROFILE_NAME, ws._PROFILE = saved_name, saved
    assert app is not None


def test_local_server_keeps_its_port(tmp_path: Path):
    from timologio.etimologio.service import EtimologioService

    svc = EtimologioService(tmp_path)
    first = svc._stable_port()
    assert EtimologioService(tmp_path)._stable_port() == first     # ίδια θύρα στην επόμενη εκκίνηση
    # Πιασμένη θύρα: νέα, και αποθηκεύεται για τις επόμενες.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", first))
        busy.listen(1)
        other = EtimologioService(tmp_path)._stable_port()
    assert other != first
    assert EtimologioService(tmp_path)._conf.get("port") == other


def test_local_sessions_live_next_to_the_data():
    src = _read(SERVICE_PY)
    fn = src[src.index("def start_local("):]
    assert 'sessions = self.data_dir / ".sessions"' in fn
    assert '"-d", f"session.save_path={sessions}"' in fn
    assert '"-d", "session.gc_maxlifetime=2592000"' in fn
    assert "self._port = self._stable_port()" in fn


def test_auth_long_session_only_for_the_desktop_shell():
    src = _read(AUTH_PHP)
    block = src[src.index("const AUTH_SHELL_SESSION_TTL"):src.index("// --- Master bootstrap")]
    assert "'lifetime' => $__shellClient ? AUTH_SHELL_SESSION_TTL : 0," in block
    assert "!empty($_COOKIE['etim_shell'])" in block
    # Ο browser κρατά ΤΟ ΙΔΙΟ όριο αδράνειας με πριν (από το php.ini).
    assert "$__webIdle = (int)ini_get('session.gc_maxlifetime');" in block
    assert block.index("$__webIdle = (int)ini_get(") < block.index("@ini_set('session.gc_maxlifetime'")
    assert "$__idle = $__shellClient ? AUTH_SHELL_SESSION_TTL : $__webIdle;" in block
    assert block.index("session_set_cookie_params(") < block.index("session_start();")
