"""Φύλακες για δύο λειτουργίες του ``app.php`` που αποτυγχάνουν ΣΙΩΠΗΛΑ.

Το ίδιο αρχείο σερβίρεται στο web και μέσα στην εφαρμογή υπολογιστή, και καμία
από τις δύο αυτές λειτουργίες δεν βγάζει σφάλμα όταν χαλάσει: η ξενάγηση
συνεχίζει να ανοίγει (απλώς δείχνει `<b>` μέσα στις προτάσεις και τοποθετεί το
κουτί έξω από την οθόνη) και το μικρόφωνο απλώς «δεν κάνει τίποτα».
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PHP = Path(__file__).resolve().parents[2] / "app.php"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tour(page: str) -> str:
    return page[page.index("// --- Guided page tour"):page.index("// --- User manual")]


# --- ξενάγηση ---------------------------------------------------------------
def test_tour_text_is_rendered_as_markup(tour: str) -> None:
    """Τα κείμενα είναι γραμμένα με <b>/<br>· με textContent φαίνονταν αυτούσια."""
    assert "$('#tourText').innerHTML=s.text" in tour
    assert "$('#tourText').textContent" not in tour


def test_tour_skips_steps_whose_target_is_missing(tour: str) -> None:
    """Ο πελάτης δεν έχει «Διαχείριση», ο server δεν έχει «Αντίγραφα».

    Ένα βήμα χωρίς στόχο έδειχνε κείμενο στη μέση της οθόνης, χωρίς δείκτη.
    """
    assert ".filter(s=>document.querySelector(s.sel))" in tour
    assert '{sel:\'[data-view="admin"]\'' not in tour, "το βήμα της Διαχείρισης επέστρεψε"


def test_tour_box_is_measured_and_clamped(tour: str) -> None:
    """Οι σταθερές 340/190 δεν χωρούσαν βήμα 380 pixel — έβγαινε εκτός οθόνης."""
    assert "box.offsetWidth" in tour and "box.offsetHeight" in tour
    assert "clamp(" in tour
    assert "340>window.innerWidth" not in tour
    # Ακαριαία κύλιση: με `smooth` το rect μετριόταν πριν φτάσει το στοιχείο.
    assert "behavior:'auto'" in tour
    assert "behavior:'smooth'" not in tour


# --- φωνή -------------------------------------------------------------------
def test_speech_errors_reach_the_user(page: str) -> None:
    """Στο web ο browser αναλαμβάνει την αναγνώριση — και μπορεί να πει όχι."""
    assert "CB_SR_MSG" in page
    for reason in ("not-allowed", "audio-capture", "network", "no-speech"):
        assert f"'{reason}'" in page, f"δεν εξηγείται το σφάλμα «{reason}»"
    # Το λαμπάκι ανάβει στο πραγματικό ξεκίνημα, όχι αισιόδοξα μετά το start().
    assert "r.onstart=" in page


def test_microphone_explains_an_insecure_page(page: str) -> None:
    """Χωρίς https κανένας browser δεν δίνει μικρόφωνο, και δεν το λέει στη σελίδα."""
    assert "window.isSecureContext" in page


def test_missing_voice_is_decided_after_the_voices_load(page: str) -> None:
    """Οι φωνές φορτώνουν ασύγχρονα· η πρώτη ματιά βρίσκει άδεια λίστα."""
    assert "if(!(speechSynthesis.getVoices()||[]).length)return null;" in page
    assert "cbSpeakBrowser(text,lang,true)" in page


def test_the_browser_engine_comes_first_in_the_browser(page: str) -> None:
    """Web Speech API πρώτα, Piper/whisper εφεδρεία — και το ανάποδο στο desktop.

    Στο web η μηχανή του server μπορεί να λείπει εντελώς (ο container δεν την
    κουβαλά)· στην εφαρμογή υπολογιστή το `webkitSpeechRecognition` παγώνει το
    QtWebEngine. Η σειρά ΔΕΝ είναι γούστο.
    """
    assert "function cbPreferBrowserVoice(){return !cbEmbedded();}" in page
    order = "cbPreferBrowserVoice()?['browser','server']:['server','browser']"
    assert order in page

    speak = page[page.index("function cbSpeak(t,retried)"):page.index("function cbSpeakWith(")]
    browser_at = speak.index("cbPreferBrowserVoice()")
    server_at = speak.index("?tts=1")
    assert browser_at < server_at, "η μηχανή του server δοκιμάζεται πριν τον browser"


def test_engine_failures_hand_over_to_the_other_engine(page: str) -> None:
    """Σφάλμα της υπηρεσίας δεν στέλνει τον χρήστη στο πληκτρολόγιο."""
    assert "CB_SR_FALLBACK" in page and "'network'" in page
    assert "CB_SR_HANDOFF" in page
    # Το onend έρχεται μετά το onerror: δεν σβήνει την ηχογράφηση που ξεκίνησε.
    end = page[page.index("r.onend=()=>{"):]
    assert "if(CB_SR_HANDOFF){" in end[:400]
