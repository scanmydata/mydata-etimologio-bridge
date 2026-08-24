"""Αντίγραφα ασφαλείας του e-Τιμολόγιο: εύρεση, επαναφορά, αυτόματη υιοθέτηση.

Το **αντίγραφο** το φτιάχνει η PHP πλευρά (`serverlink.php: link_backup_run`),
γιατί εκεί ζητιέται — μέσα από τις Ρυθμίσεις του e-Τιμολόγιο. Η **επαναφορά**
όμως δεν μπορεί να γίνει από εκεί: αντικαθιστά τη βάση πάνω στην οποία τρέχει ο
ίδιος ο server, και ο server πρέπει πρώτα να σταματήσει. Ζει λοιπόν εδώ, στην
πλευρά που ελέγχει τον κύκλο ζωής του backend.

⚠️ Η ΒΑΣΗ ΚΑΙ ΤΟ ΚΛΕΙΔΙ ΤΑΞΙΔΕΥΟΥΝ ΜΑΖΙ. Τα δεδομένα είναι κρυπτογραφημένα με
το `.enckey`: μια βάση χωρίς το κλειδί της είναι θόρυβος, και ένα κλειδί χωρίς
τη βάση του δεν ανοίγει τίποτα. Γι' αυτό το zip περιέχει και τα δύο — και γι'
αυτό η επαναφορά τα γράφει και τα δύο, ποτέ μόνο το ένα.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

#: Τι αναγνωρίζουμε μέσα σε ένα αντίγραφο. Ό,τι άλλο βρεθεί αγνοείται: ένα zip
#: δεν επιτρέπεται να γράψει αυθαίρετα αρχεία στον φάκελο δεδομένων.
MEMBERS = (
    "local.sqlite",
    "local.sqlite-wal",
    "local.sqlite-shm",
    ".enckey",
    "service.json",
)

#: Το `service.json` κρατά τα κλειδιά αυτόματης σύνδεσης ΑΥΤΗΣ της εγκατάστασης
#: (desktop_token, sched_token, bootstrap password). Επαναφέροντάς το από άλλο
#: μηχάνημα, το κέλυφος θα ζητούσε token που ο server δεν αναγνωρίζει και η
#: ενσωματωμένη σελίδα θα κατέληγε σε οθόνη σύνδεσης χωρίς γνωστό κωδικό.
SKIP_ON_RESTORE = frozenset({"service.json"})


def backups_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "backups"


def list_backups(data_dir: Path) -> list[tuple[Path, datetime, int]]:
    """Τα αντίγραφα του e-Τιμολόγιο, **νεότερο πρώτο**."""
    folder = backups_dir(data_dir)
    if not folder.is_dir():
        return []
    found = []
    for path in folder.glob("etimologio-*.zip"):
        try:
            stat = path.stat()
        except OSError:
            continue
        found.append((path, datetime.fromtimestamp(stat.st_mtime), stat.st_size))
    found.sort(key=lambda item: item[1], reverse=True)
    return found


def is_empty(data_dir: Path) -> bool:
    """Είναι ολοκαίνουρια (χωρίς εταιρείες) η βάση του e-Τιμολόγιο;

    Ο έλεγχος γίνεται στα `aade_accounts` και όχι στους χρήστες: το κέλυφος
    φτιάχνει μόνο του λογαριασμό εργασίας σε κάθε εκκίνηση, οπότε «υπάρχει
    χρήστης» δεν σημαίνει τίποτα. Εταιρεία = δουλειά του χρήστη.
    """
    db = Path(data_dir) / "local.sqlite"
    if not db.is_file():
        return True
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT 1 FROM aade_accounts LIMIT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        # Πίνακας που δεν υπάρχει ακόμη = βάση που δεν έχει καν στηθεί.
        return True
    return row is None


def members_of(archive: Path) -> list[str]:
    """Τα αναγνωρισμένα αρχεία ενός αντιγράφου (κενό = δεν είναι δικό μας)."""
    try:
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return []
    return [name for name in MEMBERS if name in names]


def restore(archive: Path, data_dir: Path) -> list[str]:
    """Γράφει το περιεχόμενο του αντιγράφου στον φάκελο δεδομένων.

    Ο backend πρέπει να είναι **σταματημένος** όταν καλείται αυτό.

    Επιστρέφει τα αρχεία που γράφτηκαν. Πριν από οτιδήποτε άλλο κρατά αντίγραφο
    «pre-restore» της τρέχουσας κατάστασης: μια επαναφορά από λάθος αρχείο δεν
    πρέπει να είναι μονόδρομος.
    """
    data_dir = Path(data_dir)
    names = members_of(archive)
    if "local.sqlite" not in names:
        raise ValueError("Το αρχείο δεν είναι αντίγραφο του e-Τιμολόγιο.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety = backups_dir(data_dir) / f"pre-restore-{stamp}"
    safety.mkdir(parents=True, exist_ok=True)
    for name in MEMBERS:
        current = data_dir / name
        if current.is_file():
            shutil.copy2(current, safety / name)

    written: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        for name in names:
            if name in SKIP_ON_RESTORE:
                continue
            (data_dir / name).write_bytes(zf.read(name))
            written.append(name)

    # Τα WAL/SHM που ΔΕΝ ήρθαν με το αντίγραφο πρέπει να φύγουν: κρατούν
    # εγγραφές της ΠΑΛΙΑΣ βάσης και η SQLite θα τις έπαιζε πάνω στη νέα.
    for name in ("local.sqlite-wal", "local.sqlite-shm"):
        if name not in written:
            (data_dir / name).unlink(missing_ok=True)

    log.info("Επαναφορά e-Τιμολόγιο από %s (%s)", archive.name, ", ".join(written))
    return written


def adopt_existing(data_dir: Path) -> Path | None:
    """Άδεια εγκατάσταση + αντίγραφο στον φάκελο ⇒ φόρτωσέ το μόνο σου.

    Η περίπτωση δεν είναι θεωρητική: ο χρήστης δείχνει στην εγκατάσταση έναν
    φάκελο δεδομένων που κουβαλά από άλλο μηχάνημα (ή από αποκατάσταση δίσκου),
    και το e-Τιμολόγιο άνοιγε **άδειο** δίπλα στα αντίγραφά του, χωρίς να πει
    λέξη. Ο Downloader κάνει ήδη το αντίστοιχο για τη δική του βάση.

    Γίνεται ΜΟΝΟ όταν δεν υπάρχει καμία εταιρεία: ποτέ δεν γράφει πάνω από
    δουλειά που υπάρχει ήδη.
    """
    data_dir = Path(data_dir)
    if not is_empty(data_dir):
        return None
    for archive, _when, _size in list_backups(data_dir):
        if "local.sqlite" not in members_of(archive):
            continue
        try:
            restore(archive, data_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            log.warning("Το αντίγραφο %s δεν φορτώθηκε: %s", archive.name, exc)
            continue
        log.info("Άδεια βάση e-Τιμολόγιο — φορτώθηκε το %s", archive.name)
        return archive
    return None
