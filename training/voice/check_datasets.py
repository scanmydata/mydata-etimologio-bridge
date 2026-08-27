# -*- coding: utf-8 -*-
"""Ελέγχει τα σύνολα εκπαίδευσης ΠΡΙΝ φάνε ώρα GPU.

Δύο κατηγορίες λάθους έχουν ήδη συμβεί σε αυτό το έργο και δεν φαίνονται με το
μάτι σε 2.500 γραμμές JSON:

* **Εκφώνηση με ψηφία ή κεφαλαία στην έξοδο.** Ό,τι μείνει αμετάφραστο το
  διαβάζει ο Piper όπως-όπως: το «12.100» ως «δώδεκα κόμμα εκατό», τα ελληνικά
  κεφαλαία χωρίς τόνο.
* **Ενέργεια εκτός συμβολαίου.** Επτά γραμμές έβγαζαν κάποτε
  `{"command":"cancel"}`, που δεν υπάρχει στο `assistant.COMMANDS` — ο
  επικυρωτής της εφαρμογής θα τις πετούσε και ο βοηθός θα απαντούσε «δεν
  κατάλαβα» σε ένα σκέτο «άκυρο».

    python training/voice/check_datasets.py

Επιστρέφει κωδικό 1 αν βρει οτιδήποτε — κάνει για CI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "desktop" / "src"))

# --- Το συμβόλαιο, διαβασμένο από τον ΚΩΔΙΚΑ, όχι αντιγραμμένο ----------------
# Αν αύριο προστεθεί ενότητα στον βοηθό, ο έλεγχος τη μαθαίνει μόνος του.
from timologio.etimologio.assistant import COMMANDS, NAV  # noqa: E402

VIEWS = {view for view, _ in NAV} | {"card"}
COMMAND_NAMES = {name for name, _, _ in COMMANDS}
#: Παραμετρικές εντολές: το «card:802576637» είναι έγκυρο, το «card» σκέτο όχι.
PARAMETRIC = ("card:", "company:")
FETCHES = {"stats:year", "stats:month", "notifications",
           "customers_count", "products_count"}
DIALOGS = {"customer", "product"}
KEYS = {"say", "navigate", "command", "dialog", "prefill", "fetch", "draft"}
DRAFT_KEYS = {"vat", "name", "item", "price", "qty", "withholding_pct"}

problems: list[str] = []


def fail(dataset: str, row: int, text: str) -> None:
    problems.append("{}[{}] {}".format(dataset, row, text))


def check_common(name: str, rows: list[dict]) -> None:
    for i, row in enumerate(rows):
        for key in ("instruction", "input", "output"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                fail(name, i, "λείπει ή είναι κενό το «{}»".format(key))


def check_tts(name: str, rows: list[dict]) -> None:
    """Η έξοδος πρέπει να είναι **μόνο** εκφωνήσιμα ελληνικά."""
    for i, row in enumerate(rows):
        out = row["output"]
        if re.search(r"[0-9]", out):
            fail(name, i, "έμεινε ψηφίο στην έξοδο: {!r}".format(out[:70]))
        if re.search(r"[Α-ΩΪΫ]{2,}", out):
            fail(name, i, "κεφαλαία (άτονα για τον Piper): {!r}".format(out[:70]))
        if re.search(r"[A-Za-z]{2,}", out):
            fail(name, i, "λατινικά στην έξοδο: {!r}".format(out[:70]))


def check_actions(name: str, rows: list[dict]) -> None:
    """Η έξοδος πρέπει να είναι JSON που η εφαρμογή δέχεται όντως."""
    for i, row in enumerate(rows):
        try:
            action = json.loads(row["output"])
        except json.JSONDecodeError as exc:
            fail(name, i, "άκυρο JSON: {}".format(exc))
            continue
        if not isinstance(action, dict) or not action:
            fail(name, i, "η ενέργεια δεν είναι μη-κενό αντικείμενο")
            continue
        unknown = set(action) - KEYS
        if unknown:
            fail(name, i, "άγνωστα κλειδιά: {}".format(sorted(unknown)))
        view = action.get("navigate")
        if view and view not in VIEWS:
            fail(name, i, "άγνωστη ενότητα: {!r}".format(view))
        command = action.get("command")
        if command and command not in COMMAND_NAMES \
                and not command.startswith(PARAMETRIC):
            fail(name, i, "εντολή εκτός συμβολαίου: {!r}".format(command))
        fetch = action.get("fetch")
        if fetch and fetch not in FETCHES:
            fail(name, i, "άγνωστο fetch: {!r}".format(fetch))
        dialog = action.get("dialog")
        if dialog and dialog not in DIALOGS:
            fail(name, i, "άγνωστος διάλογος: {!r}".format(dialog))
        draft = action.get("draft")
        if draft is not None:
            if not isinstance(draft, dict):
                fail(name, i, "το draft δεν είναι αντικείμενο")
            else:
                extra = set(draft) - DRAFT_KEYS
                if extra:
                    fail(name, i, "άγνωστα πεδία draft: {}".format(sorted(extra)))
                if not draft.get("vat") and not draft.get("name"):
                    fail(name, i, "draft χωρίς vat ούτε name")


def duplicates(name: str, rows: list[dict]) -> None:
    """Ίδια είσοδος με ΔΙΑΦΟΡΕΤΙΚΗ έξοδο διδάσκει το μοντέλο να μαντεύει."""
    seen: dict[str, str] = {}
    for i, row in enumerate(rows):
        key = row["input"].strip().lower()
        if key in seen and seen[key] != row["output"]:
            fail(name, i, "αντιφατική ετικέτα για {!r}".format(row["input"][:50]))
        seen[key] = row["output"]


def main() -> int:
    export = "--export" in sys.argv
    files = {
        "tts_normalizer_el.json": check_tts,
        "intents_el.json": check_actions,
        "faq_el.json": check_actions,
    }
    total = 0
    merged: list[dict] = []
    for filename, checker in files.items():
        path = HERE / filename
        if not path.exists():
            print("— {} λείπει (τρέξε το αντίστοιχο build_*.py)".format(filename))
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        total += len(rows)
        merged += rows
        before = len(problems)
        check_common(filename, rows)
        checker(filename, rows)
        duplicates(filename, rows)
        found = len(problems) - before
        print("{:<26} {:>5} γραμμές   {}".format(
            filename, len(rows), "καθαρό" if not found else
            "{} προβλήματα".format(found)))

    print("\nσύνολο: {} παραδείγματα".format(total))
    if problems:
        print("\nΠροβλήματα:")
        for line in problems[:40]:
            print("  -", line)
        if len(problems) > 40:
            print("  … και άλλα {}".format(len(problems) - 40))
        return 1
    print("Όλα τα σύνολα περνούν το συμβόλαιο.")

    if export:
        # Ένα αρχείο για ανέβασμα σε Colab, αντί για τρία. JSONL γιατί το
        # `datasets.load_dataset("json", ...)` το διαβάζει κατευθείαν και δεν
        # κρατά ολόκληρο τον πίνακα στη μνήμη.
        out = HERE / "etimologio_sft.jsonl"
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            for row in merged:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("εξαγωγή: {} γραμμές -> {}".format(len(merged), out.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
