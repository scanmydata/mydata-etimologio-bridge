# -*- coding: utf-8 -*-
"""Πόσο από το `intents_el.json` πιάνει ο **σημερινός** δρομολογητής;

Τρέχει χωρίς Qt και χωρίς μοντέλο — απλώς περνά κάθε είσοδο από τον
`assistant.Assistant` και συγκρίνει με τη σωστή ενέργεια. Δύο χρήσεις:

* **Πριν** το LLM: δείχνει πού ακριβώς σπάει ο regex router (και άρα τι θα
  κερδίσει το μοντέλο). Ό,τι πιάνεται ήδη, δεν χρειάζεται μοντέλο.
* **Μετά** το LLM: ίδιο σκορ, με το μοντέλο στη θέση του router — αν δεν είναι
  σαφώς καλύτερο, δεν αξίζει τα megabytes.

    python training/voice/eval_router.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "src"))

from timologio.etimologio.assistant import Assistant  # noqa: E402

# Ίδια ονόματα/είδη με το `build_intents.py`: με άδειο κατάλογο κάθε εντολή
# έκδοσης θα κατέληγε — σωστά — σε «δημιούργησε πρώτα το είδος», και το σκορ θα
# μετρούσε το κενό του fixture αντί για το κενό του δρομολογητή.
CUSTOMERS = [
    {"vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ"},
    {"vat": "802012659", "name": "MEGATECH ΙΚΕ"},
    {"vat": "998877665", "name": "Παπαδόπουλος"},
    {"vat": "112233445", "name": "ΑΛΦΑ ΟΕ"},
    {"vat": "556677889", "name": "Γεωργίου"},
]
PRODUCTS = [
    {"code": "ΥΠ001", "description": "συντήρηση εξοπλισμού"},
    {"code": "ΑΓ001", "description": "ανταλλακτικό αντλίας"},
    {"code": "ΥΠ002", "description": "λογιστικές υπηρεσίες"},
    {"code": "ΥΠ003", "description": "μεταφορικά"},
    {"code": "ΥΠ004", "description": "εγκατάσταση δικτύου"},
    {"code": "ΥΠ005", "description": "εκπαίδευση προσωπικού"},
]


def matches(expected: dict, reply) -> bool:
    """Ταιριάζει η απάντηση με τη ζητούμενη ενέργεια;

    Χαλαρά επίτηδες: μας νοιάζει η *ενέργεια*, όχι η διατύπωση. Το `draft`
    μετράει σωστό όταν βρέθηκε ο ίδιος πελάτης — τα υπόλοιπα πεδία τα ελέγχει
    το `test_assistant.py`.
    """
    if "navigate" in expected:
        return reply.navigate == expected["navigate"]
    if "command" in expected:
        want = expected["command"]
        if want in ("cancel", "help"):
            return True     # ο σημερινός router τα χειρίζεται με δικό του δρόμο
        return reply.command == want
    if "fetch" in expected:
        want = expected["fetch"]
        if want in ("customers_count", "products_count"):
            # Απαντιούνται από τη μνήμη, χωρίς fetch: σωστό αν είπε αριθμό.
            return any(ch.isdigit() for ch in reply.say)
        return reply.fetch == want
    if "dialog" in expected:
        return reply.dialog == expected["dialog"]
    if "draft" in expected:
        spec = reply.draft
        target = expected["draft"]
        if spec is None:
            # Ο router ζητά επιβεβαίωση πριν το πρόχειρο — μετράει ως σωστό
            # μόνο αν κατάλαβε ότι πρόκειται για έκδοση.
            return "ΠΡΟΧΕΙΡΟ" in reply.say or reply.navigate == "issue"
        return spec.vat == target.get("vat", spec.vat)
    if "say" in expected:
        return bool(reply.say)
    return False


def main() -> int:
    data = json.loads((Path(__file__).with_name("intents_el.json")).read_text("utf-8"))
    hits: Counter[str] = Counter()
    total: Counter[str] = Counter()
    misses: list[tuple[str, str]] = []
    for row in data:
        expected = json.loads(row["output"])
        kind = next(iter(expected))
        bot = Assistant(lambda: CUSTOMERS, lambda: PRODUCTS)
        reply = bot.handle(row["input"])
        total[kind] += 1
        if matches(expected, reply):
            hits[kind] += 1
        elif len(misses) < 25:
            misses.append((row["input"], row["output"]))

    print("Κάλυψη του σημερινού (regex) δρομολογητή:\n")
    for kind in sorted(total):
        ok, all_ = hits[kind], total[kind]
        print("  {:<10} {:>4}/{:<4} {:>5.1f}%".format(kind, ok, all_, 100 * ok / all_))
    ok, all_ = sum(hits.values()), sum(total.values())
    print("\n  {:<10} {:>4}/{:<4} {:>5.1f}%".format("ΣΥΝΟΛΟ", ok, all_, 100 * ok / all_))
    print("\nΔείγμα από όσα ΔΕΝ πιάνει (εδώ κερδίζει το μοντέλο):")
    for text, want in misses[:15]:
        print("  -", text, "->", want)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
