"""Η άρθρωση: ό,τι λέει ο βοηθός, όπως πρέπει να ακουστεί.

Ο Piper διαβάζει ό,τι του δώσεις. Το «802576637» το έβγαζε σαν έναν τεράστιο
αριθμό, το «12.100,00 €» σαν «δώδεκα κόμμα εκατό», το «ΑΦΜ» σαν «αφμ», και το
«ΕΚΔΟΘΗΚΕ» χωρίς τόνο.

⚠️ **Ο σοβαρός έλεγχος είναι ο τελευταίος**: Python και PHP πρέπει να βγάζουν
ΑΚΡΙΒΩΣ το ίδιο κείμενο. Η φωνή καλείται και από τις δύο πλευρές — αν
αποκλίνουν, η ίδια πρόταση ακούγεται αλλιώς στην εφαρμογή υπολογιστή και αλλιώς
στον browser, και κανείς δεν το καταλαβαίνει μέχρι να τα ακούσει δίπλα-δίπλα.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from timologio.etimologio.speakable import (
    digit_groups,
    money,
    number,
    say_code,
    say_date,
    say_dotted,
    to_speech,
)

REPO = Path(__file__).resolve().parents[2]
PHP_EXE = REPO / "desktop" / "installer" / "php" / "php.exe"
PHP_SRC = REPO / "speakable.php"


# --- Οι αριθμοί ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "words"),
    [
        (0, "μηδέν"), (1, "ένα"), (13, "δεκατρία"), (21, "είκοσι ένα"),
        (100, "εκατό"), (101, "εκατόν ένα"), (900, "εννιακόσια"),
        (1000, "χίλια"), (1234, "χίλια διακόσια τριάντα τέσσερα"),
        (12100, "δώδεκα χιλιάδες εκατό"),
        (1000000, "ένα εκατομμύριο"),
        (-5, "μείον πέντε"),
    ],
)
def test_number_to_words(value: int, words: str) -> None:
    assert number(value) == words


def test_the_rule_that_started_it_all() -> None:
    """ΑΦΜ ανά δύο ψηφία· αν περισσέψει τρίτο, τα τελευταία τρία μαζί."""
    assert digit_groups("802576637") == ["80", "25", "76", "637"]
    assert say_code("802576637") == (
        "ογδόντα, είκοσι πέντε, εβδομήντα έξι, εξακόσια τριάντα επτά"
    )


def test_leading_zero_is_not_a_number() -> None:
    """Το «05» δεν είναι «πέντε» — είναι «μηδέν πέντε»."""
    assert say_code("094039270").startswith("μηδέν εννέα")


def test_dotted_codes_are_not_decimals() -> None:
    """Το «2.1» δεν είναι «δύο κόμμα ένα»: είναι δύο νούμερα με τελεία."""
    assert say_dotted("2.1") == "δύο τελεία ένα"
    assert say_dotted("11.2") == "έντεκα τελεία δύο"
    assert say_dotted("0.4.18") == "μηδέν τελεία τέσσερα τελεία δεκαοκτώ"


def test_money_and_cents() -> None:
    assert money(1, 0) == "ένα ευρώ"
    assert money(1, 1) == "ένα ευρώ και ένα λεπτό"
    assert money(12100, 0) == "δώδεκα χιλιάδες εκατό ευρώ"


def test_first_of_the_month_is_ordinal() -> None:
    assert say_date(1, 3, 2026).startswith("πρώτη μαρτίου")
    assert say_date(26, 8, 2026).startswith("είκοσι έξι αυγούστου")


# --- Ολόκληρες προτάσεις -------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ΑΦΜ 802576637",
         "αφιμί, ογδόντα, είκοσι πέντε, εβδομήντα έξι, εξακόσια τριάντα επτά"),
        ("Καθαρή αξία 12.100,00 €.", "καθαρή αξία δώδεκα χιλιάδες εκατό ευρώ."),
        ("ΦΠΑ 24%", "φιπιά είκοσι τέσσερα τοις εκατό"),
        ("Εκδόθηκε στις 26/08/2026.",
         "εκδόθηκε στις είκοσι έξι αυγούστου δύο χιλιάδες είκοσι έξι."),
        ("ΤΟ ΠΑΡΑΣΤΑΤΙΚΟ ΕΚΔΟΘΗΚΕ", "το παραστατικό εκδόθηκε"),
        ("Ετοίμασα ZIP με 3 PDF.", "ετοίμασα ζιπ με τρία πι ντι εφ."),
    ],
)
def test_whole_sentences(text: str, expected: str) -> None:
    assert to_speech(text) == expected


def test_the_bug_that_hid_behind_a_full_stop() -> None:
    """Το «ΜΑΡΚ 400000123456789.» δεν αναγνωριζόταν — επειδή τελείωνε η πρόταση.

    Το δεξί σύνορο του αριθμού απέκλειε κάθε τελεία, και η τελεία της πρότασης
    είναι στίξη, όχι μέρος του αριθμού.
    """
    said = to_speech("Το παραστατικό εκδόθηκε με ΜΑΡΚ 400000123456789.")
    assert "400000123456789" not in said
    assert "μαρκ, σαράντα" in said


def test_a_long_code_gets_a_pause_before_it() -> None:
    """Το κόμμα δεν είναι διακοσμητικό: ο Piper το μεταφράζει σε παύση."""
    assert "αφιμί, ογδόντα" in to_speech("ΑΦΜ 802576637")
    # Αλλά όχι μετά από στίξη — «αφιμί:, …» δεν λέγεται.
    assert ":," not in to_speech("ΑΦΜ: 094039270")


def test_unknown_text_is_left_alone() -> None:
    """Μια άγνωστη λέξη είναι πάντα καλύτερη από μια λέξη «διορθωμένη» λάθος."""
    assert to_speech("Δεν βρήκα πελάτη με αυτό το όνομα.") == \
        "δεν βρήκα πελάτη με αυτό το όνομα."


def test_icons_are_dropped_not_spelled() -> None:
    assert "📄" not in to_speech("📄 Άνοιξα τα Παραστατικά.")


def test_empty_input_is_empty_output() -> None:
    assert to_speech("") == ""
    assert to_speech("   ") == ""


def test_a_date_is_read_as_written_not_validated() -> None:
    """Δεν ελέγχουμε ημερολόγιο — διαβάζουμε ό,τι γράφει.

    Η «31/02/2026» δεν υπάρχει, αλλά η πιστή ανάγνωση («τριάντα ένα
    φεβρουαρίου») είναι πάντα καλύτερη από το να αφήσουμε τον Piper να
    συλλαβίσει «τριάντα ένα κάθετος μηδέν δύο κάθετος…». Ό,τι δεν έχει καν
    σχήμα ημερομηνίας (μήνας 99) διαβάζεται ως σκέτοι αριθμοί — πάλι πιστά.
    """
    assert "φεβρουαρίου" in to_speech("Ημερομηνία 31/02/2026")
    nonsense = to_speech("Κωδικός 12/99/2026")
    assert "μηνός" not in nonsense and "ενενήντα εννέα" in nonsense


# --- Τα δύο δίδυμα -------------------------------------------------------------
#: Το πραγματικό λεξιλόγιο του βοηθού — ό,τι φτάνει στον Piper στην πράξη.
CORPUS = [
    "Το παραστατικό εκδόθηκε με ΜΑΡΚ 400000123456789.",
    "Ο πελάτης με ΑΦΜ 802576637 καταχωρήθηκε.",
    "ΑΦΜ: 094039270",
    "Α.Φ.Μ. 112233445",
    "GR1601101250000000012300695",
    "Καθαρή αξία 12.100,00 €.",
    "Σύνολο 1.240,50 ευρώ με ΦΠΑ 24%.",
    "Παρακράτηση 20% και έκπτωση 5,5%.",
    "Εκδόθηκε στις 26/08/2026.",
    "Κατάλαβα 26/8/26.",
    "Ο τύπος είναι 2.1 Τιμολόγιο Παροχής Υπηρεσιών.",
    "Έκδοση 0.4.18",
    "Προγραμματίστηκε για τις 9:30.",
    "Ραντεβού στις 14:05.",
    "Τηλέφωνο 2101234567",
    "ΤΟ ΠΑΡΑΣΤΑΤΙΚΟ ΕΚΔΟΘΗΚΕ ΜΕ ΕΠΙΤΥΧΙΑ",
    "ΠΡΟΣΟΧΗ: Η ΑΠΟΣΤΟΛΗ ΑΠΕΤΥΧΕ",
    "Έχεις 7 αδιάβαστες ειδοποιήσεις.",
    "Το αντίγραφο είναι 444 MB.",
    "📄 Άνοιξα τα Παραστατικά — 320 γραμμές.",
    "Κατάσταση: ΕΛΗΦΘΗ",
    "Δεν βρήκα πελάτη με αυτό το όνομα.",
    "Ετοίμασα ZIP με 12 PDF παραστατικά.",
    "Βρήκα την επωνυμία από το VIES.",
    "Στείλε το με email στο myDATA.",
    "Πληρωμή 1.000.000,00 €",
    "Ημερομηνία 31/02/2026 — άκυρη.",
    "",
    "ΑΠΥ και ΤΠΥ και ΑΛΠ.",
    "Ποσό 45,5 ευρώ",
]


@pytest.mark.skipif(not PHP_EXE.exists(), reason="δεν υπάρχει το πακεταρισμένο php.exe")
def test_php_and_python_say_exactly_the_same_thing() -> None:
    """Ο έλεγχος που δικαιολογεί τα δύο αρχεία.

    Δύο υλοποιήσεις του ίδιου κανόνα αποκλίνουν σιωπηλά — και το λάθος
    ακούγεται μόνο αν κάποιος βάλει τα δύο δίπλα-δίπλα. Εδώ μπαίνουν δίπλα.
    """
    code = (
        "require getenv('SPK');"
        "$in = json_decode(stream_get_contents(STDIN), true);"
        "$out = [];"
        "foreach ($in as $t) { $out[] = to_speech($t); }"
        "echo json_encode($out, JSON_UNESCAPED_UNICODE);"
    )
    proc = subprocess.run(
        [str(PHP_EXE), "-r", code],
        input=json.dumps(CORPUS, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env={"SPK": str(PHP_SRC), "SystemRoot": r"C:\Windows"},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[:500]
    php_out = json.loads(proc.stdout.decode("utf-8"))
    for text, from_php in zip(CORPUS, php_out):
        assert to_speech(text) == from_php, f"διαφωνία στο {text!r}"


def test_the_two_files_stay_together() -> None:
    """Ο πακεταρισμένος server παίρνει το `speakable.php` από το backend."""
    vendored = REPO / "desktop" / "backend" / "etimologio" / "speakable.php"
    assert vendored.exists(), "λείπει το αντίγραφο του backend"
    assert vendored.read_bytes() == PHP_SRC.read_bytes(), \
        "το vendored speakable.php ξέφυγε από το πρωτότυπο"


def test_the_tts_endpoint_actually_calls_it() -> None:
    """Χωρίς αυτό, ο κανονικοποιητής θα υπήρχε και δεν θα έτρεχε ποτέ."""
    php = (REPO / "etimologio.php").read_text(encoding="utf-8")
    body = php[php.index("if (!empty($_GET['tts']"):]
    body = body[:body.index("$exe   = voice_engine('piper');")]
    assert "require_once __DIR__ . '/speakable.php';" in body
    assert "$ttsText = to_speech($ttsText);" in body


def test_the_desktop_voice_calls_it_too() -> None:
    speech = (REPO / "desktop" / "src" / "timologio" / "etimologio"
              / "speech.py").read_text(encoding="utf-8")
    assert "from .speakable import to_speech" in speech
