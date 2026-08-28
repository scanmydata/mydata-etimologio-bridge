"""Το αντίγραφο ασφαλείας που δεν μπορούσε να επαναφέρει τίποτα.

ΤΙ ΣΥΝΕΒΗ (24/08/2026, επαληθευμένο στα δεδομένα του χρήστη):

* 10:42 — ο φάκελος δεδομένων στήθηκε από την αρχή· φτιάχτηκε **νέο** `.enckey`.
* 10:43 — έγινε επαναφορά βάσης από αντίγραφο.
* Αποτέλεσμα: 61 από 62 πελάτες με κλειδί API που **δεν ανοίγει**.

Και τα τρία συμπτώματα ήταν βουβά:

1. Το αντίγραφο ήταν **μόνο η βάση** — το κλειδί που την ανοίγει έμενε πίσω.
2. Η στήλη «Κατάσταση» έβγαινε από το αν το *κρυπτογράφημα* είναι μη κενό, όχι
   από το αν διαβάζεται: όλοι έδειχναν «Διαθέσιμος».
3. Η `Crypto.dec()` γυρίζει κενό όταν αποτύχει, οπότε η καρτέλα του πελάτη
   άνοιγε με άδεια πεδία σαν να μην είχε καταχωρηθεί ποτέ κλειδί.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from timologio import backup as bk
from timologio.crypto import Crypto
from timologio.db import init_db
from timologio.models import Client
from timologio.repo import get_client, list_clients, unreadable_clients, upsert_client

VAT_A, VAT_B = "123456783", "998877665"


def _seed(folder: Path) -> None:
    """Φάκελος με δύο πελάτες που έχουν διαπιστευτήρια."""
    conn = init_db(folder / "timologio.db")
    crypto = Crypto(bk.key_for(folder))
    upsert_client(conn, Client(vat=VAT_A, label="ΑΛΦΑ ΑΕ",
                               mydata_user="userA", mydata_key="a" * 32), crypto)
    upsert_client(conn, Client(vat=VAT_B, label="ΒΗΤΑ ΟΕ",
                               mydata_user="userB", mydata_key="b" * 32), crypto)
    conn.commit()
    conn.close()


# --- 1. Το αντίγραφο κουβαλά το κλειδί του ---------------------------------
def test_a_backup_now_includes_the_key_that_opens_it(tmp_path: Path):
    folder = tmp_path / "data"
    folder.mkdir()
    _seed(folder)

    target = bk.create_backup(folder / "timologio.db", reason="manual")
    assert target is not None
    key_copy = bk.key_beside(target)
    assert key_copy.exists(), "το αντίγραφο πρέπει να κουβαλά το .enckey του"
    assert key_copy.read_bytes() == bk.key_for(folder).read_bytes()


def test_pruning_takes_the_key_with_the_backup(tmp_path: Path):
    """Ορφανό κλειδί στον δίσκο είναι σκέτο ρίσκο, χωρίς κανένα όφελος."""
    folder = tmp_path / "data"
    folder.mkdir()
    _seed(folder)

    made = []
    for _ in range(bk.KEEP + 2):
        target = bk.create_backup(folder / "timologio.db", reason="manual")
        assert target is not None
        # Ίδιο δευτερόλεπτο = ίδιο όνομα· το τσιμπάμε ώστε να γίνουν διακριτά.
        renamed = target.with_name(target.name.replace("timologio-", f"timologio-{len(made)}x"))
        target.rename(renamed)
        bk.key_beside(target).rename(bk.key_beside(renamed))
        made.append(renamed)

    bk.prune(bk.backup_dir(folder), "manual", keep=2)
    left = sorted(bk.backup_dir(folder).glob("*.db"))
    keys = sorted(bk.backup_dir(folder).glob("*.enckey"))
    assert len(keys) == len(left), "κάθε αντίγραφο που έμεινε κρατά το κλειδί του"


# --- 2. Η επαναφορά σε φρέσκο φάκελο ---------------------------------------
def test_restoring_into_a_fresh_folder_recovers_the_credentials(tmp_path: Path):
    """Το ακριβές σενάριο που κόστισε 61 πελάτες."""
    old = tmp_path / "old"
    old.mkdir()
    _seed(old)
    saved = bk.create_backup(old / "timologio.db", reason="manual")
    assert saved is not None

    # Φρέσκος φάκελος: **άλλο** κλειδί, όπως μετά από νέα εγκατάσταση.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    init_db(fresh / "timologio.db").close()
    Crypto(bk.key_for(fresh))
    assert bk.key_for(fresh).read_bytes() != bk.key_for(old).read_bytes()

    bk.restore(saved, fresh / "timologio.db")

    conn = init_db(fresh / "timologio.db")
    crypto = Crypto(bk.key_for(fresh))
    client = get_client(conn, VAT_A, crypto)
    assert client is not None
    assert client.mydata_user == "userA"
    assert client.mydata_key == "a" * 32, "τα διαπιστευτήρια πρέπει να ανοίγουν"
    assert unreadable_clients(conn, crypto) == []
    conn.close()


def test_the_replaced_key_is_kept_never_deleted(tmp_path: Path):
    """Ένα κλειδί μπορεί να ανοίγει δεδομένα που δεν βλέπουμε από εδώ."""
    old = tmp_path / "old"
    old.mkdir()
    _seed(old)
    saved = bk.create_backup(old / "timologio.db", reason="manual")

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    init_db(fresh / "timologio.db").close()
    Crypto(bk.key_for(fresh))
    before = bk.key_for(fresh).read_bytes()

    bk.restore(saved, fresh / "timologio.db")

    kept = list(fresh.glob(".enckey-*-pre-restore"))
    assert len(kept) == 1, "το κλειδί που αντικαταστάθηκε πρέπει να φυλάγεται"
    assert kept[0].read_bytes() == before


def test_a_restore_into_a_working_folder_never_swaps_its_key(tmp_path: Path):
    """Μια επαναφορά δεν επιτρέπεται να χαλάσει φάκελο που δουλεύει."""
    folder = tmp_path / "data"
    folder.mkdir()
    _seed(folder)
    key_before = bk.key_for(folder).read_bytes()
    saved = bk.create_backup(folder / "timologio.db", reason="manual")

    bk.restore(saved, folder / "timologio.db")

    assert bk.key_for(folder).read_bytes() == key_before
    assert not list(folder.glob(".enckey-*-pre-restore"))


def test_restore_without_a_key_copy_leaves_a_loud_trace(tmp_path: Path, caplog):
    """Παλιό αντίγραφο (χωρίς κλειδί): δεν σιωπούμε."""
    old = tmp_path / "old"
    old.mkdir()
    _seed(old)
    saved = bk.create_backup(old / "timologio.db", reason="manual")
    bk.key_beside(saved).unlink()          # όπως κάθε αντίγραφο πριν από σήμερα

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    init_db(fresh / "timologio.db").close()
    Crypto(bk.key_for(fresh))

    with caplog.at_level("ERROR"):
        bk.restore(saved, fresh / "timologio.db")
    assert any("ΔΕΝ ανοίγουν" in r.getMessage() for r in caplog.records)


# --- 3. Η κατάσταση σταματά να λέει ψέματα ---------------------------------
def test_a_client_whose_key_cannot_be_read_is_reported(tmp_path: Path):
    folder = tmp_path / "data"
    folder.mkdir()
    _seed(folder)

    # Το κλειδί του φακέλου αλλάζει — ό,τι ακριβώς έγινε στις 24/08.
    bk.key_for(folder).unlink()
    stranger = Crypto(bk.key_for(folder))

    conn = init_db(folder / "timologio.db")
    locked = unreadable_clients(conn, stranger)
    assert sorted(locked) == sorted([VAT_A, VAT_B])

    # Και η αποθηκευμένη κατάσταση εξακολουθεί να λέει «ready»: αυτό ακριβώς
    # ήταν το παραπλανητικό, και γι' αυτό ο έλεγχος γίνεται στα δεδομένα.
    rows = {r["vat"]: r["status"] for r in list_clients(conn)}
    assert rows[VAT_A] == "ready"
    conn.close()


def test_a_healthy_folder_reports_nothing(tmp_path: Path):
    folder = tmp_path / "data"
    folder.mkdir()
    _seed(folder)
    conn = init_db(folder / "timologio.db")
    assert unreadable_clients(conn, Crypto(bk.key_for(folder))) == []
    conn.close()


# --- 4. Η οθόνη το λέει ----------------------------------------------------
pytest.importorskip("PySide6")


def test_the_clients_page_warns_about_locked_keys(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None
    monkeypatch.setenv("TIMOLOGIO_DATA_DIR", str(tmp_path))
    _seed(tmp_path)
    bk.key_for(tmp_path).unlink()          # ο φάκελος αποκτά άλλο κλειδί

    from timologio.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window.reload_clients()
        assert window.lbl_locked.isVisible() or window._locked_vats
        assert len(window._locked_vats) == 2
        text = window.lbl_locked.text()
        assert "2 πελάτες" in text
        assert "Εισαγωγή από Excel" in text, "η ειδοποίηση πρέπει να λέει τι να κάνει"
        # Και η στήλη δεν λέει πια «Διαθέσιμος».
        labels = {window.table.item(r, 1).text(): window.table.item(r, 3).text()
                  for r in range(window.table.rowCount())}
        assert set(labels.values()) == {"Κλειδί κλειδωμένο"}
    finally:
        window.close()
