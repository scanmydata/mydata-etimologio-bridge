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

### Κυκλοφορία 0.4.11 — ο φάκελος που «άδειαζε», και οι ρυθμίσεις που χώρεσαν

- [x] ⚠️ **Η ΑΥΤΟΜΑΤΗ ΕΝΗΜΕΡΩΣΗ ΞΕΓΡΑΦΕ ΤΟΝ ΦΑΚΕΛΟ ΔΕΔΟΜΕΝΩΝ.** Το
      `{param:DATADIR|}` του Inno **κόβει την τιμή στο πρώτο κενό**. Στο log του
      ίδιου του installer φαίνεται να φτάνει ολόκληρο το
      `/DATADIR="C:\…\Παραστατικά myDATA"`, αλλά στο μητρώο γραφόταν
      `C:\…\Παραστατικά`. Η επόμενη εκκίνηση άνοιγε ΚΑΙΝΟΥΡΙΑ ΑΔΕΙΑ βάση — και
      μαζί της άδειαζε και το e-Τιμολόγιο, που ζει σε υποφάκελο του ίδιου
      φακέλου. Επαληθεύτηκε στο πραγματικό μηχάνημα: μητρώο
      `…\Παραστατικά` (94 KB, 0 πελάτες) ενώ τα δεδομένα κάθονταν στο
      `…\Παραστατικά myDATA` (3,2 MB). Το `/DIR` και το `/LOG` δεν επηρεάζονται —
      τα διαβάζει ο ίδιος ο Inno, όχι το `{param:}`.
      Διόρθωση: `CmdLineParam()` πάνω σε `ParamStr` (parser των Windows, σέβεται
      τα εισαγωγικά). Καμία παράμετρος δεν διαβάζεται πια με `{param:}`.
- [x] **Επισκευή για όποιον χάλασε ήδη**: το `config.recover_data_dir()` βλέπει
      ρυθμισμένο φάκελο χωρίς πελάτες, βρίσκει τον αδελφό που ξεκινά με το ίδιο
      όνομα (το κόψιμο γίνεται πάντα σε κενό), τον υιοθετεί και **διορθώνει το
      μητρώο**. Δεν μετακινεί και δεν σβήνει τίποτα. Καινούρια εγκατάσταση δεν
      το αγγίζει.
- [x] **e-Τιμολόγιο: επαναφορά από αντίγραφο** (`etimologio/backup.py`). Γράφει
      πίσω βάση **και** κλειδί (χωριστά δεν λένε τίποτα), κρατά «pre-restore»,
      και **σβήνει το παλιό WAL** — αλλιώς η SQLite το ξαναέπαιζε πάνω στη νέα
      βάση. Το `service.json` ΔΕΝ επαναφέρεται: κρατά τα κλειδιά αυτής της
      εγκατάστασης, και ένα ξένο θα άφηνε το κέλυφος με token που ο server δεν
      αναγνωρίζει. Ζει στην πλευρά του Qt γιατί ο server πρέπει να **σταματήσει**
      πρώτα — τη βάση που αντικαθίσταται τη χρησιμοποιεί ο ίδιος.
- [x] **Άδεια εγκατάσταση + αντίγραφα στον φάκελο ⇒ φορτώνονται μόνα τους** στην
      εκκίνηση (`adopt_existing`). Ποτέ πάνω από υπάρχουσα δουλειά: ο έλεγχος
      είναι «καμία εταιρεία», όχι «κανένας χρήστης» (τον χρήστη εργασίας τον
      φτιάχνει μόνο του το κέλυφος σε κάθε εκκίνηση).
- [x] **Οι Ρυθμίσεις σε πτυσσόμενες ενότητες** (local + web, ένα αρχείο): 8
      panel, 2215px → 591px κλειστά. Γίνεται με κώδικα και όχι με markup, ώστε
      κάθε νέο panel να γίνεται ενότητα χωρίς να το θυμηθεί κανείς. Η ξενάγηση
      ανοίγει μόνη της την ενότητα του στόχου (`sectReveal`) — κλειστή ενότητα
      σημαίνει στοιχείο μηδενικών διαστάσεων, δηλαδή δείκτη στη γωνία.
- [x] **Χρονοπρογραμματισμός λήψης** (`schedule.py`, καθαρό από Qt): ώρα, ημέρες,
      «όλοι με κλειδί» ή «μόνο οι επιλεγμένοι». Οι επιλεγμένοι **παγώνουν** τη
      στιγμή της αποθήκευσης, αλλιώς ένα κλικ στη λίστα άλλαζε σιωπηλά τι
      κατεβαίνει αύριο στις επτά. Το ραντεβού ελέγχεται ως *στιγμή της ημέρας*
      και όχι ως «πέρασαν 24 ώρες»: υπολογιστής κλειστός στις 07:00 και ανοιχτός
      στις 11:00 κατεβάζει, μία φορά. Τρέχει ΜΕΣΑ στην εφαρμογή (χρειάζεται βάση,
      κλειδί και browser· δεύτερο headless στιγμιότυπο θα κλείδωνε την ίδια βάση).
- [x] **Δοκιμή κωδικών myDATA στη δημιουργία πελάτη**: `RequestMyExpenses` για
      τον τρέχοντα μήνα (REST API v2.0.1 §4.2.9) — σύνολα, όχι κατέβασμα. Το
      «Api myData» και το «Subscription key e-timologio» έχουν την ΙΔΙΑ μορφή
      (32 hex), οπότε ο έλεγχος μορφής τα δεχόταν και τα δύο και το λάθος
      φαινόταν ώρες αργότερα μέσα σε μαζική λήψη. Ζωντανά επαληθευμένο: λάθος
      κλειδί → 403 → ελληνικό μήνυμα με οδηγία. **Μηδέν εγγραφές δεν είναι
      αποτυχία** (μπορεί να μην έχει έξοδα ο μήνας).
- [x] Εγχειρίδια (Downloader §2 και §9β, e-Τιμολόγιο §12) και **και οι δύο**
      ξεναγήσεις ενημερώθηκαν.
- [x] Από την οθόνη σύνδεσης του web έφυγαν τα δύο λογότυπα της σουίτας.
- [x] 27 νέα tests· σουίτα **522 passed / 13 skipped**.

### Κυκλοφορία 0.4.13 — δύο συναρτήσεις με το ίδιο όνομα, και μια γραμμή τίτλου που δεν άκουγε

- [x] **Το popup «Στήλες»/φίλτρου ήταν ΧΩΡΙΣ styling.** Κάθε κανόνας του
      `#colFilterPop` είχε τον επιλογέα του γραμμένο **δύο φορές**
      (`#colFilterPop .cf-item .cf-item{…}` = «cf-item μέσα σε cf-item»), οπότε
      δεν ταίριαζε κανένας: οι επιλογές έπεφταν η μία δίπλα στην άλλη σαν
      τρεχούμενο κείμενο. Καμία προειδοποίηση πουθενά — η CSS αγνοεί σιωπηλά ό,τι
      δεν ταιριάζει. Μαζί: το βελάκι ταξινόμησης έφευγε από τις ετικέτες
      («Επωνυμία ▲» → «Επωνυμία», και στον τίτλο του φίλτρου, που υπολογίζεται
      πια τη στιγμή του κλικ), η ανώνυμη στήλη ενεργειών δεν εμφανίζεται ως
      «(χωρίς τίτλο)», και οι μακριές τιμές κόβονται με «…» μέσα σε `<span>`
      (πάνω σε flex container το `text-overflow` δεν πιάνει ποτέ — εκεί ήταν
      γραμμένο).
- [x] **Έξω η «🚫 Απόκρυψη»** από τον επιλογέα φίλτρων: η ίδια ενέργεια ζει στο
      «⚙ Στήλες», με όλες τις στήλες μπροστά σου και με τρόπο να τις ξαναφέρεις.
- [x] **`zip_read()` ΥΠΑΡΧΕΙ ΗΔΗ στην PHP** (ext/zip, το παλιό procedural API
      δίπλα στα `zip_open`/`zip_entry_read`). Η επέκταση είναι φορτωμένη για τα
      .xlsx των τραπεζών, άρα η δική μας δήλωση θα έριχνε **ολόκληρη την
      εφαρμογή** με «Cannot redeclare» — στον server, όχι στη φορητή PHP της
      ανάπτυξης, όπου η επέκταση λείπει. Μετονομάστηκε σε `zip_unpack()`.
      Μαζί: τα includes του `etimologio.php` έγιναν `require_once` (σκέτο
      `require` δίπλα σε `require_once` για το ίδιο αρχείο είναι ωρολογιακή
      βόμβα σειράς φόρτωσης).
- [x] **Επαναφορά του server από αντίγραφο** — τοπικό ή από το Drive, μέσα από
      την κάρτα του διαχειριστή. Σειρά βημάτων: αντίγραφο του **τώρα**
      («pre-restore») → αποκρυπτογράφηση → άνοιγμα → **έλεγχος ότι μέσα υπάρχει
      βάση της σωστής μηχανής** → `.enckey` → βάση. Ζητά να **γραφτεί** η λέξη
      ΕΠΑΝΑΦΟΡΑ (και στη σελίδα και στο endpoint): ένα confirm() πατιέται
      αντανακλαστικά και αυτό δεν ξεγίνεται. Ζωντανά επαληθευμένο σε
      SQLite: εγγραφή μετά το αντίγραφο εξαφανίστηκε, χαλασμένο `.enckey`
      επέστρεψε ολόκληρο, κανένα `-wal`/`-shm` δεν επέζησε.
- [x] `zip_unpack()` (καθαρή PHP, χωρίς ZipArchive όπως και ο writer) **ελέγχει
      το CRC κάθε εγγραφής**: ένα αντίγραφο που ξεπακετάρει σκουπίδια χωρίς να
      διαμαρτυρηθεί είναι χειρότερο από ένα που αρνείται να ανοίξει.
      `gdrive_download()` χωριστά από το `gdrive_call`, που περνά τα πάντα από
      `json_decode` — ένα κρυπτογραφημένο αντίγραφο δεν είναι JSON.
- [x] **Η επωνυμία από ΑΦΜ δεν ερχόταν ΠΟΤΕ στο «Νέα εταιρεία».** Το
      `taxis_name` περνά μέσα από συνεδρία e-timologio, δηλαδή θέλει εταιρεία
      **ήδη επιλεγμένη** με έγκυρα διαπιστευτήρια — ακριβώς αυτό που δεν υπάρχει
      όταν καταχωρείς την πρώτη σου. Η αποτυχία καταπινόταν ως «δεν βρέθηκε».
      Μπήκε `viesName()` (VIES REST, δημόσιο, χωρίς σύνδεση) ως δεύτερο
      σκαλοπάτι στο `nameForVat` και **τρίτο** στο `customerInfo`, με οθόνη
      αναμονής. Ζωντανά: `802576637` → «ΤΟ ΒΑΨΙΜΟ Ε Ε» (το `||ΤΟ ΒΑΨΙΜΟ` κόβεται).
- [x] **«🔑 Δοκιμή κωδικών» στο παράθυρο εταιρείας**, με **δύο** αποτελέσματα:
      myDATA REST (`RequestMyExpenses`, τρέχων μήνας) **και** σύνδεση
      e-timologio. Ένα σκέτο «ΟΚ» θα έκρυβε ακριβώς την περίπτωση που γεννά τα
      περισσότερα λάθη — τα δύο κλειδιά έχουν την ίδια μορφή. Δικό της cookie
      jar: μια αποτυχημένη δοκιμή δεν βγάζει τον χρήστη έξω. Ζωντανά
      επαληθευμένο με ψεύτικο κλειδί: 403 + 
      απόρριψη e-timologio, με ελληνική οδηγία για το καθένα.
- [x] **Η έκδοση ήταν γραμμένη στο χρώμα των διαχωριστικών** (`p.line` = #2b3b54
      πάνω σε #0a111e), στα 10px — φτιαγμένο για να μην το βλέπεις. Τώρα
      `p.muted` στα 12px, με hover, και **κλικ = «Έλεγχος για ενημερώσεις»**:
      αρχική οθόνη, πλαϊνό μενού και Ρυθμίσεις καλούν την **ίδια** συνάρτηση
      (δεύτερη θα σήμαινε δεύτερο νήμα και δύο απαντήσεις στην ίδια ερώτηση).
- [x] **Η γραμμή τίτλου ακολουθεί την ΠΑΛΕΤΑ, όχι απλώς «σκούρο».** Η σκούρη
      λειτουργία των Windows δίνει το `#202020` του συστήματος — πάνω από το
      ναυτικό μπλε του μενού διαβάζεται σαν ξένο κομμάτι κολλημένο στην κορυφή.
      Μπήκαν τα `DWMWA_CAPTION_COLOR`/`TEXT_COLOR`/`BORDER_COLOR` (34/35/36,
      Windows 11 22000+· σε παλιότερα αγνοούνται και μένει η σκούρη λειτουργία).
      Η αλλαγή θέματος ξαναβάφει **όλα** τα ανοιχτά παράθυρα, όχι μόνο το κύριο.
- [x] **Το εγχειρίδιο του web σε διάταξη Downloader.** Τύπωνε τα `<b>` του
      κειμένου **ως κείμενο** («\<b>έτσι\</b>»), έβγαζε κουκκίδες και παραγράφους
      ολόιδιες σε γκρι, και δεν είχε ούτε σήμα ούτε αρίθμηση σελίδων. Τώρα:
      εξώφυλλο με λογότυπο και έκδοση, κεφαλίδες στο χρώμα της εφαρμογής,
      κουκκίδες με κρεμαστή εσοχή, έντονα με πραγματική γραμματοσειρά (και
      χρώμα ως εφεδρεία αν δεν κατέβει), υποσέλιδο με «σελ. ν/Ν».
- [x] **§3δ στο `DEPLOY.md`: τι αλλάζει αν το repo γίνει private.** Το σοβαρό
      δεν είναι το Coolify: ο auto-updater ρωτά **ανώνυμα** το
      `api.github.com/…/releases/latest` και σε private repo παίρνει 404 —
      κάθε εγκατάσταση παύει σιωπηλά να βλέπει ενημερώσεις.
- [x] 30 νέα tests· σουίτα **552 passed / 13 skipped**.

### Κυκλοφορία 0.4.14 — ένα CSP που έκοβε σιωπηλά, και μια βάση που «χαλούσε» μετά από επιτυχία

- [x] **«Η βιβλιοθήκη PDF δεν φόρτωσε» — έφταιγε το δικό μας CSP.** Ο Apache
      στέλνει `script-src 'self'`, και το `jspdf` ερχόταν από **jsdelivr**: το
      `<script>` δεν εκτελούνταν ΠΟΤΕ στο web. Μαζί του έπεφταν όλες οι
      λειτουργίες PDF (εγχειρίδιο, καρτέλα, εξαγωγές) — και το `connect-src
      'self'` έκοβε επιπλέον τη γραμματοσειρά DejaVu. Δεν χαλαρώσαμε το CSP:
      τα τέσσερα αρχεία μπήκαν στο `assets/vendor/` (όπως ήδη το `pdf-lib`).
      Κερδίζει και η εφαρμογή υπολογιστή, που τρέχει χωρίς internet.
- [x] **Επαναφορά που έλεγε «επιτυχία» και άφηνε τη βάση malformed.** Το
      γράψιμο του αρχείου SQLite γινόταν με **ανοιχτή** σύνδεση: το αρχείο
      διαβαζόταν από νέα σύνδεση, αλλά η υπάρχουσα έσκαγε με «database disk
      image is malformed» — η επόμενη οθόνη μετά την «επιτυχή» επαναφορά έλεγε
      «η βάση δεν είναι διαθέσιμη». Το `localdb(true)` κλείνει πια τη σύνδεση
      πριν γραφτεί το αρχείο. Μετρημένο σε πραγματική επαναφορά, όχι θεωρητικό.
- [x] **Επαναφορά και από αρχείο του χρήστη** (`source=upload`, multipart): η
      περίπτωση «ο server ξαναστήθηκε από το μηδέν, η λίστα είναι άδεια, το
      μόνο αντίγραφο είναι στο laptop». Το πιο συχνό «δεν δουλεύει» εδώ δεν
      είναι σφάλμα κώδικα αλλά το `upload_max_filesize` — λέγεται ονομαστικά,
      με την τιμή του και με την εναλλακτική του Drive.
- [x] **Τα κουτιά του browser έγιναν παράθυρα της εφαρμογής.** 39 σημεία:
      `uiConfirm` / `uiPrompt` / `uiAlert`, με θέμα, τίτλο, κόκκινο κουμπί για
      τις επικίνδυνες, Escape = άκυρο, Enter = ΟΚ. Τα `confirm()` του browser
      δείχνουν τη διεύθυνση του site από πάνω, δεν παίρνουν θέμα, και μέσα στο
      QtWebEngine κάποια δεν εμφανίζονται **καθόλου** — η ερώτηση απαντιόταν
      «όχι» και η ενέργεια δεν γινόταν ποτέ, χωρίς κανένα μήνυμα.
- [x] **Η αναμονή δεν σκεπάζει την οθόνη**: κάρτα κάτω δεξιά (142×69) αντί για
      modal με σκούρο backdrop σε όλη την οθόνη — για μια αναζήτηση επωνυμίας
      δύο δευτερολέπτων. Όταν υπάρχει ανοιχτό `<dialog>` η κάρτα **μετακομίζει
      μέσα του**: το «top layer» των browsers δεν το φτάνει κανένα z-index.
- [x] **Ο επιλογέας στηλών έφευγε κάτω από την οθόνη.** `top = r.bottom + 4`
      χωρίς κανένα όριο. Το `popPlace()` μετρά και ανοίγει προς τα **πάνω** όταν
      δεν χωρά από κάτω· η αλλαγή μεγέθους κλείνει το ανοιχτό παράθυρο αντί να
      το αφήσει καρφωμένο εκτός οθόνης. Επαληθευμένο σε 900×520 και 1280×720.
- [x] **Το μπάνερ «🧮 Λογιστής — βλέπεις Ν εταιρείες» έφυγε.** Ο ρόλος γράφεται
      ήδη στην πάνω μπάρα και στον υπότιτλο. Έμεινε ΜΟΝΟ η προειδοποίηση
      «λογιστές χωρίς καμία ανατεθειμένη εταιρεία» — αυτό είναι πρόβλημα, όχι
      διακόσμηση, και η κορδέλα κρύβεται τελείως όταν δεν υπάρχει.
- [x] **Η Διαχείριση σε πτυσσόμενες ενότητες**, όπως οι Ρυθμίσεις (5 ενότητες).
- [x] **Το Ctrl+K ψάχνει τα πάντα**: ενότητες (ο κατάλογος είναι το ίδιο το
      μενού, ώστε μια νέα σελίδα να γίνεται αυτόματα αναζητήσιμη), ενότητες
      Ρυθμίσεων/Διαχείρισης ονομαστικά, είδη, σειρές, παραστατικά, και σκέτο
      ΜΑΡΚ που ανοίγει το PDF. Χωρίς τόνους, χωρίς κεφαλαία. Ο βοηθός την καλεί
      με «ψάξε …». **Παγίδα που πιάστηκε γράφοντάς το:** το `let SERIES=[]` στο
      top level ενός classic script ΔΕΝ γράφεται στο `window` — το
      `window.SERIES` είναι πάντα `undefined` και η αναζήτηση δεν θα έβρισκε
      ποτέ σειρά, χωρίς κανένα σφάλμα.
- [x] **Ο χρονοπρογραμματισμός έγινε σελίδα του μενού** (`schedule_page.py`).
      Ζούσε ως τρίτο κουτί στον Πίνακα ελέγχου και **δεν χωρούσε**: σε παράθυρο
      που δεν ήταν πλήρους οθόνης οι επεξηγήσεις κόβονταν, και το «μόνο οι
      επιλεγμένοι» δεν είχε πού να δείξει ΠΟΙΟΙ — η επιλογή γινόταν σιωπηλά από
      τα κουτάκια μιας άλλης οθόνης. Τώρα: λίστα με αναζήτηση, «Όλους/Κανέναν»
      **που αφορούν όσους φαίνονται** (με ενεργό φίλτρο, ένα «Όλους» που
      τσέκαρε και τους κρυμμένους θα ήταν παγίδα), και η επιλογή ανήκει στο
      πρόγραμμα.
- [x] **Ο Πίνακας ελέγχου κυλά** (`QScrollArea`): ό,τι περίσσευε πριν απλώς
      κοβόταν, χωρίς μπάρα και χωρίς τρόπο να το φτάσεις.
- [x] Ξεναγήσεις και εγχειρίδια (Downloader §9β, e-Τιμολόγιο §11ε/§11ια/§12β)
      ενημερώθηκαν· δύο νέα βήματα στην ξενάγηση του web. Η ξενάγηση δεν δείχνει
      σε κρυφό `<input type=file>` — `display:none` σημαίνει δείκτη στη γωνία.
      Και τα 23 βήματα μέσα στα όρια σε 900×520 και 1280×720.
- [x] Ο ελεγκτής JS (`tools/js_check.js`) μπερδευόταν από PHP μέσα σε
      `<script src=…>`: το `[^>]*` σταματούσε στο `>` του `?>`.
- [x] 25 νέα tests· σουίτα **577 passed / 13 skipped**.

### Κυκλοφορία 0.4.16 — οι ειδοποιήσεις: το ποσό και το ✕

- [x] **Ένα τιμολόγιο 12.100 € εμφανιζόταν ως 12,10 €.** Ο έλεγχος ΑΑΔΕ έγραφε
      το σύνολο με δικό του `str_replace([',',' '], ['.',''])` αντί για τον
      `parseMoney()` που υπάρχει ακριβώς γι' αυτό και χρησιμοποιείται σε τρία
      άλλα σημεία. Το «12.100,00» γινόταν «12.100.00», και η `(float)` της PHP
      **σταματά στη δεύτερη τελεία**: 12.1. Αναπαράχθηκε με τον παλιό κώδικα
      πριν αγγιχτεί τίποτα.
- [x] **Ο `parseMoney()` σκληρύνθηκε** για τη μία περίπτωση που ούτε εκείνος
      κάλυπτε: στρογγυλό ποσό **χωρίς κόμμα** («12.100»), όπου δεν υπάρχει
      υποδιαστολή να πει ότι η τελεία είναι χιλιάδες. Ο κανόνας: σκέτες τελείες
      που χωρίζουν ΑΚΡΙΒΩΣ τριάδες ψηφίων είναι χιλιάδες· το «1234.56» μένει
      αγγλική υποδιαστολή. Ο ίδιος κανόνας πέρασε και στον `parse_money()` της
      Python — δύο parsers που διαφωνούν είναι χειρότεροι από έναν λάθος. Και οι
      δύο συμφωνούν σε 13 περιπτώσεις.
- [x] **Όσες ειδοποιήσεις γράφτηκαν ήδη με λάθος ποσό διορθώνονται μόνες τους**
      (`notification_fix_amount`). Το `notification_exists` προσπερνά ό,τι
      υπάρχει, οπότε χωρίς αυτό το «12,10» θα έμενε στην καμπάνα για πάντα.
      Τρέχει στον επόμενο «🛰️ Έλεγχος ΑΑΔΕ» και **μόνο** για `source='aade'`:
      μια ειδοποίηση έκδοσης κρατά το ποσό που υπολόγισε η ίδια η εφαρμογή.
      Idempotent — δεύτερη κλήση δεν ξαναγράφει.
- [x] **«✕» σε κάθε ειδοποίηση.** Υπήρχε μόνο «διαβασμένη»: η λίστα κρατούσε για
      πάντα κάθε ΜΑΡΚ που πέρασε ποτέ. Το ✕ ζει ΜΕΣΑ στην πρώτη γραμμή, μετά το
      ποσό — ως `position:absolute` θα καθόταν πάνω του (το ποσό είναι
      `margin-left:auto` στην ίδια γραμμή). Μετρημένο: 11px από το δεξί όριο,
      13px από την κορυφή, καμία επικάλυψη.
- [x] Το ✕ κάνει `stopPropagation`: η γραμμή έχει δικό της `onclick`, και χωρίς
      αυτό θα έφευγαν δύο αιτήματα — το δεύτερο ζητώντας ανάγνωση σε ό,τι μόλις
      σβήστηκε. Επαληθευμένο ότι φεύγει **μόνο** `notif_delete`.
- [x] Το endpoint είναι **scoped** (`db_scope_clause`): χωρίς αυτό ένας λογιστής
      θα έσβηνε ειδοποίηση εταιρείας που δεν βλέπει, στέλνοντας ένα id στην τύχη.
      Επιστρέφει `deleted` (από `rowCount`) και το νέο πλήθος αδιάβαστων.
- [x] **Στόχος ξενάγησης με μηδενικές διαστάσεις δεν δείχνει πια στη γωνία.**
      «Υπάρχει στο DOM» δεν σημαίνει «φαίνεται»: μια κάρτα που δεν έχει φορτώσει
      ακόμη είναι `hidden`, και το δαχτυλίδι πήγαινε στο (0,0) δείχνοντας το
      τίποτα. Τώρα το βήμα δίνει κεντραρισμένο κείμενο χωρίς δείκτη.
- [x] Ξενάγηση και εγχειρίδια ενημερώθηκαν για το ✕ και για τη διόρθωση των ποσών.
- [x] 18 νέα tests· σουίτα **597 passed / 13 skipped**.

### Κυκλοφορία 0.4.17 — ο πίνακας που κόλλαγε, και οι ημερομηνίες

- [x] **Τα Παραστατικά άνοιγαν αργά και «κόλλαγαν».** Δύο μετρημένες αιτίες:
      ο πίνακας έφτιαχνε **δύο widgets ανά γραμμή** (κουμπί ανοίγματος μέσα σε
      container) και ξαναχτιζόταν **σε κάθε πλήκτρο** της αναζήτησης. Το κουμπί
      έγινε κελί με εικονίδιο (`_open_item` + `cellClicked`) και η αναζήτηση
      περιμένει 220ms. Με 8.000 παραστατικά: **4,45s → 1,89s** το άνοιγμα.
- [x] **«Ανανέωση» = έλεγχος του ΦΑΚΕΛΟΥ, όχι μόνο της βάσης** (`reconcile_downloads`).
      Το PDF γράφεται πρώτο και το `mark_downloaded` δεύτερο· μια διακοπή
      ανάμεσα άφηνε αρχείο στον δίσκο και «Αναμονή» στην οθόνη, για πάντα.
      Ασύμμετρο επίτηδες: ό,τι βρεθεί γίνεται «Ελήφθη», ό,τι λείπει **μόνο
      μετριέται** — μεταφερμένο PDF δεν είναι λόγος να ξανακατέβει ο μισός
      χρόνος του πελάτη. Τρέχει και σιωπηλά σε κάθε άνοιγμα της σελίδας.
      - Μία σάρωση φακέλου αντί για δύο stat ανά γραμμή, και φιλτράρισμα κατά
        φάκελο έτους/μήνα: 8.000 εκκρεμή σε **0,13s** αντί για 1,4s.
      - Ένα αρχείο δεν μπορεί να «ανήκει» σε δύο παραστατικά (`claimed`).
- [x] **Στήλη «Τύπος» με ονομασία** (`doctypes.py`, όλο το Παράρτημα myDATA):
      «2.1 Τιμολόγιο Παροχής Υπηρεσιών». Αναζήτηση και με τα δύο («2.1» ή
      «υπηρεσι»), ταξινόμηση κατά αριθμό (το σκέτο κείμενο έβαζε το 11.1 πριν
      το 2.1), φίλτρο στήλης με τις αναγνώσιμες τιμές. Το πλάτος φαρδαίνει μία
      φορά και μόνο αν δεν το έχει ρυθμίσει ο χρήστης.
- [x] **Ημερομηνίες, και στα δύο προγράμματα.** Εικονίδιο ημερολογίου αντί για
      βελάκι «κάτω», και ελεύθερη πληκτρολόγηση: «26/8/26» → 26/08/2026 (δεκτά
      και «26-8-2026», «26.08.26»). Άκυρη ημερομηνία κρατά την προηγούμενη τιμή.
      - Desktop: `GrDateEdit.validate/fixup/commit_typed`. Το `fixup` του Qt δεν
        καλείται αξιόπιστα (το QAbstractSpinBox κρατά cache και επαναφέρει
        σιωπηλά την παλιά τιμή) — γι' αυτό υπάρχει ρητό commit σε focus-out/Enter.
      - Web: `dtParse`/`dtMask`/`dtFix` + `addDatePickers` (native επιλογέας με
        `showPicker()`, χωρίς εξωτερική βιβλιοθήκη — το CSP δεν επιτρέπει CDN).
      - Τέσσερα πεδία του e-Τιμολόγιο ήταν σκέτα `QDateEdit`, χωρίς ημερολόγιο.
- [x] **Το dropdown της προεπισκόπησης εκτύπωσης έμοιαζε άδειο.** Το γενικό
      `padding: 6px 9px` έκοβε το κείμενο μέσα στη χαμηλή γραμμή εργαλείων: το
      «100,0%» φαινόταν κομμένο στη μέση. Επιβεβαιώθηκε με screenshot πριν/μετά.
      Μπήκε και tooltip — το πεδίο δεν είχε ετικέτα πουθενά.
- [x] **Γραμμή τίτλου σε ΚΑΘΕ παράθυρο** (`install_title_bar_painter`). Βαφόταν
      μόνο το κεντρικό· κάθε διάλογος άνοιγε με λευκή μπάρα πάνω από σκούρα
      εφαρμογή.
- [x] **Το panel του πελάτη ανοιγοκλείνει και αλλάζει μέγεθος.** Κουμπί
      «Λεπτομέρειες», και ελάχιστο πλάτος 240 αντί για 440 — ήταν **ίσο** με το
      κανονικό, δηλαδή το χώρισμα δεν σερνόταν καθόλου. Ο πίνακας πήρε ρητό
      (μικρό) ελάχιστο, αλλιώς το QSplitter σεβόταν το minimumSizeHint των δέκα
      στηλών. Πλάτος και κατάσταση θυμούνται· κλειστό μένει κλειστό.
- [x] **Η ξενάγηση του e-Τιμολόγιο δεν φώτιζε τίποτα στην εφαρμογή υπολογιστή.**
      Τα βήματα έδειχναν σε συνδέσμους του πλαϊνού μενού του web, που στην
      desktop είναι κρυμμένο: υπήρχαν στο DOM αλλά με μηδενικές διαστάσεις.
      Πλέον δείχνουν στον τίτλο της κάθε οθόνης, και τα δύο βήματα που μιλούν
      *για* το μενού φεύγουν εντελώς (`tourEmbedFix`, `TOUR_WEB_ONLY`).
- [x] Εγχειρίδια και ξενάγηση ενημερώθηκαν (Downloader και e-Τιμολόγιο, web+desktop).
- [x] 46 νέα tests· σουίτα **643 passed / 13 skipped**.

### Κυκλοφορία 0.4.18 — η άρθρωση, με κώδικα αντί για μοντέλο

- [x] **Ο κανονικοποιητής εκφώνησης μπήκε στο προϊόν.** Ζούσε ως *δεδομένα*
      μέσα στο `build_dataset.py` — δηλαδή ως παραδείγματα για ένα μοντέλο που
      δεν υπάρχει ακόμη. Τώρα τρέχει πραγματικά, πριν από τον Piper:
      - [`speakable.py`](../../desktop/src/timologio/etimologio/speakable.py) →
        `speech._speakable` (εφαρμογή υπολογιστή)
      - [`speakable.php`](../../speakable.php) → `?tts=1` του `etimologio.php`
        (server και webshell)
      - **0 MB, 0 ms.** Το μοντέλο θα κόστιζε 533 MB για τον ίδιο κανόνα.
- [x] Τι διορθώνει: ΑΦΜ/ΜΑΡΚ/τηλέφωνα ανά δύο ψηφία με παύση· ποσά («12.100,00 €»
      → «δώδεκα χιλιάδες εκατό ευρώ»)· ποσοστά· ημερομηνίες, και τις σύντομες
      («26/8/26»)· ώρες· κωδικούς τύπων («2.1» → «δύο τελεία ένα», ΟΧΙ «δύο
      κόμμα ένα»)· αριθμούς έκδοσης· IBAN· 60 συντομογραφίες (ΑΦΜ→«αφιμί»,
      ΦΠΑ→«φιπιά», VIES→«βίες»)· κεφαλαία→τονισμένα πεζά.
- [x] **Δύο υλοποιήσεις, ένα test που τις βάζει δίπλα-δίπλα.** Η φωνή καλείται
      και από τις δύο πλευρές· αν αποκλίνουν, η ίδια πρόταση ακούγεται αλλιώς
      στην εφαρμογή και αλλιώς στον browser και κανείς δεν το καταλαβαίνει.
      Το `test_speakable.py` τρέχει το πακεταρισμένο `php.exe` πάνω σε 30
      πραγματικές προτάσεις και απαιτεί **ίδιο κείμενο** — καθαρό.
- [x] **Το σύνολο εκπαίδευσης δανείζεται τον ίδιο μετατροπέα.** Το
      `build_dataset.py` δεν κρατά αντίγραφο: αν κρατούσε, τα δύο θα ξέφευγαν
      σιωπηλά και θα εκπαιδεύαμε μοντέλο να μιμείται κάτι διαφορετικό από αυτό
      που ακούει ο χρήστης.
- [x] Σφάλμα που βρέθηκε γράφοντάς το: το δεξί σύνορο του αριθμού απέκλειε κάθε
      τελεία, οπότε το «ΜΑΡΚ 400000123456789**.**» δεν αναγνωριζόταν **καθόλου**
      — μόνο και μόνο επειδή τελείωνε η πρόταση.

- [x] **Ο δρομολογητής: αγγλικά 26,7% → 100%, ελληνικά 85,8% → 100%.**
      Αγγλικά κλειδιά σε πλοήγηση/εντολές/ερωτήσεις/διαλόγους, και στις **δύο**
      υλοποιήσεις (`assistant.py` και `cbHandle` του `app.php`) — η δεύτερη
      είναι αυτή που τρέχει στην πράξη.
      - **Ηχητική ισοπέδωση** (`fold`): «εταιρεία» και «ετερεία» είναι ο ίδιος
        ήχος. Δεύτερο πέρασμα μόνο, ώστε να μη μπορεί να χαλάσει σωστή απάντηση.
      - Ασαφές ταίριασμα επωνυμίας (difflib, κατώφλι 0,82) για «Παπαδόποιλος».
      - Το όνομα δεν ρουφά πια το ποσό: «στην ΑΛΦΑ ΟΕ για 500» έψαχνε πελάτη
        «ΑΛΦΑ ΟΕ για 500».
      - Λέξη τιμολόγησης **χωρίς τίποτα να εκδοθεί** είναι όνομα οθόνης, όχι
        εντολή: «τα παραστατικά», «μαζική έκδοση», «cancel an invoice».
      - Ρητή **άρνηση** σε ό,τι ζητά οριστική έκδοση, αντί για «δεν κατάλαβα».
- [x] **Δύο μετρήσεις, γιατί το 100% είναι παραπλανητικό.** Το `eval_router.py`
      μετρά πάνω στα ίδια δεδομένα από τα οποία γράφτηκαν τα μοτίβα. Το νέο
      `eval_heldout.py` μετρά σε **52 φράσεις γραμμένες στο χέρι**, εκτός
      δεδομένων: **65,4% → 92,3%**. Και τα δύο τρέχουν στη σουίτα.
- [x] **Έρευνα μοντέλων** ([MODELS.md §3β](../../training/voice/MODELS.md)):
      το `jobautomation/OpenEuroLLM-Greek` είναι fine-tune **Gemma 3** τρίτου,
      8,1 GB, και η δήλωση «Apache 2.0» αντιφάσκει με τους Gemma Terms που
      ακολουθούν τα παράγωγα. Το ίδιο το OpenEuroLLM δεν έχει βγάλει μοντέλο
      για χρήση. Η ευρωπαϊκή εναλλακτική που **υπάρχει** είναι το
      `EuroLLM-1.7B-Instruct` (Apache 2.0, ελληνικά, 1,05 GB), δυνατό ακριβώς
      στη μετατροπή κειμένου — καταγράφηκε, δεν έγινε προεπιλογή.
- [x] Τρίτο σύνολο δεδομένων `faq_el.json` (211 παραδείγματα, 47 θέματα) και
      `check_datasets.py` που διαβάζει το συμβόλαιο **από τον κώδικα**.
- [x] 78 νέα tests· σουίτα **721 passed / 13 skipped**.
