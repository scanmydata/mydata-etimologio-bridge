# Deploying the shared backend (Coolify + Docker + Postgres)

One container serves **both** halves of the product: the browser UI (`app.php`)
that client businesses use, and the JSON API the desktop app talks to in
**thin-client** mode. The accountant and every client therefore work on the same
data.

```
 Desktop (accountant)                    VPS — Coolify
 ┌───────────────────┐                   ┌──────────────────────────────┐
 │ Downloader        │                   │ Traefik (TLS, from Coolify)  │
 │ e-Τιμολόγιο Pro   │ ── HTTPS + login ►│ etimologio (this image, :8080)│
 └───────────────────┘                   │ Postgres  +  volume → /data  │
 Web clients ── HTTPS ──────────────────►└──────────────────────────────┘
```

## 1. Create the Postgres service

In Coolify: **New Resource → Database → PostgreSQL**. Note the internal
connection details; Coolify exposes them to apps in the same project.

## 2. Create the application

**New Resource → Application → from your Git repository**, Build Pack
**Dockerfile**, port **8080**. Coolify handles TLS and routing; a Cloudflare
proxy in front is optional.

## 3. Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DB_DSN` | yes | `pgsql:host=<service>;port=5432;dbname=etimologio` — leave empty to fall back to a SQLite file on the volume |
| `DB_USER`, `DB_PASS` | yes | Postgres credentials |
| `MASTER_ADMIN_EMAIL` | yes | Bootstrapped on first boot |
| `MASTER_ADMIN_PASSWORD` | first boot | Hashed into the DB on first run; **clear it afterwards** |
| `APP_URL` | yes | Public URL, no trailing slash — used in email links |
| `SCHED_TOKEN` | for scheduling | `php -r "echo bin2hex(random_bytes(24));"`. Empty disables scheduled issuance |
| `RESEND_API_KEY`, `RESEND_EMAIL_SENDER` | for email | Preferred provider; the sender domain must be verified |
| `SMTP_*`, `MAIL_PROVIDER` | optional | SMTP fallback |
| `NOTIFY_ADMIN_EMAIL` | optional | `-` disables issuance emails |

`config.php` is **generated at container start** from these, so the image holds
no secrets.

## 4. Persistent volume — required

Mount a volume at **`/data`**. It holds:

- `.enckey` — the at-rest encryption key. **Losing it makes stored data
  unreadable.** Back it up.
- `.cookies/` — per-account ΑΑΔΕ session jars.
- `.localdata.sqlite` — only when `DB_DSN` is empty.

## 5. Point the desktop at the server

In the desktop app: **e-Τιμολόγιο Pro → Ρυθμίσεις → Σύνδεση σε server**, enter
the public URL and log in. The app stops spawning its bundled PHP and becomes a
thin client. Switching back to **Τοπικά (offline)** is a single click.

## 6. Moving existing local data to the server (one-off)

```bash
php tools/migrate_to_server.php --from /path/to/.localdata.sqlite \
    --dsn "pgsql:host=…;dbname=etimologio" --user … --pass …
```

Copies users, accounts, cached datasets, payments, customer meta, scheduled jobs
and notifications. It is a **one-time export/import**, not continuous
sync — run it while nobody is issuing.

## Notes

- **No `zip` extension needed**: archives are produced by `zipwriter.php` using
  zlib, so bulk ZIP export behaves identically here, on the portable PHP the
  desktop bundles, and on slim images.
- **TLS to ΑΑΔΕ** works out of the box — `ca-certificates` is installed. (The
  portable desktop PHP needs `curl.cainfo` set explicitly; see the packaging
  notes.)
- The scheduler ticks once a minute inside the container when `SCHED_TOKEN` is
  set, mirroring the Task Scheduler entry a standalone install creates.
