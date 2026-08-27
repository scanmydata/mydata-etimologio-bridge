# -*- coding: utf-8 -*-
"""Το τίμιο νούμερο: φράσεις που **δεν** είναι στα δεδομένα εκπαίδευσης.

Το `eval_router.py` μετρά πάνω στο `intents_el.json` — το ίδιο σύνολο από το
οποίο γράφτηκαν τα μοτίβα. Ένα 100% εκεί σημαίνει «καλύπτει ό,τι σκεφτήκαμε»,
όχι «καταλαβαίνει ελληνικά». Είναι χρήσιμο ως δίχτυ παλινδρόμησης και
παραπλανητικό ως μέτρο ικανότητας.

Το `heldout_el.json` γράφτηκε **στο χέρι**, με διατυπώσεις που δεν υπάρχουν
πουθενά στα σύνολα: άλλα ρήματα, άλλη σειρά λέξεων, συνώνυμα, και ερωτήσεις που
ένας λογιστής θα έκανε αυθόρμητα.

    python training/voice/eval_heldout.py

Αυτό το ποσοστό είναι που δείχνει αν αξίζει το μοντέλο.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from eval_router import CUSTOMERS, PRODUCTS  # noqa: E402

from timologio.etimologio.assistant import Assistant  # noqa: E402

UNKNOWN = "δεν το καταλαβα"


def verdict(expect: str, reply) -> bool:
    """Ταιριάζει η απάντηση με το ζητούμενο; Χαλαρά, όπως και στο eval_router."""
    kind, _, want = expect.partition("=")
    said = reply.say.lower()
    if kind == "navigate":
        return reply.navigate == want
    if kind == "command":
        return reply.command == want
    if kind == "fetch":
        if want in ("customers_count", "products_count"):
            return any(ch.isdigit() for ch in reply.say)
        return reply.fetch == want
    if kind == "dialog":
        return reply.dialog == want
    if kind == "notifications-any":
        # Και το «άνοιξέ τες» και το «πόσες είναι» απαντούν στην ερώτηση.
        return reply.fetch == "notifications" or reply.navigate == "notifications"
    if kind == "draft":
        # Ίδιο κριτήριο με το `eval_router.matches`: ο βοηθός συχνά ζητά
        # επιβεβαίωση πριν φτιάξει το πρόχειρο, και αυτό ΕΙΝΑΙ σωστή απάντηση —
        # όχι αστοχία. Αλλιώς θα μετρούσαμε τη διατύπωση, όχι την κατανόηση.
        return reply.draft is not None or "ΠΡΟΧΕΙΡΟ" in reply.say
    if kind == "draft-or-issue":
        # Μισοακουσμένο όνομα: αρκεί να κατάλαβε ότι πρόκειται για έκδοση.
        return reply.draft is not None or reply.navigate == "issue" \
            or "ΠΡΟΧΕΙΡΟ" in reply.say or "πελάτη" in said
    if kind == "refusal":
        return "προχειρο" in said.replace("ό", "ο") or "οριστικη εκδοση" in \
            said.replace("ή", "η").replace("ι", "ι")
    if kind == "say":
        return bool(reply.say) and UNKNOWN not in said.replace("ά", "α")
    if kind == "unknown":
        # Το σωστό εδώ είναι να ΜΗΝ κάνει κάτι: ούτε πλοήγηση ούτε εντολή.
        return not (reply.navigate or reply.command or reply.fetch
                    or reply.dialog or reply.draft)
    raise ValueError(expect)


def main() -> int:
    rows = json.loads((Path(__file__).with_name("heldout_el.json")).read_text("utf-8"))
    greek = re.compile(r"[Ά-ώ]")
    ok = {"EL": 0, "EN": 0}
    total = {"EL": 0, "EN": 0}
    misses: list[tuple[str, str, str]] = []
    for row in rows:
        lang = "EL" if greek.search(row["input"]) else "EN"
        total[lang] += 1
        bot = Assistant(lambda: CUSTOMERS, lambda: PRODUCTS)
        reply = bot.handle(row["input"])
        if verdict(row["expect"], reply):
            ok[lang] += 1
        else:
            got = (reply.navigate or reply.command or reply.fetch or reply.dialog
                   or ("draft" if reply.draft else "") or reply.say[:40])
            misses.append((row["input"], row["expect"], got))

    print("Φράσεις ΕΚΤΟΣ δεδομένων εκπαίδευσης:\n")
    for lang in ("EL", "EN"):
        if total[lang]:
            print("  {}  {:>3}/{:<3} {:>5.1f}%".format(
                lang, ok[lang], total[lang], 100 * ok[lang] / total[lang]))
    hits, count = sum(ok.values()), sum(total.values())
    print("\n  ΣΥΝΟΛΟ {:>3}/{:<3} {:>5.1f}%".format(hits, count, 100 * hits / count))
    if misses:
        print("\nΤι δεν πιάνει (εδώ κερδίζει το μοντέλο):")
        for text, want, got in misses:
            print("  «{}»\n     ήθελα {} · πήρα {}".format(text, want, got))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
