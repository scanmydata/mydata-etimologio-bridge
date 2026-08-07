# Plan: Merge e‑Τιμολόγιο Pro into the Timologio Downloader as one unified product

## Context

Two separate scanmydata apps become one:

- **Timologio Downloader** — a mature **PySide6/Qt desktop app** (`Documents/timologio-downloader`, repo `scanmydata/MyData-Invoice-Downloader`, v0.2.25 on origin; local is 1 behind → pull first). Encrypted local data folder, a `standalone / server / terminal` role model with LAN sharing (`sharing.py`, `presence.py`, `sync.py`), tray, auto‑update via Task Scheduler, `MainWindow` = `SideMenu` + `QStackedWidget`.
- **e‑Τιμολόγιο Pro** — the **PHP** app we just built (`Documents/mydata-etimologio-bridge`): `app.php`/`etimologio.php` + SQLite + crypto; issuance, customers, ledgers, bank import, scheduled issuance, notifications, roles (master/editor/business), 2FA, Resend/SMTP email.

**Goal:** one program that opens to a **launcher** (choose **Timologio Downloader** or **AADE e‑Τιμολόγιο Pro**, switch back and forth anytime). The **accountant‑admin** runs both on the desktop and, beyond notifications, can **fully access each client's e‑Τιμολόγιο Pro**. **Clients** use e‑Τιμολόγιο Pro from a **web browser**. Local (accountant) and web (clients) **share one backend**.

**Decisions (from the user):**
- Backend stays **PHP** (keep the code we built).
- Desktop e‑Τιμολόγιο Pro UI = **full native PySide6 rewrite** matching the downloader; the PHP layer is a **JSON API**; the existing HTML/JS `app.php` UI stays for **web clients**.
- **Shared backend on a dedicated 3rd VPS**, running in **Docker**, managed by **Coolify**; clients (web) and the accountant (desktop, entering server URL + credentials) both connect to it.
- **Desktop runs in two modes:** **start with local offline mode** (bundled `php.exe` + local SQLite), and **switch to thin‑client** to the VPS once the server is set up.
- **Central VPS DB = Postgres** (Coolify‑provisioned). ⇒ the PHP data layer must support **both SQLite (offline) and Postgres (server)**.
- Accountant has **full access to each client's** e‑Τιμολόγιο Pro (reuse staff all‑company roles) + a direct jump from the Downloader/notifications.

**Accepted trade‑offs:** e‑Τιμολόγιο Pro keeps **two frontends** (native Qt desktop + web HTML), both thin over the PHP API; and the DB layer gains a **dual‑dialect** abstraction.

---

## Target architecture

```
  Desktop (accountant)                         Central VPS (Coolify‑managed Docker)
  ┌───────────────────────────┐                ┌───────────────────────────────────┐
  │ Timologio Downloader.exe  │                │  Caddy/Traefik (TLS)              │
  │  Launcher / switch        │                │      │                            │
  │  ┌─────────┐  ┌─────────┐ │   HTTPS + login │  php‑fpm  (etimologio.php API +  │
  │  │Downloader│ │e‑Τιμ.Pro│ │◄───────────────►│           app.php web UI)        │
  │  │(native)  │ │(native  │ │    (thin mode)  │      │                            │
  │  └─────────┘  │  Qt)    │ │                 │  Postgres  +  volume(.enckey,    │
  │        │      └────┬────┘ │                 │            .cookies, uploads)    │
  │        │           │offline│  local SQLite  └───────────────▲──────────────────┘
  │        ▼           ▼ (php.exe -S)                           │ HTTPS
  │  timologio.db  etimologio(local)                    Web clients (browser → app.php)
  └───────────────────────────┘
```

- **One Qt window, two apps:** add a **Launcher** page + an **e‑Τιμολόγιο Pro** area to `MainWindow`; a top segmented control + `SideMenu` section switch anytime. Native e‑Τιμολόγιο pages live in their own `QStackedWidget`, styled via `theme.py`.
- **Two backend modes (config‑switchable):**
  - **Offline/local (bootstrap):** the Qt app spawns bundled `php.exe -S 127.0.0.1:<port> -t backend/etimologio` with a **SQLite** `DB_DSN`; data under `data_dir/etimologio/`.
  - **Thin‑client (once VPS is up):** a Settings screen stores **server URL + login**; the native Qt UI (and web clients) all talk to the VPS backend (Postgres). No local PHP.
- **Native → PHP over HTTP:** new `EtimologioClient` (`requests.Session`, modeled on `src/timologio/mydata/client.py`) calls `etimologio.php` (`?auth=login/login_totp/me`, `?accounts`, issue, `?bulk_issue`, `?sched_*`, `?notifications`, prefs…), holding the session cookie. No business logic duplicated in Python.
- **Accountant → client jump:** staff (master/editor) already resolve any company; add "Open this client in e‑Τιμολόγιο Pro" from the Downloader client row / notification, de‑linking into the account switcher for that ΑΦΜ.
- **Roles reused as‑is:** desktop accountant = `master`/`editor`; web clients = `business`. Invitations, 2FA, per‑admin email prefs, scheduler, notifications all carry over.

---

## Backend workstream A — dual‑dialect DB (SQLite + Postgres)

`backend/etimologio/localdb.php` (and any raw SQL in `etimologio.php`) become **driver‑aware**, selected by a `DB_DSN`/env (`sqlite:…` vs `pgsql:…`):

- Branch the **DDL** per driver: `AUTOINCREMENT` → Postgres `GENERATED … AS IDENTITY`/`SERIAL`; `TEXT DEFAULT (datetime('now'))` → `timestamptz DEFAULT now()`; drop `PRAGMA journal_mode=WAL` for pg.
- Normalize the handful of SQLite‑isms: `datetime('now')` → `now()`; `INSERT … ON CONFLICT(…) DO UPDATE` (both support it — align column/`excluded` syntax); `strftime`/date filters used by ledgers/search.
- Keep the encrypted‑at‑rest model unchanged (crypto.php is DB‑agnostic; ciphertext stored as TEXT/`bytea`‑as‑text).
- Add a tiny `db_dialect()` helper and a migration/`CREATE TABLE IF NOT EXISTS` path that runs on both. Verify by running the **same** smoke tests against a local SQLite and a local Postgres (docker) instance.

---

## Backend workstream B — Dockerized VPS deployment via Coolify

- **Dockerfile** for `backend/etimologio`: `php:8.3-fpm` + Caddy (or nginx) + required extensions (`pdo_pgsql`, `pdo_sqlite`, `openssl`, `curl`, `mbstring`, `zip`), plus a cron/entrypoint that runs `scheduler.php` every minute inside the container.
- **Coolify** deploys from the git repo (auto‑build on push), provisions a **Postgres** service, injects env: `DB_DSN`, `RESEND_API_KEY`/`RESEND_EMAIL_SENDER`, `SCHED_TOKEN`, `APP_URL`, master admin bootstrap. TLS + reverse proxy handled by Coolify's Traefik; **Cloudflare DNS/proxy optional in front**.
- **Persistent volume** for `.enckey`, `.cookies/`, and any uploads; Postgres has its own managed volume/backup via Coolify.
- **"Just enter credentials":** the accountant’s desktop (thin mode) and clients only need the public URL + their login; the operator manages the server through Coolify.

---

## Repo & merge strategy

- Vendor the PHP app **into** the downloader repo, preserving history: `git subtree add --prefix=backend/etimologio https://github.com/scanmydata/mydata-etimologio-bridge.git main` (future updates via `git subtree pull`). PHP lives at `backend/etimologio/`.
- New Python package `src/timologio/etimologio/`: `client.py` (API), `service.py` (local PHP lifecycle + mode switch + health check), `pages/` (one module per view), `shell.py` (stacked container + launcher wiring).
- The standalone `mydata-etimologio-bridge` repo stays the upstream source of truth for the PHP.

---

## Packaging (Windows, PyInstaller + Inno Setup)

- Bundle a **portable PHP runtime** (`php.exe` + `php.ini` + ext DLLs incl. `pdo_sqlite`, `openssl`, `curl`, `mbstring`, `zip`; `pdo_pgsql` optional for local‑against‑remote‑pg tests) under `backend/php/`. Add `backend/php/**` and `backend/etimologio/**` to `datas` in `installer/timologio.spec` (same `datas=[(path,".")]` pattern); resolve via `sys._MEIPASS`.
- **`service.py`** writes a generated `config.php` (offline) or stores the server URL/session (thin) into `data_dir/etimologio/`, spawns/tears down the local PHP in offline mode, and health‑checks either target.
- **Scheduler:** offline/standalone → register `scheduler.php` every minute via Task Scheduler (reuse `gui/updater.py`); server → cron inside the container.
- `installer/timologio.iss` already offers role selection; extend copy to mention e‑Τιμολόγιο Pro and (server) point to the Coolify‑hosted backend.

---

## Native UI — phased roadmap (bulk of the work)

Each page = a `QWidget` on `theme.py`, calling `EtimologioClient`. Until a page is ported, the launcher offers "Open in browser" for that section (no QtWebEngine dependency).

- **Phase 0 — plumbing + offline mode:** subtree merge; dual‑dialect DB (SQLite path first); bundle PHP; `service.py` (spawn/health/teardown, offline SQLite); `EtimologioClient` (login/2FA/me/accounts); Launcher + switch wired into `MainWindow._PAGES`/`_on_menu` + `SideMenu`; theme sync. Deliverable: pick e‑Τιμολόγιο Pro → native login → account switcher against the **local** backend.
- **Phase 1 — core issuance:** Έκδοση (customer autocomplete, line editor, series/pay, taxes, save‑draft/preview/issue), Πελάτες + Καρτέλα, + "Open client from Downloader".
- **Phase 2 — catalogs & lifecycle:** Είδη, Σειρές, Πρόχειρα, Ακύρωση/Πιστωτικά.
- **Phase 3 — volume & money:** Μαζική έκδοση, Εισαγωγή πληρωμών (bank import), Στατιστικά.
- **Phase 4 — platform:** Προγραμματισμός, Ειδοποιήσεις (bell + feed), Ρυθμίσεις (password, 2FA enrol w/ QR via `qrcode`+Qt, per‑admin email prefs), Διαχείριση (roles + invitations).
- **Phase 5 — server + web:** Postgres dialect finalized; **Coolify/Docker VPS** deploy; desktop **thin‑client** mode (enter server URL + creds); web clients via the public URL; one‑time **local→server data migration** (export SQLite → import into Postgres) when the office moves online.

PDF/preview: reuse the PHP real‑AADE PDF endpoints; render/download natively (Qt `QPdfView`/save‑to‑file), no JS PDF stack on desktop.

---

## Risks / notes

- **Two frontends** (native Qt + web HTML) — accepted; logic stays in the PHP API so both are thin.
- **Dual‑dialect DB** adds a real backend workstream; mitigated by branching only the DDL + a few SQLite‑isms and testing both engines.
- **Native rewrite is large** — hence phasing; the product stays usable throughout (unported pages open in the browser against the same backend).
- **Local→server migration** is a one‑time export/import, **not** continuous bidirectional sync (kept intentionally simple).
- **Bundling PHP** in a Qt app is unusual but self‑contained and consistent with the downloader already driving external processes.

---

## Verification

- **Backend/API (both engines):** with the portable PHP (`%TEMP%/phpbin`, memory `local-php-testing`), run the smoke suite against **SQLite** and a **local Postgres (docker)** — `?auth=login/login_totp`, `?accounts`, issue (draft), `?sched_*`, `?notifications`, prefs — confirming identical behavior.
- **Desktop shell:** run from source (`entry.py`/`uv run`); Launcher → switch → native login → each ported page round‑trips against the **local** backend; confirm PHP child teardown on exit + single‑instance.
- **Thin‑client + roles:** point the desktop at the VPS URL; accountant (`master`/`editor`) logs in, opens a client's company, issues; a `business` web login on the same VPS shares the DB and the accountant sees the notification.
- **VPS/Coolify:** deploy via Coolify (Docker + Postgres), verify TLS, `scheduler.php` cron runs, and `app.php` serves web clients over the public URL.
- **Packaging:** build via `installer/build.ps1`; install each role; verify bundled PHP starts in offline mode and thin mode reaches the VPS.
