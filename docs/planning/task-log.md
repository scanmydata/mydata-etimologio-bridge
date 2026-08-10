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
