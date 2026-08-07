---
name: etimologio-architecture
description: "How the mydata-etimologio-bridge PHP app is structured (request flow, auth, issue paths)"
metadata: 
  node_type: memory
  type: project
  originSessionId: d99a09dd-f89c-4baf-bfc0-e7400408007d
  modified: 2026-08-07T18:39:39.309Z
---

Multi-tenant PHP bridge over ΑΑΔΕ e-timologio. Key files:

- **etimologio.php** (~4k lines): monolith — helper functions at top (hoisted), then a big top-down request dispatch after `// --- API ENTRY POINT`. `require auth.php` sets up session + resolves the active AADE account into constants `COMPANY_VAT`/`USERNAME`/`SUBSCRIPTION_KEY`/`COOKIE_FILE` (defined **once** per request). `login()` uses those constants to reach AADE. Live-issue paths that get a ΜΑΡΚ: multi-line invoice (`lines` JSON), legacy `amount>0`, `bulk_issue`, credit note. Delivery notes (9.x, `delivery_note`) also go through `createInvoice` but are a separate path.
- **auth.php**: session, master/business users, `auth_resolve_account()` (picks account by `?account=` VAT among the user's), legacy `$ACCOUNTS` migration.
- **localdb.php**: SQLite (WAL), all encrypted-at-rest via crypto.php (`enc`/`dec`/`enc_num`/`dec_num`). Tables: payments, app_cache, customer_meta, users (now incl. `totp_secret`/`totp_enabled`/`invited_by`), aade_accounts, **scheduled_jobs**, **issue_notifications**.
- **mail.php**: `send_mail()` — Resend HTTPS API (`RESEND_API_KEY`) preferred, PHP `mail()`/SMTP fallback; `MAIL_PROVIDER=auto|resend|smtp`; `mail_template()`/`mail_button()` branded HTML (embeds app icon data URI). Used by all auth emails + issuance notifications. No-ops gracefully when unconfigured.
- **totp.php**: RFC 6238 TOTP (Base32, HMAC-SHA1, `otpauth://` URI). 2FA optional per user.
- Roles: **master** (full admin), **editor/λογιστής** (all companies, no member mgmt), **business** (own only). `is_staff()`/`user_is_staff()` = master|editor → `auth_resolve_account()` resolves ANY company (`accounts_all_full()`/`account_by_vat()`); notifications + `sched_list` + `?accounts` are all-scoped for staff. Invites: `?auth=admin_invite` → `invited` user + reset-token activation email. 2FA login is two-step (`login` → `totp_required` → `login_totp`).
- **app.php**: single-file UI. `api(params)` = GET to etimologio.php (auto-adds `account`); large payloads POST manually. Views are `.view` sections toggled by `showView(v)`; nav = `.nav-item[data-view]`. Native `<dialog>` modals opened via `id.showModal()`.
- **scheduler.php**: CLI runner (added for TODO 90). Reads due `scheduled_jobs`, **replays** each over loopback HTTP to etimologio.php using the **service-auth branch** (`sched_token`+`sched_uid`, loopback-only, before the login gate) which sets `$_SESSION['uid']` and re-calls `auth_resolve_account()`. Needs `SCHED_TOKEN`+`APP_BASE_URL` in config.php and a per-minute cron/Task-Scheduler trigger.

TODO 90/91 (scheduled issuance + accountant/admin issue notifications) implemented 2026-08. Notifications recorded by `notifyIssue()` on every live issue **except 9.x delivery notes**; master sees all accounts, business sees own. See [[local-php-testing]] to run it.
