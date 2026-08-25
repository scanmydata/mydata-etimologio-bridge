"""Έλεγχος για νεότερη έκδοση, μέσω των Releases του GitHub.

Δεν υπάρχει auto-updater: το πρόγραμμα δεν κατεβάζει ούτε τρέχει τίποτα μόνο
του — απλώς ρωτά ποια είναι η τελευταία δημοσιευμένη έκδοση και, αν είναι
νεότερη, δείχνει σύνδεσμο. Η λήψη και η εγκατάσταση μένουν ρητά στον χρήστη.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape
from pathlib import Path

log = logging.getLogger(__name__)

#: Τα repos που κοιτάζουμε, με σειρά προτεραιότητας. ΔΥΟ, όχι ένα: το προϊόν
#: μετακόμισε στο `mydata-etimologio-bridge` (εκεί ζει πια ολόκληρο — Downloader
#: + e-Τιμολόγιο Pro), αλλά οι ήδη εγκατεστημένες εκδόσεις ρωτούν ακόμη το παλιό.
#: Ρωτώντας ΚΑΙ ΤΑ ΔΥΟ και κρατώντας τη νεότερη έκδοση, μια κυκλοφορία σε όποιο
#: από τα δύο φτάνει σε όλους — και δεν ξανακολλάει το προϊόν επειδή το release
#: βγήκε «στο λάθος repo».
OWNER_REPOS = (
    "scanmydata/mydata-etimologio-bridge",
    "scanmydata/MyData-Invoice-Downloader",
)
OWNER_REPO = OWNER_REPOS[0]
API_URL = f"https://api.github.com/repos/{OWNER_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{OWNER_REPO}/releases/latest"

#: Όνομα του προσωρινού scheduled task που τρέχει την ενημέρωση. Το ίδιο όνομα
#: το σβήνει το script στην αρχή του, ώστε να μη μένουν σκουπίδια στον
#: χρονοπρογραμματιστή.
UPDATE_TASK_NAME = "TimologioDownloaderUpdate"


def parse_version(text: str) -> tuple[int, ...]:
    """«v0.2.3» -> (0, 2, 3). Ανθεκτικό σε ό,τι δεν είναι αριθμός."""
    cleaned = text.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    url: str
    asset_url: str = ""   # άμεσος σύνδεσμος του setup.exe (κενό αν λείπει)
    asset_name: str = ""
    asset_size: int = 0
    notes: str = ""       # σημειώσεις έκδοσης (Markdown από το GitHub release)

    @property
    def is_newer(self) -> bool:
        return parse_version(self.latest) > parse_version(self.current)

    @property
    def can_auto_install(self) -> bool:
        """Υπάρχει installer να κατεβάσουμε; Χωρίς αυτόν μένει μόνο ο σύνδεσμος."""
        return bool(self.asset_url)


def check(current: str, timeout: int = 8) -> UpdateInfo:
    """Ρωτά το GitHub για την τελευταία έκδοση. Σηκώνει εξαίρεση αν αποτύχει.

    Ρωτά ΟΛΑ τα ``OWNER_REPOS`` και κρατά τη νεότερη κυκλοφορία. Ένα repo που
    δεν απαντά (404, δίκτυο) αγνοείται· αν δεν απαντήσει ΚΑΝΕΝΑ, η εξαίρεση του
    πρώτου ταξιδεύει προς τα πάνω — ο χρήστης πρέπει να δει πραγματικό σφάλμα,
    όχι ψεύτικο «είστε ενημερωμένοι».
    """
    best: UpdateInfo | None = None
    first_error: Exception | None = None
    for repo in OWNER_REPOS:
        try:
            info = _check_repo(repo, current, timeout)
        except Exception as exc:            # noqa: BLE001 — δες docstring
            log.warning("έλεγχος έκδοσης: το %s δεν απάντησε (%s)", repo, exc)
            if first_error is None:
                first_error = exc
            continue
        if best is None or parse_version(info.latest) > parse_version(best.latest):
            best = info
    if best is None:
        raise first_error if first_error is not None else RuntimeError("κανένα repo")
    return best


def _check_repo(repo: str, current: str, timeout: int) -> UpdateInfo:
    """Η τελευταία κυκλοφορία ΕΝΟΣ repo. Σηκώνει εξαίρεση αν δεν απαντήσει."""
    import requests

    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        timeout=timeout,
        headers={"Accept": "application/vnd.github+json"},
    )
    response.raise_for_status()
    data = response.json()
    tag = str(data.get("tag_name") or "").strip()
    url = (str(data.get("html_url") or "").strip()
           or f"https://github.com/{repo}/releases/latest")

    asset_url = asset_name = ""
    asset_size = 0
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.lower().endswith(".exe"):
            asset_url = str(asset.get("browser_download_url") or "")
            asset_name = name
            asset_size = int(asset.get("size") or 0)
            break

    return UpdateInfo(
        current=current,
        latest=tag.lstrip("vV") or "?",
        url=url,
        asset_url=asset_url,
        asset_name=asset_name,
        asset_size=asset_size,
        notes=str(data.get("body") or "").strip(),
    )


def download(asset_url: str, dest: Path, progress=None, timeout: int = 30) -> Path:
    """Κατεβάζει τον installer σε ``dest``. ``progress(done, total)`` προαιρετικό.

    Γράφεται σε προσωρινό αρχείο και μετονομάζεται στο τέλος, ώστε μια διακοπή
    στη μέση να μην αφήσει μισό «έγκυρο» installer.
    """
    import requests

    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(asset_url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    tmp.replace(dest)
    return dest


def build_updater_script(
    *, pid: int, setup: Path, app_exe: Path, data_dir: Path, role: str, tray: bool,
    install_dir: Path | None = None,
) -> str:
    """PowerShell που τρέχει ΑΦΟΥ κλείσει η εφαρμογή: εγκαθιστά και ξαναανοίγει.

    Περιμένει πρώτα να τερματίσει η τρέχουσα διεργασία (ώστε να ξεκλειδώσουν τα
    αρχεία), τρέχει τον installer σιωπηλά περνώντας τις ΤΡΕΧΟΥΣΕΣ ρυθμίσεις
    (φάκελος/ρόλος/tray) ώστε να μη χαθούν, και μετά ξεκινά τη νέα έκδοση.

    ``install_dir`` (ο φάκελος όπου τρέχει ήδη η εφαρμογή, από το ``sys.executable``)
    περνιέται ρητά ως ``/DIR`` στον installer. ΚΡΙΣΙΜΟ: χωρίς αυτό, αν λείπει το
    κλειδί απεγκατάστασης του Inno (π.χ. εγκατάσταση από παλιότερη έκδοση, ή
    χειροκίνητη αντιγραφή), ο installer ΔΕΝ βρίσκει την προηγούμενη εγκατάσταση και
    εγκαθιστά στον **προεπιλεγμένο** φάκελο — όχι εκεί που τρέχει η εφαρμογή. Τότε
    η νέα έκδοση πάει αλλού, και το relaunch ξανανοίγει την **παλιά** («η ενημέρωση
    δεν δουλεύει»). Με ρητό ``/DIR`` η αναβάθμιση γίνεται πάντα ακριβώς από πάνω.
    """
    def q(text: str) -> str:  # single-quoted PowerShell literal
        return "'" + str(text).replace("'", "''") + "'"

    def esc(text: str) -> str:  # για χρήση μέσα σε ήδη single-quoted literal
        return str(text).replace("'", "''")

    tray_flag = "/TRAY=1" if tray else "/TRAY=0"
    # Ο installer γράφει log δίπλα στο setup, ώστε μια αποτυχία να είναι ορατή.
    log_path = setup.with_name("timologio_update_inno.log")
    # Δικό μας log του ΙΔΙΟΥ του script: χωρίς αυτό, όταν «η ενημέρωση δεν
    # δουλεύει» δεν υπάρχει κανένα ίχνος για το πού κόλλησε. Τώρα κάθε βήμα
    # καταγράφεται με ώρα, οπότε το πρόβλημα είναι πάντα ορατό.
    run_log = setup.with_name("timologio_update_run.log")
    proc_name = app_exe.stem
    # ΚΡΙΣΙΜΟ — διπλά εισαγωγικά γύρω από ΚΑΘΕ διαδρομή: το
    # `Start-Process -ArgumentList @('a','b c')` του Windows PowerShell 5.1 ΔΕΝ
    # βάζει εισαγωγικά στα στοιχεία του πίνακα — τα ενώνει με κενά. Έτσι ένα
    # `/DATADIR=C:\...\Παραστατικά myDATA` έσπαγε στο κενό: ο installer έβλεπε
    # `/DATADIR=C:\...\Παραστατικά`, έφτιαχνε ΝΕΟ άδειο φάκελο «Παραστατικά» και
    # έγραφε εκεί το μητρώο — η εφαρμογή άνοιγε σε άδεια βάση («έφτιαξε νέο
    # φάκελο μόνο του»). Με τα `"..."` μέσα στο ίδιο το όρισμα, το setup.exe
    # δέχεται τη διαδρομή ΟΛΟΚΛΗΡΗ (ο Inno αφαιρεί τα εισαγωγικά). Ισχύει για
    # όποια διαδρομή μπορεί να έχει κενό ή ελληνικά: /DIR, /LOG, /DATADIR.
    dir_arg = f"'/DIR=\"{esc(install_dir)}\"'," if install_dir is not None else ""
    args = (
        f"'/SILENT','/SUPPRESSMSGBOXES','/NORESTART',"
        f"{dir_arg}"
        f"'/LOG=\"{esc(log_path)}\"',"
        f"'/DATADIR=\"{esc(data_dir)}\"',"
        f"'/ROLE={role}','{tray_flag}'"
    )
    return (
        "$ErrorActionPreference='SilentlyContinue'\n"
        f"$log={q(run_log)}\n"
        "function L($m){ (\"[{0}] {1}\" -f (Get-Date -Format 'HH:mm:ss'), $m) | "
        "Out-File -FilePath $log -Append -Encoding utf8 }\n"
        f"L ('start pid={int(pid)}')\n"
        # Το ΚΡΙΣΙΜΟ βήμα (η εγκατάσταση) μπαίνει σε try/finally: ό,τι κι αν
        # στραβώσει, (α) καταγράφεται με λεπτομέρεια και (β) η εφαρμογή ξανανοίγει
        # πάντα στο finally — ποτέ δεν μένει ο χρήστης χωρίς πρόγραμμα ανοιχτό.
        "try {\n"
        # Αν μας ξεκίνησε το Task Scheduler, σβήσε το task — έχει ήδη πυροδοτηθεί.
        f"  schtasks.exe /Delete /TN '{UPDATE_TASK_NAME}' /F 2>$null | Out-Null\n"
        # Περίμενε τη διεργασία που ζήτησε την ενημέρωση…
        f"  Wait-Process -Id {int(pid)} -Timeout 60\n"
        # …και κάθε άλλη ανοιχτή instance (server + τερματικό στο ίδιο μηχάνημα).
        "  $deadline=(Get-Date).AddSeconds(30)\n"
        f"  while ((Get-Process -Name {q(proc_name)} -ErrorAction SilentlyContinue) "
        f"-and (Get-Date) -lt $deadline) {{ Start-Sleep -Milliseconds 500 }}\n"
        f"  Stop-Process -Name {q(proc_name)} -Force -ErrorAction SilentlyContinue\n"
        "  L 'instances stopped'\n"
        # ΓΙΑΤΙ ΟΧΙ πια χειροκίνητη αναμονή ξεκλειδώματος αρχείων (ήταν εδώ που
        # «κόλλαγε» ενίοτε η ενημέρωση): τη δουλειά την κάνει πλέον ο ΙΔΙΟΣ ο
        # installer μέσω του Restart Manager (CloseApplications=yes στο .iss),
        # που κλείνει ό,τι κρατά ακόμη κλειδωμένα αρχεία. Ένας μικρός σταθερός
        # χρόνος αρκεί για να απελευθερώσει ο kernel τα mapped DLL.
        "  Start-Sleep -Seconds 3\n"
        "  L 'running installer'\n"
        f"  $p=Start-Process -Wait -PassThru -FilePath {q(setup)} -ArgumentList @({args})\n"
        "  L ('installer exit=' + $(if ($p) { $p.ExitCode } else { 'null' }))\n"
        "} catch {\n"
        "  L ('ERROR: ' + $_.Exception.Message)\n"
        "} finally {\n"
        # --show: μετά την ενημέρωση ο χρήστης πρέπει να ΔΕΙ την εφαρμογή, όχι να
        # «εξαφανιστεί» στο tray. Τρέχει ΠΑΝΤΑ (και σε αποτυχία) ώστε ο χρήστης να
        # μη μείνει χωρίς ανοιχτό πρόγραμμα.
        f"  Start-Process -FilePath {q(app_exe)} -ArgumentList '--show'\n"
        "  L 'relaunched'\n"
        "}\n"
    )


def powershell_exe() -> str:
    """Πλήρης διαδρομή του Windows PowerShell 5.1.

    Το PATH δεν είναι εγγυημένο μέσα στο πακεταρισμένο περιβάλλον, οπότε ένα
    σκέτο ``"powershell"`` μπορεί να μη βρεθεί.
    """
    full = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    return str(full) if full.exists() else "powershell"


def launch_detached(
    script_path: Path, *, run_log: Path | None = None, start_token: str | None = None,
) -> bool:
    """Ξεκινά το PowerShell script της ενημέρωσης ΑΠΟΣΠΑΣΜΕΝΑ από την εφαρμογή,
    ώστε να επιβιώσει του κλεισίματός της. Επιστρέφει ``True`` αν ξεκίνησε.

    ΓΙΑΤΙ Task Scheduler και όχι απλό detached process: πολλά περιβάλλοντα βάζουν
    την εφαρμογή σε **Job Object με kill-on-close**. Όταν κλείνει η εφαρμογή, το
    job σκοτώνει ΚΑΙ κάθε παιδί-διεργασία — ακόμη και «detached». Το
    ``CREATE_BREAKAWAY_FROM_JOB`` υποτίθεται ότι το λύνει, αλλά αν το job ΔΕΝ
    επιτρέπει breakaway (μετρημένα, συμβαίνει), η δημιουργία διεργασίας αποτυγχάνει
    και το script δεν τρέχει ΠΟΤΕ — «κατέβαινε αλλά δεν εγκαθιστούσε». Ένα
    scheduled task τρέχει κάτω από την υπηρεσία του χρονοπρογραμματιστή, εντελώς
    έξω από το job της εφαρμογής, οπότε επιβιώνει πάντα. Ο απλός detached τρόπος
    μένει ως εφεδρεία για συστήματα όπου το schtasks είναι απενεργοποιημένο.

    ΕΠΑΛΗΘΕΥΣΗ (κρίσιμο για «universal»): το ``schtasks`` έχει παρατηρηθεί να
    επιστρέφει **επιτυχία** ενώ το task μένει σε κατάσταση *Queued* και ΔΕΝ
    εκτελείται ποτέ — τότε ο παλιός κώδικας γύριζε ``True`` και δεν δοκίμαζε ποτέ
    την εφεδρεία, κι έτσι «η ενημέρωση δεν δούλευε» σιωπηλά. Τώρα, αν δοθεί
    ``run_log``+``start_token``, περιμένουμε να εμφανιστεί το token (το script το
    γράφει ως ΠΡΩΤΗ του ενέργεια). Αν δεν εμφανιστεί, θεωρούμε ότι ο τρόπος
    απέτυχε και δοκιμάζουμε τον επόμενο. Έτσι κερδίζει όποιος τρόπος όντως τρέχει
    στο συγκεκριμένο μηχάνημα, κι αν κανένας δεν τρέξει επιστρέφουμε ``False`` (ο
    καλών δείχνει τότε μήνυμα για χειροκίνητη λήψη).
    """
    ps = powershell_exe()
    since = run_log.stat().st_size if (run_log and run_log.exists()) else 0

    def started() -> bool:
        if run_log is None or start_token is None:
            return True  # χωρίς log δεν γίνεται επαλήθευση — δεχόμαστε το «ξεκίνησε»
        # 6 δευτ. ήταν λίγα: μια «κρύα» εκκίνηση PowerShell με antivirus από πάνω
        # θέλει άνετα 10-15. Και δεν κοστίζει τίποτα να περιμένουμε — η εφαρμογή
        # ούτως ή άλλως κλείνει.
        return _wait_for_marker(run_log, start_token, since, timeout=25.0)

    if _schedule_via_task(ps, script_path):
        if started():
            log.info("Ενημέρωση: ξεκίνησε μέσω Task Scheduler.")
            return True
        log.warning("Ενημέρωση: το task δεν έτρεξε (%s) — δοκιμή απευθείας.", _task_status())
        _delete_update_task()

    if _launch_via_popen(ps, script_path):
        if started():
            log.info("Ενημέρωση: ξεκίνησε ως detached process.")
            return True
        log.warning("Ενημέρωση: ο detached τρόπος δεν εκτέλεσε το script.")

    log.error("Ενημέρωση: δεν κατάφερε να ξεκινήσει με κανέναν τρόπο.")
    return False


def _wait_for_marker(run_log: Path, token: str, since: int, timeout: float) -> bool:
    """Περιμένει έως ``timeout`` δευτ. να εμφανιστεί το ``token`` στο ``run_log``,
    γραμμένο ΜΕΤΑ το ``since`` offset (ώστε να μη μπερδευτεί με προηγούμενη
    ενημέρωση). Το script το γράφει ως πρώτη ενέργεια — άρα η εμφάνισή του
    σημαίνει ότι όντως ξεκίνησε."""
    import time

    needle = token.encode("utf-8")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(run_log, "rb") as fh:
                fh.seek(since)
                if needle in fh.read():
                    return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def _delete_update_task() -> None:
    """Σβήνει το task ενημέρωσης σιωπηλά (π.χ. έμεινε Queued και πάμε σε εφεδρεία),
    ώστε να μην τρέξει αργότερα και ξεκινήσει δεύτερη εγκατάσταση."""
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", UPDATE_TASK_NAME, "/F"],
            capture_output=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _task_xml(powershell: str, script_path: Path) -> str:
    """Ο ορισμός του task σε XML.

    ⚠️ ΓΙΑΤΙ XML ΚΑΙ ΟΧΙ `/TR`: το `schtasks /Create` με σκέτες παραμέτρους
    φτιάχνει task με **«Μην ξεκινάς με μπαταρία»** αναμμένο — είναι το default
    του και ΔΕΝ υπάρχει flag να το σβήσεις. Σε κάθε φορητό (ή σε σταθερό με
    UPS που δηλώνεται ως μπαταρία), το `/Run` επιστρέφει «SUCCESS», το
    «Last Result» γράφει 0, και το task μένει για πάντα σε κατάσταση
    **Queued**: η ενημέρωση «ξεκινούσε» και δεν εγκαθιστούσε ποτέ τίποτα.
    Μετρημένο ζωντανά (25/8/2026): με `/TR` το task έμεινε Queued >36 δευτ.,
    με το ίδιο ακριβώς action μέσω XML έτρεξε σε **0,5 δευτ.**

    Το `<StartWhenAvailable>` καλύπτει και το σενάριο «ο υπολογιστής κοιμήθηκε»,
    και το `IgnoreNew` εμποδίζει δεύτερη εγκατάσταση αν κάτι ξαναπυροδοτηθεί.
    """
    args = (f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
            f'-NonInteractive -File "{script_path}"')
    domain = os.environ.get("USERDOMAIN", "")
    user = os.environ.get("USERNAME", "")
    who = f"{domain}\\{user}" if domain and user else (user or "")
    start = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    principal = (f"<UserId>{xml_escape(who)}</UserId>"
                 "<LogonType>InteractiveToken</LogonType>"
                 "<RunLevel>LeastPrivilege</RunLevel>") if who else (
                 "<LogonType>InteractiveToken</LogonType>")
    return (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        "<RegistrationInfo><Description>Ενημέρωση ScanmyData Suite</Description></RegistrationInfo>"
        f"<Triggers><TimeTrigger><StartBoundary>{start}</StartBoundary>"
        "<Enabled>true</Enabled></TimeTrigger></Triggers>"
        f'<Principals><Principal id="Author">{principal}</Principal></Principals>'
        "<Settings>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>"
        "<RunOnlyIfIdle>false</RunOnlyIfIdle>"
        "<AllowStartOnDemand>true</AllowStartOnDemand>"
        "<Enabled>true</Enabled>"
        "<ExecutionTimeLimit>PT1H</ExecutionTimeLimit>"
        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "</Settings>"
        '<Actions Context="Author"><Exec>'
        f"<Command>{xml_escape(powershell)}</Command>"
        f"<Arguments>{xml_escape(args)}</Arguments>"
        "</Exec></Actions></Task>"
    )


def _task_status() -> str:
    """Η κατάσταση του task σε μία γραμμή, για το log.

    Χωρίς αυτό, ένα task που μένει «Queued» είναι αόρατο: το `/Run` λέει
    SUCCESS και μετά σιωπή. Με αυτό, το log γράφει «Queued» και ξέρεις αμέσως
    ότι φταίει συνθήκη του χρονοπρογραμματιστή, όχι το script.
    """
    try:
        out = subprocess.run(
            ["schtasks", "/Query", "/TN", UPDATE_TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True, timeout=20,
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return "άγνωστη"
    keep = [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith(("Status:", "Last Result:", "Κατάσταση:"))]
    return " · ".join(keep) or "άγνωστη"


def _schedule_via_task(powershell: str, script_path: Path) -> bool:
    """Καταχωρεί ένα εφάπαξ task που τρέχει το script και το πυροδοτεί αμέσως."""
    xml_path = script_path.with_name("timologio_update_task.xml")
    try:
        # UTF-16: το schtasks /XML δέχεται ΜΟΝΟ αυτό (αλλιώς «Το αρχείο XML
        # περιέχει μη έγκυρο χαρακτήρα»), και οι ελληνικές διαδρομές το θέλουν.
        xml_path.write_text(_task_xml(powershell, script_path), encoding="utf-16")
    except OSError as exc:
        log.warning("Ενημέρωση: δεν γράφτηκε το XML του task: %s", exc)
        return False
    try:
        created = subprocess.run(
            ["schtasks", "/Create", "/TN", UPDATE_TASK_NAME, "/XML", str(xml_path), "/F"],
            capture_output=True, timeout=20,
        )
        if created.returncode != 0:
            log.warning("schtasks /Create /XML: %s",
                        created.stderr.decode("utf-8", "replace").strip())
            return False
        ran = subprocess.run(
            ["schtasks", "/Run", "/TN", UPDATE_TASK_NAME],
            capture_output=True, timeout=20,
        )
        if ran.returncode != 0:
            log.warning("schtasks /Run: %s",
                        ran.stderr.decode("utf-8", "replace").strip())
            return False
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Task Scheduler μη διαθέσιμο: %s", exc)
        return False


def _launch_via_popen(powershell: str, script_path: Path) -> bool:
    """Εφεδρεία: απευθείας detached process, με προσπάθεια breakaway από το job."""
    cmd = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-WindowStyle", "Hidden", "-File", str(script_path)]
    detached = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    create_breakaway_from_job = 0x01000000
    try:
        subprocess.Popen(
            cmd, creationflags=detached | create_breakaway_from_job,
            close_fds=True,
        )
        return True
    except OSError:
        log.warning("Breakaway from job απέτυχε — εκκίνηση χωρίς αυτό.")
    try:
        subprocess.Popen(cmd, creationflags=detached, close_fds=True)
        return True
    except OSError as exc:
        log.error("Δεν ξεκίνησε το script ενημέρωσης: %s", exc)
        return False
