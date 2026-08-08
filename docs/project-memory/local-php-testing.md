---
name: local-php-testing
description: How to lint and run this PHP app locally (no PHP on PATH; portable PHP + ini)
metadata: 
  node_type: memory
  type: reference
  originSessionId: d99a09dd-f89c-4baf-bfc0-e7400408007d
  modified: 2026-08-08T14:33:50.941Z
---

This machine has **no PHP on PATH** and no XAMPP/laragon. To lint or run the bridge locally:

1. Portable PHP already fetched once to `%TEMP%\phpbin\php.exe` (PHP 8.3 NTS x64 from windows.php.net/downloads/releases/). Re-download if gone.
2. It ships with **no php.ini**, so pdo_sqlite/openssl/curl/mbstring are OFF by default → `PDOException: could not find driver`. Create `%TEMP%\phpbin\php.ini` with a **Windows-style** `extension_dir="C:\...\phpbin\ext"` and `extension=pdo_sqlite` / `sqlite3` / `openssl` / `mbstring` / `curl` (bare names, not `php_*.dll`; a Unix `/c/...` extension_dir fails to load).
3. Lint: `php -l file.php`. Serve: `php -c <ini> -S 127.0.0.1:8199` from the repo root.
4. The app needs a `config.php` (gitignored, normally absent). For tests write a throwaway one with `$ACCOUNTS=[]`, `LOCAL_DB`/`ENC_KEY_FILE` pointed at a temp dir, master creds, and `SCHED_TOKEN`/`APP_BASE_URL`. **Delete it afterwards** so it doesn't shadow the user's real config.
5. Kill stale servers with PowerShell `Get-Process php | Stop-Process -Force` — a leftover server on the port silently serves old code/ini.
6. The in-app Browser pane can't screenshot here ("not compositing"), but `read_page`/`get_page_text`/`javascript_tool` work fine for verifying the DOM.
7. Greek text sent via `curl --data` from Git-Bash gets mojibake'd (bad codepage); inject UTF-8 test data via `php -r` instead. The app's own encryption round-trips Greek correctly.

8. **Outbound TLS to ΑΑΔΕ needs a CA bundle.** The portable PHP ships no CA
   roots, so `curl` to `https://mydata.aade.gr/timologio` fails with OpenSSL
   error 60 ("self-signed certificate in certificate chain") and the bridge
   returns `{"success":false,"error":"Could not reach e-timologio"}`. Fix: add
   `curl.cainfo="…/certifi/cacert.pem"` + `openssl.cafile=…` to the php.ini
   (reuse the Downloader venv's `certifi/cacert.pem`). This is also a **packaging
   requirement** for the bundled PHP. Verified live (VAT 802576637): after the
   fix, `list_customers`/`search_invoices` return real data.

See [[etimologio-architecture]] for the app's request flow and
[[etimologio-downloader-merge]] for the merge status.
