"""Ο οδηγός έκδοσης, και το dropdown ειδών που «δεν λειτουργούσε καθόλου».

Τρεις χωριστές αιτίες, όλες επαληθευμένες ζωντανά στον browser:

1. **Ο οδηγός ρωτούσε δύο φορές.** Διάλεγες «Ιδιώτης» και το «+ Νέος πελάτης»
   άνοιγε στην καρτέλα «Με ΑΦΜ (Taxisnet)» — η εφαρμογή ήξερε ήδη την απάντηση.
2. **Μια αποτυχημένη ανανέωση ΕΣΒΗΝΕ τη λίστα ειδών.** Το `buildProdMap(d.products||[])`
   έγραφε άδειο πίνακα πάνω σε 12 είδη που μόλις είχαν φορτώσει από την κρυφή
   μνήμη, κάθε φορά που ο server απαντούσε `success:false` (π.χ. 409 «διάλεξε
   πρώτα εταιρεία»). Το dropdown έμενε με μόνο το «➕ Νέο είδος…».
3. **Η αναζήτηση ειδών δεν άντεχε τόνο.** «Χρωματισμών» → 0 αποτελέσματα·
   «χρωματισμων» → 6. Τα δεδομένα της ΑΑΔΕ είναι ΚΕΦΑΛΑΙΑ ΚΑΙ ΑΤΟΝΑ.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_PHP = REPO / "app.php"
NODE = shutil.which("node")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# --- 1. Ο οδηγός δεν ξαναρωτά ---------------------------------------------
def test_the_wizard_opens_the_tab_it_already_knows():
    src = _read(APP_PHP)
    assert "function openCustomerModal(onSaved,prefillAfm,tab){" in src
    assert "custTab(tab==='personal'?'personal':'afm')" in src

    fn = src[src.index("function newCustFromIssue()"):]
    fn = fn[: fn.index("document.addEventListener")]
    assert "ISSUE_WHO==='idiot'?'personal':'afm'" in fn
    # Ο ιδιώτης δεν παίρνει προσυμπληρωμένο ΑΦΜ — δεν έχει.
    assert "ISSUE_WHO==='idiot'?'':(/^\\d{9}$/.test(typed)?typed:'')" in fn


def test_a_private_customer_clears_the_vat_field():
    """Κρατώντας ό,τι είχε πληκτρολογηθεί, η απόδειξη έβγαινε σε άλλον."""
    src = _read(APP_PHP)
    fn = src[src.index("function newCustFromIssue()"):]
    fn = fn[: fn.index("document.addEventListener")]
    assert "$('#iAfm').value=c.vat||'';" in fn
    assert "$('#iAfm').value=c.vat||$('#iAfm').value" not in fn


# --- 2. Τίποτα δεν σβήνεται από αποτυχημένη ανανέωση -----------------------
def test_a_failed_refresh_never_empties_a_list():
    src = _read(APP_PHP)
    assert "function freshRows(d,key){" in src
    guard = src[src.index("function freshRows(d,key){"):]
    guard = guard[: guard.index("\n}")]
    # Αποτυχία → `null` → ο καλών δεν πειράζει τίποτα.
    assert "if(!d||d.success===false)return null;" in guard

    # Και οι τέσσερις θέσεις που έγραφαν τυφλά.
    assert "buildProdMap(d.products||[])" not in src
    assert "SERIES=d.rows||[]" not in src
    assert "SERIES=d.series||[];}catch(e){}}" not in src
    for call in ("const rows=freshRows(d,'rows');", "const rows=freshRows(d,'series');"):
        assert call in src, call


def test_an_empty_but_successful_answer_is_believed():
    """«Δεν έχεις είδη» είναι αληθινή πληροφορία και πρέπει να εφαρμόζεται.

    Ο φύλακας είναι μόνο η αποτυχία — αλλιώς η λίστα δεν καθαρίζει ποτέ.
    """
    src = _read(APP_PHP)
    fn = src[src.index("async function loadProductList()"):]
    fn = fn[: fn.index("let PROD_EDIT")]
    assert "if(rows)buildProdMap(rows);" in fn
    assert "rows.length||" not in fn


def test_the_item_list_now_refreshes_through_the_cache():
    """Πριν, η κρυφή μνήμη ειδών γέμιζε μόνο αν άνοιγες την οθόνη «Είδη»."""
    src = _read(APP_PHP)
    fn = src[src.index("async function loadProductList()"):]
    fn = fn[: fn.index("let PROD_EDIT")]
    assert "api({cached:'products'})" in fn
    assert "api({sync:'products'})" in fn, "το sync γράφει ΚΑΙ την κρυφή μνήμη"
    assert "list_products:1" not in fn


# --- 3. Κάθε επιλογέας ψάχνει χωρίς τόνους ---------------------------------
def test_no_picker_is_left_matching_raw_lowercase():
    src = _read(APP_PHP)
    assert "toLowerCase().includes(term)" not in src, (
        "κάθε επιλογέας πρέπει να περνά από grFold — αλλιώς ο τόνος που γράφει "
        "ο χρήστης δεν συναντά ποτέ τα άτονα δεδομένα της ΑΑΔΕ"
    )


@pytest.mark.parametrize("picker", [
    "prodAc", "custAc", "blkCustAc", "blkProdAc", "dnCustAc", "dnProdAc", "cxAc",
])
def test_every_picker_folds_its_term(picker: str):
    src = _read(APP_PHP)
    head = src[src.index("function " + picker + "("):]
    head = head[: head.index("\n", head.index("{"))]
    assert "grFold(" in head, picker


# --- 4. Ο ίδιος ο κώδικας, σε λειτουργία ----------------------------------
PRODUCTS = [
    {"product_code": "1", "description": "ΕΡΓΑΣΙΕΣ ΧΡΩΜΑΤΙΣΜΩΝ ΒΑΣΗ ΣΥΜΦΩΝΗΤΙΚΟΥ", "vat": "1"},
    {"product_code": "3", "description": "ΕΠΙΣΚΕΥΕΣ", "vat": "1"},
    {"product_code": "4", "description": "ΕΡΓΑΣΙΕΣ ΧΡΩΜΑΤΙΣΜΩΝ", "vat": "1"},
]

_WANTED = ("grFold", "vatPct", "freshRows")


def _extract(src: str, name: str) -> str:
    i = src.index("function " + name + "(")
    depth, started = 0, False
    in_str = None
    in_re = in_line = in_blk = False
    j = i
    while j < len(src):
        c, n = src[j], src[j + 1 : j + 2]
        prev = src[j - 1] if j else "\n"
        if in_line:
            if c == "\n":
                in_line = False
        elif in_blk:
            if c == "*" and n == "/":
                in_blk = False
                j += 1
        elif in_str:
            if c == "\\":
                j += 1
            elif c == in_str:
                in_str = None
        elif in_re:
            if c == "\\":
                j += 1
            elif c == "[":
                while src[j] != "]":
                    j += 1
                    if src[j] == "\\":
                        j += 1
            elif c == "/":
                in_re = False
        elif c == "/" and n == "/":
            in_line = True
            j += 1
        elif c == "/" and n == "*":
            in_blk = True
            j += 1
        elif c in "\"'`":
            in_str = c
        elif c == "/" and prev in "=(,:[!&|?{};+-*%\n ":
            in_re = True
        elif c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return src[i : j + 1]
        j += 1
    raise AssertionError(name)


@pytest.mark.skipif(NODE is None, reason="δεν υπάρχει node")
def test_the_item_picker_and_the_guard_behave(tmp_path: Path):
    src = _read(APP_PHP)
    funcs = "\n".join(_extract(src, n) for n in _WANTED)

    driver = tmp_path / "run.js"
    driver.write_text(
        funcs
        + "\nlet PRODMAP={};"
        + "\nfunction buildProdMap(products){PRODMAP={};(products||[]).forEach(p=>{"
          "const code=p.product_code||p.code;if(!code)return;"
          "PRODMAP[code]={desc:p.description||'',vat:p.vat||''};});}"
        + "\nconst ROWS=" + json.dumps(PRODUCTS, ensure_ascii=False) + ";"
        + "\nconst hits=t=>{const term=grFold(t).trim();"
          "return Object.keys(PRODMAP).filter(c=>!term||"
          "grFold(c+' '+PRODMAP[c].desc).includes(term)).length;};"
        + "\nconst out={};"
        + "\nbuildProdMap(ROWS); out.φορτωμένα=Object.keys(PRODMAP).length;"
        # Μια αποτυχημένη ανανέωση δεν αγγίζει τίποτα.
        + "\nlet r=freshRows({success:false,error:'409'},'rows');"
          "if(r)buildProdMap(r); out.μετά_από_αποτυχία=Object.keys(PRODMAP).length;"
        + "\nr=freshRows({success:true},'rows');"
          "if(r)buildProdMap(r); out.χωρίς_rows=Object.keys(PRODMAP).length;"
        # Επιτυχής άδεια απάντηση καθαρίζει.
        + "\nr=freshRows({success:true,rows:[]},'rows');"
          "if(r)buildProdMap(r); out.επιτυχές_άδειο=Object.keys(PRODMAP).length;"
        + "\nbuildProdMap(ROWS);"
        + "\n['ΧΡΩΜΑΤΙΣΜΩΝ','χρωματισμων','Χρωματισμών','Επισκευές','επισκευεσ','ζζζ','']"
          ".forEach(t=>out['q:'+t]=hits(t));"
        + "\nconsole.log(JSON.stringify(out));\n",
        encoding="utf-8",
    )
    chk = subprocess.run([NODE, "--check", str(driver)], capture_output=True, text=True)
    assert chk.returncode == 0, chk.stderr
    run = subprocess.run([NODE, str(driver)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert run.returncode == 0, run.stderr
    got = json.loads(run.stdout)

    assert got["φορτωμένα"] == 3
    assert got["μετά_από_αποτυχία"] == 3, "409 δεν σβήνει τα είδη"
    assert got["χωρίς_rows"] == 3, "απάντηση χωρίς πεδίο rows δεν σβήνει τίποτα"
    assert got["επιτυχές_άδειο"] == 0, "«δεν έχεις είδη» πρέπει να εφαρμόζεται"

    # Ο τόνος που γράφει ο άνθρωπος βρίσκει τα άτονα δεδομένα της ΑΑΔΕ.
    assert got["q:ΧΡΩΜΑΤΙΣΜΩΝ"] == 2
    assert got["q:χρωματισμων"] == 2
    assert got["q:Χρωματισμών"] == 2, "ήταν 0 — αυτό ήταν το «δεν λειτουργεί καθόλου»"
    assert got["q:Επισκευές"] == 1
    assert got["q:επισκευεσ"] == 1, "και το τελικό «ς»"
    assert got["q:ζζζ"] == 0
    assert got["q:"] == 3, "χωρίς όρο, όλα"
