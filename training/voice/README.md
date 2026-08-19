# Φωνή του βοηθού — τι μοντέλα τρέχουν και τι από αυτά εκπαιδεύεται

## 1. Η αλυσίδα, όπως είναι σήμερα

```
μικρόφωνο ─► whisper.cpp (ggml-small-q5_1) ─► κείμενο
                                               │
                                               ▼
                                    assistant.py / cbHandle
                                    (regex router — ΟΧΙ μοντέλο)
                                               │
                                               ▼
                                    απάντηση σε κείμενο
                                               │
                                               ▼
                             Piper (el_GR-joy-medium.onnx) ─► WAV ─► winsound
```

| Κομμάτι | Μοντέλο | Αρχιτεκτονική | Πού ζει |
|---|---|---|---|
| Ακοή (STT) | `ggml-small-q5_1.bin` (~182 MB) | Whisper (encoder-decoder), quantized ggml | [timologio.spec:142](../../desktop/installer/timologio.spec:142), κλήση στο [etimologio.php:4185](../../etimologio.php:4185) |
| Φωνή (TTS) | `el_GR-joy-medium.onnx`, `en_US-lessac-medium.onnx` (~63 MB έκαστο) | Piper = VITS + espeak-ng phonemizer, ONNX | [speech.py](../../desktop/src/timologio/etimologio/speech.py), κλήση στο [etimologio.php:4008](../../etimologio.php:4008) |
| Ακοή (εναλλακτική, desktop) | `vosk-model-el-gr-0.7` (~1.1 GB, προαιρετικό) | Kaldi | [voice.py](../../desktop/src/timologio/etimologio/voice.py) |
| «Μυαλό» | — | κανόνες/regex | [assistant.py](../../desktop/src/timologio/etimologio/assistant.py) |

Δύο πράγματα που εξηγούν όλα τα λάθη προφοράς:

1. **Ο Piper διαβάζει ό,τι του δώσεις.** Το `802576637` το βγάζει σαν έναν
   αριθμό «οκτακόσια δύο εκατομμύρια…», το `ΑΦΜ` σαν «αφμ».
2. **Ο κώδικας ήδη πεζοποιεί το κείμενο** ([speech.py `_speakable`](../../desktop/src/timologio/etimologio/speech.py),
   [etimologio.php:4021](../../etimologio.php:4021)) γιατί τα ελληνικά κεφαλαία δεν έχουν τόνο.
   Το `mb_strtolower` όμως δεν *βάζει* τόνο: το `ΕΚΔΟΘΗΚΕ` γίνεται `εκδοθηκε`,
   άτονο, και ο Piper το τονίζει λάθος.

## 2. Τι εκπαιδεύεται στο Unsloth και τι όχι

| Θέλω | Unsloth; | Πώς |
|---|---|---|
| Ο Piper να λέει το ΑΦΜ ανά 2 ψηφία | **Όχι** | Δεν είναι θέμα φωνής — είναι θέμα κειμένου. Κανονικοποιητής πριν τον Piper (§3) |
| Νέα φωνή στον Piper | **Όχι** | `piper_train` (PyTorch Lightning, VITS fine-tune) — §5 |
| Καλύτερη αναγνώριση ελληνικών εντολών | **Ναι** | Unsloth Whisper LoRA → επιστροφή σε ggml — §6 |
| Ο βοηθός να καταλαβαίνει ελεύθερο λόγο (αντί regex) | **Ναι** | Κλασικό SFT σε μικρό LLM — ίδιο μοτίβο με το §3 |

Το Unsloth κάνει LoRA σε μοντέλα transformers. Ο Piper είναι VITS σε ONNX —
άλλη οικογένεια, άλλο εργαλείο. Ό,τι λέει «Unsloth TTS» αφορά LLM-based TTS
(Orpheus, Sesame CSM, Llasa) — μοντέλα 1-3B που θέλουν GPU στην εκτέλεση.
Για εφαρμογή που τρέχει σε CPU λογιστή και ήδη ζυγίζει 452 MB, δεν είναι δρόμος.

## 3. Ο κανονικοποιητής εκφώνησης (αυτό που ζήτησες)

Μπαίνει **ανάμεσα** στην απάντηση του βοηθού και τον Piper:

```
απάντηση ─► κανονικοποιητής ─► «αφιμί, ογδόντα, είκοσι πέντε, …» ─► Piper
```

Κανόνας ΑΦΜ/ΜΑΡΚ/τηλεφώνου: **ανά 2 ψηφία σαν αριθμός· αν στο τέλος
περισσεύει τρίτο ψηφίο, τα τελευταία 3 σαν ένας αριθμός.**

```
802576637 → 80 · 25 · 76 · 637
          → «ογδόντα, είκοσι πέντε, εβδομήντα έξι, εξακόσια τριάντα επτά»
```

Το κόμμα δεν είναι διακοσμητικό: ο Piper το μεταφράζει σε παύση.

### Αρχεία

| Αρχείο | Τι κάνει |
|---|---|
| `build_dataset.py` | Παράγει το σύνολο εκφώνησης. Έχει μέσα **λειτουργικό** μετατροπέα ελληνικών αριθμών (`say_code`, `money`, `say_date`, `percent`) |
| `tts_normalizer_el.json` | 890 παραδείγματα `{instruction, input, output}` για την εκφώνηση |
| `build_intents.py` | Παράγει το σύνολο **δρομολόγησης**: εντολή → JSON ενέργεια |
| `intents_el.json` | 728 παραδείγματα, με θόρυβο αναγνώρισης και αρνήσεις οριστικής έκδοσης |
| `eval_router.py` | Πόσο από το `intents_el.json` πιάνει ο **σημερινός** regex router (87%) |
| `train_unsloth.py` | LoRA στο Unsloth + εξαγωγή GGUF |
| [`LOCAL-LLM.md`](LOCAL-LLM.md) | Το σχέδιο ενσωμάτωσης τοπικού LLM στην εφαρμογή |

### Τι περιέχει το σύνολο

ΑΦΜ σκέτα και μέσα σε προτάσεις · ΜΑΡΚ 15ψήφια · σειρές/αριθμοί παραστατικών ·
ποσά σε ευρώ και λεπτά · ποσοστά ΦΠΑ/παρακράτησης · ημερομηνίες και ώρες ·
IBAN · τηλέφωνα · συντομογραφίες (ΑΦΜ→«αφιμί», ΦΠΑ→«φιπιά», ΑΑΔΕ→«ααδέ»,
PDF→«πι ντι εφ», ΔΟΥ→«εφορία») · κεφαλαία→τονισμένα πεζά (ΕΚΔΟΘΗΚΕ→«εκδόθηκε») ·
και **προτάσεις που δεν πρέπει να αλλάξουν** — χωρίς αυτές το μοντέλο αρχίζει
να «διορθώνει» ό,τι βρει.

### Πώς το μεγαλώνεις

Οι πίνακες `ACRONYMS` και `CAPS` στο `build_dataset.py` είναι το σημείο που
ακουμπάς. Πρόσθεσε ζευγάρι, ξανατρέξε:

```bash
python training/voice/build_dataset.py
```

## 4. Εκπαίδευση στο Unsloth — βήματα

**1. Περιβάλλον** (Colab T4 ή τοπική NVIDIA· σε CPU δεν τρέχει):

```bash
pip install unsloth
```

**2. Εκπαίδευση** (~10-15 λεπτά για 890 παραδείγματα × 3 εποχές):

```bash
python training/voice/train_unsloth.py
```

Το μοντέλο βάσης είναι `unsloth/Qwen3-0.6B` — μικρό επίτηδες, γιατί το q4_k_m
του βγαίνει ~400 MB. Το `unsloth/Qwen3-1.7B` κάνει λιγότερα λάθη σε τονισμό
αλλά ~1.1 GB.

**3. Έλεγχος.** Το script τυπώνει μια δοκιμαστική πρόταση πριν την εξαγωγή.
Αν το ΑΦΜ δεν σπάσει σε ομάδες, δεν έφτασαν οι εποχές — ανέβασέ τες σε 5.

**4. Εξαγωγή σε GGUF** (γίνεται από το ίδιο script):

```python
model.save_pretrained_gguf("gguf", tokenizer, quantization_method="q4_k_m")
```

**5. Σύνδεση με την εφαρμογή.** Το GGUF θέλει `llama-cli`/`llama-server` δίπλα
του, με το ίδιο μοτίβο που ήδη χρησιμοποιεί το `voice_engine()` στο
[etimologio.php:3973](../../etimologio.php:3973): μια σταθερά στο `config.php`,
γραμμένη από το [service.py](../../desktop/src/timologio/etimologio/service.py),
και ένα `proc_open` πριν το `?tts=1` καλέσει τον Piper. Το prompt πρέπει να
χτίζεται **ακριβώς** όπως στο `train_unsloth.py` (`PROMPT`).

> ⚠️ Κόστος: +400 MB μοντέλο +llama.cpp, και ~0.3-1 δευτ. καθυστέρηση πριν
> ακουστεί η πρώτη λέξη. Ο ίδιος κανόνας ως **κώδικας** κοστίζει 0 MB και 0 ms:
> ο μετατροπέας στο `build_dataset.py` (`say_code`, `money`, `say_date`)
> μεταφέρεται σε PHP/Python σε μια συνεδρία. Το LLM αξίζει μόνο όταν θέλεις
> κάλυψη σε ό,τι δεν προβλέψαμε — ελεύθερο κείμενο, ξένα ονόματα, ορθογραφία.

## 5. Νέες φωνές στον Piper

**Α. Έτοιμες φωνές** (λεπτά, όχι εκπαίδευση). Κατέβασε `.onnx` + `.onnx.json`
από το [Piper voices](https://huggingface.co/rhasspy/piper-voices), βάλ' τα στο
`desktop/installer/piper/voices/`, και δήλωσέ τα σε **δύο** σημεία:

* [`speech._VOICE_PREFERRED`](../../desktop/src/timologio/etimologio/speech.py) — ποια προτιμάται ανά γλώσσα
* [`timologio.spec` `_VOICES_KEEP`](../../desktop/installer/timologio.spec:124) — αλλιώς το build τις κόβει

Για επιλογή φωνής από τον χρήστη χρειάζεται και τρίτο: το `voice_engine()`
δέχεται σήμερα μόνο `voice_el`/`voice_en`.

**Β. Δική σου φωνή** (fine-tune, όχι Unsloth):

```bash
pip install piper-tts[train]
# 1. Ηχογράφηση: 22050 Hz mono WAV + metadata.csv (id|κείμενο), 30-60 λεπτά καθαρού λόγου
python -m piper_train.preprocess --language el --input-dir dataset --output-dir out \
       --dataset-format ljspeech --single-speaker --sample-rate 22050
# 2. Fine-tune ΠΑΝΩ στο el_GR-joy-medium checkpoint — από το μηδέν θέλει δεκάδες ώρες
python -m piper_train --dataset-dir out --batch-size 16 --max_epochs 2000 \
       --resume_from_checkpoint el_GR-joy-medium.ckpt --precision 32
# 3. Εξαγωγή σε ONNX
python -m piper_train.export_onnx out/lightning_logs/version_0/checkpoints/last.ckpt voice.onnx
```

Το `.onnx.json` το αντιγράφεις από τη φωνή-βάση και αλλάζεις μόνο το όνομα —
χωρίς αυτό ο Piper σκάει ([speech.voice_path](../../desktop/src/timologio/etimologio/speech.py)).

## 6. Whisper — εδώ όντως δουλεύει το Unsloth

Το `ggml-small-q5_1` επιλέχθηκε αφού το `base` έβγαζε «Αν εξέτας τα τυστικά»
για «άνοιξε τα στατιστικά» ([timologio.spec:145](../../desktop/installer/timologio.spec:145)).
Fine-tune στο λεξιλόγιό σου (ΑΦΜ, «πιστωτικό», «παρακράτηση», ονόματα πελατών)
διορθώνει ακριβώς αυτό.

**Τα δεδομένα είναι ήχος, όχι JSON.** Η μορφή `{instruction, input, output}`
δεν ισχύει εδώ:

```python
{"audio": {"array": <float32 16 kHz>, "sampling_rate": 16000},
 "sentence": "έκδοση τιμολογίου στον 802576637 καθαρή αξία εκατό"}
```

Πρακτικά: 200-500 ηχογραφήσεις πραγματικών εντολών (2-8 δευτ. η κάθε μία), από
όσους περισσότερους ομιλητές γίνεται. Μπορείς να τις μαζέψεις **από το ίδιο το
`?stt=1`** — κρατά το WAV και τη διορθωμένη μεταγραφή.

```python
from unsloth import FastModel
model, tok = FastModel.from_pretrained("unsloth/whisper-small", load_in_4bit=False)
model = FastModel.get_peft_model(model, r=32, lora_alpha=32)
# → SFT με WhisperProcessor, μετά merge_and_unload()
```

Επιστροφή στο πακέτο (το whisper.cpp δεν φορτώνει safetensors):

```bash
python whisper.cpp/models/convert-h5-to-ggml.py ./merged-whisper ./whisper ./out
./whisper.cpp/build/bin/quantize ./out/ggml-model.bin ggml-small-q5_1.bin q5_1
```

Το αρχείο μπαίνει στο `desktop/installer/whisper/` — το
[`speech.whisper_model`](../../desktop/src/timologio/etimologio/speech.py) παίρνει
πάντα το **μεγαλύτερο** `ggml-*.bin` του φακέλου, οπότε σβήσε το παλιό ή δώσε
του μικρότερο μέγεθος quantization.
