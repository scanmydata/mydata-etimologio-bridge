# Φωνή του βοηθού — τι μοντέλα τρέχουν και τι από αυτά εκπαιδεύεται

> **Από πού να ξεκινήσεις:** [MODELS.md](MODELS.md) — ποια μοντέλα για ακοή
> (Whisper), φωνή (Piper) και «μυαλό» (Qwen3.5-0.8B), με μεγέθη, άδειες και
> ταχύτητες σε μηχάνημα χωρίς κάρτα γραφικών, και πώς εκπαιδεύεται το καθένα.
> Για τη λίστα προτάσεων που θα ηχογραφήσεις: `python training/voice/build_readlist.py`.


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
2. **Η πεζοποίηση από μόνη της δεν έφτανε.** Ο κώδικας πεζοποιούσε (τα ελληνικά
   κεφαλαία δεν έχουν τόνο), αλλά το `mb_strtolower` δεν *βάζει* τόνο: το
   `ΕΚΔΟΘΗΚΕ` γινόταν `εκδοθηκε`, άτονο, και ο Piper το τόνιζε λάθος.

**Και τα δύο λύθηκαν στην 0.4.18** από τον κανονικοποιητή του §3 — με κώδικα,
όχι με μοντέλο.

## 2. Τι εκπαιδεύεται στο Unsloth και τι όχι

| Θέλω | Unsloth; | Πώς |
|---|---|---|
| Ο Piper να λέει το ΑΦΜ ανά 2 ψηφία | **Όχι** ✅ | Δεν ήταν θέμα φωνής — ήταν θέμα κειμένου. Έγινε με κώδικα, 0 MB (§3) |
| Νέα φωνή στον Piper | **Όχι** | `piper_train` (PyTorch Lightning, VITS fine-tune) — §5 |
| Καλύτερη αναγνώριση ελληνικών εντολών | **Ναι** | Unsloth Whisper LoRA → επιστροφή σε ggml — §6 |
| Ο βοηθός να καταλαβαίνει ελεύθερο λόγο (αντί regex) | **Ναι** | Κλασικό SFT σε μικρό LLM — ίδιο μοτίβο με το §3 |
| Ο βοηθός να απαντά **«πώς γίνεται»** | **Ναι** | Ίδιο LoRA, τρίτο σύνολο (`faq_el.json`) |

> **Ποιο μοντέλο;** `unsloth/Qwen3.5-0.8B` — q4_k_m 533 MB, Apache 2.0, 201
> γλώσσες, και δεν «σκέφτεται» από μόνο του πριν απαντήσει. Το σκεπτικό και οι
> υποψήφιοι που απορρίφθηκαν (LFM2.5, FunctionGemma, Meltemi/Krikri) είναι στο
> [MODELS.md §3](MODELS.md). Σύντομη εκδοχή: **δεν υπάρχει ελληνικό μοντέλο
> κάτω από 2B**, οπότε διαλέγουμε το καλύτερο μικρό πολύγλωσσο.

Το Unsloth κάνει LoRA σε μοντέλα transformers. Ο Piper είναι VITS σε ONNX —
άλλη οικογένεια, άλλο εργαλείο. Ό,τι λέει «Unsloth TTS» αφορά LLM-based TTS
(Orpheus, Sesame CSM, Llasa) — μοντέλα 1-3B που θέλουν GPU στην εκτέλεση.
Για εφαρμογή που τρέχει σε CPU λογιστή και ήδη ζυγίζει 452 MB, δεν είναι δρόμος.

## 3. Ο κανονικοποιητής εκφώνησης — ✅ ΤΡΕΧΕΙ ΗΔΗ (0.4.18)

Δεν είναι πια σχέδιο: είναι κώδικας μέσα στο προϊόν, **0 MB και 0 ms**.

| Αρχείο | Πού καλείται |
|---|---|
| [`speakable.py`](../../desktop/src/timologio/etimologio/speakable.py) | `speech._speakable`, πριν από τον Piper της εφαρμογής υπολογιστή |
| [`speakable.php`](../../speakable.php) | `?tts=1` του `etimologio.php`, πριν από τον Piper του server |

Δύο υλοποιήσεις, γιατί η φωνή καλείται από δύο πλευρές — και ένα test που
απαιτεί να βγάζουν **ακριβώς** το ίδιο κείμενο σε 30 πραγματικές προτάσεις.
Το σύνολο εκπαίδευσης παράγεται πλέον **από αυτόν τον ίδιο κώδικα**, οπότε
μοντέλο και προϊόν δεν μπορούν να ξεφύγουν.

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
| `build_dataset.py` | Παράγει το σύνολο **εκφώνησης**, **δανειζόμενο** τον μετατροπέα από το `speakable` του προϊόντος — ώστε δεδομένα και φωνή να μην ξεφύγουν ποτέ |
| `tts_normalizer_el.json` | **1.398** παραδείγματα `{instruction, input, output}` για την εκφώνηση |
| `build_intents.py` | Παράγει το σύνολο **δρομολόγησης**: εντολή → JSON ενέργεια |
| `intents_el.json` | **849** παραδείγματα, με θόρυβο αναγνώρισης και αρνήσεις οριστικής έκδοσης |
| `build_faq.py` | Παράγει το σύνολο **γνώσης**: «πώς δουλεύει η εφαρμογή» → σύντομη απάντηση + πλοήγηση |
| `faq_el.json` | **211** παραδείγματα από τα ίδια τα εγχειρίδια, 47 θέματα |
| `check_datasets.py` | Ελέγχει και τα τρία σύνολα **πριν** φάνε ώρα GPU: συμβόλαιο ενεργειών, ψηφία/κεφαλαία που ξέμειναν, αντιφατικές ετικέτες |
| `eval_router.py` | Πόσο από το `intents_el.json` πιάνει ο regex router — **100%**. Δίχτυ παλινδρόμησης: μετρά πάνω στα ίδια δεδομένα από τα οποία γράφτηκαν τα μοτίβα |
| `eval_heldout.py` · `heldout_el.json` | Το **τίμιο** ποσοστό: 52 φράσεις γραμμένες στο χέρι, εκτός δεδομένων εκπαίδευσης — **92,3%** (ήταν 65,4%) |
| `train_unsloth.py` | LoRA στο Unsloth (`--task tts\|router\|faq\|all`) + εξαγωγή GGUF |
| [`MODELS.md`](MODELS.md) | **Ποιο μοντέλο και γιατί** — ακοή, φωνή, «μυαλό», με μεγέθη και άδειες |
| [`LOCAL-LLM.md`](LOCAL-LLM.md) | Το σχέδιο ενσωμάτωσης τοπικού LLM στην εφαρμογή |

Η σειρά, κάθε φορά που αλλάζει η εφαρμογή:

```bash
python training/voice/build_dataset.py
python training/voice/build_intents.py
python training/voice/build_faq.py
python training/voice/check_datasets.py --export   # ΤΕΛΕΥΤΑΙΟ, πάντα
```

Το `--export` γράφει και ένα **`etimologio_sft.jsonl`** με όλα ενωμένα (2.458
γραμμές) — ένα αρχείο για ανέβασμα στο Colab αντί για τρία:

```python
from datasets import load_dataset
ds = load_dataset("json", data_files="etimologio_sft.jsonl", split="train")
```

### Τι περιέχει το σύνολο

ΑΦΜ σκέτα και μέσα σε προτάσεις · ΜΑΡΚ 15ψήφια · σειρές/αριθμοί παραστατικών ·
ποσά σε ευρώ και λεπτά · ποσοστά ΦΠΑ/παρακράτησης · ημερομηνίες και ώρες ·
IBAN · τηλέφωνα · συντομογραφίες (ΑΦΜ→«αφιμί», ΦΠΑ→«φιπιά», ΑΑΔΕ→«ααδέ»,
PDF→«πι ντι εφ», ΔΟΥ→«εφορία») · κεφαλαία→τονισμένα πεζά (ΕΚΔΟΘΗΚΕ→«εκδόθηκε») ·
και **προτάσεις που δεν πρέπει να αλλάξουν** — χωρίς αυτές το μοντέλο αρχίζει
να «διορθώνει» ό,τι βρει.

Από την αναθεώρηση της 0.4.17 και μετά:

* **Κωδικοί τύπων παραστατικών.** Το «2.1» δεν είναι «δύο κόμμα ένα»: είναι
  «δύο τελεία ένα», και ακολουθεί η ονομασία («Τιμολόγιο Παροχής Υπηρεσιών»).
  Η στήλη «Τύπος» τα λέει και τα δύο σε κάθε γραμμή του πίνακα.
* **Καταστάσεις λήψης** («ΕΛΗΦΘΗ», «ΑΝΑΜΟΝΗ», «ΜΟΝΟ ONLINE») και τα μηνύματα
  του ελέγχου φακέλου.
* **Ειδοποιήσεις** με σωστά ποσά — το «12.100,00 €» ήταν το σφάλμα της 0.4.16.
* **Αντίγραφα και επαναφορά**: μεγέθη αρχείων («444,4 MB»), αριθμοί έκδοσης
  («0.4.17» → «μηδέν τελεία τέσσερα τελεία δεκαεπτά»), η λέξη ΕΠΑΝΑΦΟΡΑ.
* **VIES, REST API, myDATA, Taxisnet, Drive, Excel, Ctrl+K** — 24 νέες
  συντομογραφίες που ο Piper συλλάβιζε.
* **Σύντομες ημερομηνίες**: το «26/8/26» που δέχεται πλέον το πεδίο πρέπει να
  ακούγεται ολόκληρο, αλλιώς ο χρήστης δεν ξέρει τι κατάλαβε το πρόγραμμα.

### Πώς το μεγαλώνεις

Οι πίνακες `ACRONYMS` και `CAPS` ζουν πλέον στο
[`speakable.py`](../../desktop/src/timologio/etimologio/speakable.py) — και μαζί
τους στο `speakable.php`. **Ένα ζευγάρι που θα προσθέσεις εκεί μπαίνει
ταυτόχρονα στη φωνή ΚΑΙ στο σύνολο εκπαίδευσης**, γιατί το `build_dataset.py`
τα δανείζεται. Ο `DOC_TYPES` μένει στο `build_dataset.py`: είναι μόνο δεδομένα.

Πρόσθεσε ζευγάρι, ξανατρέξε — και **πάντα** τον έλεγχο:

```bash
python training/voice/build_dataset.py
python training/voice/check_datasets.py
```

Ο έλεγχος πιάνει ακριβώς ό,τι δεν φαίνεται με το μάτι σε 1.415 γραμμές: ψηφίο ή
κεφαλαίο που ξέμεινε στην έξοδο (θα το διαβάσει ο Piper όπως-όπως), λατινικοί
χαρακτήρες, και αντιφατικές ετικέτες.

## 4. Εκπαίδευση στο Unsloth — βήματα

**1. Περιβάλλον** (Colab T4 ή τοπική NVIDIA· σε CPU δεν τρέχει):

```bash
pip install unsloth
```

**2. Εκπαίδευση** (~20-30 λεπτά για 2.458 παραδείγματα × 3 εποχές σε T4):

```bash
python training/voice/train_unsloth.py            # και τα τρία σύνολα μαζί
python training/voice/train_unsloth.py --task tts # μόνο η εκφώνηση
```

Το μοντέλο βάσης είναι **`unsloth/Qwen3.5-0.8B`** (q4_k_m 533 MB, Apache 2.0).
Με `--model unsloth/Qwen3-0.6B` γυρίζεις στα 397 MB, με `Qwen3-1.7B` παίρνεις
καλύτερο τονισμό στο 1,1 GB. Δες [MODELS.md §3](MODELS.md) για το γιατί.

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

> ⚠️ Κόστος: +533 MB μοντέλο +llama.cpp, και ~0.3-1 δευτ. καθυστέρηση πριν
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
