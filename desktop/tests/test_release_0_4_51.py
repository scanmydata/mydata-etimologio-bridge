"""e-Τιμολόγιο Pro: σωστή επωνυμία στις οριστικές, μνήμη που εμπιστευόμαστε, τοπικός scheduler.

* **Επωνυμίες.** Η φόρμα μπορούσε να στείλει ΑΦΜ ενός πελάτη με επωνυμία άλλου:
  η άντληση έπεφτε σε `list[0]` (τον πρώτο της λίστας), η επωνυμία του
  προηγούμενου πελάτη έμενε όταν άλλαζε το ΑΦΜ, και η αναζήτηση πελάτη στον
  server διάβαζε τον κωδικό από την ΠΡΩΤΗ γραμμή του πίνακα. Τώρα η έκδοση για
  ελληνικό ΑΦΜ παίρνει υποχρεωτικά την επωνυμία του Taxisnet.

* **Μνήμη.** Οι λίστες απαντούν από τη βάση όσο είναι έμπιστες (καμία δική μας
  αλλαγή, κανένα νέο στην ΑΑΔΕ, μέσα σε 6 ώρες)· στον server ο scheduler τις
  ξαναβεβαιώνει στο παρασκήνιο με `sync_all`.

* **Τοπικός scheduler.** Οι προγραμματισμένες εκδόσεις δεν έτρεχαν ποτέ στην
  εφαρμογή υπολογιστή: το `scheduler.php` το καλούσε μόνο το cron του server.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from timologio.etimologio import service as svc

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "desktop" / "backend" / "etimologio"
ROOT_FILES = ["etimologio.php", "app.php", "scheduler.php", "localdb.php"]


def _read(name: str, root: Path = REPO) -> str:
    return (root / name).read_text("utf-8")


# ===========================================================================
# 0. Τα δύο αντίγραφα του backend είναι ίδια (πακετάρεται το desktop/backend)
# ===========================================================================
@pytest.mark.parametrize("name", ROOT_FILES)
def test_backend_copy_matches_root(name: str) -> None:
    assert _read(name) == _read(name, BACKEND), f"{name}: το desktop/backend δεν συγχρονίστηκε"


# ===========================================================================
# 1. Επωνυμίες
# ===========================================================================
def test_afm_lookup_never_falls_back_to_the_first_customer() -> None:
    app = _read("app.php")
    body = app[app.index("async function afmDetails("):app.index("function afmMismatchFlash(")]
    assert "||list[0]" not in body
    assert "String(x.vat||'')===afm" in body


def test_changing_the_afm_clears_the_previous_customer() -> None:
    app = _read("app.php")
    body = app[app.index("function lookupAfm()"):app.index("// Lines editor (multi-line).")]
    assert "issueCustClear()" in body
    # Μια αργή απάντηση για ΠΑΛΙΟ ΑΦΜ δεν γράφει πάνω στο νέο.
    assert "$('#iAfm').value.trim()!==afm" in body


def test_live_issue_uses_the_authoritative_name() -> None:
    php = _read("etimologio.php")
    create = php[php.index("function createInvoice("):php.index("// Normalise to a list of lines.")]
    assert "authoritativeCounterpart($ch, $afm)" in create
    assert "$name = $auth['name'];" in create
    # Η απάντηση λέει τι διορθώθηκε, και η ειδοποίηση παίρνει τη σωστή επωνυμία.
    assert php.count("annotateNameCorrection(") >= 4


def test_search_customer_reads_the_matching_row_only() -> None:
    php = _read("etimologio.php")
    body = php[php.index("function searchCustomer("):php.index("function custNameNorm(")]
    assert "listCustomers(" in body
    assert "!== $afm) continue;" in body


def test_new_customer_name_is_kept_as_taxisnet_gives_it() -> None:
    php = _read("etimologio.php")
    body = php[php.index("function createCustomer("):php.index("function createPersonalCustomer(")]
    assert "strtoupper(" not in body


def _php() -> str | None:
    return svc.resolve_php() or shutil.which("php")


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [("ΑΛΦΑ Α.Ε.", "Άλφα ΑΕ", True), ("ΒΗΤΑ ΑΕ", "ΑΛΦΑ ΑΕ", False), ("MEGATECH  ΙΚΕ", "megatech ι.κ.ε", True)],
)
def test_name_comparison_ignores_accents_case_and_punctuation(a: str, b: str, same: bool, tmp_path: Path) -> None:
    php = _php()
    if not php:
        pytest.skip("χωρίς PHP")
    src = _read("etimologio.php")
    fn = re.search(r"function custNameNorm.*?\n}\n", src, re.S).group(0)
    script = tmp_path / "t.php"
    script.write_text(
        "<?php\n" + fn + f"echo custNameNorm({a!r}) === custNameNorm({b!r}) ? 'same' : 'diff';\n", "utf-8"
    )
    cmd = [php]
    ini = svc.resolve_php_ini(php)
    if ini:
        cmd += ["-c", ini]
    out = subprocess.run(cmd + [str(script)], capture_output=True, text=True, timeout=30, check=False)
    assert out.stdout.strip() == ("same" if same else "diff"), out.stderr


# ===========================================================================
# 2. Μνήμη
# ===========================================================================
def test_failed_sync_never_overwrites_the_cache() -> None:
    php = _read("etimologio.php")
    body = php[php.index("function runSyncKind("):php.index("$__syncCtx = [")]
    guard = body.index("$r['success'] === false")
    assert guard < body.index("cache_set(COMPANY_VAT, $syncKind, $rows);")


def test_outside_activity_invalidates_docs() -> None:
    php = _read("etimologio.php")
    assert "cacheMarkDirty(COMPANY_VAT, $__dirty);" in php
    assert "'trusted' => cacheTrusted(" in php


def test_server_scheduler_runs_background_sync_but_not_locally() -> None:
    sch = _read("scheduler.php")
    assert "'sync_all'" in sch
    assert "defined('BG_SYNC_MINUTES')" in sch
    assert "if (!defined('SCHEDULER_LOCAL'))" in sch


# ===========================================================================
# 3. Μηνύματα / αναμονή
# ===========================================================================
def test_flash_messages_are_dismissable_and_movable() -> None:
    app = _read("app.php")
    assert 'id="flashStack"' in app and 'data-float="flash"' in app and 'data-float="busy"' in app
    assert "flash-x" in app and "busy-x" in app
    assert "key:'pos.'+name" in app          # η θέση πάει στις προτιμήσεις του χρήστη
    assert "function busyOff(id)" in app


# ===========================================================================
# 4. Τοπικός scheduler
# ===========================================================================
def test_local_config_marks_the_scheduler_local(tmp_path: Path, monkeypatch) -> None:
    written: dict[str, str] = {}
    root = tmp_path / "backend"
    root.mkdir()
    monkeypatch.setattr(svc, "resolve_backend_root", lambda: root)
    s = svc.EtimologioService(tmp_path / "data")
    s._write_config(8123)
    written["c"] = (root / "config.php").read_text("utf-8")
    assert "const SCHEDULER_LOCAL = true;" in written["c"]
    assert "const BG_SYNC_MINUTES = 0;" in written["c"]
    assert "const APP_BASE_URL = 'http://127.0.0.1:8123';" in written["c"]


def test_scheduler_command_targets_scheduler_php(tmp_path: Path) -> None:
    s = svc.EtimologioService(tmp_path)
    cmd = s.scheduler_command("php.exe", "php.ini", "/x/cacert.pem", tmp_path)
    assert cmd[0] == "php.exe" and cmd[-1] == str(tmp_path / "scheduler.php")
    assert "curl.cainfo=/x/cacert.pem" in cmd


def test_scheduler_loop_runs_while_the_server_lives_and_stops_with_it(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "b"
    root.mkdir()
    (root / "scheduler.php").write_text("<?php", "utf-8")
    s = svc.EtimologioService(tmp_path)
    ran = threading.Event()
    monkeypatch.setattr(s, "run_scheduler_once", lambda cmd, r: ran.set())

    class Alive:
        def poll(self):
            return None

    s._proc = Alive()  # type: ignore[assignment]
    monkeypatch.setattr(s, "SCHED_INTERVAL", 0.01)
    # Η πρώτη αναμονή (20″) δεν μετρά στο τεστ.
    orig_wait = s._sched_stop.wait
    monkeypatch.setattr(s._sched_stop, "wait", lambda t: orig_wait(min(t, 0.01)))
    s._start_scheduler("php", None, None, root)
    assert ran.wait(3), "ο scheduler δεν έτρεξε"
    s._proc = None
    s.stop()
    s._sched_thread.join(3)
    assert not s._sched_thread.is_alive()


def test_local_scheduler_skips_jobs_that_expired_while_closed() -> None:
    sch = _read("scheduler.php")
    body = sch[sch.index("foreach ($due as $job) {"):]
    stale = body.index("defined('SCHEDULER_LOCAL') && $staleH > 0")
    assert stale < body.index("sched_set_status($id, 'running');")
    assert "strtotime($nextS) <= time()" in body      # η επόμενη εμφάνιση είναι στο ΜΕΛΛΟΝ


def test_sched_add_without_recurrence_does_not_crash() -> None:
    db = _read("localdb.php")
    assert "? ($d['recurrence'] ?? 'none') : 'none'" in db
