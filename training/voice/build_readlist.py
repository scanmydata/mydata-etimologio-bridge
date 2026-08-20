# -*- coding: utf-8 -*-
"""Οι προτάσεις που θα ηχογραφήσεις — για Piper (φωνή) και Whisper (ακοή).

Τα JSON σύνολα εκπαιδεύουν **κείμενο**. Το STT και το TTS θέλουν **ήχο**, και
ο ήχος δεν παράγεται συνθετικά: πρέπει να τον διαβάσεις. Αυτό το script φτιάχνει
τη λίστα ανάγνωσης από ό,τι λέει και ακούει πραγματικά η εφαρμογή, ώστε η
ηχογράφηση να καλύπτει το **δικό μας** λεξιλόγιο και όχι γενικές φράσεις.

    python training/voice/build_readlist.py

Παράγει στο `training/voice/readlist/`:

* `piper_el.csv`  — προτάσεις για κλωνοποίηση ελληνικής φωνής (μορφή Piper)
* `piper_en.csv`  — το ίδιο για αγγλική φωνή
* `whisper_el.txt` — εντολές που πρέπει να αναγνωρίζονται σωστά
* `whisper_en.txt`
* `README.txt`    — πώς ηχογραφείς και τι μορφή θέλει το καθένα

Δες [MODELS.md](MODELS.md) για το ποια μοντέλα και γιατί.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "readlist"

GREEK = re.compile(r"[Ά-ώ]")

#: Πόσο μεγάλη πρέπει να είναι μια πρόταση για να αξίζει ηχογράφηση. Οι πολύ
#: κοντές («αρχική») δεν διδάσκουν προσωδία· οι πολύ μεγάλες κουράζουν και
#: βγαίνουν με λάθη.
MIN_CHARS, MAX_CHARS = 12, 140


def load(name: str) -> list[dict]:
    return json.loads((HERE / name).read_text("utf-8"))


def dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = re.sub(r"\s+", " ", line.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(re.sub(r"\s+", " ", line.strip()))
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)

    intents = load("intents_el.json")
    tts = load("tts_normalizer_el.json")

    # --- Piper: ό,τι ΛΕΕΙ ο βοηθός ------------------------------------------
    # Η φωνή πρέπει να μάθει τα δικά μας ποσά, ΑΦΜ και όρους, γι' αυτό η βάση
    # είναι οι κανονικοποιημένες εκφωνήσεις: εκεί ζουν τα «οκτακόσια δεκαπέντε
    # ευρώ και πενήντα λεπτά» που δεν υπάρχουν σε κανένα γενικό σύνολο.
    spoken = [r["output"] for r in tts]
    # Και οι απαντήσεις του ίδιου του δρομολογητή, όπως τις ακούει ο χρήστης.
    for row in intents:
        action = json.loads(row["output"])
        if isinstance(action.get("say"), str):
            spoken.append(action["say"])

    piper_el = [t for t in dedupe(spoken) if GREEK.search(t) and MIN_CHARS <= len(t) <= MAX_CHARS]

    # Για τα αγγλικά δεν υπάρχει αντίστοιχο σύνολο· δίνουμε έναν πυρήνα με τους
    # ίδιους αριθμούς και όρους, ώστε η αγγλική φωνή να μη λέει τα ποσά λάθος.
    piper_en = [
        "Your invoice has been saved as a draft.",
        "The document number is four hundred billion, fourteen million.",
        "Total amount: eight hundred and fifteen euro and fifty cents.",
        "The customer has an outstanding balance of one thousand two hundred euro.",
        "I only prepare drafts. You press the red button to issue.",
        "The tax office is not responding right now.",
        "There is no internet connection on this computer.",
        "I found three customers matching that name.",
        "Value added tax, twenty four percent.",
        "Withholding tax, twenty percent, on services.",
        "Series alpha, number one hundred and seven.",
        "Issued on the third of February, two thousand twenty six.",
        "The ledger has been sent to the customer by email.",
        "Backup finished. Ninety four megabytes were uploaded.",
        "Opening the customer card now.",
    ]

    # --- Whisper: ό,τι ΑΚΟΥΕΙ ο βοηθός --------------------------------------
    heard = [r["input"] for r in intents]
    whisper_el = [t for t in dedupe(heard) if GREEK.search(t)]
    whisper_en = [t for t in dedupe(heard) if not GREEK.search(t)]

    def write_csv(name: str, lines: list[str], prefix: str) -> None:
        # Μορφή Piper/LJSpeech: «αρχείο|κείμενο», διαχωριστικό «|».
        body = "\n".join(
            "{}_{:04d}.wav|{}".format(prefix, i + 1, text) for i, text in enumerate(lines)
        )
        (OUT / name).write_text(body + "\n", encoding="utf-8")
        print("{:>16}  {} προτάσεις".format(name, len(lines)))

    def write_txt(name: str, lines: list[str]) -> None:
        (OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("{:>16}  {} εντολές".format(name, len(lines)))

    write_csv("piper_el.csv", piper_el, "el")
    write_csv("piper_en.csv", piper_en, "en")
    write_txt("whisper_el.txt", whisper_el)
    write_txt("whisper_en.txt", whisper_en)

    (OUT / "README.txt").write_text(README, encoding="utf-8")
    print("\nΟδηγίες ηχογράφησης: {}".format(OUT / "README.txt"))
    return 0


README = """ΗΧΟΓΡΑΦΗΣΗ ΓΙΑ ΤΑ ΤΟΠΙΚΑ ΜΟΝΤΕΛΑ
==================================

Δύο διαφορετικές δουλειές. Μην τις μπερδέψεις.


1. ΦΩΝΗ (Piper) — piper_el.csv / piper_en.csv
---------------------------------------------
Διαβάζεις ΕΣΥ τις προτάσεις. Το αποτέλεσμα είναι η φωνή που θα μιλά η εφαρμογή.

  * WAV 22050 Hz, mono, 16-bit.
  * Ένα αρχείο ανά πρόταση, με το όνομα που γράφει η πρώτη στήλη.
  * Ίδιο μικρόφωνο, ίδιο δωμάτιο, ίδια απόσταση, ΟΛΕΣ τις φορές.
  * Χωρίς ηχώ, χωρίς κλιματιστικό, χωρίς μουσική. Η καθαρότητα μετράει
    περισσότερο από την ποσότητα: 30 καθαρά λεπτά νικούν 2 βρόμικες ώρες.
  * Διάβασε ΦΥΣΙΚΑ, όπως θα το έλεγες σε πελάτη. Αν το διαβάσεις σαν ρομπότ,
    ρομπότ θα ακούγεται και το μοντέλο.
  * Κόψε τη σιωπή στην αρχή και στο τέλος κάθε αρχείου.

Στόχος: 30–60 λεπτά ήχου ανά γλώσσα. Μετά:

    python -m piper.train fit --data.csv_path piper_el.csv ... \\
        --ckpt_path el_GR-joy-medium.ckpt

Λεπτομέρειες στο MODELS.md §2.


2. ΑΚΟΗ (Whisper) — whisper_el.txt / whisper_en.txt
---------------------------------------------------
Εδώ ΔΕΝ χρειάζεται να διαβάσεις τα πάντα. Αυτές είναι οι εντολές που πρέπει να
αναγνωρίζονται σωστά· χρησιμεύουν με δύο τρόπους:

  α) ΕΛΕΓΧΟΣ: πες μερικές στο μικρόφωνο της εφαρμογής και δες τι κατάλαβε.
     Ό,τι ακούγεται λάθος είναι υποψήφιο για fine-tune.

  β) ΕΚΠΑΙΔΕΥΣΗ: ηχογράφησε όσες θέλεις (ιδανικά από ΠΟΛΛΑ άτομα και σε
     διαφορετικά μικρόφωνα — εδώ η ποικιλία βοηθά, σε αντίθεση με το Piper).

ΤΟ ΚΑΛΥΤΕΡΟ ΣΥΝΟΛΟ ΔΕΝ ΕΙΝΑΙ ΑΥΤΟ: είναι οι ΑΛΗΘΙΝΕΣ εντολές που λέει ο κόσμος
στην εφαρμογή. 300–500 πραγματικές αξίζουν όσο 5.000 από λίστα. Δες MODELS.md §6
για το πώς μαζεύονται, με συγκατάθεση και χωρίς να φύγει τίποτα από το μηχάνημα.
"""


if __name__ == "__main__":
    raise SystemExit(main())
