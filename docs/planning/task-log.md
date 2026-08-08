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

- [~] **Phase 1 — core issuance (native Qt):**
  - [x] Client API: `customers`/`create_customer`/`search_invoices`/`payments` (+ `customers_cached`)
  - [x] Native **Πελάτες** page (search by name/ΑΦΜ, list, create customer, open card)
  - [x] Native **Καρτέλα** (issued invoices + local payments + computed balance, default year range)
  - [x] **"Open client from the Downloader"** — clients-table context action → `open_client_in_etimologio(vat)` → `EtimologioShell.focus_customer`
  - [x] 11 new unit tests (fake client + sync worker); full suite **319 passed**
  - [x] **Live retrieval verified** against real ΑΑΔΕ creds (VAT 802576637): 27 πελάτες + 15 τιμολόγια through the shared `EtimologioClient`→bridge→AADE path
  - [ ] Έκδοση (customer autocomplete, line editor, series/pay, taxes, draft/preview/issue) — next
- [ ] **Phase 2 — catalogs & lifecycle:** Είδη, Σειρές, Πρόχειρα, Ακύρωση/Πιστωτικά
- [ ] **Phase 3 — volume & money:** Μαζική έκδοση, Εισαγωγή πληρωμών (bank import), Στατιστικά
- [ ] **Phase 4 — platform:** Προγραμματισμός, Ειδοποιήσεις (bell + feed), Ρυθμίσεις (password, 2FA QR, per‑admin email prefs), Διαχείριση (roles + invitations)
- [ ] **Phase 5 — server + web:** Dockerfile + Coolify VPS (Postgres), desktop thin‑client mode, web clients via the public URL, one‑time local→server data migration
- [ ] **Packaging:** bundle a portable `php.exe` into PyInstaller `datas`; scheduler via Task Scheduler (standalone) / container cron (server).
  - ⚠️ **CA bundle required:** the bundled PHP must ship a `cacert.pem` with `curl.cainfo`/`openssl.cafile` set in its `php.ini`, or outbound TLS to `mydata.aade.gr` fails with OpenSSL error 60. Reuse certifi's bundle (same as the Downloader's Python side). Discovered during the Phase‑1 live test.
