"""Το dropdown που ήταν αόρατο, και η μνήμη που δεν κρύβει τις δικές μας αλλαγές.

**Η αιτία που δεν φαινόταν το dropdown ειδών ήταν CSS, όχι JavaScript.**
Η λίστα άνοιγε, γέμιζε σωστά, και κοβόταν ολόκληρη: το `.ac-panel` είναι
`position:absolute` στο `top:100%` — δηλαδή **έξω** από το κελί του — και ο
κανόνας `table td{overflow:hidden}` (που υπάρχει για το ellipsis) το έκοβε.
Γι' αυτό κάθε έλεγχος σε JavaScript έδειχνε «ανοιχτό με 13 επιλογές» ενώ στην
οθόνη δεν υπήρχε τίποτα, και γι' αυτό ίσχυε σε ΚΑΘΕ πίνακα: έκδοση, μαζική
έκδοση, δελτίο αποστολής, εισαγωγή πληρωμών.

Δεύτερο, ανεξάρτητο: σε στενό παράθυρο το `.panel table{overflow-x:auto}` κάνει
τον πίνακα δοχείο κύλισης, που κόβει το ίδιο πράγμα.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
ETIM_PHP = REPO / "etimologio.php"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# --- 1. Το κελί δεν κόβει πια τη λίστα του --------------------------------
def test_cells_that_host_a_dropdown_do_not_clip_it():
    src = _read(APP_PHP)
    assert "table td.ac-cell{overflow:visible}" in src
    # Και ΚΑΘΕ κελί που φιλοξενεί λίστα έχει την κλάση — αλλιώς η εξαίρεση
    # ισχύει για άλλα κελιά από αυτά που τη χρειάζονται.
    cells = re.findall(r"<td[^>]*>(?:(?!</td>).)*?ac-panel", src, re.S)
    assert cells, "δεν βρέθηκε κανένα κελί με ac-panel"
    without = [c[:80] for c in cells if "ac-cell" not in c.split(">")[0]]
    assert without == [], f"κελιά με λίστα χωρίς ac-cell: {without}"


def test_the_narrow_window_scroller_makes_the_same_exception():
    """Σε στενό παράθυρο ο πίνακας γίνεται δοχείο κύλισης και κόβει το ίδιο."""
    src = _read(APP_PHP)
    assert ".panel table:has(td.ac-cell){display:table;overflow-x:visible" in src


def test_the_clipping_rule_itself_is_still_there():
    """Δεν καταργήθηκε — τα υπόλοιπα κελιά εξακολουθούν να κόβουν με «…»."""
    assert "table td{overflow:hidden;text-overflow:ellipsis}" in _read(APP_PHP)


# --- 2. Η φρεσκάδα δεν κρύβει δική μας εγγραφή ----------------------------
def test_our_own_writes_always_beat_the_freshness_check():
    src = _read(APP_PHP)
    assert "const CACHE_DIRTY=new Set();" in src
    fn = src[src.index("function cacheIsFresh("):]
    fn = fn[: fn.index("\n}")]
    # Πρώτα το σημάδι, μετά η ηλικία — και το σημάδι καταναλώνεται.
    assert "if(CACHE_DIRTY.has(kind)){CACHE_DIRTY.delete(kind);return false;}" in fn
    assert fn.index("CACHE_DIRTY") < fn.index("age_seconds")


@pytest.mark.parametrize("marker", [
    "seriesModal.close();toast(`Η σειρά «${code}» δημιουργήθηκε`,'ok');cacheTouch('series');",
    "toast('Η σειρά διαγράφηκε','ok');cacheTouch('series');",
    "cacheTouch('products');\n    await loadProductList();loadProducts();",
    "toast('Διαγράφηκε','ok');cacheTouch('products');",
    "toast('Αποθηκεύτηκε','ok');cacheTouch('customers');",
    "toast('Ο πελάτης ενημερώθηκε','ok');cacheTouch('customers');",
])
def test_every_write_marks_its_kind(marker: str):
    assert marker in _read(APP_PHP)


def test_both_loaders_go_through_the_single_freshness_check():
    """Δύο αντίγραφα του κανόνα σημαίνει ότι το ένα θα ξεχαστεί."""
    src = _read(APP_PHP)
    for fname, end in (("async function loadProductList()", "let PROD_EDIT"),
                       ("async function loadIssueTypes()", "function issueTypeChange()")):
        fn = src[src.index(fname): src.index(end)]
        assert "cacheIsFresh(" in fn, fname
        # Καμία χειροκίνητη σύγκριση ηλικίας παρακάμπτοντας τον έλεγχο.
        assert "age_seconds<CACHE_FRESH_MIN" not in fn, fname


def test_the_server_reports_the_age_so_the_browser_need_not_guess():
    src = _read(ETIM_PHP)
    assert "'age_seconds' => $age," in src
    # UTC ρητά: το `synced_at` γράφεται UTC και στις δύο διαλέκτους.
    assert "strtotime((string)$c['synced_at'] . ' UTC')" in src


# --- 3. Ο έλεγχος ΑΑΔΕ κάθε πέντε λεπτά -----------------------------------
def test_the_aade_check_runs_every_five_minutes():
    src = _read(APP_PHP)
    assert "const AADE_CHECK_MIN=5;" in src
    assert "setInterval(()=>checkAadeNewDocs(),AADE_CHECK_MIN*60000);" in src
    assert "1800000" not in src, "το παλιό μισάωρο δεν πρέπει να έχει μείνει πουθενά"


# --- 4. Μικρά, αλλά ορατά --------------------------------------------------
def test_the_credential_test_stops_reporting_the_month():
    """Το πλήθος εγγραφών δεν είναι αποτέλεσμα της δοκιμής των κλειδιών."""
    src = _read(ETIM_PHP)
    assert "'msg' => 'Έγκυρα — η ΑΑΔΕ δέχτηκε τα διαπιστευτήρια.'" in src
    # Μόνο σε κώδικα, όχι σε σχόλιο: το σχόλιο εξηγεί γιατί έφυγε.
    body = src[: src.index("// --- 2. e-timologio")]
    code = [ln for ln in body.splitlines() if not ln.strip().startswith("//")]
    assert not [ln for ln in code if "είναι χωρίς έξοδα" in ln]


def test_the_products_box_says_search_not_filter():
    src = _read(APP_PHP)
    assert 'id="prodFilter" placeholder="Αναζήτηση κωδικού ή περιγραφής…"' in src
    assert 'placeholder="Φίλτρο…"' not in src


def test_an_unknown_view_name_does_not_throw():
    """Ο βοηθός βγάζει ονόματα οθονών από κείμενο· ένα λάθος όνομα έσκαγε."""
    fn = _read(APP_PHP)
    fn = fn[fn.index("function showView(v){"):]
    fn = fn[: fn.index("\n}")]
    assert "if(!target){console.warn" in fn
    assert "$('#view-'+v).classList.add('active')" not in fn


# --- 5. Τα περιγράμματα ξεχωρίζουν ----------------------------------------
def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        h = h.lstrip("#")
        parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        parts = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    l1, l2 = lum(a), lum(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


@pytest.mark.parametrize(("theme", "line", "grounds"), [
    ("σκοτεινό", "#4d6894", ("#131f33", "#18263d", "#0b1220")),
    ("φωτεινό", "#8aa2bd", ("#ffffff", "#eef3fa", "#f1f5fb")),
])
def test_box_borders_are_actually_visible(theme, line, grounds):
    """Ήταν 1,3:1 — τα κουτιά δεν είχαν ορατό όριο, «έλιωναν» μεταξύ τους."""
    src = _read(APP_PHP)
    assert line in src, f"το {theme} θέμα δεν χρησιμοποιεί {line}"
    for bg in grounds:
        assert _contrast(line, bg) >= 2.3, f"{theme}: {line} πάνω σε {bg}"
