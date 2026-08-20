# -*- coding: utf-8 -*-
"""Εκπαίδευση LoRA στο Unsloth για τον κανονικοποιητή εκφώνησης.

Τρέχει σε GPU (Colab T4 φτάνει· ~10-15 λεπτά για 890 παραδείγματα και 3 εποχές).
ΔΕΝ τρέχει σε CPU — το Unsloth θέλει CUDA.

    pip install unsloth
    python train_unsloth.py

Στο τέλος βγάζει:
  * lora_tts_normalizer/            → τα βάρη LoRA (μικρά, ~20 MB)
  * gguf/                           → q4_k_m για llama.cpp, ό,τι θα φορτώσει η εφαρμογή
"""

from __future__ import annotations

import json
from pathlib import Path

from datasets import Dataset
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel

# --- Ποιο μοντέλο -------------------------------------------------------------
# 0.6B γιατί το έργο έχει ήδη φάει 452 MB σε installer: το q4_k_m αυτού βγαίνει
# ~400 MB. Αν το μηχάνημα του λογιστή αντέχει, το 1.7B κάνει λιγότερα λάθη σε
# ελληνικό τονισμό. Και τα δύο τρέχουν σε CPU μέσω llama.cpp.
MODEL = "unsloth/Qwen3-0.6B"
MAX_SEQ = 512
DATA = Path(__file__).with_name("tts_normalizer_el.json")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL,
    max_seq_length=MAX_SEQ,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,                       # 16 αρκεί: η δουλειά είναι μετασχηματισμός, όχι γνώση
    lora_alpha=16,
    lora_dropout=0.0,
    bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth",
    random_state=3407,
)

# --- Το prompt ----------------------------------------------------------------
# ⚠️ ΑΚΡΙΒΩΣ το ίδιο κείμενο πρέπει να χτίζεται και στην εκτέλεση. Κάθε διαφορά
# (ακόμη κι ένα κενό) χαλάει την ακρίβεια χωρίς κανένα ορατό σφάλμα.
PROMPT = """### Οδηγία:
{instruction}

### Κείμενο:
{input}

### Εκφώνηση:
{output}"""

EOS = tokenizer.eos_token


def to_text(batch):
    texts = [
        PROMPT.format(instruction=i, input=n, output=o) + EOS
        for i, n, o in zip(batch["instruction"], batch["input"], batch["output"])
    ]
    return {"text": texts}


rows = json.loads(DATA.read_text(encoding="utf-8"))
dataset = Dataset.from_list(rows).map(to_text, batched=True)

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
        num_train_epochs=3,     # 3 εποχές: με 1 δεν μαθαίνει τις ομάδες ψηφίων
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

# --- Γρήγορος έλεγχος πριν την εξαγωγή ----------------------------------------
FastLanguageModel.for_inference(model)
probe = PROMPT.format(
    instruction=rows[0]["instruction"],
    input="Το παραστατικό εκδόθηκε στον πελάτη με ΑΦΜ 802576637, σύνολο 1.240,50 €.",
    output="",
)
ids = tokenizer([probe], return_tensors="pt").to("cuda")
print(tokenizer.batch_decode(model.generate(**ids, max_new_tokens=160))[0])

# --- Εξαγωγή ------------------------------------------------------------------
model.save_pretrained("lora_tts_normalizer")
tokenizer.save_pretrained("lora_tts_normalizer")

# Το GGUF είναι αυτό που φορτώνει το llama.cpp στον υπολογιστή του λογιστή.
model.save_pretrained_gguf("gguf", tokenizer, quantization_method="q4_k_m")
