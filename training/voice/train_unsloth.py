# -*- coding: utf-8 -*-
"""Εκπαίδευση LoRA στο Unsloth για τον βοηθό του e-Τιμολόγιο.

Τρεις δουλειές, ΕΝΑ μοντέλο:

    tts     κείμενο → εκφώνηση      (tts_normalizer_el.json)
    router  εντολή  → JSON ενέργεια (intents_el.json)
    faq     ερώτηση → JSON απάντηση (faq_el.json)

Χωράνε μαζί επειδή η `instruction` κάθε γραμμής λέει ποια δουλειά είναι — και
ένα μοντέλο σημαίνει **μία φορά** φόρτωμα στη μνήμη του λογιστή, όχι τρεις.

    pip install unsloth
    python train_unsloth.py                 # και τα τρία σύνολα
    python train_unsloth.py --task tts      # μόνο η εκφώνηση
    python train_unsloth.py --model unsloth/Qwen3-0.6B --epochs 5

Θέλει CUDA. Σε CPU δεν τρέχει — Colab T4 φτάνει (~20-30 λεπτά για τα τρία
σύνολα × 3 εποχές).

Βγάζει:
  * lora_etimologio/   τα βάρη LoRA (~20-40 MB)
  * gguf/              q4_k_m για llama.cpp, ό,τι φορτώνει η εφαρμογή
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets import Dataset
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel

HERE = Path(__file__).parent

#: Τα σύνολα, με τη σειρά που τα θέλουμε στο mix.
DATASETS = {
    "tts": HERE / "tts_normalizer_el.json",
    "router": HERE / "intents_el.json",
    "faq": HERE / "faq_el.json",
}

# --- Ποιο μοντέλο -------------------------------------------------------------
# Δες MODELS.md §3 για το γιατί. Περίληψη: δεν υπάρχει ελληνικό μοντέλο κάτω από
# 2B, οπότε διαλέγουμε πολύγλωσσο. Το Qwen3.5-0.8B απαντά **χωρίς thinking από
# προεπιλογή** — το Qwen3 βγάζει `<think>…</think>` πριν από το JSON αν δεν του
# το απαγορεύσεις ρητά, που είναι και καθυστέρηση και σπασμένο parsing.
DEFAULT_MODEL = "unsloth/Qwen3.5-0.8B"
MAX_SEQ = 1024      # οι απαντήσεις του FAQ είναι μεγαλύτερες από τις παλιές

# ⚠️ ΑΚΡΙΒΩΣ το ίδιο κείμενο πρέπει να χτίζεται και στην εκτέλεση. Κάθε διαφορά
# (ακόμη κι ένα κενό) χαλάει την ακρίβεια χωρίς κανένα ορατό σφάλμα.
PROMPT = """### Οδηγία:
{instruction}

### Κείμενο:
{input}

### Απάντηση:
{output}"""


def load_rows(tasks: list[str]) -> list[dict]:
    rows: list[dict] = []
    for task in tasks:
        path = DATASETS[task]
        if not path.exists():
            raise SystemExit(
                "Λείπει το {}. Τρέξε πρώτα:  python build_{}.py".format(
                    path.name, {"tts": "dataset", "router": "intents",
                                "faq": "faq"}[task])
            )
        part = json.loads(path.read_text(encoding="utf-8"))
        print("{:>7}: {} παραδείγματα".format(task, len(part)))
        rows += part
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=[*DATASETS, "all"], default="all")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--quant", default="q4_k_m")
    ap.add_argument("--no-gguf", action="store_true",
                    help="μόνο LoRA — για γρήγορη δοκιμή χωρίς μετατροπή")
    args = ap.parse_args()

    tasks = list(DATASETS) if args.task == "all" else [args.task]
    rows = load_rows(tasks)
    print("σύνολο: {} παραδείγματα, μοντέλο {}".format(len(rows), args.model))

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=MAX_SEQ,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        # r=16 αρκεί για μετασχηματισμό. Το FAQ όμως προσθέτει **γνώση** (τι
        # λέει το εγχειρίδιο), και η γνώση θέλει λίγο περισσότερο χώρο: αν οι
        # απαντήσεις βγαίνουν αόριστες, ανέβασέ το σε 32 πριν αλλάξεις μοντέλο.
        r=args.rank,
        lora_alpha=args.rank,
        lora_dropout=0.0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    eos = tokenizer.eos_token

    def to_text(batch):
        return {"text": [
            PROMPT.format(instruction=i, input=n, output=o) + eos
            for i, n, o in zip(batch["instruction"], batch["input"], batch["output"])
        ]}

    dataset = Dataset.from_list(rows).shuffle(seed=3407).map(to_text, batched=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=MAX_SEQ,
            per_device_train_batch_size=8,
            gradient_accumulation_steps=2,
            warmup_steps=10,
            num_train_epochs=args.epochs,
            learning_rate=2e-4,
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir="outputs",
            report_to="none",
        ),
    )
    trainer.train()

    # --- Έλεγχος πριν την εξαγωγή ---------------------------------------------
    # Μία δοκιμή ανά δουλειά. Αν το ΑΦΜ δεν σπάσει σε ομάδες ή το JSON βγει
    # μισό, δεν έφτασαν οι εποχές — ανέβασέ τες σε 5 πριν κατηγορήσεις το μοντέλο.
    FastLanguageModel.for_inference(model)
    probes = {
        "tts": ("Μετάτρεψε το κείμενο σε μορφή έτοιμη για εκφώνηση: αριθμοί, "
                "ΑΦΜ, ποσά, ημερομηνίες και συντομογραφίες γίνονται λέξεις, "
                "όπως τα λέει Έλληνας λογιστής.",
                "Το παραστατικό 2.1 εκδόθηκε στον πελάτη με ΑΦΜ 802576637, "
                "σύνολο 12.100,00 €."),
        "router": (json.loads(DATASETS["router"].read_text(encoding="utf-8"))[0]
                   ["instruction"],
                   "κόψε ένα τιμολόγιο στη Μεγατέκ για διακόσια ευρώ"),
        "faq": (json.loads(DATASETS["faq"].read_text(encoding="utf-8"))[0]
                ["instruction"],
                "γιατί λέει αναμονή ενώ το κατέβασα"),
    }
    for task in tasks:
        instruction, text = probes[task]
        probe = PROMPT.format(instruction=instruction, input=text, output="")
        ids = tokenizer([probe], return_tensors="pt").to("cuda")
        print("\n--- δοκιμή {} ---".format(task))
        print(tokenizer.batch_decode(model.generate(**ids, max_new_tokens=200))[0])

    # --- Εξαγωγή ---------------------------------------------------------------
    model.save_pretrained("lora_etimologio")
    tokenizer.save_pretrained("lora_etimologio")
    if not args.no_gguf:
        # Το GGUF είναι αυτό που φορτώνει το llama.cpp στον υπολογιστή του λογιστή.
        model.save_pretrained_gguf("gguf", tokenizer,
                                   quantization_method=args.quant)


if __name__ == "__main__":
    main()
