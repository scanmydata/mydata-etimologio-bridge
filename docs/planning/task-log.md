# Task log — e‑Τιμολόγιο Pro & the Downloader merge

Snapshot of the working task list across the recent sessions. See
[`merge-plan.md`](merge-plan.md) for the approved architecture and
[`../project-memory/`](../project-memory) for the durable notes.

## Session A — e‑Τιμολόγιο Pro platform features (repo: `mydata-etimologio-bridge`, pushed to `main`)

- [x] App icon from the ScanmyData logo + invoicing/€ badge (`tools/make_icon.py` → `assets/icons/`)
- [x] DB layer: `scheduled_jobs` + `issue_notifications` tables & helpers
- [x] **TODO 91** — issuance notifications backend + endpoints (`notifyIssue`, `?notifications/notif_read/notif_count`)
- [x] **TODO 90** — scheduled issuance backend + `scheduler.php` runner (loopback service‑auth, recurrence, status/history)
- [x] app.php UI: notifications bell + feed, schedule modal + Προγραμματισμός view, manual PDF update
- [x] `mail.php` — Resend + SMTP provider abstraction + branded HTML template
- [x] Wire email into all auth flows (signup/approval/forgot/invitations) + issuance notifications
- [x] Roles + email invitations (master / editor‑λογιστής / business); staff all‑company access
- [x] Optional 2FA (authenticator TOTP, RFC 6238) with QR enrolment + two‑step login
- [x] Full UI‑managed scheduler (admin all‑companies + client own)
- [x] `config.example.php` + TODO + local end‑to‑end tests (portable PHP)
- [x] Per‑admin email notification preferences (which companies + which movement types)
- [x] Move Ξενάγηση/Εγχειρίδιο buttons above the theme toggle; deepen the manual PDF; update the page tour
- [x] Lint, test, commit + push (`main`)

## Session B — Merge into the Downloader (now vendored here under `desktop/`)

> **Single‑branch consolidation.** The whole desktop product (the
> `MyData-Invoice-Downloader` tree with all Phase‑0 merge work) is vendored into
> **this** branch under [`desktop/`](../../desktop) via `git subtree`, history
> preserved. This branch now contains *everything* — the standalone PHP bridge at
> the repo root **and** the unified desktop app under `desktop/` (which carries its
> own copy of the bridge at `desktop/backend/etimologio/`). The
> `MyData-Invoice-Downloader` repo is left **untouched** (its `merge/etimologio-pro`
> branch stays local and is not pushed). Re‑sync after further desktop work with:
> `git subtree pull --prefix=desktop <downloader-path> merge/etimologio-pro`.

- [x] Pull downloader to v0.2.25 + subtree‑merge the PHP bridge into `backend/etimologio/`
- [x] **Backend A** — dual‑dialect DB layer (SQLite + Postgres) via `DB_DSN` (`db_dialect()`/`db_now_sql()`/`db_insert()` + DDL translator); SQLite verified, Postgres to verify on the VPS
- [x] Python `EtimologioClient` (API) + `service.py` (local PHP lifecycle; offline/thin modes)
- [x] Qt shell: launcher + Downloader ↔ e‑Τιμολόγιο switch + native login (offline auto‑login → home); full suite 308 passed

### Phase 0 delivered above. Remaining roadmap (from `merge-plan.md`)

- [x] **Phase 1 — core issuance (native Qt):** ✅ complete
  - [x] Client API: `customers`/`create_customer`/`search_invoices`/`payments`/`issue_invoice` (+ `customers_cached`)
  - [x] Native **Πελάτες** page (search by name/ΑΦΜ, list, create customer, open card)
  - [x] Native **Καρτέλα** (issued invoices + local payments + computed balance, default year range)
  - [x] Native **Έκδοση** (type/series/payment, customer + ΑΦΜ άντληση, multi-line editor with live totals, **πρόχειρο / προεπισκόπηση PDF / έκδοση** modes)
  - [x] **"Open client from the Downloader"** — clients-table context action → `open_client_in_etimologio(vat)` → `EtimologioShell.focus_customer`
  - [x] 17 new unit tests; full suite **325 passed**
  - [x] **Live-verified** vs real ΑΑΔΕ (VAT 802576637): retrieval (27 πελάτες + 15 τιμολόγια) **and** a DRAFT issue via the real `IssuePage` — UI totals matched the backend exactly (145,00 / 34,80 / 179,80). Caught+fixed a rate-as-fraction bug (bridge wants 0.24, not 24) during the live test.
- [x] **Phase 2 — catalogs & lifecycle:** ✅ complete
  - [x] Native **Είδη** (list + new + delete), **Σειρές** (list + new + delete) — shared `ListPage` base
  - [x] Native **Πρόχειρα** (list + delete)
  - [x] Native **Ακύρωση/Πιστωτικό** — correlated credit note by original ΜΑΡΚ (πρόχειρο/preview/issue)
  - [x] Client API: `products`/`create_product`/`delete_product`, `series`/`create_series`/`delete_series`, `temp_invoices`/`delete_temp`, `credit_note`
  - [x] 6 more tests; full suite **331 passed**
  - [x] **Live-verified** vs real ΑΑΔΕ: Είδη 10 · Σειρές 5 · Πρόχειρα 3, and a DRAFT credit note for a real ΜΑΡΚ (→ type 61, saved, nothing submitted). Test drafts cleaned up afterwards.
- [x] **Phase 3 — volume & money:** ✅ complete
  - [x] Native **Μαζική έκδοση** (shared header + per-row customer/line, batch drafts or live issue, per-row results written back)
  - [x] Native **Πληρωμές** — local ledger (list + manual add) **and** bank-statement import (parse → review → register)
  - [x] Native **Στατιστικά** — breakdown per document type + net turnover, period switch
  - [x] **Statistics caching** (as requested): `cache_set`/`cache_get` write-through on every live call, `?statistics&stats_cached=1` instant read served **before the AADE login**, and a `?sync=statistics` branch that refreshes all three periods at once. The cache is DB-backed (`app_cache`, encrypted, per company+period) so the **same code path** caches for the local offline client (SQLite), the thin client, and the VPS (Postgres).
  - [x] Client API: `statistics(period, cached=)`, `sync(kind)`, `bulk_issue`, `bank_preview`/`bank_import`, `add_payment`/`delete_payment`
  - [x] 8 more tests; full suite **339 passed**
  - [x] **Live-verified** vs real ΑΑΔΕ: statistics cache **2.45s → 0.01s** (~245× faster, identical data, survives restarts — confirmed encrypted rows in `app_cache` for month/preMonth/year); a 2-item bulk **draft** batch (both OK); payment add/list/delete round-trip. All test drafts deleted afterwards.
- [x] **Phase 4 — platform:** ✅ complete
  - [x] Native **Προγραμματισμός** (job list + cancel), **Ειδοποιήσεις** (feed, unread in bold, mark‑all‑read), **Ρυθμίσεις** (password, **2FA with a real QR**, per‑admin email prefs), **Διαχείριση** (users, roles, invitations, activate/disable)
  - [x] **Μαζική εκτύπωση με προεπισκόπηση + εξαγωγή ZIP** — new **Παραστατικά** page (search, checkbox multi‑select) and the same on the **Καρτέλα**; PDFs pulled by ΜΑΡΚ (`bulkpdf.py`), previewed through the *Downloader's own* `print_pdfs` dialog, packed flat with de‑duplicated names
  - [x] **UI harmonised with the Downloader** — `pages/ui.py` (cards, page headers, tiles, KPI stats, themed buttons/tables); every hardcoded colour replaced by theme object names so light/dark both work; home rebuilt as a header card + KPI tiles + a 3‑column launcher grid; new `stats`/`schedule`/`bell`/`settings` icons
  - [x] **All 14 sections are native** — nothing falls back to the browser
  - [x] 🐞 **Bug found & fixed:** `shell._run` dropped results because the `_Job` (and its signal object) could be garbage‑collected before emitting — an intermittently "never loading" page. Jobs are now kept in `_INFLIGHT` until they report; 2 regression tests added
  - [x] +11 tests; full suite **350 passed**
  - [x] **Live-verified** vs real ΑΑΔΕ: 4 real PDFs fetched (~99KB each, valid `%PDF`), zipped (374KB, integrity‑checked) and confirmed to render 4 pages through the print engine; notifications/scheduler/admin/prefs endpoints all OK; 2FA setup returns a scannable QR
- [x] **Phase 5 — server + web:** ✅ complete (deployment ready; VPS rollout is an operations step)
  - [x] **`Dockerfile`** (php:8.3-apache, `pdo_pgsql`+`pdo_sqlite`, CA certs) + **`deploy/entrypoint.sh`** that renders `config.php` from the environment at boot (no secrets in the image) and ticks `scheduler.php` every minute + **`healthz.php`** probe
  - [x] **`deploy/README.md`** — Coolify walkthrough: Postgres service, env table, the required `/data` volume (`.enckey`, cookies), pointing the desktop at the server
  - [x] **`tools/migrate_to_server.php`** — one‑off SQLite→Postgres copy (shared columns only, `ON CONFLICT DO NOTHING`, sequence reset, `--dry-run`)
  - [x] Desktop **thin‑client UI** — «Σύνδεση σε server» card in Ρυθμίσεις; switches offline ↔ thin live without restarting
- [x] **Μαζική εκτύπωση & ZIP στο web / thin client**
  - [x] **`zipwriter.php`** — ZIP built with zlib only. `ZipArchive` is absent from the portable PHP *and* slim images, so the existing `invoices_zip` endpoint was **broken outside a full PHP install**; it now works everywhere (verified against an independent reader: valid, UTF‑8 Greek names, DEFLATE/STORE)
  - [x] `?bulk_pdf` endpoint — `mode=zip` streams the archive, `mode=json` returns base64 PDFs so the browser can merge them (pdf‑lib) into one document for a **native print preview**. Falls back to one tab per PDF
  - [x] Καρτέλα gains «🖨️ Μαζική εκτύπωση» + «🗜️ ZIP παραστατικών» — the client can print/export **their own** documents
- [x] **UI parity with the Downloader (web)**
  - [x] Toggles rebuilt to the desktop `ToggleSwitch` spec — 40×22 track, 16px knob, 18px travel, `--line`→`--accent2`, knob `--muted`→`--on-accent`, under a «ΡΥΘΜΙΣΕΙΣ» separator, labels «Φωτεινό θέμα»/«Βοηθητικά μηνύματα» (stable, like the desktop)
  - [x] **Sidebar now follows the theme** (`--menu-bg`, the desktop's `menu_bg` values) instead of a hardcoded dark gradient; header likewise (`--header-bg`)
- [x] **Digital assistant upgraded** — evaluated NLP.js / Transformers.js and rejected both (megabytes + CDN/model dependency, incompatible with offline desktop and self‑hosting); instead: accent/case‑insensitive normalisation (halved the keyword table), a declarative intent map covering **every** feature (bulk print, ZIP, notifications, scheduler, 2FA, admin, payments, stats), a always‑available «άκυρο» escape, and a fuller help card
- [x] **Manual PDF + page tour updated** — new «3β. Μαζική εκτύπωση & εξαγωγή ZIP» and «11β. Ψηφιακός βοηθός» sections (15 chapters); tour gains Ακύρωση/Πιστωτικό, the assistant, and the reworded toggles (16 steps)
- [x] 🐞 **Bugs found & fixed during the accountant‑side review**
  - Assistant: «πήγαινε στα παραστατικά» matched the issuance keyword `παραστατ` and started an invoice flow, then the stuck context swallowed every later command. Navigation now wins, and «άκυρο» always resets
  - Light theme contrast: hardcoded `#04222f` on active nav items and primary buttons, a permanently dark sidebar/header under theme‑switching text, and `--muted` at 3.46:1. **Automated contrast audit now reports 0 failures in both themes** (was 7 in light)
- [ ] **Packaging:** bundle a portable `php.exe` into PyInstaller `datas`; scheduler via Task Scheduler (standalone) / container cron (server).
  - ⚠️ **CA bundle required:** the bundled PHP must ship a `cacert.pem` with `curl.cainfo`/`openssl.cafile` set in its `php.ini`, or outbound TLS to `mydata.aade.gr` fails with OpenSSL error 60. Reuse certifi's bundle (same as the Downloader's Python side). Discovered during the Phase‑1 live test.

## Session C — Ο server έτοιμος για Coolify + cloudflared (branch `deploy/server`)

Στόχος: το image να μπορεί να σταθεί σε δημόσιο hostname (θύρα **8080** πίσω από
υπάρχον cloudflared tunnel), με τη βάση να δένει από το connection string του
Coolify και τη **σύνδεση εταιρειών με τα κλειδιά ΑΑΔΕ** αποδεδειγμένα λειτουργική
πάνω σε Postgres.

- [x] **Σύνδεση βάσης με ένα URL** — `deploy/dburl.php`: το `DATABASE_URL` /
      `POSTGRES_URL` του Coolify σπάει σε `DB_DSN`/`DB_USER`/`DB_PASS` στο boot
      (υποστηρίζει `sslmode`, percent‑encoded κωδικούς). Το entrypoint **περιμένει**
      τη βάση ως 60s πριν σηκώσει τον Apache, αντί να σκάει το πρώτο request.
- [x] **`ENCRYPTION_KEY` από το περιβάλλον** — το κλειδί μπορεί πλέον να ζει στα
      μυστικά του Coolify αντί για το volume· αν λείπει, ισχύει το `/data/.enckey`
      όπως πριν.
- [x] 🐞 **Το image δεν φόρτωνε `pdo_pgsql`** — το `apt-get purge --auto-remove
      libpq-dev` έπαιρνε μαζί και το `libpq5`. Το build ακολουθεί πλέον το επίσημο
      μοτίβο (`savedAptMark` + `ldd`), προσθέτει `zip` (ανάγνωση .xlsx) και
      `sodium` όπου λείπει, και **αποτυγχάνει** αν λείπει `pdo_pgsql`/`sodium`.
- [x] **`deploy/php.ini`** — το base image δεν έχει καθόλου php.ini, άρα έτρεχε με
      `display_errors=On` (DSN και χρήστης βάσης στη σελίδα), 128M μνήμη και 30s
      όριο, λίγα για μαζική εξαγωγή PDF/ZIP. Τώρα: σφάλματα μόνο στα logs, 512M /
      300s / 32M upload (ρυθμιζόμενα από env), ώρα Ελλάδας, opcache.
- [x] **`deploy/apache-etimologio.conf`** — σερβίρονται μόνο `app.php`,
      `etimologio.php`, `healthz.php`, `assets/`· κόβονται `config.php`, `tools/`,
      `deploy/`, `.md`, dotfiles, βάσεις και αρχεία βιβλιοθήκης· κεφαλίδες
      ασφαλείας· `no-store` στο API· `/` → `/app.php`. Το web root έγινε **μη
      εγγράψιμο** από τον χρήστη του Apache (το lock του scheduler πήγε στο `/data`).
- [x] **Σωστή συμπεριφορά πίσω από proxy** — `req_is_https()` (X‑Forwarded‑Proto /
      CF‑Visitor): cookie συνεδρίας `Secure` μόνο σε HTTPS (χωρίς να σπάει το
      offline 127.0.0.1), `HttpOnly` + `SameSite=Lax` παντού.
- [x] 🐞 **Σύνδεσμος επαναφοράς κωδικού από `Host`** — φτιαχνόταν από την κεφαλίδα
      του αιτήματος· πλαστό `Host` σε «ξέχασα τον κωδικό» έστελνε στο θύμα
      σύνδεσμο προς ξένο domain. Πλέον βγαίνει από το `APP_URL` (`app_base_url()`).
- [x] **Σκλήρυνση των «loopback» μονοπατιών** — service‑auth του scheduler και
      desktop autologin απαιτούν και **απουσία** κεφαλίδων proxy (`req_is_loopback()`).
- [x] 🐞 **Stale cache ρυθμίσεων** — το `setting_get()` κρατούσε στατική cache που
      το `setting_set()` δεν ακύρωνε: «αποθήκευσε και διάβασε» μέσα στο ίδιο
      request γύριζε την παλιά τιμή (π.χ. αλλαγή SMTP και αμέσως δοκιμαστική
      αποστολή). Νέο `settings_all(reset:)` — και το `user_prefs_all()` το
      χρησιμοποιεί αντί για δεύτερο query.
- [x] 🐞 **`.xlsx` χωρίς την επέκταση `zip`** — `new ZipArchive()` χωρίς έλεγχο
      έριχνε fatal (λευκή οθόνη). Τώρα: καθαρό μήνυμα «σώσ' το ως CSV», και το
      `bank_preview` πιάνει κάθε σφάλμα ανάλυσης αρχείου.
- [x] **Χωρίς λευκές οθόνες όταν πέφτει η βάση** — global handler: 503 με
      ελληνικό μήνυμα (ή JSON για το API), λεπτομέρειες μόνο στο log.
- [x] **`opcache_reset()` μόνο τοπικά** — στον server άδειαζε την cache όλης της
      εφαρμογής σε κάθε άνοιγμα σελίδας.
- [x] **`healthz.php?db=1`** — «απαντά και η βάση», χωρίς να αποκαλύπτει τίποτα.
- [x] **`tools/pg_smoke.php`** — ένα τρέξιμο ελέγχει επεκτάσεις, σύνδεση, όλους
      τους πίνακες, κρυπτογράφηση, **καταχώριση εταιρείας + κλειδιών ΑΑΔΕ και
      επανανάγνωσή τους**, ανάθεση σε λογιστή, πληρωμές, cache/upserts,
      ειδοποιήσεις, χρονοπρογραμματισμό και TLS προς ΑΑΔΕ — και καθαρίζει μόνο του.
      Τρέχει ίδιο σε SQLite και Postgres· **επαληθεύτηκε τοπικά σε SQLite** (42
      έλεγχοι· αποτυγχάνουν μόνο οι 3 της κρυπτογράφησης, γιατί η φορητή PHP των
      Windows δεν έχει `sodium` — στο image είναι υποχρεωτικό).
- [x] **Τεκμηρίωση** — `DEPLOY.md` (Coolify με `DATABASE_URL`, νέες μεταβλητές,
      **§5 σύνδεση εταιρειών με τα κλειδιά ΑΑΔΕ**, §6 έλεγχος με `pg_smoke`, §10 τι
      κάνει το image για την έκθεση), `CLOUDFLARED.md` (rate limiting αντί για
      Access, γιατί να μη μπει mod_remoteip), `deploy/README.md` → δείκτης στα δύο.
- [ ] **Απομένει (στον server):** `docker compose up -d` ή deploy από Coolify,
      `php tools/pg_smoke.php` μέσα στον container (πρώτη πραγματική επαλήθευση
      Postgres), προσθήκη hostname στο υπάρχον tunnel, `APP_URL` + redeploy.
- [x] ⚠️ **Ξεχωριστό εύρημα (εφαρμογή υπολογιστή) — ΛΥΘΗΚΕ:** η φορητή PHP που
      πακεταριζόταν **δεν είχε `sodium`**, και το `crypto.php` σε αυτή την
      περίπτωση αποθηκεύει **καθαρό κείμενο** (graceful fallback): σε τοπική
      εγκατάσταση τα subscription keys, τα ονόματα πελατών και τα ποσά ήταν
      ασφράγιστα μέσα στο SQLite. Δες Session D.

## Session D — Κρυπτογράφηση και στην τοπική εγκατάσταση

- [x] **`sodium` στη φορητή PHP** (`desktop/installer/build.ps1`): `php_sodium.dll`
      στο `$keep`, `extension=sodium` στο παραγόμενο `php.ini`, και «sodium» στην
      επαλήθευση με `php -m` — το build **σκάει** αν λείπει.
- [x] **Ο έλεγχος φρεσκάδας που έλειπε:** το βήμα παρέκαμπτε τη λήψη αν υπήρχε
      `php.exe`, οπότε ένα κλαδεμένο δέντρο από παλιότερο build δεν θα έπαιρνε
      ΠΟΤΕ τη νέα επέκταση (και το build θα έσκαγε στην επαλήθευση χωρίς να λέει
      γιατί). Τώρα ελέγχει ότι υπάρχουν όλα τα DLL του `$keep` και, αν λείπει
      κάποιο, ξαναφέρνει τη φορητή PHP.
- [x] **Εφάπαξ κρυπτογράφηση όσων γράφτηκαν καθαρά** — `crypto_backfill_plaintext()`
      στο `localdb.php`, στο τέλος του `localdb()`: την πρώτη φορά που η βάση
      ανοίγει με sodium διαθέσιμο, κάθε κρυπτογραφούμενη στήλη που έμεινε καθαρή
      ξαναγράφεται (8 πίνακες / 16 στήλες), μέσα σε συναλλαγή, με σημαία
      `crypto.backfilled` στο `app_settings`. Χωρίς sodium **δεν** μπαίνει σημαία,
      ώστε να τρέξει όταν κάποτε υπάρξει· σε αποτυχία γίνεται rollback και
      ξαναπροσπαθεί στο επόμενο άνοιγμα.
- [x] **Η σιωπηλή υποχώρηση έγινε θορυβώδης** — `crypto_warn_no_sodium()`: μία
      γραμμή στο `php-server.log` ανά διεργασία, αντί για τίποτα.
- [x] **Επαληθεύτηκε τοπικά** με τη φορητή PHP του installer (8.3.33 + sodium):
      `tools/pg_smoke.php` **42/42** (ήταν 39/42 — έπεφταν ακριβώς οι τρεις της
      κρυπτογράφησης)· βάση «παλιάς εγκατάστασης» με 16 καθαρά πεδία →
      **16 κρυπτογραφήθηκαν, 0 έμειναν καθαρά**, όλα διαβάζονται σωστά μέσα από το
      API, δεύτερο τρέξιμο δεν ξαναγράφει τίποτα· end-to-end μέσω HTTP, το
      `SUBKEY-SECRET` **δεν** υπάρχει πια καθαρό μέσα στο αρχείο SQLite.
- [x] **Συγχρονίστηκε το vendored αντίγραφο** `desktop/backend/etimologio/` (9
      αρχεία PHP + `tools/pg_smoke.php`), ώστε ο installer να πακετάρει τις ίδιες
      διορθώσεις — μαζί και όσες έγιναν στη Session C.
- [ ] **Απομένει:** τρέξιμο του `build.ps1` και δοκιμή του installer σε καθαρό
      μηχάνημα. Σε **αυτό** το μηχάνημα το `php_sodium.dll` + `libsodium.dll`
      μπήκαν ήδη με το χέρι στο `desktop/installer/php/` (gitignored), οπότε το
      build δεν θα ξανακατεβάσει τίποτα· σε καθαρό checkout θα το κατεβάσει μόνο
      του.

## Session E — 0.4.7: σύνδεση local ↔ web, ειδοποιήσεις από την ΑΑΔΕ, στήλες

> **Το branch του server ήταν πίσω.** Το `deploy/server` είχε μείνει στην 0.4.1
> ενώ η κύρια γραμμή (`planning/etimologio-merge`) ήταν στην **0.4.6** — 5
> commits, 59 αρχεία. Η δουλειά αυτής της συνεδρίας γράφτηκε πρώτα πάνω στο
> παλιό branch και μετά **ενοποιήθηκε** με την κύρια γραμμή· στη διαδρομή
> αποδείχθηκε ότι δύο από τα ζητούμενα υπήρχαν ήδη εκεί, σε καλύτερη μορφή, και
> η δική μου υλοποίηση **αφαιρέθηκε** υπέρ τους.

- [x] **Σύνδεση εγκατάστασης γραφείου με τον web server — το κομμάτι που έλειπε.**
      Η κύρια γραμμή είχε ήδη ολόκληρο το σύστημα κλειδιών (`access_keys`,
      `?auth=access_provision`, κλειδί που κουβαλά τη διεύθυνση:
      `etim1_<base64 host>_<μυστικό>`) — αλλά **μόνο** μέσα από τον Πίνακα
      ελέγχου του Downloader. Στις Ρυθμίσεις του e‑Τιμολόγιο, εκεί που ψάχνει ο
      λογιστής, δεν υπήρχε τίποτα.
  - Νέα κάρτα «☁️ Σύνδεση με web server» στις Ρυθμίσεις, ορατή **μόνο** σε
    εγκατάσταση γραφείου (`DESKTOP_TOKEN`): επικόλληση κλειδιού, κατάσταση,
    λίστα εταιρειών και **έτοιμος σύνδεσμος για κάθε πελάτη** (αντιγραφή/άνοιγμα).
  - Τοπικά endpoints `link_get` / `link_connect` / `link_disconnect`: αποκωδικοποιούν
    το κλειδί, ρωτούν τον server (`access_provision`) και γράφουν το
    **`service.json`** (`mode: thin`, `server_url`) — το ίδιο αρχείο που διαβάζει
    η εφαρμογή υπολογιστή όταν ξεκινά. Γι' αυτό το UI λέει ρητά «κλείσε και
    ξανάνοιξε την εφαρμογή».
  - 🐞 Δύο σφάλματα πιάστηκαν στη ζωντανή δοκιμή: το `%` της PHP δίνει αρνητικό
    για αρνητικό αριστερό μέλος (έσκαγε το padding του base64), και ένα literal
    newline μέσα σε `alert('…')` έριχνε **ολόκληρο** το inline script.
  - Επαληθεύτηκε με δύο instances: κλειδί από τον server → σύνδεση → `service.json`
    γίνεται `thin` → αποσύνδεση → `offline`. Λάθος κλειδί και κακή μορφή
    απορρίπτονται με καθαρό μήνυμα.
  - **Αφαιρέθηκε** η δική μου παράλληλη υλοποίηση (πίνακας `api_keys`,
    `auth_api_key_login()`, `admin_key_*`, `?api=import`, ανέβασμα δεδομένων ανά
    εταιρεία): δούλευε και είχε δοκιμαστεί, αλλά δύο συστήματα κλειδιών στο ίδιο
    προϊόν είναι χειρότερα από ένα. Με το `mode: thin` το ανέβασμα δεν χρειάζεται
    — τα δεδομένα **είναι** στον server· για παλιά τοπικά δεδομένα υπάρχει το
    `tools/migrate_to_server.php`.
- [x] **Ειδοποιήσεις και για ό,τι ΔΕΝ εκδόθηκε από εδώ** (γνήσια νέο) — `?sync=newdocs`
      με **δική του cache**, ώστε να μην «κουρεύει» τη λίστα των Παραστατικών:
      συγκρίνει την αποθηκευμένη cache με την πλατφόρμα και γράφει ειδοποίηση για
      κάθε νέο ΜΑΡΚ (`source='aade'`, σήμανση 🛰️). Τρέχει 9 δευτ. μετά το άνοιγμα,
      κάθε 30 λεπτά, στο event `online`, και χειροκίνητα από «🛰️ Έλεγχος ΑΑΔΕ»
      στην καμπάνα. `notification_exists()` κόβει τα διπλά.
- [x] **Το κουμπί «⚙ Στήλες» σε ΚΑΘΕ πίνακα.** Ο επιλογέας υπήρχε ήδη
      (`openColumnChooser`), αλλά το κουμπί ήταν γραμμένο με το χέρι **μόνο** στα
      Παραστατικά. Τώρα η μπάρα μπαίνει μόνη της από το `attachColumnFilters()`,
      δείχνει πόσες στήλες είναι κρυμμένες, και το χειρόγραφο κουμπί αφαιρέθηκε.
      Επαληθεύτηκε σε **13 πίνακες / 10 ενότητες**.
- [x] **Εικονίδιο installer** — νέο `installer-icon.ico` από το
      `etimologio-logo.png` (το σήμα ScanmyData που δείχνει το μενού κάτω
      αριστερά)· `SetupIconFile=installer-icon.ico`. Η εφαρμογή κρατά το δικό της
      `icon.ico`. Το `make_icon.py` το παράγει πλέον μαζί με τα υπόλοιπα.
- [x] **Έκδοση 0.4.7** στα τρία σημεία + συγχρονισμός του vendored
      `desktop/backend/etimologio/`. `pg_smoke` **42/42**.
- [x] **`DEPLOY.md §11`** — βήμα-βήμα live δοκιμή σύνδεσης γραφείου ↔ server.
- [ ] **Δεν έγιναν** (εκτός αιτήματος): αμφίδρομος συγχρονισμός, και ενημέρωση
      εγχειριδίου/ξενάγησης για τα νέα κουμπιά.
- ⚠️ **Λάθος της συνεδρίας:** ένα `cp $REPO/*.php` σε φάκελο δοκιμών πήρε μαζί και
      το πραγματικό `config.php`, και ένα poll της ανοιχτής καρτέλας έτρεξε το
      `crypto_backfill_plaintext()` πάνω στην **πραγματική** τοπική βάση (51 πεδία
      κρυπτογραφήθηκαν με νέο `.enckey`). Αντιστράφηκε πλήρως (52 πεδία ξανά
      καθαρά, η σημαία διαγράφηκε, αντίγραφο `local.sqlite.bak-*` δίπλα).
      **Κανόνας:** ποτέ `cp $REPO/*.php` σε φάκελο δοκιμών.

## Session F — 0.4.7 (β' γύρος): οι ρυθμίσεις στο σπίτι τους, αμφίδρομος συγχρονισμός

- [x] **Ό,τι είναι e‑Τιμολόγιο, ρυθμίζεται μέσα στο e‑Τιμολόγιο.** Ο Πίνακας
      ελέγχου του Downloader έχασε τα δύο κουτιά που δεν του ανήκαν: «πού
      αποθηκεύονται τα δεδομένα» (σύνδεση σε server) και «Αντίγραφα ασφαλείας».
      Μαζί έφυγαν οι βοηθοί τους (`_decode_key`, `_verify_access_key`,
      `etim_backend_changed`, `_switch_etim_backend`).
- [x] **Νέα κάρτα «💾 Αντίγραφα ασφαλείας»** στις Ρυθμίσεις του e‑Τιμολόγιο:
      zip με βάση **και** κλειδί κρυπτογράφησης (+ WAL, service.json), κρατά τα
      14 νεότερα, με λήψη του τελευταίου μέσα από την εφαρμογή. Χτίζεται με το
      `zipwriter.php` (zlib) — η φορητή PHP δεν έχει `ZipArchive`, και αντίγραφο
      που δουλεύει «μόνο σε πλήρη PHP» δεν είναι αντίγραφο.
- [x] **Αμφίδρομος συγχρονισμός** — `?api=sync` στον server, `?auth=link_sync`
      τοπικά, **ίδια** `sync_apply()` και στις δύο άκρες (καμία πλευρά δεν είναι
      «η σωστή»). Πληρωμές: ταυτότητα από το περιεχόμενο → καμία διπλοεγγραφή.
      Καρτέλες: κερδίζει η νεότερη, και **ίδιο περιεχόμενο = καμία εγγραφή** (
      χωρίς αυτόν τον έλεγχο οι δύο πλευρές ξαναέγραφαν αιώνια η μία την άλλη).
      Διαγραφές δεν ταξιδεύουν — γραμμένο ρητά στο `DEPLOY.md`.
  - Ταυτοποίηση μηχανής με το **ίδιο** κλειδί πρόσβασης (`auth_access_key_login()`,
      Bearer). 🐞 Ο server αναγνωρίζει το **μυστικό**, όχι ολόκληρο το `etim1_…`
      token — το πρώτο τρέξιμο έσκαγε με «Απαιτείται σύνδεση».
  - **Επαληθεύτηκε με δύο instances:** πληρωμή του γραφείου → βρέθηκε στον server·
      πληρωμή που γράφτηκε στο web → κατέβηκε στο γραφείο· τρίτος συγχρονισμός
      `sent 0 / recv 0` και **2 πληρωμές σε κάθε πλευρά**.
- [x] **`serverlink.php`** — η σύνδεση/συγχρονισμός/αντίγραφα βγήκαν από το
      `etimologio.php` σε δικό τους αρχείο, ώστε να δοκιμάζονται χωρίς να
      σηκώνεται η εφαρμογή. Το `pg_smoke.php` απέκτησε ενότητα **«6β. Κλειδί
      σύνδεσης με server»** (46 έλεγχοι πλέον, όλοι περνούν) και το αντίστοιχο
      python test αποσύρθηκε με δείκτη στο νέο του σπίτι.
- [x] **Έξοδος κινδύνου στο κέλυφος**: σε λειτουργία server που δεν απαντά, η
      οθόνη σφάλματος δίνει «Επιστροφή σε τοπικά δεδομένα». Χωρίς αυτό, η
      αφαίρεση του κουμπιού από τον Πίνακα ελέγχου θα κλείδωνε την εγκατάσταση
      έξω από τα ίδια της τα δεδομένα.
- [x] **Εγχειρίδιο & ξενάγηση**: τέσσερις νέες ενότητες στο εγχειρίδιο του web
      (11ζ σύνδεση, 11η αμφίδρομος συγχρονισμός, 11θ αντίγραφα, 11ι ειδοποιήσεις
      ΑΑΔΕ), δύο νέα βήματα ξενάγησης, και οι ίδιες ενότητες στο εγχειρίδιο της
      εφαρμογής υπολογιστή (`help.py`).
- [x] **`DEPLOY.md §11`** ξαναγράφτηκε: ένας δρόμος σύνδεσης (Ρυθμίσεις), πίνακας
      με το τι ταξιδεύει και τι όχι στον συγχρονισμό.

### Κυκλοφορία 0.4.7

- [x] **Installer**: `TimologioDownloader-0.4.7-setup.exe` — **442,4 MB**, χτίστηκε
      με `installer/build.ps1`. Το Inno Setup 6 ήταν εγκατεστημένο **ανά χρήστη**
      (`%LOCALAPPDATA%\Programs`), γι' αυτό ένας πρόχειρος έλεγχος μόνο στο
      `Program Files` το είχε βγάλει «απόν».
      Επαληθεύτηκε μέσα στο παγωμένο bundle: `backend/etimologio/serverlink.php`
      υπάρχει, και η φορητή PHP φορτώνει **sodium** + pdo_sqlite + pdo_pgsql +
      curl + mbstring.
- [x] **Και οι δύο γραμμές στην 0.4.7**: `planning/etimologio-merge` πήρε όλη την
      εφαρμογή (χωρίς `DEPLOY.md`, `CLOUDFLARED.md`, `docker-compose.yml`,
      `.env.example` — μένουν στο branch του server). Οι δύο κλάδοι διαφέρουν
      πλέον **μόνο** σε αυτά τα 4 αρχεία.
- [x] **Ενσωματώθηκαν 3 commits του χρήστη** που είχαν πάει στο remote όσο
      δούλευα (`libsqlite3-dev` για το `pdo_sqlite`, μορφοποίηση Dockerfile) —
      rebase, όχι force-push· η διόρθωση πέρασε και στην κύρια γραμμή.
- [x] **Tag `v0.4.7`** μετακινήθηκε στο commit που όντως χτίστηκε.
- [x] **Release** στο repo του bridge, με τον installer συνημμένο. **Δεν** μπήκε
      στο `MyData-Invoice-Downloader`, δηλαδή **δεν** ενεργοποιεί αυτόματη
      ενημέρωση στις εγκατεστημένες εφαρμογές — απόφαση του χρήστη, ώστε να
      δοκιμάσει πρώτος.

### Θύρα 8090 + έλεγχος ενημερώσεων

- [x] **Η εφαρμογή μετακόμισε στην 8090.** Στη 8080 απαντά **το ίδιο το Coolify**
      σε αυτόν τον server: ένα deploy εκεί είτε δεν δένει τη θύρα είτε — χειρότερα
      — βγάζει τον πίνακα του Coolify στο internet μέσω του tunnel. Ο αριθμός
      άλλαξε **παντού μαζί**: `Listen`/`VirtualHost`/`EXPOSE`/healthcheck του
      `Dockerfile`, `APP_BASE_URL` του `entrypoint.sh` (το χτυπά ο
      χρονοπρογραμματιστής μέσα στον container), `docker-compose.yml`, `DEPLOY.md`,
      `CLOUDFLARED.md`.
- [x] **Hostname**: `etimologiopro.scanmydata.gr` σε `CLOUDFLARED.md`, `DEPLOY.md`,
      `.env.example` — όχι πια placeholder.
- [x] **Ο έλεγχος ενημερώσεων ρωτά πλέον ΚΑΙ ΤΑ ΔΥΟ repos** και κρατά τη νεότερη
      κυκλοφορία (`updates.OWNER_REPOS`). Το πρόβλημα ήταν σιωπηλό και κλειστό:
      το `updates.py` ρωτούσε **μόνο** το `MyData-Invoice-Downloader`, που έχει
      ακόμη **v0.2.30**· μια εγκατάσταση 0.4.7 έπαιρνε 0.2.30 < 0.4.7 και έλεγε
      «είστε ενημερωμένοι» — καμία μελλοντική έκδοση δεν θα έφτανε ποτέ.
      Ζωντανός έλεγχος: βρίσκει `0.4.7` με τον installer (463 MB) από το bridge,
      επιβιώνει όταν ένα repo δίνει 404, και **σκάει** όταν πέφτουν και τα δύο
      (ποτέ ψεύτικο «ενημερωμένος»). 3 νέα tests· σουίτα **479 passed / 13 skipped**.
- [x] ⚠️ **Το venv του `desktop/` δείχνει σε ΑΛΛΟ checkout**
      (`.venv/Lib/site-packages/timologio_downloader.pth` →
      `C:\Users\tony-pc\Documents\timologio-downloader\src`). Χωρίς
      `PYTHONPATH=<αυτό το repo>/desktop/src` τα tests τρέχουν πάνω στο **παλιό**
      δέντρο και δείχνουν πράσινα για κώδικα που δεν άλλαξε.

### Κυκλοφορία 0.4.8 — τι πραγματικά έφταιγε

- [x] **Το «δεν πατιέται τίποτα» και το «χάθηκαν τα δεδομένα» ήταν ΤΟ ΙΔΙΟ σφάλμα.**
      Δύο ελληνικές προστακτικές με απόστροφο μέσα σε μονά εισαγωγικά της JS
      («στείλ' το», «Σβήσ' την») έκλειναν το string και έριχναν ΟΛΟ το inline
      script. Καμία `onclick`, κανένα `loadCustomers()`, κενός επιλογέας
      εταιρείας. Επαληθεύτηκε ότι τα δεδομένα ήταν πάντα εκεί: `local.sqlite`
      2 εταιρείες / 2 χρήστες / πληρωμές, `timologio.db` 155 πελάτες / 94
      παραστατικά — ίδια με το αντίγραφο της 20ής Αυγούστου.
- [x] **`tools/js_check.js`**: parser πάνω στα inline `<script>` των σελίδων PHP.
      Δοκιμάστηκε ανάποδα (με την απόστροφο πίσω → exit 1). Ο `php -l` δεν
      βλέπει τέτοιο σφάλμα και ο έλεγχος υγείας λέει «ok» — μόνο η κονσόλα ξέρει.
- [x] **Άντληση επωνυμίας από ΑΦΜ**: το `?afm=` δεν επιστρέφει ποτέ στοιχεία
      (δες [[aade-endpoint-quirks]]). Το δεύτερο βήμα (`list_customers&cust_vat`)
      μπήκε σε κοινό `afmDetails()` για έκδοση/δελτίο/καρτέλα/νέο πελάτη.
- [x] **Κινητό**: συρτάρι με σήμα αριστερά του ☰· κεφαλίδα 221px → 107px.
- [x] **`staff_invite_client`**: ο λογιστής προσκαλεί πελάτη σε εταιρεία που
      διαχειρίζεται. Ρόλος πάντα `business`, έλεγχος ανάθεσης στον server.
- [x] **Εικονίδιο ScanmyData** σε λευκή πλακέτα, ίδιο σε setup.exe και γραμμή
      εργασιών. Το κόψιμο του σήματος βρίσκει μόνο του το κενό πριν το λεκτικό.
- [x] **Συνεδρίες στο volume**: κάθε deploy τις έσβηνε και πετούσε έξω όποιον
      δούλευε.
- [x] Installer **442,4 MB**, σουίτα **479 passed / 13 skipped**.

**Εκκρεμεί:** το παλιό repo `MyData-Invoice-Downloader` έχει σταματήσει στην
**v0.2.30** (12 Αυγ) με κώδικα ΜΟΝΟ του Downloader. Μια κυκλοφορία εκεί με
νούμερο μεγαλύτερο από της γέφυρας θα «αναβάθμιζε» τους πάντες σε προϊόν χωρίς
e-Τιμολόγιο. Από την 0.4.8 ο έλεγχος κοιτά και τα δύο repos και κρατά τη
νεότερη έκδοση.


### Κυκλοφορία 0.4.10 — φωνή, ξενάγηση, και τα σήματα που δεν έφτασαν ποτέ

- [x] **Ο φωνητικός έλεγχος «δεν λειτουργούσε στο web» επειδή σιωπούσε.** Ο
      container ΔΕΝ κουβαλά piper/whisper (`voice_caps` → `stt:false`), οπότε
      αναλαμβάνει ο browser — και εκεί κάθε `onerror` απλώς έσβηνε το κόκκινο
      λαμπάκι. Ο χρήστης πατούσε το μικρόφωνο και δεν γινόταν τίποτα.
      Επαληθεύτηκε ζωντανά: `error:not-allowed`, καμία ένδειξη.
- [x] **Σειρά μηχανών ανά κόσμο** (`cbPreferBrowserVoice`): στον browser
      προηγείται το Web Speech API (είναι ήδη εκεί, δεν στέλνει ήχο στον server
      μας, δουλεύει και σε εγκατάσταση χωρίς μηχανές)· στην εφαρμογή υπολογιστή
      προηγείται η δική μας (το `webkitSpeechRecognition` ΠΑΓΩΝΕΙ το
      QtWebEngine, και τα Windows δεν έχουν ελληνική φωνή). Η δεύτερη μένει
      πάντα εφεδρεία: σφάλμα *της υπηρεσίας* (`network`) παραδίδει τη σκυτάλη
      στη δική μας, ενώ `not-allowed`/`audio-capture` απλώς εξηγείται (θα
      σκόνταφτε και το whisper στο ίδιο μικρόφωνο).
- [x] **Ο βοηθός σώπαινε σε browser που ΕΙΧΕ τη φωνή.** Οι φωνές φορτώνουν
      ασύγχρονα· η πρώτη ματιά έβρισκε άδεια λίστα και το `CB_VOICE_WARNED`
      κλείδωνε το «δεν υπάρχει ελληνική φωνή» ΜΙΑ ΦΟΡΑ ΚΑΙ ΓΙΑ ΠΑΝΤΑ.
- [x] **Ξενάγηση:** τα κείμενα είναι γραμμένα με `<b>`/`<br>` και βγαίνανε
      αυτούσια (`textContent` → `innerHTML`)· η κύλιση ήταν `smooth`, οπότε το
      `getBoundingClientRect` μετριόταν ΠΡΙΝ φτάσει το στοιχείο και ο δείκτης
      κάθονταν αλλού· και το κουτί τοποθετούνταν με σταθερές 340×190 ενώ το
      βήμα του βοηθού είναι 381px. Τώρα μετριέται πραγματικά και κλειδώνεται
      μέσα στο viewport — 0 βήματα εκτός ορίων σε 1280×720, 1000×420, 375×812
      (ήταν 4). Το βήμα «Διαχείριση» έφυγε (μόνο ο διαχειριστής το βλέπει) και
      όσα βήματα δεν έχουν στόχο φιλτράρονται μόνα τους.
- [x] **Τα νέα λογότυπα δεν έφταιγε ο κώδικας.** Το live σέρβιρε ακόμη το παλιό
      εικονίδιο (22.103 bytes, `cf-cache-status: HIT`, `Age: 52629`): σταθερό
      URL + `max-age=86400` + Cloudflare = μια μέρα καθυστέρηση, και αόριστα σε
      κάθε browser που το είχε ήδη. Νέα `asset_url()` βάζει σφραγίδα `?v=<mtime>`
      σε εικονίδια/manifest/λογότυπα. Τα δύο σήματα μπήκαν στο web
      (`assets/brand/logo-{etimologio,downloader}.png`), η οθόνη σύνδεσης
      απέκτησε επιτέλους λογότυπο και λωρίδα «σουίτας».
- [x] **Ρυθμίσεις υπολογιστή μέσα στη σελίδα**: γέφυρα **QWebChannel**
      (`window.etimHost`) → «Εκκίνηση στο tray» + «Έλεγχος για ενημερώσεις» στις
      Ρυθμίσεις του e-Τιμολόγιο, με τους ΙΔΙΟΥΣ χειριστές του πίνακα ελέγχου
      (ένας διακόπτης, δύο οθόνες). Το `qwebchannel.js` έρχεται από πόρο του
      QtWebEngine — τίποτα να ξεχαστεί στο packaging. ⚠️ Τα user scripts ΔΕΝ
      τρέχουν σε `data:` URL: ο έλεγχος έδειχνε ψεύτικη αποτυχία.
- [x] **Η γραμμή κατάστασης μιλούσε για εφαρμογή που δεν είχες διαλέξει.** Το
      `_chrome_for` την έσβηνε, αλλά η λίστα πελατών φορτώνει ΜΕΤΑ και ξανάγραφε
      από πάνω. Νέο `_set_counts_status()`.
- [x] **Μετονομασία σε «Timologio Downloader»** (μενού, κάρτα αρχικής οθόνης,
      τίτλος παραθύρου, tray) και **έκδοση** στην αρχική οθόνη με κανονικό χρώμα
      κειμένου αντί για «muted» στα 13px.
- [x] **Εικονίδιο συντόμευσης**: το exe φορούσε ήδη το σήμα ScanmyData, αλλά τα
      Windows κρατούν επίμονη μνήμη εικονιδίων ανά συντόμευση — μετά από
      αναβάθμιση (ίδιο AppId, ίδιο όνομα exe) έδειχνε το παλιό. Ρητό
      `IconFilename` σε νέα διαδρομή (`{app}\ScanmyDataSuite.ico`) τη σπάει.
- [x] Παράπλευρο: το `Launcher.restyle()` ρωτούσε ιδιότητα `etim` που δεν
      οριζόταν ποτέ — μετά από κάθε αλλαγή θέματος **και οι δύο** κάρτες
      έπαιρναν το σήμα του Downloader.
- [x] 14 νέα tests (`test_desktop_prefs_bridge.py`, `test_web_tour_and_voice.py`)·
      σουίτα **493 passed / 13 skipped**.
