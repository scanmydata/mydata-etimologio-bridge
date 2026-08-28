"""Αντίγραφα ασφαλείας της βάσης — **και του κλειδιού της**.

Η βάση κρατά τα credentials και το ιστορικό λήψεων· τα PDF ξανακατεβαίνουν, η
βάση όχι. Παίρνουμε αντίγραφο **πριν** από κάθε import και κάθε sync — δηλαδή
πριν από κάθε ενέργεια που γράφει.

Χρησιμοποιείται το sqlite3 backup API αντί για απλό copy: δουλεύει σωστά ακόμη
κι όταν η βάση είναι ανοιχτή σε WAL mode, όπου ένα σκέτο copy μπορεί να πιάσει
ασυνεπές snapshot.

ΓΙΑΤΙ ΤΑΞΙΔΕΥΕΙ ΚΑΙ ΤΟ ``.enckey``
----------------------------------
Τα credentials είναι κρυπτογραφημένα με κλειδί που ζει **έξω** από τη βάση, στο
``.enckey`` του φακέλου δεδομένων. Ένα αντίγραφο μόνο της βάσης είναι λοιπόν
μισό: αν ο φάκελος στηθεί από την αρχή (νέο κλειδί) και μετά γίνει επαναφορά,
οι πελάτες επιστρέφουν **αλλά τα κλειδιά τους δεν ανοίγουν**. Δεν σκάει τίποτα:
η ``dec()`` γυρίζει κενό, η κατάσταση λέει «Διαθέσιμος» επειδή το κρυπτογράφημα
υπάρχει, και η λήψη αποτυγχάνει χωρίς να πει γιατί.

Συνέβη ακριβώς αυτό (24/08/2026): φρέσκος φάκελος στις 10:42, επαναφορά βάσης
στις 10:43, και 61 από 62 πελάτες έμειναν με κλειδιά που κανείς δεν μπορούσε να
διαβάσει. Από εδώ και πέρα κάθε αντίγραφο κουβαλά το κλειδί του, δίπλα του, με
το ίδιο όνομα και κατάληξη ``.enckey``.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

#: Πόσα αντίγραφα κρατάμε ανά είδος.
KEEP = 10

_STAMP = "%Y%m%d-%H%M%S"


def backup_dir(data_dir: Path) -> Path:
    return data_dir / "backups"


def key_for(data_dir: Path) -> Path:
    """Το κλειδί κρυπτογράφησης ενός φακέλου δεδομένων."""
    return data_dir / ".enckey"


def key_beside(backup_path: Path) -> Path:
    """Το κλειδί που ανήκει σε ΑΥΤΟ το αντίγραφο (ίδιο όνομα, .enckey)."""
    return backup_path.with_suffix(".enckey")


def create_backup(db_path: Path, reason: str = "manual") -> Path | None:
    """Φτιάχνει αντίγραφο. Επιστρέφει τη διαδρομή, ή None αν δεν υπάρχει βάση.

    Ποτέ δεν σηκώνει εξαίρεση προς τα πάνω: ένα αποτυχημένο backup δεν πρέπει
    να εμποδίσει τη δουλειά του χρήστη — απλώς καταγράφεται.
    """
    if not db_path.exists():
        return None
    target_dir = backup_dir(db_path.parent)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime(_STAMP)
    target = target_dir / f"timologio-{stamp}-{reason}.db"

    try:
        source = sqlite3.connect(db_path)
        dest = sqlite3.connect(target)
        with dest:
            source.backup(dest)  # συνεπές snapshot ακόμη και σε WAL
        dest.close()
        source.close()
    except sqlite3.Error as exc:
        log.warning("Αποτυχία αντιγράφου ασφαλείας: %s", exc)
        target.unlink(missing_ok=True)
        return None

    # Το κλειδί δίπλα στο αντίγραφο. Χωρίς αυτό η επαναφορά δίνει πελάτες με
    # κλειδιά που δεν ανοίγουν — δείτε το σχόλιο στην κορυφή του αρχείου.
    key = key_for(db_path.parent)
    if key.exists():
        try:
            shutil.copy2(key, key_beside(target))
        except OSError as exc:  # ένα αποτυχημένο αντίγραφο κλειδιού δεν μπλοκάρει
            log.warning("Το .enckey δεν αντιγράφηκε: %s", exc)

    prune(target_dir, reason)
    log.info("Αντίγραφο ασφαλείας: %s", target.name)
    return target


def prune(target_dir: Path, reason: str, keep: int = KEEP) -> int:
    """Κρατά τα `keep` νεότερα αντίγραφα του ίδιου είδους."""
    files = sorted(
        target_dir.glob(f"timologio-*-{reason}.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old in files[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
        # Το κλειδί δεν έχει νόημα να επιζήσει του αντιγράφου του — και δεν
        # πρέπει: ένα ορφανό κλειδί στον δίσκο είναι σκέτο ρίσκο.
        key_beside(old).unlink(missing_ok=True)
    return removed


def list_backups(data_dir: Path) -> list[tuple[Path, datetime, int]]:
    """(διαδρομή, ημερομηνία, μέγεθος) — νεότερα πρώτα."""
    target_dir = backup_dir(data_dir)
    if not target_dir.exists():
        return []
    out = []
    for path in target_dir.glob("timologio-*.db"):
        stat = path.stat()
        out.append((path, datetime.fromtimestamp(stat.st_mtime), stat.st_size))
    return sorted(out, key=lambda row: row[1], reverse=True)


def _credentials_open(db_path: Path, key_path: Path) -> tuple[int, int]:
    """(πόσα διαβάζονται, πόσα υπάρχουν) credentials με ΑΥΤΟ το κλειδί.

    Ο έλεγχος γίνεται με τα ίδια τα δεδομένα, όχι με σύγκριση αρχείων: δύο
    διαφορετικά ``.enckey`` μπορεί να είναι και τα δύο «έγκυρα» — μόνο ένα
    ανοίγει τη συγκεκριμένη βάση.
    """
    from .crypto import Crypto  # τοπικά: το backup.py φορτώνεται και χωρίς GUI

    if not db_path.exists() or not key_path.exists():
        return (0, 0)
    try:
        crypto = Crypto(key_path)
    except Exception:  # noqa: BLE001 — προστατευμένος φάκελος, χωρίς κωδικό εδώ
        return (0, 0)
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return (0, 0)
    try:
        rows = conn.execute(
            "SELECT mydata_key_enc FROM clients WHERE mydata_key_enc <> ''"
        ).fetchall()
    except sqlite3.Error:
        return (0, 0)
    finally:
        conn.close()
    return (sum(1 for r in rows if crypto.dec(r[0])), len(rows))


def restore(backup_path: Path, db_path: Path) -> Path:
    """Επαναφέρει αντίγραφο — και το κλειδί του, αν χρειάζεται.

    Η τρέχουσα βάση δεν διαγράφεται: κρατιέται ως αντίγραφο «pre-restore», ώστε
    μια λάθος επαναφορά να είναι αναστρέψιμη.

    Το ``.enckey`` **δεν** αντικαθίσταται αυτόματα κάθε φορά: μπαίνει μόνο όταν
    το τρέχον δεν ανοίγει τα επαναφερμένα credentials ενώ αυτό του αντιγράφου
    τα ανοίγει. Έτσι μια επαναφορά σε φάκελο που δουλεύει δεν μπορεί να τον
    χαλάσει, και μια επαναφορά σε φρέσκο φάκελο δεν αφήνει κλειδωμένα δεδομένα.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Δεν βρέθηκε το αντίγραφο: {backup_path}")

    safety = create_backup(db_path, reason="pre-restore")

    # Τα WAL/SHM του τρέχοντος αρχείου πρέπει να φύγουν, αλλιώς η SQLite μπορεί
    # να τα ξαναπαίξει πάνω στην επαναφερμένη βάση.
    for extra in (db_path.with_suffix(db_path.suffix + "-wal"),
                  db_path.with_suffix(db_path.suffix + "-shm")):
        extra.unlink(missing_ok=True)

    source = sqlite3.connect(backup_path)
    dest = sqlite3.connect(db_path)
    with dest:
        source.backup(dest)
    dest.close()
    source.close()

    # Ανοίγουν τα επαναφερμένα credentials με το κλειδί που έχει ο φάκελος;
    current = key_for(db_path.parent)
    opened, total = _credentials_open(db_path, current)
    if total and not opened:
        spare = key_beside(backup_path)
        if spare.exists() and _credentials_open(db_path, spare)[0]:
            # Το παλιό κλειδί φυλάγεται πριν αντικατασταθεί: ποτέ δεν σβήνουμε
            # κλειδί: μπορεί να ανοίγει δεδομένα που δεν βλέπουμε από εδώ.
            if current.exists():
                shutil.copy2(current, current.with_name(
                    f".enckey-{datetime.now().strftime(_STAMP)}-pre-restore"))
            shutil.copy2(spare, current)
            opened, total = _credentials_open(db_path, current)
            log.info("Επαναφέρθηκε και το κλειδί του αντιγράφου (%d/%d credentials)",
                     opened, total)
        else:
            # Δεν κρύβουμε το πρόβλημα: ο καλών το δείχνει στον χρήστη.
            log.error("Η επαναφορά έφερε %d credentials που ΔΕΝ ανοίγουν με το "
                      "κλειδί αυτού του φακέλου — λείπει το .enckey του αντιγράφου.",
                      total)

    log.info("Έγινε επαναφορά από %s (ασφάλεια: %s)", backup_path.name,
             safety.name if safety else "—")
    return db_path
