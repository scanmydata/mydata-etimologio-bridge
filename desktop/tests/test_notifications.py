"""Οι ειδοποιήσεις: το ποσό και το ✕.

Και τα δύο ήταν σφάλματα που **δεν φαίνονταν πουθενά** παρά μόνο στα μάτια του
χρήστη: ένα τιμολόγιο 12.100 € που γράφεται 12,10 €, και μια λίστα που δεν
αδειάζει ποτέ.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"
LOCALDB = REPO / "localdb.php"


@pytest.fixture(scope="module")
def page() -> str:
    return APP_PHP.read_text(encoding="utf-8")


# --- Το ποσό ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12.100,00 €", 12100.0),   # η περίπτωση που το ανέδειξε
        ("12.100", 12100.0),        # στρογγυλό, χωρίς κόμμα: εδώ έσπαγε
        ("1.234,56", 1234.56),
        ("1.234.567", 1234567.0),
        ("-1.500,25", -1500.25),
        ("1234.56", 1234.56),       # αγγλική μορφή: η τελεία ΕΙΝΑΙ υποδιαστολή
        ("12,10", 12.1),
        ("999", 999.0),
        ("", 0.0),
        ("σκουπίδι", 0.0),
    ],
)
def test_python_money_parser(text: str, expected: float) -> None:
    from timologio.etimologio.pages.base import parse_money

    assert parse_money(text) == pytest.approx(expected)


def test_the_php_parser_follows_the_same_rule() -> None:
    """Δύο parsers που διαφωνούν είναι χειρότεροι από έναν λάθος: το ίδιο ποσό
    θα φαινόταν αλλιώς στη σελίδα και αλλιώς στην εφαρμογή υπολογιστή."""
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("function parseMoney(string $s): float {"):]
    body = body[:body.index("\n}")]
    # Σκέτες τελείες που χωρίζουν ΑΚΡΙΒΩΣ τριάδες = χιλιάδες.
    assert r"^-?\d{1,3}(\.\d{3})+$" in body

    py = (REPO / "desktop" / "src" / "timologio" / "etimologio" / "pages" / "base.py").read_text(
        encoding="utf-8"
    )
    assert r"^-?\d{1,3}(\.\d{3})+$" in py


def test_the_aade_check_uses_the_shared_parser() -> None:
    """Το σημείο του σφάλματος: δικό του `str_replace` αντί για τον helper.

    Το «,»→«.» έκανε το «12.100,00» → «12.100.00», και η `(float)` της PHP
    σταματά στη δεύτερη τελεία: **12.1**.
    """
    php = ETIM_PHP.read_text(encoding="utf-8")
    assert "str_replace([',', ' '], ['.', ''], (string)($inv['total']" not in php
    body = php[php.index("'source'        => 'aade',") - 900:]
    assert "parseMoney((string)($inv['total'] ?? '0'))" in body[:900]


def test_amounts_written_with_the_old_bug_repair_themselves() -> None:
    """Το `notification_exists` προσπερνά ό,τι υπάρχει ήδη, οπότε χωρίς αυτό το
    λάθος νούμερο θα έμενε στην καμπάνα για πάντα."""
    db = LOCALDB.read_text(encoding="utf-8")
    assert "function notification_fix_amount(" in db
    body = db[db.index("function notification_fix_amount("):]
    body = body[:body.index("\n\nfunction ")]
    # ΜΟΝΟ όσες γεννήθηκαν από το scrape: μια ειδοποίηση έκδοσης κρατά το ποσό
    # που υπολόγισε η ίδια η εφαρμογή και δεν την ακουμπάμε.
    assert "source = 'aade'" in body
    # Και δεν ξαναγράφει όταν το ποσό είναι ήδη σωστό.
    assert "abs($stored - round($amount, 2)) < 0.005" in body

    php = ETIM_PHP.read_text(encoding="utf-8")
    assert "notification_fix_amount(COMPANY_VAT, $mk," in php


# --- Το ✕ ------------------------------------------------------------------
def test_every_notification_can_be_dismissed(page: str) -> None:
    assert 'class="nt-x"' in page
    assert "onclick=\"notifDelete(event," in page
    assert "function notifDelete(ev,id)" in page


def test_the_x_does_not_also_mark_it_read(page: str) -> None:
    """Η γραμμή έχει δικό της `onclick`: χωρίς stopPropagation θα έφευγαν δύο
    αιτήματα, και το δεύτερο θα ζητούσε ανάγνωση σε ό,τι μόλις σβήστηκε."""
    body = page[page.index("async function notifDelete(ev,id){"):]
    body = body[:body.index("\n}")]
    assert "ev.stopPropagation()" in body


def test_the_x_sits_top_right_and_never_covers_the_amount(page: str) -> None:
    """Ως `position:absolute` θα καθόταν πάνω στο ποσό, που είναι
    `margin-left:auto` στην ίδια γραμμή."""
    css = page[page.index(".notif-item .nt-x{"):]
    css = css[:css.index("}")]
    assert "position:absolute" not in css
    assert "flex:0 0 auto" in css
    # Και ζει ΜΕΣΑ στην πρώτη γραμμή, μετά το ποσό.
    markup = page[page.index('<span class="nt-amt">${amt}</span>'):]
    assert 'class="nt-x"' in markup[:260]


def test_the_endpoint_is_scoped() -> None:
    """Χωρίς scope, ένας λογιστής θα έσβηνε ειδοποίηση εταιρείας που δεν βλέπει,
    στέλνοντας ένα id στην τύχη."""
    php = ETIM_PHP.read_text(encoding="utf-8")
    body = php[php.index("if (!empty($_GET['notif_delete']"):]
    body = body[:body.index("\n}")]
    assert "$__acctScope" in body

    db = LOCALDB.read_text(encoding="utf-8")
    fn = db[db.index("function notification_delete("):]
    fn = fn[:fn.index("\n}")]
    assert "db_scope_clause($scope)" in fn
    assert "rowCount()" in fn, "να ξέρουμε αν όντως έσβησε κάτι"


def test_the_bell_follows_the_deletion(page: str) -> None:
    body = page[page.index("async function notifDelete(ev,id){"):]
    body = body[:body.index("\n}")]
    assert "setBell(d.unread||0)" in body
    # Άδειασε η λίστα ⇒ το μήνυμα «καμία ειδοποίηση», όχι κενό κουτί.
    assert "renderNotifications([])" in body
