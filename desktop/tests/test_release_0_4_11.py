"""Φύλακες για τις αλλαγές της 0.4.11.

Καθένα από αυτά αντιστοιχεί σε κάτι που **έσπασε σιωπηλά** ή που θα ξανασπάσει
με μια αθώα μετονομασία, χωρίς κανένα σφάλμα πουθενά.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
AUTHVIEW = REPO / "authview.php"
ISS = Path(__file__).resolve().parents[1] / "installer" / "timologio.iss"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


# --- ο installer έκοβε τον φάκελο δεδομένων στο κενό ------------------------
def test_installer_never_reads_a_path_with_the_param_constant() -> None:
    """`{param:…}` κόβει την τιμή στο πρώτο κενό — μετρημένο σε πραγματικό update.

    Το `/DATADIR="C:\\…\\Παραστατικά myDATA"` έφτανε ΟΛΟΚΛΗΡΟ στο setup.exe
    (φαίνεται στο log του Inno) και γραφόταν στο μητρώο ως
    `C:\\…\\Παραστατικά`. Η επόμενη εκκίνηση άνοιγε άδεια βάση.
    """
    script = ISS.read_text(encoding="utf-8-sig")
    assert "function CmdLineParam" in script
    assert "ParamStr(I)" in script
    # Μόνο ο ΚΩΔΙΚΑΣ μετράει: τα σχόλια εξηγούν ακριβώς αυτή την παγίδα και
    # οφείλουν να αναφέρουν το όνομά της.
    code = [
        line for line in script.splitlines()
        if not line.lstrip().startswith((";", "//"))
    ]
    offenders = [line.strip() for line in code if "{param:" in line]
    assert offenders == [], f"επέστρεψε το κόψιμο στο κενό: {offenders}"


# --- δοκιμή διαπιστευτηρίων myDATA ------------------------------------------
def test_credentials_are_tested_against_the_documented_endpoint() -> None:
    """myDATA REST API v2.0.1 §4.2.9 — σύνολα εξόδων, όχι κατέβασμα."""
    from timologio.config import URL_REQUEST_MY_EXPENSES
    from timologio.mydata.client import MydataClient

    assert URL_REQUEST_MY_EXPENSES.endswith("/RequestMyExpenses")
    assert URL_REQUEST_MY_EXPENSES.startswith("https://mydatapi.aade.gr/myDATA")
    assert hasattr(MydataClient, "check_credentials")


def test_the_probe_asks_for_the_current_month_in_aade_format() -> None:
    from timologio.gui.client_dialog import current_month

    date_from, date_to = current_month()
    assert date_from.startswith("01/"), "η περίοδος ξεκινά την 1η του μήνα"
    for value in (date_from, date_to):
        day, month, year = value.split("/")
        assert (len(day), len(month), len(year)) == (2, 2, 4), "μορφή dd/MM/yyyy"
    assert date_from[3:] == date_to[3:], "ίδιος μήνας και χρόνος"


def test_zero_expenses_is_not_a_failure() -> None:
    """Ένας πελάτης μπορεί κάλλιστα να μην έχει έξοδα αυτόν τον μήνα."""
    from timologio.gui import client_dialog

    source = Path(client_dialog.__file__).read_text(encoding="utf-8")
    body = source[source.index("class _CredentialProbe"):]
    assert "self.done.emit(True," in body
    assert "χωρίς έξοδα" in body


# --- ρυθμίσεις σε πτυσσόμενες ενότητες --------------------------------------
def test_settings_are_split_into_collapsible_sections(page: str) -> None:
    assert "function setupSections" in page
    assert "setupSections('#view-settings')" in page
    assert "sectAll('#view-settings',true)" in page
    # Η ξενάγηση δείχνει πεδία ΜΕΣΑ σε ενότητες: κλειστή ενότητα = στοιχείο
    # μηδενικών διαστάσεων, δηλαδή δείκτης στη γωνία της οθόνης.
    assert "function sectReveal" in page
    place = page[page.index("function tourPlace"):]
    assert "sectReveal(el);" in place[:400]


# --- επαναφορά από αντίγραφο ------------------------------------------------
def test_the_page_asks_the_app_to_restore(page: str) -> None:
    """Η επαναφορά ΔΕΝ γίνεται από την PHP: αντικαθιστά τη βάση του ίδιου server."""
    from timologio.etimologio import webshell

    assert 'id="bkRestore"' in page
    assert "h.restoreBackup();" in page
    source = Path(webshell.__file__).read_text(encoding="utf-8")
    assert "def restoreBackup(" in source
    body = source[source.index("def restore_backup(self)"):]
    stop_at = body.index("etim_backup.restore(")
    assert "self.shutdown()" in body[:stop_at], "ο server πρέπει να σταματήσει ΠΡΙΝ"


def test_an_empty_install_loads_the_folder_by_itself() -> None:
    from timologio.etimologio import service

    source = Path(service.__file__).read_text(encoding="utf-8")
    body = source[source.index("def start_local"):]
    assert "adopt_existing" in body[:body.index("self._port = _free_port()")]


# --- η οθόνη σύνδεσης -------------------------------------------------------
def test_the_login_screen_shows_one_logo_not_three() -> None:
    markup = AUTHVIEW.read_text(encoding="utf-8")
    assert "logo-downloader" not in markup
    assert 'class="suite"' not in markup
    assert "brand-logo" in markup, "το σήμα του e-Τιμολόγιο μένει"
