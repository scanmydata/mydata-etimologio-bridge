"""Πέντε παράπονα της 0.4.19, με απόδειξη το καθένα.

* «η δοκιμή κωδικών rest-api λέει *Unexpected token '<'*» — ένα warning της PHP
  τυπωνόταν ΠΡΙΝ τη JSON και την αχρήστευε ολόκληρη. Συνέβαινε **μόνο** στην
  τοπική εγκατάσταση, γιατί εκεί ο ενσωματωμένος server της PHP τρέχει με
  `display_errors` ανοιχτό — στον VPS το `php.ini-production` το κλείνει.
* «η αναζήτηση να πιάνει όλες τις στήλες» — έπιανε ΑΦΜ και επωνυμία, ενώ ο
  πίνακας δείχνει δέκα στήλες.
* «στα Παραστατικά ο πελάτης με επωνυμία» — ο πίνακας της ΑΑΔΕ έχει μόνο ΑΦΜ
  αγοραστή· η επωνυμία υπάρχει μόνο στο δικό μας πελατολόγιο.
* «ο ιδιώτης να μπορεί να πάρει και ΑΦΜ» — προαιρετικά.
* «στον χρονοπρογραμματισμό: *Πελάτες*, ΑΦΜ–επωνυμία, ορατά κουτάκια» — η λίστα
  έδειχνε «031174383 · 031174383» επειδή ζητούσε στήλη `name` που δεν υπάρχει.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. Κανένα σφάλμα PHP μέσα στο σώμα της απάντησης ------------------------
def test_php_errors_never_reach_the_response_body():
    src = _read(ETIM_PHP)
    # Πριν από ΚΑΘΕ έξοδο: το φράγμα μπαίνει αμέσως μετά τα require, όχι σε
    # συνάρτηση που μπορεί να μην κληθεί ποτέ.
    guard = src.index("@ini_set('display_errors', '0')")
    assert guard < src.index("function jsonResponse")
    assert "@ini_set('html_errors', '0')" in src
    assert "@ini_set('log_errors', '1')" in src


def test_fatal_error_answers_as_json():
    """Και το μοιραίο σφάλμα βγαίνει ως JSON, με το πραγματικό μήνυμα."""
    src = _read(ETIM_PHP)
    handler = src[src.index("register_shutdown_function"):]
    handler = handler[: handler.index("// --- RESPONSE HELPERS")]
    assert "E_ERROR" in handler and "E_PARSE" in handler
    # Ποτέ δεύτερη απάντηση πάνω σε μία που ήδη έφυγε.
    assert "headers_sent()" in handler
    assert "'Content-Type: application/json'" in handler


@pytest.mark.skipif(not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe")
def test_bundled_php_prints_warnings_when_nobody_stops_it(tmp_path: Path):
    """Η απόδειξη ότι το φράγμα χρειάζεται.

    Ο ενσωματωμένος server της PHP τυπώνει τα warnings στην απάντηση όταν
    κανείς δεν του πει το αντίθετο — και ακριβώς αυτό έσπαγε τη JSON.
    """
    script = tmp_path / "leak.php"
    script.write_text(
        "<?php\n"
        "header('Content-Type: application/json');\n"
        "$x = $neverAssigned;\n"
        "echo json_encode(['success' => true]);\n",
        encoding="utf-8",
    )
    bare = subprocess.run(
        [str(PHP_EXE), "-n", "-d", "display_errors=1", "-f", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    assert not bare.lstrip().startswith("{"), "χωρίς φράγμα η απάντηση πρέπει να μολύνεται"
    assert "Warning" in bare

    guarded = subprocess.run(
        [str(PHP_EXE), "-n", "-d", "display_errors=0", "-d", "log_errors=0", "-f", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    assert guarded.strip() == '{"success":true}'


def test_local_server_logs_errors_to_a_file_of_its_own():
    src = _read(REPO / "desktop" / "src" / "timologio" / "etimologio" / "service.py")
    start = src.index("def start_local")
    body = src[start : src.index("def _wait_healthy")]
    for flag in ('"display_errors=0"', '"html_errors=0"', '"log_errors=1"'):
        assert flag in body, flag
    assert "php-errors.log" in body


# --- 2. Ό,τι δεν είναι JSON γίνεται αναγνώσιμο μήνυμα ------------------------
def test_non_json_replies_become_readable():
    src = _read(APP_PHP)
    assert "function apiParse(" in src
    # Και οι ΔΥΟ δρόμοι προς τον server περνούν από εκεί: το `apost` έκανε
    # σκέτο `r.json()`, και εκεί γεννιόταν το «Unexpected token '<'».
    assert "return apiParse(r);" in src
    assert "const d=await apiParse(r);" in src
    assert "r.json();}" not in src
    # Το μήνυμα λέει τι απάντησε ο server, όχι τι δεν κατάλαβε ο browser.
    assert "'HTTP '+status" in src


# --- 3. Ο πελάτης με επωνυμία στα Παραστατικά --------------------------------
def test_documents_table_shows_the_customer_name():
    src = _read(APP_PHP)
    assert "function docWho(i){" in src
    who = src[src.index("function docWho(i){"):]
    who = who[: who.index("function docRows()")]
    # Πρώτα ό,τι έστειλε η ΑΑΔΕ, μετά το πελατολόγιο, και ΤΕΛΕΥΤΑΙΟ το ΑΦΜ:
    # ποτέ κενό κελί.
    assert "i.counterpart_name||i.counterpart" in who
    assert "ALL_CUSTOMERS.map(custFields).find" in who
    assert "return (c&&c.name)?c.name:vat;" in who
    # Η αναζήτηση βλέπει ό,τι βλέπει το μάτι.
    rows = src[src.index("function docRows()"):]
    rows = rows[: rows.index("function renderDocs()")]
    assert "docWho(i)" in rows


def test_documents_table_never_waits_for_a_full_customer_sync():
    """Η επωνυμία δεν επιτρέπεται να καθυστερεί τον πίνακα.

    Το `cachedThenSync` περιμένει ΚΑΙ τον γύρο προς την ΑΑΔΕ· μια στήλη δεν
    αξίζει δευτερόλεπτα λευκής οθόνης.
    """
    src = _read(APP_PHP)
    load = src[src.index("async function loadDocs()"):]
    load = load[: load.index("function docWho(i)")]
    assert "await api({cached:'customers'})" in load
    assert "await loadCustomers()" not in load
    # Όταν όμως φτάσει φρέσκο πελατολόγιο, η στήλη ξαναγράφεται μόνη της.
    assert "if(ALL_DOCS.length&&$('#docTable'))renderDocs();" in src


# --- 4. Ο ιδιώτης με προαιρετικό ΑΦΜ ----------------------------------------
def test_personal_customer_accepts_an_optional_vat():
    src = _read(APP_PHP)
    assert 'id="cpVat"' in src
    save = src[src.index("async function saveCustomer()"):]
    save = save[: save.index("// Customer card")]
    # Κενό επιτρέπεται· μισό ΑΦΜ όχι — φαίνεται έγκυρο και δεν είναι.
    assert "cpv&&cpv.length!==9" in save
    assert "cust_vat:cpv" in save
    assert "saved={vat:cpv," in save
    # Και η καρτέλα δεν κρατά το ΑΦΜ του προηγούμενου πελάτη.
    assert "'cpName','cpVat'" in src
    # Ο τίτλος δεν λέει πια «χωρίς ΑΦΜ»: θα διέψευδε το ίδιο του το πεδίο.
    assert "Ιδιώτης (χωρίς ΑΦΜ)" not in src


def test_backend_already_carried_the_vat_through():
    """Το πεδίο υπήρχε στον server· έλειπε μόνο από τη φόρμα."""
    src = _read(ETIM_PHP)
    assert "$custVat" in src
    fn = src[src.index("function createPersonalCustomer("):]
    fn = fn[: fn.index("\n}\n")]
    assert "'CustomerVat'                => $customerVat," in fn
