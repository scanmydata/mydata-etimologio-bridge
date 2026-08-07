---
name: etimologio-downloader-merge
description: "Merging e-Τιμολόγιο Pro (PHP) into the Timologio Downloader (PySide6) as one product — branch, layout, run/test, phase status"
metadata: 
  node_type: memory
  type: project
  originSessionId: d99a09dd-f89c-4baf-bfc0-e7400408007d
  modified: 2026-08-07T22:38:09.698Z
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

**Status: Phase 0 done** (subtree, dual-dialect DB, client+service, launcher +
native login + offline auto-login → home). **Next:** Phase 1 native pages
(Έκδοση, Πελάτες/Καρτέλα) + "open client from Downloader"; then catalogs,
volume/money, platform (scheduler/notifications/settings/admin), then Docker/
Coolify VPS + thin-client + web. Bundling php.exe into PyInstaller (`datas`) is
still pending (packaging phase).
