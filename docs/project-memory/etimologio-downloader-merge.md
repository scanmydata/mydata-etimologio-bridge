---
name: etimologio-downloader-merge
description: "Merging e-Τιμολόγιο Pro (PHP) into the Timologio Downloader (PySide6) as one product — branch, layout, run/test, phase status"
metadata: 
  node_type: memory
  type: project
  originSessionId: d99a09dd-f89c-4baf-bfc0-e7400408007d
  modified: 2026-08-10T18:12:00.943Z
---

Merging the PHP e-Τιμολόγιο Pro into the PySide6 **Timologio Downloader**
(`C:\Users\tony-pc\Documents\timologio-downloader`, repo
`scanmydata/MyData-Invoice-Downloader`) so one app launches either tool and
switches anytime. Plan file: `C:\Users\tony-pc\.claude\plans\flickering-wishing-bird.md`.

**Architecture:** desktop keeps a native PySide6 UI; e-Τιμολόγιο's PHP stays the
backend (JSON API). Desktop runs **offline** (bundled `php -S` + SQLite under
`<data_dir>/etimologio/`) first, later **thin-client** to a central **VPS**
(Postgres, Docker via **Coolify**; clients use `app.php` on the web, accountant
via desktop; shared backend). Roles reused: master/editor = accountant (all
companies), business = client.

**Single-branch consolidation:** the whole downloader tree (with all Phase-0
work) is now **vendored into the bridge repo** on branch
`planning/etimologio-merge` under `desktop/` via `git subtree` (commit 0b946b2,
history preserved). That branch contains everything: standalone PHP at repo root
+ the unified desktop app at `desktop/` (its own bridge copy at
`desktop/backend/etimologio/`). The **downloader repo is left untouched** — its
`merge/etimologio-pro` branch stays local, not pushed. Re-sync desktop work with
`git subtree pull --prefix=desktop <downloader-path> merge/etimologio-pro`.

**Work is on branch `merge/etimologio-pro`** (NOT pushed; `main` stays stable).
- PHP vendored via `git subtree` at `backend/etimologio/` (upstream stays
  `scanmydata/mydata-etimologio-bridge`; pull with `git subtree pull`).
- `backend/etimologio/localdb.php` is now **dual-dialect** (`db_dialect()`,
  `db_now_sql()`, `db_insert()` + a DDL translator) selected by `DB_DSN`
  (env-overridable). SQLite verified; Postgres to verify on the VPS.
- Native side: `src/timologio/etimologio/` — `client.py` (requests over
  etimologio.php), `service.py` (PHP lifecycle/modes), `shell.py`
  (`EtimologioShell`: login/2FA/home). Wired into `MainWindow` (`_PAGES` +
  `_open_etimologio`, SideMenu "ΕΦΑΡΜΟΓΕΣ" section, `etimologio` icon).

**Run/test locally (no bundle):** set `TIMOLOGIO_ETIM_PHP` to the portable
`php.exe` ([[local-php-testing]]), `TIMOLOGIO_DATA_DIR` to a scratch dir,
`QT_QPA_PLATFORM=offscreen`, then `PYTHONPATH=src .venv/Scripts/python.exe -m
timologio.etimologio.service` (backend selftest) or drive `EtimologioShell`.
No `uv`/`docker` on PATH here — use `.venv/Scripts/python.exe`; Postgres testing
waits for the VPS. Full pytest: `... -m pytest -q` (308 passed at Phase 0).

**Status: Phase 0 + Phase 1 done.** Phase 1 (`etimologio/pages/`): native
**Πελάτες**, **Καρτέλα**, **Έκδοση** (multi-line editor, πρόχειρο/preview/issue),
client API (`customers`/`create_customer`/`search_invoices`/`payments`/`issue_invoice`),
native nav in `shell.py`, **"open client from Downloader"** (clients context menu
→ `MainWindow.open_client_in_etimologio` → `EtimologioShell.focus_customer`), 17
tests (325 total pass). **Live-verified** vs real ΑΑΔΕ (VAT 802576637):
retrieval (27 customers + 15 invoices) + a DRAFT issue whose UI totals matched
the backend exactly. Two gotchas found live: php.ini needs `curl.cainfo` CA
bundle ([[local-php-testing]]); line `rate` must be a FRACTION (0.24) on the
wire, not a percent. **Phase 2 done too:** native Είδη/Σειρές/Πρόχειρα (shared
`ListPage` base) + Ακύρωση/Πιστωτικό (credit_note by ΜΑΡΚ); client methods for
each; live-verified. **Phase 3 done:** Μαζική έκδοση, Πληρωμές (local ledger +
bank import), Στατιστικά — **with caching** (user requirement): `app_cache`
write-through on live calls, `?statistics&stats_cached=1` served BEFORE the AADE
login (2.45s → 0.01s live-measured), `?sync=statistics` refreshes all three
periods. DB-backed ⇒ identical for offline/thin-client/VPS. 339 tests.
**Next: Phase 4** — Προγραμματισμός, Ειδοποιήσεις, Ρυθμίσεις (2FA/prefs),
Διαχείριση; then
volume/money, platform (scheduler/notifications/settings/admin), then Docker/
Coolify VPS + thin-client + web. Bundling php.exe into PyInstaller (`datas`) is
still pending (packaging phase).
