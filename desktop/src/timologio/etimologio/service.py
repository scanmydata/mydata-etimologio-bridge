"""Backend lifecycle for e-Τιμολόγιο Pro.

Two modes, switchable from the UI and remembered in ``service.json``:

* **offline** — spawn a local ``php -S 127.0.0.1:<port>`` serving the vendored
  ``backend/etimologio`` app against a local **SQLite** file under the data dir.
* **thin** — no local PHP; the native UI (and web clients) talk to the shared
  **VPS** backend (Postgres) at a configured URL.

The PHP source, a portable ``php.exe`` and (later) the VPS URL are the only
moving parts; everything else is the same JSON API in both modes.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

from ..config import APP_VERSION

log = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _meipass() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def resolve_backend_root() -> Path:
    """Directory holding ``etimologio.php`` (the PHP app)."""
    mp = _meipass()
    if mp and (mp / "backend" / "etimologio" / "etimologio.php").exists():
        return mp / "backend" / "etimologio"
    # Running from source: <repo>/backend/etimologio ; this file is
    # <repo>/src/timologio/etimologio/service.py → parents[3] == <repo>.
    repo = Path(__file__).resolve().parents[3]
    return repo / "backend" / "etimologio"


def resolve_php() -> str | None:
    """Path to a PHP CLI: env override → bundled runtime → PATH."""
    env = os.environ.get("TIMOLOGIO_ETIM_PHP")
    if env and Path(env).exists():
        return env
    mp = _meipass()
    if mp:
        exe = mp / "backend" / "php" / ("php.exe" if os.name == "nt" else "php")
        if exe.exists():
            return str(exe)
    return shutil.which("php")


def resolve_php_ini(php_path: str) -> str | None:
    """A ``php.ini`` to load extensions from (pdo_sqlite/openssl/curl/mbstring)."""
    env = os.environ.get("TIMOLOGIO_ETIM_PHP_INI")
    if env and Path(env).exists():
        return env
    cand = Path(php_path).with_name("php.ini")
    return str(cand) if cand.exists() else None


def resolve_cacert(php_path: str) -> str | None:
    """Absolute path to the CA bundle shipped next to the bundled PHP.

    It must be passed absolute on the command line. PHP resolves `extension_dir`
    relative to the ini file, but `curl.cainfo` relative to the **working
    directory** — and we start the server with the cwd set to the backend folder.
    A relative value there produced `error adding trust anchors from file`
    (curl error 77) and every ΑΑΔΕ call failed, but only in the packaged build.
    """
    env = os.environ.get("TIMOLOGIO_ETIM_CACERT")
    if env and Path(env).exists():
        return env
    cand = Path(php_path).with_name("cacert.pem")
    return str(cand.resolve()) if cand.exists() else None


class EtimologioService:
    def __init__(self, data_root: Path) -> None:
        #: Persistent, writable data dir for this backend (own SQLite/.enckey).
        self.data_dir = Path(data_root) / "etimologio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._proc: subprocess.Popen[bytes] | None = None
        self._port: int | None = None
        self._conf = self._load_conf()

    # --- persisted service config -----------------------------------------
    @property
    def _conf_path(self) -> Path:
        return self.data_dir / "service.json"

    def _load_conf(self) -> dict:
        try:
            return json.loads(self._conf_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_conf(self) -> None:
        self._conf_path.write_text(
            json.dumps(self._conf, ensure_ascii=False, indent=2), "utf-8"
        )

    def mode(self) -> str:
        return self._conf.get("mode", "offline")

    def server_url(self) -> str:
        return self._conf.get("server_url", "")

    def set_mode(self, mode: str, server_url: str = "") -> None:
        self._conf["mode"] = "thin" if mode == "thin" else "offline"
        if server_url:
            self._conf["server_url"] = server_url.rstrip("/")
        self._save_conf()

    def desktop_token(self) -> str:
        """Το κλειδί αυτόματης σύνδεσης του ενσωματωμένου UI (loopback μόνο)."""
        return str(self._conf.get("desktop_token", ""))

    def bootstrap_credentials(self) -> tuple[str, str]:
        """Offline master-admin login, generated once and persisted."""
        email = self._conf.get("bootstrap_email")
        password = self._conf.get("bootstrap_password")
        if not email or not password:
            email = email or "admin@localhost"
            password = password or secrets.token_urlsafe(18)
            self._conf["bootstrap_email"] = email
            self._conf["bootstrap_password"] = password
            self._save_conf()
        return email, password

    # --- addressing --------------------------------------------------------
    def base_url(self) -> str:
        if self.mode() == "thin":
            return self.server_url()
        if self._port is None:
            raise RuntimeError("local backend not started")
        return f"http://127.0.0.1:{self._port}"

    # --- offline lifecycle -------------------------------------------------
    def _write_config(self, port: int) -> None:
        """Generate the PHP ``config.php`` for offline (SQLite) operation."""
        root = resolve_backend_root()
        email, password = self.bootstrap_credentials()

        def phpstr(path: Path) -> str:
            return str(path).replace("\\", "/")

        sched_token = self._conf.setdefault("sched_token", secrets.token_hex(16))
        # Το κλειδί με το οποίο η ίδια η εφαρμογή συνδέεται στο backend της, ώστε
        # το ενσωματωμένο UI να μη ζητά κωδικό που παρήγαγε η ίδια.
        desktop_token = self._conf.setdefault("desktop_token", secrets.token_hex(24))
        self._save_conf()
        # Η φωνή του βοηθού: ίδια μηχανή για το ενσωματωμένο UI και για κάθε
        # browser που δείχνει σε αυτό το backend.
        from . import speech

        engine = speech.engine_path(self.data_dir)
        piper_exe = phpstr(engine) if engine else ""
        voice_el = speech.voice_path("el", self.data_dir)
        voice_en = speech.voice_path("en", self.data_dir)
        piper_el = phpstr(voice_el) if voice_el else ""
        piper_en = phpstr(voice_en) if voice_en else ""
        # Η αναγνώριση φωνής ακολουθεί τον ίδιο δρόμο με τη φωνή: μηχανή δίπλα
        # μας, endpoint στο backend, ίδιο UI για browser και εφαρμογή.
        stt_exe = speech.whisper_engine(self.data_dir)
        stt_model = speech.whisper_model(self.data_dir)
        whisper_exe = phpstr(stt_exe) if stt_exe else ""
        whisper_model = phpstr(stt_model) if stt_model else ""
        base = f"http://127.0.0.1:{port}"
        config = f"""<?php
// Auto-generated by the desktop app (offline mode). Do not edit by hand.
$ACCOUNTS = [];
const BASE_URL   = 'https://mydata.aade.gr/timologio';
const COOKIE_DIR = '{phpstr(self.data_dir / '.cookies')}';
const LOCAL_DB   = '{phpstr(self.data_dir / 'local.sqlite')}';
const ENC_KEY_FILE = '{phpstr(self.data_dir / '.enckey')}';
const ZERO_VAT_TYPES = ['22', '23'];
const MASTER_ADMIN_EMAIL    = '{email}';
const MASTER_ADMIN_PASSWORD = '{password}';
const MAIL_PROVIDER = 'auto';
const RESEND_API_KEY = '';
const RESEND_EMAIL_SENDER = '';
const SMTP_FROM = '';
const SMTP_HOST = ''; const SMTP_PORT = 587; const SMTP_USER = ''; const SMTP_PASS = '';
const APP_URL = '{base}';
const APP_BASE_URL = '{base}';
const SCHED_TOKEN = '{sched_token}';
const DESKTOP_TOKEN = '{desktop_token}';
const PIPER_EXE = '{piper_exe}';
const PIPER_VOICE_EL = '{piper_el}';
const PIPER_VOICE_EN = '{piper_en}';
const WHISPER_EXE = '{whisper_exe}';
const WHISPER_MODEL = '{whisper_model}';
const APP_VERSION_LABEL = '{APP_VERSION}';
const NOTIFY_ADMIN_EMAIL = '';
"""
        (root / "config.php").write_text(config, "utf-8")

    def start_local(self, wait_seconds: float = 8.0) -> str:
        """Spawn the local PHP server and return its base URL."""
        if self.mode() == "thin":
            return self.base_url()
        if self._proc and self._proc.poll() is None:
            return self.base_url()
        php = resolve_php()
        if not php:
            raise RuntimeError(
                "Δεν βρέθηκε PHP. Ορίστε TIMOLOGIO_ETIM_PHP ή εγκαταστήστε PHP."
            )
        root = resolve_backend_root()
        if not (root / "etimologio.php").exists():
            raise RuntimeError(f"Λείπει το backend e-Τιμολόγιο ({root}).")
        self._port = _free_port()
        self._write_config(self._port)
        (self.data_dir / ".cookies").mkdir(exist_ok=True)
        logfile = open(self.data_dir / "php-server.log", "ab")  # noqa: SIM115
        cmd = [php]
        ini = resolve_php_ini(php)
        if ini:
            cmd += ["-c", ini]
        cacert = resolve_cacert(php)
        if cacert:
            # Absolute, and on the command line: see resolve_cacert() for why the
            # ini's relative value is not enough.
            cmd += ["-d", f"curl.cainfo={cacert}", "-d", f"openssl.cafile={cacert}"]
        cmd += ["-S", f"127.0.0.1:{self._port}", "-t", str(root)]
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=logfile,
            stderr=logfile,
            creationflags=_CREATE_NO_WINDOW,
        )
        if not self._wait_healthy(wait_seconds):
            self.stop()
            raise RuntimeError("Ο τοπικός server e-Τιμολόγιο δεν ξεκίνησε.")
        log.info("e-Τιμολόγιο local backend on %s", self.base_url())
        return self.base_url()

    def _wait_healthy(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        url = f"{self.base_url()}/etimologio.php?auth=me"
        while time.monotonic() < deadline:
            if self._proc and self._proc.poll() is not None:
                return False  # process died
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200 and resp.json().get("success"):
                    return True
            except (requests.RequestException, ValueError):
                pass
            time.sleep(0.25)
        return False

    def health(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url()}/etimologio.php?auth=me", timeout=4)
            return resp.status_code == 200 and bool(resp.json().get("success"))
        except (requests.RequestException, ValueError, RuntimeError):
            return False

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _selftest() -> int:
    """`python -m timologio.etimologio.service` — start offline, hit the API."""
    logging.basicConfig(level=logging.INFO)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    data_root = Path(os.environ.get("TIMOLOGIO_DATA_DIR", Path.home() / ".etim-selftest"))
    svc = EtimologioService(data_root)
    svc.set_mode("offline")
    from .client import EtimologioClient

    url = svc.start_local()
    try:
        client = EtimologioClient(url)
        print("me (pre-login):", client.me().get("authenticated"))
        email, password = svc.bootstrap_credentials()
        print("login:", client.login(email, password).get("success"))
        me = client.me()
        print("is_staff:", me.get("is_staff"))
        # A fresh master has no company; link one so the switcher has content.
        users = client.call({"auth": "admin_users"}).get("users", [])
        master = next((u for u in users if u["role"] == "master"), None)
        if master:
            client.call(
                {"auth": "admin_add_account"},
                data={
                    "user_id": master["id"],
                    "vat": "999999999",
                    "label": "TEST-CO",
                    "username": "u",
                    "subkey": "k",
                },
                method="POST",
            )
        print("accounts:", client.accounts().get("accounts"))
        print("notif_count:", client.notif_count())
        print("OK")
        return 0
    finally:
        svc.stop()


if __name__ == "__main__":
    raise SystemExit(_selftest())
