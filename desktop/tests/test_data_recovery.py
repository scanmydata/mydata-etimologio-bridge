"""Ο φάκελος δεδομένων και τα αντίγραφα του e-Τιμολόγιο.

Και τα δύο αφορούν το ίδιο σύμπτωμα, το χειρότερο που έχει η εφαρμογή: ανοίγει
κανονικά και **δεν έχει τα δεδομένα σου**. Δεν σκάει τίποτα, δεν γράφεται
τίποτα στο log, και ο χρήστης συμπεραίνει ότι τα έχασε.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from timologio import config
from timologio.etimologio import backup as etim_backup


def _db_with_clients(path: Path, rows: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE clients (vat TEXT)")
    for i in range(rows):
        conn.execute("INSERT INTO clients VALUES (?)", (f"00000000{i}",))
    conn.commit()
    conn.close()


def _empty_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE clients (vat TEXT)")
    conn.commit()
    conn.close()


# --- ο φάκελος δεδομένων ----------------------------------------------------
def test_the_configured_folder_wins_when_it_has_data(tmp_path: Path) -> None:
    good = tmp_path / "Παραστατικά myDATA"
    _db_with_clients(good / "timologio.db")
    assert config.recover_data_dir(good) == good


def test_a_truncated_folder_finds_the_real_one(tmp_path: Path, monkeypatch) -> None:
    """Το κόψιμο του installer γίνεται ΠΑΝΤΑ σε κενό.

    Ο πραγματικός φάκελος είναι λοιπόν αδελφός που ξεκινά με το ίδιο όνομα —
    ακριβώς το «Παραστατικά» δίπλα στο «Παραστατικά myDATA».
    """
    real = tmp_path / "Παραστατικά myDATA"
    _db_with_clients(real / "timologio.db", rows=3)
    truncated = tmp_path / "Παραστατικά"
    _empty_db(truncated / "timologio.db")   # ό,τι έφτιαξε η άδεια εκκίνηση

    saved: list[Path] = []
    monkeypatch.setattr(config, "_save_data_dir", saved.append)
    monkeypatch.setattr(config, "_default_data_dir", lambda: tmp_path / "δεν υπάρχει")

    assert config.recover_data_dir(truncated) == real
    # Και το διορθώνει, αλλιώς θα το ξαναβρίσκαμε σε κάθε εκκίνηση.
    assert saved == [real]


def test_a_fresh_install_is_left_alone(tmp_path: Path, monkeypatch) -> None:
    """Πρώτη εγκατάσταση: κανένας φάκελος δεν έχει πελάτες — μην ψάχνεις αλλού."""
    monkeypatch.setattr(config, "_default_data_dir", lambda: tmp_path / "προεπιλογή")
    monkeypatch.setattr(config, "_save_data_dir", lambda _path: pytest.fail("δεν έπρεπε"))
    fresh = tmp_path / "καινούριος"
    fresh.mkdir()
    assert config.recover_data_dir(fresh) == fresh


# --- αντίγραφα e-Τιμολόγιο --------------------------------------------------
def _archive(path: Path, *, db: bytes = b"SQLite format 3\0", key: bytes = b"k") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("local.sqlite", db)
        zf.writestr(".enckey", key)
        zf.writestr("service.json", '{"desktop_token":"ΑΛΛΟΥ ΜΗΧΑΝΗΜΑΤΟΣ"}')
    return path


def test_restore_writes_the_database_and_its_key(tmp_path: Path) -> None:
    """Χωρίς το κλειδί, η βάση είναι θόρυβος — ταξιδεύουν πάντα μαζί."""
    archive = _archive(tmp_path / "backups" / "etimologio-20260101-000000.zip",
                       db=b"NEW", key=b"NEWKEY")
    (tmp_path / "local.sqlite").write_bytes(b"OLD")
    (tmp_path / ".enckey").write_bytes(b"OLDKEY")

    written = etim_backup.restore(archive, tmp_path)

    assert (tmp_path / "local.sqlite").read_bytes() == b"NEW"
    assert (tmp_path / ".enckey").read_bytes() == b"NEWKEY"
    assert "service.json" not in written, "τα κλειδιά ΑΥΤΗΣ της εγκατάστασης δεν αντικαθίστανται"


def test_restore_keeps_the_current_state_as_pre_restore(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "backups" / "etimologio-20260101-000000.zip")
    (tmp_path / "local.sqlite").write_bytes(b"OLD")
    (tmp_path / ".enckey").write_bytes(b"OLDKEY")

    etim_backup.restore(archive, tmp_path)

    kept = list((tmp_path / "backups").glob("pre-restore-*/local.sqlite"))
    assert len(kept) == 1 and kept[0].read_bytes() == b"OLD"


def test_a_stale_wal_never_survives_a_restore(tmp_path: Path) -> None:
    """Το WAL της ΠΑΛΙΑΣ βάσης θα ξαναπαιζόταν πάνω στη νέα."""
    archive = _archive(tmp_path / "backups" / "etimologio-20260101-000000.zip")
    (tmp_path / "local.sqlite").write_bytes(b"OLD")
    (tmp_path / "local.sqlite-wal").write_bytes(b"STALE")

    etim_backup.restore(archive, tmp_path)

    assert not (tmp_path / "local.sqlite-wal").exists()


def test_a_foreign_zip_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "φωτογραφίες.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("cat.jpg", b"x")
    with pytest.raises(ValueError):
        etim_backup.restore(other, tmp_path)


def test_an_empty_install_adopts_the_newest_backup(tmp_path: Path) -> None:
    """Φάκελος από άλλο μηχάνημα: φορτώνεται μόνος του στην εκκίνηση."""
    old = _archive(tmp_path / "backups" / "etimologio-20260101-000000.zip", db=b"OLD")
    new = _archive(tmp_path / "backups" / "etimologio-20260202-000000.zip", db=b"NEW")
    import os
    import time

    os.utime(old, (time.time() - 600, time.time() - 600))

    assert etim_backup.adopt_existing(tmp_path) == new
    assert (tmp_path / "local.sqlite").read_bytes() == b"NEW"


def test_adoption_never_overwrites_existing_work(tmp_path: Path) -> None:
    """Υπάρχει εταιρεία ⇒ μη ΤΟΛΜΗΣΕΙΣ να γράψεις από πάνω."""
    _archive(tmp_path / "backups" / "etimologio-20260101-000000.zip", db=b"BACKUP")
    db = tmp_path / "local.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE aade_accounts (vat TEXT)")
    conn.execute("INSERT INTO aade_accounts VALUES ('802576637')")
    conn.commit()
    conn.close()
    before = db.read_bytes()

    assert etim_backup.adopt_existing(tmp_path) is None
    assert db.read_bytes() == before


def test_a_database_without_companies_counts_as_empty(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "local.sqlite")
    conn.execute("CREATE TABLE aade_accounts (vat TEXT)")
    conn.commit()
    conn.close()
    assert etim_backup.is_empty(tmp_path) is True
