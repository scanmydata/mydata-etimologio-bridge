"""Τα Παραστατικά: ο τύπος με το όνομά του, και η «Ανανέωση» που κοιτά τον φάκελο.

Τρία παράπονα, μία σελίδα:

* «στη στήλη τύπος να εμφανίζεται και το κείμενο» — ο σκέτος κωδικός «2.1» δεν
  λέει τίποτα σε όποιον δεν τον ξέρει απ' έξω, και δεν αναζητείται με λέξη.
* «κολλάει» — ο πίνακας έφτιαχνε **δύο widgets ανά γραμμή** για το κουμπί
  ανοίγματος, και ξαναχτιζόταν σε κάθε πλήκτρο της αναζήτησης.
* «πατώντας ανανέωση δεν τσεκάρει τους φακέλους» — η ανανέωση ξαναέτρεχε το ίδιο
  query πάνω στην ίδια, λάθος βάση.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from timologio.doctypes import INVOICE_TYPE_NAMES, type_label, type_name

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from timologio.config import Settings  # noqa: E402
from timologio.crypto import Crypto  # noqa: E402
from timologio.db import init_db  # noqa: E402
from timologio.gui import documents_view as dv  # noqa: E402
from timologio.models import Client, Direction, DocStatus, Document  # noqa: E402
from timologio.repo import upsert_client, upsert_document  # noqa: E402
from timologio.sync import reconcile_downloads  # noqa: E402

CLIENT_VAT = "123456783"


# --- ο τύπος με το όνομά του -------------------------------------------------
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("2.1", "2.1 Τιμολόγιο Παροχής Υπηρεσιών"),
        ("1.1", "1.1 Τιμολόγιο Πώλησης"),
        ("11.2", "11.2 ΑΠΥ — Απόδειξη Παροχής Υπηρεσιών"),
        ("", "—"),
        # Άγνωστος (ή νέος) κωδικός: επιστρέφεται όπως ήρθε. Η ΑΑΔΕ προσθέτει
        # τύπους — μια γραμμή δεν επιτρέπεται να χαθεί επειδή δεν τον ξέρουμε.
        ("99.9", "99.9"),
    ],
)
def test_type_label(code: str, expected: str) -> None:
    assert type_label(code) == expected


def test_sort_key_follows_the_annex_not_the_alphabet() -> None:
    """Σκέτο κείμενο έβαζε το «11.1» πριν από το «2.1»."""
    order = sorted(["11.1", "2.1", "1.1", "13.30"], key=dv._type_sort_key)
    assert order == ["1.1", "2.1", "11.1", "13.30"]


def test_labels_are_unique_enough_to_tell_apart() -> None:
    """Δύο τύποι με ΤΟ ΙΔΙΟ όνομα θα ήταν χειρότεροι από τον σκέτο κωδικό."""
    for code in ("13.30", "14.30"):
        assert code in INVOICE_TYPE_NAMES
    assert type_name("2.1") != type_name("2.2")


# --- η σελίδα ---------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def view(app, tmp_path: Path):
    conn = init_db(tmp_path / "t.db")
    crypto = Crypto(tmp_path / ".enckey")
    cid = upsert_client(
        conn,
        Client(vat=CLIENT_VAT, label="ΔΕΙΓΜΑ ΑΕ", mydata_user="u", mydata_key="k" * 32),
        crypto,
    )
    for i, itype in enumerate(("2.1", "1.1")):
        upsert_document(
            conn, cid,
            # Ξεχωριστή σειρά/ΑΑ: αλλιώς τα δύο παραστατικά καταλήγουν στο ΙΔΙΟ
            # όνομα αρχείου, που δεν είναι η συνηθισμένη περίπτωση.
            Document(mark=f"m{i}", invoice_type=itype, issuer_vat="987654324",
                     counter_vat=CLIENT_VAT, issue_date="2026-07-10",
                     series="A", aa=str(100 + i),
                     total_value=10.0, direction=Direction.INCOMING,
                     downloading_invoice_url="https://x.gr/a"),
        )
    conn.commit()
    page = dv.DocumentsView(Settings(data_dir=tmp_path), QSettings("scanmydata-test", "dt"))
    page.show_client(conn, CLIENT_VAT, "ΔΕΙΓΜΑ ΑΕ", "all")
    return page


def test_the_column_shows_code_and_name(view) -> None:
    texts = {view.table.item(r, dv._COL_TYPE).text() for r in range(view.table.rowCount())}
    assert "2.1 Τιμολόγιο Παροχής Υπηρεσιών" in texts
    assert "1.1 Τιμολόγιο Πώλησης" in texts


def test_search_finds_the_type_by_word(view) -> None:
    """Ο λόγος που μπήκε το κείμενο: «υπηρεσι» δεν έβρισκε τίποτα."""
    view.search.setText("υπηρεσι")
    view._fill()
    assert view.table.rowCount() == 1
    assert view.table.item(0, dv._COL_TYPE).text().startswith("2.1")
    # Και ο κωδικός συνεχίζει να δουλεύει.
    view.search.setText("1.1")
    view._fill()
    assert view.table.rowCount() == 1


def test_column_filter_lists_the_readable_values(view) -> None:
    values = view._distinct_col_values(dv._COL_TYPE)
    assert "2.1 Τιμολόγιο Παροχής Υπηρεσιών" in values


def test_typing_does_not_rebuild_the_table_on_every_key(view) -> None:
    """Με μερικές χιλιάδες γραμμές, ένα ξαναγέμισμα ανά πλήκτρο πάγωνε την
    εφαρμογή όσο πληκτρολογούσε ο χρήστης."""
    fills: list[int] = []
    view._fill = lambda: fills.append(1)  # type: ignore[method-assign]
    view.search.setText("αβγ")
    assert fills == [], "το φιλτράρισμα έτρεξε ακαριαία, χωρίς αναμονή"
    assert view._search_timer.isActive()


def test_no_widget_per_row(view) -> None:
    """Η στήλη ανοίγματος είναι κελί, όχι κουμπί-widget: δύο widgets ανά γραμμή
    κόστιζαν ~3 δευτερόλεπτα σε 8.000 παραστατικά, σε κάθε γέμισμα."""
    for r in range(view.table.rowCount()):
        assert view.table.cellWidget(r, dv._COL_OPEN) is None
        assert view.table.item(r, dv._COL_OPEN) is not None


def test_open_cell_carries_the_action(view) -> None:
    item = view.table.item(0, dv._COL_OPEN)
    # Χωρίς αρχείο και χωρίς «μόνο online»: τίποτα να ανοίξει.
    assert item.data(dv._ACT_ROLE) is None


# --- η ανανέωση κοιτά τον φάκελο --------------------------------------------
def _pdf_for(conn, settings: Settings, mark: str) -> Path:
    """Γράφει στον δίσκο το PDF που ΘΑ έγραφε η λήψη, χωρίς να πειράξει τη βάση.

    Αυτή ακριβώς είναι η κατάσταση που άφηνε πίσω της μια διακοπή: το αρχείο
    γράφεται πρώτο, η εγγραφή «ελήφθη» δεύτερη.
    """
    from timologio.download import target_path
    from timologio.sync import _doc_from_row

    row = conn.execute("SELECT * FROM documents WHERE mark=?", (mark,)).fetchone()
    path = target_path(settings.storage_root, CLIENT_VAT, _doc_from_row(row),
                       client_label="ΔΕΙΓΜΑ ΑΕ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n" + b"x" * 400 + b"\n%%EOF\n")
    return path


def test_reconcile_marks_what_is_already_on_disk(view) -> None:
    settings = view._settings
    conn = view._conn
    assert conn.execute("SELECT status FROM documents WHERE mark='m0'").fetchone()[0] \
        == DocStatus.PENDING.value
    _pdf_for(conn, settings, "m0")

    fixed, missing = reconcile_downloads(conn, settings, CLIENT_VAT)
    assert (fixed, missing) == (1, 0)
    row = conn.execute("SELECT status, local_path, file_bytes FROM documents "
                       "WHERE mark='m0'").fetchone()
    assert row["status"] == DocStatus.DOWNLOADED.value
    assert row["local_path"]
    assert row["file_bytes"] > 0


def test_reconcile_only_counts_missing_files_never_undoes_them(view) -> None:
    """Ένα μεταφερμένο PDF δεν είναι λόγος να ξανακατέβει ο μισός χρόνος του
    πελάτη: το λέμε στον χρήστη και αποφασίζει εκείνος."""
    conn, settings = view._conn, view._settings
    path = _pdf_for(conn, settings, "m1")
    reconcile_downloads(conn, settings, CLIENT_VAT)
    assert conn.execute("SELECT status FROM documents WHERE mark='m1'").fetchone()[0] \
        == DocStatus.DOWNLOADED.value

    path.unlink()
    fixed, missing = reconcile_downloads(conn, settings, CLIENT_VAT)
    assert (fixed, missing) == (0, 1)
    assert conn.execute("SELECT status FROM documents WHERE mark='m1'").fetchone()[0] \
        == DocStatus.DOWNLOADED.value, "η κατάσταση ΔΕΝ γυρίζει πίσω μόνη της"


def test_reconcile_is_quiet_about_an_unknown_client(view) -> None:
    assert reconcile_downloads(view._conn, view._settings, "000000000") == (0, 0)


def test_reconcile_does_no_work_when_there_is_nothing_to_find(view, monkeypatch) -> None:
    """Ο έλεγχος τρέχει σε ΚΑΘΕ άνοιγμα των Παραστατικών.

    Με 8.000 εκκρεμή, το «χτίσε τη διαδρομή κάθε παραστατικού και ρώτα τον
    δίσκο» κόστιζε περίπου ενάμισι δευτερόλεπτο — για να μη βρει τίποτα.
    """
    built: list[str] = []
    import timologio.sync as sync

    real = sync.target_path
    monkeypatch.setattr(
        sync, "target_path",
        lambda *a, **k: (built.append("x"), real(*a, **k))[1],
    )
    assert reconcile_downloads(view._conn, view._settings, CLIENT_VAT) == (0, 0)
    assert built == [], "χτίστηκαν διαδρομές ενώ ο φάκελος είναι άδειος"


def test_a_stray_file_in_the_wrong_month_is_ignored(view) -> None:
    """Το φιλτράρισμα κατά φάκελο έτους/μήνα δεν επιτρέπεται να ταιριάξει
    παραστατικό με αρχείο άλλης περιόδου."""
    root = view._settings.storage_root
    stray = root / "123456783 ΔΕΙΓΜΑ ΑΕ" / "2019" / "01" / "τυχαίο.pdf"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"%PDF-1.4\n" + b"x" * 400 + b"\n%%EOF\n")
    assert reconcile_downloads(view._conn, view._settings, CLIENT_VAT) == (0, 0)


def test_refresh_button_runs_the_folder_check(view, monkeypatch) -> None:
    """Το κουμπί έλεγε «ξαναδιαβάζει από τη βάση» — και αυτό ακριβώς έκανε."""
    seen: list[str] = []
    monkeypatch.setattr(
        "timologio.sync.reconcile_downloads",
        lambda conn, settings, vat: (seen.append(vat), (0, 0))[1],
    )
    view._refresh_clicked()
    assert seen == [CLIENT_VAT]
