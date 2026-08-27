"""Ο δρομολογητής: αγγλικά, θόρυβος αναγνώρισης, και οι νέες λειτουργίες.

Γιατί υπάρχει αυτό το αρχείο: ο βοηθός καταλάβαινε **26%** από τις αγγλικές
εντολές, ενώ η εφαρμογή έχει επιλογέα γλώσσας και το whisper αναγνωρίζει
αγγλικά. Και δεν ήξερε τίποτα για ό,τι μπήκε από την 0.4.13 και μετά.

⚠️ Δύο μετρήσεις, και η δεύτερη είναι η σοβαρή:

* `eval_router.py` μετρά πάνω στο `intents_el.json` — το ίδιο σύνολο από το
  οποίο γράφτηκαν τα μοτίβα. Είναι δίχτυ παλινδρόμησης, όχι μέτρο ικανότητας.
* `eval_heldout.py` μετρά σε φράσεις γραμμένες στο χέρι, που **δεν** υπάρχουν
  πουθενά στα δεδομένα. Αυτό το ποσοστό λέει την αλήθεια.
"""

from __future__ import annotations

import pytest

from timologio.etimologio.assistant import (
    Assistant,
    fold,
    normalize,
    resolve_customer,
)

CUSTOMERS = [
    {"vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ"},
    {"vat": "802012659", "name": "MEGATECH ΙΚΕ"},
    {"vat": "998877665", "name": "Παπαδόπουλος"},
]
PRODUCTS = [{"code": "ΥΠ005", "description": "εκπαίδευση προσωπικού"}]


@pytest.fixture
def bot() -> Assistant:
    return Assistant(lambda: CUSTOMERS, lambda: PRODUCTS)


# --- αγγλικά ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "view"),
    [
        ("open the customers", "customers"),
        ("show me the documents", "documents"),
        ("where are my drafts", "drafts"),
        ("open the scheduler", "schedule"),
        ("statistics", "stats"),
        ("credit note", "credit"),
        ("bank import", "payments"),
        ("users and roles", "admin"),
        ("mass issue", "bulk"),
        ("customer card", "card"),
    ],
)
def test_english_navigation(bot: Assistant, text: str, view: str) -> None:
    assert bot.handle(text).navigate == view


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("user guide", "manual"),
        ("make a backup", "backup"),
        ("sign me out", "logout"),
        ("reload the page", "refresh"),
        ("be quiet", "speak:off"),
        ("open the palette", "palette"),
    ],
)
def test_english_commands(bot: Assistant, text: str, command: str) -> None:
    assert bot.handle(text).command == command


def test_english_targeted_commands(bot: Assistant) -> None:
    assert bot.handle("open the card of 998877665").command == "card:998877665"
    assert bot.handle("switch to company 094039270").command == "company:094039270"


def test_english_questions(bot: Assistant) -> None:
    assert bot.handle("turnover this month").fetch == "stats:month"
    assert bot.handle("how much did I invoice this year").fetch == "stats:year"
    assert "3" in bot.handle("how many clients are registered").say


# --- θόρυβος αναγνώρισης ------------------------------------------------------
def test_fold_makes_homophones_identical() -> None:
    """«εταιρεία» και «ετερεία» είναι ο ίδιος ήχος — και το ίδιο κείμενο."""
    assert fold(normalize("εταιρεία")) == fold(normalize("ετερεία"))
    assert fold(normalize("ξενάγηση")) == fold(normalize("ξενάγιση"))


@pytest.mark.parametrize(
    ("misheard", "command"),
    [("κάνε ξενάγιση", "tour"), ("άνιξε τη φονή", "speak:on")],
)
def test_misheard_commands_still_land(bot: Assistant, misheard: str, command: str) -> None:
    assert bot.handle(misheard).command == command


def test_misheard_company_switch(bot: Assistant) -> None:
    assert bot.handle("δούλεψε στην ετερεία 802012659").command == "company:802012659"


def test_fold_never_steals_an_exact_match(bot: Assistant) -> None:
    """Το «εγχειρίδιο» περιέχει «ιδι», που είναι το folded «είδη».

    Χωρίς το κατώφλι μήκους, η εντολή για το εγχειρίδιο άνοιγε τα Είδη.
    """
    assert bot.handle("άνοιξε το εγχειρίδιο").command == "manual"


def test_misheard_customer_name_still_resolves() -> None:
    """Ένα γράμμα διαφορά δεν είναι άλλος πελάτης."""
    assert resolve_customer(CUSTOMERS, "Παπαδόποιλος", "")["vat"] == "998877665"
    # Αλλά ούτε και οτιδήποτε: άσχετο όνομα μένει άγνωστο.
    assert resolve_customer(CUSTOMERS, "Αναγνωστόπουλος", "") is None


# --- οι λειτουργίες που δεν είναι εντολές -------------------------------------
@pytest.mark.parametrize(
    ("text", "view", "word"),
    [
        ("διάγραψε τις ειδοποιήσεις", "notifications", "✕"),
        ("γιατί λέει αναμονή", "documents", "Ανανέωση"),
        ("θέλω επαναφορά από αντίγραφο", "settings", "ΕΠΑΝΑΦΟΡΑ"),
        ("δοκίμασε τα κλειδιά", "customers", "Δοκιμή"),
        ("βάλε σκούρο θέμα", "settings", "Φωτεινό θέμα"),
    ],
)
def test_page_level_features_get_directions(
    bot: Assistant, text: str, view: str, word: str
) -> None:
    reply = bot.handle(text)
    assert reply.navigate == view
    assert word in reply.say


def test_column_chooser_answers_without_navigating(bot: Assistant) -> None:
    reply = bot.handle("θέλω άλλες στήλες")
    assert "Στήλες" in reply.say
    assert not reply.navigate


# --- ο κανόνας που δεν διαπραγματεύεται ---------------------------------------
@pytest.mark.parametrize(
    "text",
    ["στείλε το οριστικά στην ΑΑΔΕ", "πάρε ΜΑΡΚ για αυτό",
     "οριστικοποίησέ το", "issue it officially", "submit it to the tax office"],
)
def test_final_issue_is_always_refused(bot: Assistant, text: str) -> None:
    reply = bot.handle(text)
    assert "ΠΡΟΧΕΙΡΟ" in reply.say
    assert reply.draft is None


# --- πλοήγηση που έχανε από την έκδοση ----------------------------------------
@pytest.mark.parametrize(
    ("text", "view"),
    [
        ("τα παραστατικά", "documents"),
        ("τα τιμολόγιά μου", "documents"),
        ("τη μαζική έκδοση", "bulk"),
        ("την ακύρωση παραστατικού", "credit"),
        ("invoice series", "series"),
        ("scheduled invoices", "schedule"),
    ],
)
def test_section_names_are_not_issue_commands(bot: Assistant, text: str, view: str) -> None:
    """Λέξη τιμολόγησης ΧΩΡΙΣ τίποτα να εκδοθεί είναι όνομα οθόνης."""
    assert bot.handle(text).navigate == view


def test_a_real_issue_command_still_issues(bot: Assistant) -> None:
    """Ο έλεγχος από πάνω δεν επιτρέπεται να φάει τις αληθινές εντολές."""
    reply = bot.handle("τιμολόγιο στον 094039270 καθαρή αξία 100 είδος εκπαίδευση")
    assert reply.draft is not None or "ΠΡΟΧΕΙΡΟ" in reply.say


def test_the_name_does_not_swallow_the_amount(bot: Assistant) -> None:
    """Το «κόψε τιμολόγιο στην ΞΕΝΤΕ ΑΕ για 500» έψαχνε πελάτη «ΞΕΝΤΕ ΑΕ για 500»."""
    from timologio.etimologio.assistant import parse_issue

    assert parse_issue("κόψε τιμολόγιο στην ΞΕΝΤΕ ΑΕ για 500").name == "ΞΕΝΤΕ ΑΕ"
    assert parse_issue("τιμολόγιο στον Παπαδόπουλος 200 ευρώ").name == "Παπαδόπουλος"


# --- τα δύο ποσοστά -----------------------------------------------------------
def test_the_training_set_is_fully_covered() -> None:
    """Δίχτυ παλινδρόμησης: ό,τι έχει γραφτεί στα δεδομένα, πρέπει να πιάνεται."""
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "training" / "voice"))
    # Το πελατολόγιο/κατάλογος του eval_router, όχι το μικρό fixture αυτού του
    # αρχείου: με άδειο κατάλογο κάθε εντολή έκδοσης θα κατέληγε — σωστά — σε
    # «δημιούργησε πρώτα το είδος», και θα μετρούσαμε το κενό του fixture.
    from eval_router import CUSTOMERS as ALL  # noqa: PLC0415
    from eval_router import PRODUCTS as CATALOGUE  # noqa: PLC0415
    from eval_router import matches  # noqa: PLC0415

    rows = json.loads(
        (root / "training" / "voice" / "intents_el.json").read_text("utf-8")
    )
    misses = [
        row["input"] for row in rows
        if not matches(json.loads(row["output"]),
                       Assistant(lambda: ALL, lambda: CATALOGUE).handle(row["input"]))
    ]
    assert not misses, misses[:10]


def test_unknown_phrasings_do_not_regress() -> None:
    """Το ποσοστό που μετράει: φράσεις εκτός δεδομένων εκπαίδευσης.

    Το κατώφλι είναι σκόπιμα χαμηλότερο από το τρέχον (92%): φυλάει από
    οπισθοδρόμηση, δεν κλειδώνει έναν αριθμό που θα σπάει σε κάθε προσθήκη.
    """
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "training" / "voice"))
    from eval_heldout import verdict  # noqa: PLC0415

    rows = json.loads(
        (root / "training" / "voice" / "heldout_el.json").read_text("utf-8")
    )
    hits = sum(
        verdict(row["expect"],
                Assistant(lambda: CUSTOMERS, lambda: PRODUCTS).handle(row["input"]))
        for row in rows
    )
    assert hits / len(rows) >= 0.80, f"{hits}/{len(rows)}"
