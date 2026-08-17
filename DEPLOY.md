# Στήσιμο του e‑Τιμολόγιο Pro server (home server / VPS)

Αυτό το branch (`deploy/server`) έχει τα deployment αρχεία **στη ρίζα**, ώστε το
Coolify (ή ένα σκέτο `docker compose up`) να τα βρει χωρίς καμία ρύθμιση. Ο
φάκελος `desktop/` (η εφαρμογή υπολογιστή) υπάρχει κι εδώ γιατί είναι το ίδιο
repo, αλλά **δεν μπαίνει στο image** — το `.dockerignore` τον αποκλείει μαζί με
τα `docs/` και `.git/`.

Ένας container σερβίρει **και τα δύο μισά** του προϊόντος:

- το **web UI** (`app.php`) που χρησιμοποιούν οι πελάτες‑επιχειρήσεις από browser
- το **JSON API** που χρησιμοποιεί η εφαρμογή υπολογιστή σε λειτουργία thin client

Έτσι ο λογιστής και οι πελάτες του δουλεύουν πάνω στα **ίδια δεδομένα**.

```
 Υπολογιστής λογιστή                    Home server
 ┌───────────────────┐                  ┌────────────────────────────────┐
 │ Downloader        │                  │ cloudflared ──► Coolify proxy  │
 │ e‑Τιμολόγιο Pro   │ ── HTTPS ───────►│      │                         │
 └───────────────────┘                  │ etimologio (αυτό το image):8080│
 Πελάτες ── HTTPS (browser) ───────────►│ Postgres  +  volume → /data    │
                                        └────────────────────────────────┘
```

> 🔗 Οι ρυθμίσεις **cloudflared** περιγράφονται ξεχωριστά στο
> [`CLOUDFLARED.md`](CLOUDFLARED.md) — ο server τρέχει ήδη άλλες υπηρεσίες
> cloudflared, οπότε **δεν** στήνουμε νέο tunnel· προσθέτουμε ένα ακόμη hostname
> στο υπάρχον.

---

## 1. Γρήγορο στήσιμο με Docker Compose (χωρίς Coolify)

Ο πιο απλός τρόπος για να δουλέψει ο home server σήμερα:

```bash
git clone -b deploy/server https://github.com/scanmydata/mydata-etimologio-bridge.git
cd mydata-etimologio-bridge
cp .env.example .env      # συμπλήρωσέ το (δες §3)
docker compose up -d
docker compose logs -f etimologio
```

Έλεγχος: `curl http://localhost:8080/healthz.php` → `ok`

Το compose σηκώνει **Postgres 16** + την εφαρμογή, με named volumes για τα
δεδομένα. Δεν εκθέτει τίποτα στο internet — αυτό το κάνει το cloudflared.

---

## 2. Στήσιμο με Coolify

1. **Postgres:** *New Resource → Database → PostgreSQL*. Κράτα host/db/user/pass.
2. **Εφαρμογή:** *New Resource → Application → Git repository*
   - Branch: **`deploy/server`**
   - Build Pack: **Dockerfile**
   - Port: **8080**
3. **Volume (υποχρεωτικό):** mount στο **`/data`**.
4. Πέρασε τα env του §3 και κάνε Deploy.

Το Coolify βάζει μόνο του reverse proxy· το cloudflared δείχνει σε αυτό.

---

## 3. Μεταβλητές περιβάλλοντος

Το `config.php` **παράγεται στο boot** από αυτές (`deploy/entrypoint.sh`), οπότε
το image δεν περιέχει κανένα μυστικό.

| Μεταβλητή | Υποχρεωτική | Σημείωση |
|---|---|---|
| `DB_DSN` | ✅ | `pgsql:host=postgres;port=5432;dbname=etimologio` |
| `DB_USER`, `DB_PASS` | ✅ | στοιχεία Postgres |
| `MASTER_ADMIN_EMAIL` | ✅ | ο πρώτος διαχειριστής |
| `MASTER_ADMIN_PASSWORD` | 1η εκκίνηση | αποθηκεύεται **hashed**· **σβήσ' το μετά** |
| `APP_URL` | ✅ | δημόσιο URL, χωρίς `/` στο τέλος — μπαίνει στα emails |
| `SCHED_TOKEN` | για χρονοπρογραμματισμό | `openssl rand -hex 24`· κενό = απενεργοποιημένος |
| `RESEND_API_KEY`, `RESEND_EMAIL_SENDER` | για email | προτεινόμενο· το domain αποστολέα θέλει επαλήθευση |
| `SMTP_*`, `MAIL_PROVIDER` | προαιρετικά | εναλλακτική του Resend· `SMTP_SECURE` = `tls` (587) / `ssl` (465) / `none` |
| `NOTIFY_ADMIN_EMAIL` | προαιρετικό | `-` απενεργοποιεί τα email εκδόσεων |

---

## 4. Το volume `/data` — μη το χάσεις

| Αρχείο | Τι είναι |
|---|---|
| `.enckey` | **το κλειδί κρυπτογράφησης**. Χωρίς αυτό τα αποθηκευμένα στοιχεία ΑΑΔΕ **δεν διαβάζονται ποτέ ξανά** |
| `.cookies/` | συνεδρίες ΑΑΔΕ ανά λογαριασμό |
| `.localdata.sqlite` | μόνο αν δεν έχεις ορίσει `DB_DSN` |

> ⚠️ Πάρε αντίγραφο του `.enckey` **χωριστά** από τη βάση. Η βάση χωρίς το κλειδί
> είναι άχρηστη, και το κλειδί χωρίς τη βάση επίσης — χρειάζονται και τα δύο.

---

## 5. Έλεγχος ότι δουλεύει

```bash
curl -s http://localhost:8080/healthz.php                 # → ok
curl -s "http://localhost:8080/etimologio.php?auth=me"    # → JSON (χωρίς σύνδεση)
docker compose exec etimologio php -m | grep -E "pdo_pgsql|curl|openssl"
docker compose exec etimologio php -r 'var_dump(PDO::getAvailableDrivers());'

# Η ανάθεση εταιρειών σε λογιστές (0.4.1) — ο πίνακας φτιάχνεται μόνος του:
docker compose exec postgres psql -U etimologio -d etimologio -c '\d account_managers'
```

**Δοκίμασε το email πριν προσκαλέσεις κόσμο:** Ρυθμίσεις → Πάροχος email →
«✉️ Δοκιμαστική αποστολή». Ο container πρέπει να μπορεί να βγει στην έξω θύρα
587 (ή 465) — σε πολλά VPS είναι κλειστή από τον πάροχο και τότε ο μόνος δρόμος
είναι το Resend (HTTPS).

Μετά, από browser: `https://<το hostname σου>/app.php` → οθόνη σύνδεσης.

**Σύνδεση της εφαρμογής υπολογιστή:** e‑Τιμολόγιο Pro → **Ρυθμίσεις** →
«Σύνδεση σε server» → βάλε το δημόσιο URL → **Σύνδεση σε server**.

---

## 6. Μεταφορά υπαρχόντων τοπικών δεδομένων (μία φορά)

Αν ένα γραφείο ξεκίνησε τοπικά (SQLite) και μετακομίζει στον server:

```bash
php tools/migrate_to_server.php \
  --from "/path/Παραστατικά myDATA/etimologio/local.sqlite" \
  --dsn "pgsql:host=postgres;dbname=etimologio" --user … --pass … --dry-run
```

Τρέξε πρώτα με `--dry-run`. **Αντίγραψε και το `.enckey`** στο volume, αλλιώς
όλα θα μεταφερθούν κρυπτογραφημένα και αδιάβαστα.

---

## 7. Τι ΔΕΝ είναι έτοιμο ακόμη

- **Πολλαπλά λογιστικά γραφεία στον ίδιο server.** Από την 0.4.1 ο ρόλος
  `editor` (λογιστής) βλέπει **μόνο** τις εταιρείες που του αναθέτει ο
  διαχειριστής — αυτό λύνει τον διαχωρισμό *μέσα* σε ένα γραφείο. Ο ρόλος
  `master` εξακολουθεί να βλέπει τα πάντα, οπότε για **δύο ανεξάρτητα γραφεία**
  στον ίδιο server χρειάζεται ακόμη απομόνωση με `tenant_id`: μέχρι τότε, **ένα
  instance ανά γραφείο**.
- **Αυτόματα backup σε Google Drive** — δεν έχει υλοποιηθεί· προς το παρόν
  χειροκίνητα (`pg_dump` + tarball του `/data`).
- **Infisical** — τα μυστικά μπαίνουν σήμερα ως απλά env στο Coolify.

---

## 8. Τι αλλάζει με την 0.4.1

- **Ανάθεση εταιρειών σε λογιστές.** Νέος πίνακας `account_managers`. Στην
  **πρώτη** εκκίνηση μετά την αναβάθμιση, κάθε υπάρχων λογιστής παίρνει ό,τι
  έβλεπε μέχρι τότε (δηλαδή τα πάντα) — αλλιώς θα κλειδωνόταν έξω. Πέρασε από
  **Διαχείριση → Χρήστες** και περιόρισε τις αναθέσεις· η ίδια οθόνη
  προειδοποιεί για λογιστές χωρίς καμία εταιρεία.
- **Το SMTP στέλνει πραγματικά.** Μέχρι την 0.4.0 τα πεδία `SMTP_HOST/USER/PASS`
  συλλέγονταν αλλά η αποστολή γινόταν με `mail()`, που στο image δεν έχει relay:
  **τίποτα δεν έφευγε, χωρίς μήνυμα λάθους**. Αν το γραφείο βασιζόταν σε SMTP,
  δες ξανά τις ρυθμίσεις και πάτα «Δοκιμαστική αποστολή».
- **Φωνή του βοηθού.** Οι μηχανές (Piper/whisper.cpp) **δεν** ταξιδεύουν στο
  image του server — είναι εκατοντάδες MB και δεν έχουν νόημα σε container. Τα
  `?tts=` / `?stt=` απαντούν `501` και το UI πέφτει πίσω στη φωνή του browser
  (ή ζητά γραπτή εντολή). Θέλεις φωνή στον server; Βάλε τα binaries σε volume
  και όρισε `PIPER_EXE` / `PIPER_VOICE_EL` / `WHISPER_EXE` / `WHISPER_MODEL`
  στο `config.php`.
- **Προτιμήσεις UI ανά χρήστη** (πλάτη/σειρά στηλών) ζουν στο `app_settings`,
  άρα ταξιδεύουν με τη βάση: ο ίδιος χρήστης βρίσκει τη διάταξή του και από
  άλλον υπολογιστή.
