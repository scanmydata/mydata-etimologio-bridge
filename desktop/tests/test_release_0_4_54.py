"""0.4.54 — ο Τίτλος Κτήσης (3.1/3.2) είναι έξοδο του εκδότη, και η εφαρμογή
υπολογιστή δεν χάνει τη σύνδεση του e-Τιμολόγιο Pro όταν χαθεί η συνεδρία
του server.

Τίτλος Κτήσης: τον εκδίδει ο ΑΓΟΡΑΣΤΗΣ, όταν ο πωλητής δεν είναι υπόχρεος
(αγρότης, ιδιώτης) ή αρνείται να εκδώσει. Εκδότης = λήπτης των αγαθών,
αντισυμβαλλόμενος = πωλητής. Μετρημένο: 36 τίτλοι κτήσης αγοράς αγροτικών
προϊόντων μετρούσαν στα έσοδα του αγοραστή.

Σύνδεση: η συνεδρία PHP ζει σε αρχείο του server. Όταν χανόταν (deploy,
καθαρισμός), η εφαρμογή έδειχνε τη φόρμα σύνδεσης παρότι το cookie ήταν
έγκυρο. Τώρα ένα διακριτικό «να με θυμάσαι» (hash στη βάση, cookie HttpOnly)
την ξαναστήνει σιωπηλά — μόνο για την εφαρμογή υπολογιστή.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from timologio.doctypes import BUYER_ISSUED_TYPES, doc_kind, expense_sql, income_sql

REPO = Path(__file__).resolve().parents[2]
CLIENT = "803170280"
FARMER = "031234476"


@pytest.mark.parametrize("code", ["3.1", "3.2"])
def test_acquisition_title_is_an_expense_of_the_buyer_who_issues_it(code):
    assert doc_kind(CLIENT, CLIENT, code) == "expense"
    # Ο πελάτης ως πωλητής (αντισυμβαλλόμενος): έσοδο.
    assert doc_kind(FARMER, CLIENT, code) == "income"


def test_other_types_unchanged():
    assert doc_kind(CLIENT, CLIENT, "1.1") == "income"
    assert doc_kind(FARMER, CLIENT, "1.1") == "expense"
    assert doc_kind(FARMER, CLIENT, "2.1", True) == "income"      # αυτοτιμολόγηση
    assert doc_kind(CLIENT, CLIENT, "17.1") == "expense"
    assert BUYER_ISSUED_TYPES == {"3.1", "3.2"}


def test_sql_agrees_with_doc_kind():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE d (issuer_vat TEXT, invoice_type TEXT, self_pricing INTEGER)")
    rows = [(CLIENT, "3.1", 0), (FARMER, "3.1", 0), (CLIENT, " 3.2", 0), (CLIENT, "1.1", 0),
            (FARMER, "1.1", 0), (FARMER, "2.1", 1), (CLIENT, "16.1", 0)]
    conn.executemany("INSERT INTO d VALUES (?,?,?)", rows)
    inc = income_sql("issuer_vat", "?", "invoice_type", "self_pricing")
    exp = expense_sql("issuer_vat", "?", "invoice_type", "self_pricing")
    for issuer, code, sp in rows:
        want = doc_kind(issuer, CLIENT, code, sp)
        where = "issuer_vat=? AND invoice_type=? AND self_pricing=?"
        got_inc = conn.execute(f"SELECT COUNT(*) FROM d WHERE {where} AND {inc}",
                               (issuer, code, sp, *[CLIENT] * inc.count("?"))).fetchone()[0]
        got_exp = conn.execute(f"SELECT COUNT(*) FROM d WHERE {where} AND {exp}",
                               (issuer, code, sp, *[CLIENT] * exp.count("?"))).fetchone()[0]
        assert (got_inc, got_exp) == ((1, 0) if want == "income" else (0, 1)), (issuer, code)


# ---------------------------------------------------------------------------
# e-Τιμολόγιο Pro: «να με θυμάσαι» της εφαρμογής υπολογιστή
# ---------------------------------------------------------------------------
def _auth() -> str:
    return (REPO / "auth.php").read_text(encoding="utf-8")


def test_the_desktop_copies_are_identical():
    for name in ("auth.php", "etimologio.php"):
        assert (REPO / name).read_bytes() == (REPO / "desktop/backend/etimologio" / name).read_bytes()


def test_remember_token_restores_a_lost_session_only_for_the_desktop_app():
    src = _auth()
    block = src[src.index("if (session_status() === PHP_SESSION_NONE)"):src.index("// --- Master bootstrap")]
    # Οι σταθερές δεν «ανεβαίνουν» όπως οι συναρτήσεις: πριν από το session block.
    assert src.index("const AUTH_REMEMBER_COOKIE") < src.index("if (session_status() === PHP_SESSION_NONE)")
    assert block.index("session_start();") < block.index("if ($__shellClient) auth_remember_touch();")
    touch = src[src.index("function auth_remember_touch"):src.index("// --- Master bootstrap")]
    assert "$_SESSION['uid'] = (int)$u['id'];" in touch
    assert "hash_equals((string)($d['pw'] ?? ''), auth_password_tag($u))" in touch   # αλλαγή κωδικού = άκυρο
    assert "$u['status'] === 'active'" in touch
    issue = src[src.index("function auth_remember_issue"):src.index("function auth_remember_forget")]
    assert "if (!auth_is_shell_client()) return;" in issue
    assert "random_bytes(32)" in issue
    assert "'httponly' => true" in src[src.index("function auth_remember_cookie"):]


def test_only_the_hash_is_stored_and_logout_forgets_it():
    src = _auth()
    assert "'remember.' . hash('sha256', $token)" in src
    logout = src[src.index("function auth_logout"):]
    logout = logout[:logout.index("\n}\n")]
    assert "auth_remember_forget();" in logout
    for fn in ("function auth_login(", "function auth_login_totp("):
        body = src[src.index(fn):]
        body = body[:body.index("\n}\n")]
        assert "auth_remember_issue($u);" in body, fn


def test_own_password_change_keeps_this_device_signed_in():
    api = (REPO / "etimologio.php").read_text(encoding="utf-8")
    case = api[api.index("case 'change_password':"):]
    case = case[:case.index("jsonResponse(['success' => true]);")]
    assert "auth_remember_issue(user_by_id((int)$u['id']))" in case
