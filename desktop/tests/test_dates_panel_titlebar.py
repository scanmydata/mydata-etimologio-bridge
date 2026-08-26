"""Ημερομηνίες, δεξί panel, γραμμές τίτλου, προεπισκόπηση — τα μικρά που ενοχλούν.

Κοινό νήμα: πράγματα που **φαίνονταν** σωστά στον κώδικα και λάθος στην οθόνη.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from timologio.gui import theme  # noqa: E402
from timologio.gui.widgets import GrDateEdit, parse_gr_date  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    theme.apply_theme(instance, "dark")
    yield instance


# --- ημερομηνίες όπως τις γράφει ο κόσμος -----------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("26/8/26", "26/08/2026"),      # η περίπτωση που το ζήτησε
        ("26/08/2026", "26/08/2026"),
        ("1/1/26", "01/01/2026"),
        ("26-8-2026", "26/08/2026"),
        ("26.08.26", "26/08/2026"),
        ("5/12/2025", "05/12/2025"),
    ],
)
def test_loose_dates_are_understood(text: str, expected: str) -> None:
    parsed = parse_gr_date(text)
    assert parsed is not None
    assert parsed.toString("dd/MM/yyyy") == expected


@pytest.mark.parametrize("text", ["31/2/26", "26/13/26", "26/8", "", "αύριο", "26//8/26"])
def test_impossible_dates_are_refused(text: str) -> None:
    """Το «31/02» δεν πρέπει να φτάσει ποτέ ως αίτημα στην ΑΑΔΕ."""
    assert parse_gr_date(text) is None


def test_two_digit_year_is_this_century() -> None:
    """Το myDATA ξεκίνησε το 2019 — «26» δεν σημαίνει ποτέ 1926."""
    assert parse_gr_date("26/8/26").year() == 2026


def test_field_commits_what_the_user_typed(app) -> None:
    """Το `fixup` του Qt δεν καλείται αξιόπιστα: χωρίς ρητό commit, η
    ημερομηνία που πληκτρολόγησε ο χρήστης αγνοούνταν **χωρίς μήνυμα**."""
    host = QWidget()
    box = QVBoxLayout(host)
    field, other = GrDateEdit(), QLineEdit()
    box.addWidget(field)
    box.addWidget(other)
    host.show()

    field.setFocus()
    field.lineEdit().setText("9/9/25")
    other.setFocus()  # ο χρήστης πάει αλλού
    app.processEvents()
    assert field.gr() == "09/09/2025"


def test_field_keeps_the_old_value_on_nonsense(app) -> None:
    field = GrDateEdit()
    field.setDate(QDate(2026, 3, 4))
    field.lineEdit().setText("31/2/26")
    field.commit_typed()
    assert field.gr() == "04/03/2026"


def test_date_fields_show_a_calendar_not_an_arrow() -> None:
    """Το βελάκι «κάτω» υπόσχεται λίστα· το πεδίο ανοίγει ημερολόγιο."""
    qss = theme.build(theme.DARK)
    arrow = re.search(r"QDateEdit::down-arrow \{\{?\s*image: url\(\"([^\"]+)\"\)", qss)
    assert arrow, "το QDateEdit δεν έχει δικό του εικονίδιο"
    assert "calendar-" in arrow.group(1)
    # Και το combo κρατά το βελάκι του.
    combo = re.search(r"QComboBox::down-arrow \{\s*image: url\(\"([^\"]+)\"\)", qss)
    assert combo and "arrow-" in combo.group(1)


def test_no_bare_date_field_is_left_in_the_etimologio_pages() -> None:
    """Τα σκέτα QDateEdit δεν είχαν ούτε ημερολόγιο ούτε ελληνική μορφή."""
    pages = REPO / "desktop" / "src" / "timologio" / "etimologio" / "pages"
    for path in pages.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "QDateEdit(" not in text, f"{path.name}: έμεινε σκέτο QDateEdit"


# --- το ίδιο, στο web -------------------------------------------------------
@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


def test_web_dates_accept_the_same_shorthand(page: str) -> None:
    body = page[page.index("function dtParse(v){"):]
    body = body[:body.index("\n}")]
    # Ένας διαχωριστής, δύο ή τέσσερα ψηφία έτους.
    assert r"[\/.\-]" in body
    assert "2000+ +m[3]" in body
    # Και έλεγχος υπαρκτής ημερομηνίας, όχι μόνο σχήματος.
    assert "getFullYear()!==y" in body


def test_web_mask_no_longer_eats_the_slashes(page: str) -> None:
    """Η παλιά μάσκα ξανακολλούσε τις καθέτους σε σταθερές θέσεις, οπότε το
    «26/8/26» γινόταν «26/82/6» — ήταν αδύνατο να γραφτεί."""
    body = page[page.index("function dtMask(el){"):]
    body = body[:body.index("\n}")]
    assert "el.value.replace(/[^\\d]/g,'')" not in body
    assert "caps=[2,2,4]" in body


def test_web_date_fields_get_a_calendar_button(page: str) -> None:
    assert "function addDatePickers(" in page
    assert "addEyes();addDatePickers();" in page, "δεν καλείται στην εκκίνηση"
    body = page[page.index("function addDatePickers(root){"):]
    body = body[:body.index("\n}\n")]
    assert "showPicker()" in body
    assert "native.click()" in body, "χρειάζεται εφεδρεία για παλιότερες μηχανές"
    # Στο blur η συντομογραφία γίνεται πλήρης ημερομηνία.
    assert "dtFix(inp)" in body


def test_web_date_wrapper_has_a_floor_width(page: str) -> None:
    """Χωρίς min-width το `.field` μάζευε στο πλάτος της ετικέτας και το κουμπί
    του ημερολογίου κάθονταν στη μέση του πεδίου."""
    css = page[page.index("  .dtwrap{"):]
    css = css[:css.index("\n  .dtwrap input")]
    assert "min-width:132px" in css
    assert "position:relative" in css


# --- η ξενάγηση μέσα στην εφαρμογή υπολογιστή -------------------------------
def test_tour_does_not_point_at_the_hidden_web_menu(page: str) -> None:
    """Στο desktop το πλαϊνό μενού του web είναι κρυμμένο: τα βήματα υπήρχαν στο
    DOM αλλά με μηδενικές διαστάσεις, οπότε η ξενάγηση έβγαινε χωρίς δαχτυλίδι."""
    assert "function tourEmbedFix(s){" in page
    body = page[page.index("function tourEmbedFix(s){"):]
    body = body[:body.index("\n}")]
    assert "isEmbedded()" in body
    assert "'#view-'+m[1]+' h2.title'" in body
    # Και τα δύο βήματα που μιλούν ΓΙΑ το μενού φεύγουν εντελώς.
    assert "TOUR_WEB_ONLY=['.side-actions','#themeToggle']" in page


# --- γραμμή τίτλου παντού ----------------------------------------------------
def test_every_window_gets_the_theme_title_bar(app, monkeypatch) -> None:
    """Ήταν βαμμένο μόνο το κεντρικό παράθυρο· κάθε διάλογος άνοιγε με λευκή
    μπάρα πάνω από σκούρα εφαρμογή."""
    painted: list[str] = []
    monkeypatch.setattr(
        theme, "paint_title_bar",
        lambda window, dark: painted.append(type(window).__name__) or True,
    )
    painter = theme.install_title_bar_painter(app)
    try:
        dialog = QWidget()
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.show()
        app.processEvents()
        assert painted, "κανένα παράθυρο δεν βάφτηκε"
    finally:
        app.removeEventFilter(painter)


def test_installer_wires_the_painter() -> None:
    boot = (REPO / "desktop" / "src" / "timologio" / "gui" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "install_title_bar_painter(app)" in boot


# --- προεπισκόπηση εκτύπωσης -------------------------------------------------
def test_zoom_field_is_not_clipped_by_the_app_padding() -> None:
    """Το γενικό `padding: 6px 9px` έτρωγε το κείμενο μέσα στη χαμηλή γραμμή
    εργαλείων: το «100,0%» φαινόταν κομμένο στη μέση, δηλαδή σαν άδειο κουτί."""
    src = (REPO / "desktop" / "src" / "timologio" / "gui" / "printing.py").read_text(
        encoding="utf-8"
    )
    body = src[src.index("def _fix_toolbar_combos("):]
    body = body[:body.index("\ndef ")]
    assert "padding:1px 4px" in body
    assert "Μεγέθυνση της προεπισκόπησης" in body, "το πεδίο δεν έχει ετικέτα πουθενά"


# --- το δεξί panel των πελατών ----------------------------------------------
def test_panel_can_be_dragged_narrower_than_its_default() -> None:
    """Το ελάχιστο ήταν ΙΣΟ με το κανονικό πλάτος — δηλαδή το χώρισμα δεν
    σερνόταν καθόλου."""
    from timologio.gui import main_window as mw

    assert mw._PANEL_MIN < mw._PANEL_W


def test_panel_has_a_switch_and_remembers_its_width() -> None:
    src = (REPO / "desktop" / "src" / "timologio" / "gui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "self.btn_panel = QPushButton" in src
    assert "_on_panel_toggled" in src
    assert 'self._prefs.setValue("panel/width", width)' in src
    # Μια νέα επιλογή δεν ξαναρίχνει το panel στα μούτρα του χρήστη.
    assert "self._set_panel_open(self._panel_wanted, animate=animate)" in src
    # Και ο πίνακας μπορεί να στενέψει, αλλιώς το χώρισμα δεν κουνιέται.
    assert "table_holder.setMinimumWidth(320)" in src
