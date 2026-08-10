#!/bin/sh
# Container entrypoint: render config.php from the environment, then start the
# scheduler tick and hand over to Apache.
#
# config.php is generated at boot rather than baked in, so the image carries no
# secrets and Coolify stays the single place where they are set.
set -eu

DATA_DIR="${ETIM_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/.cookies"

php_str() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/\\\\'/g")"; }

cat > /var/www/html/config.php <<PHP
<?php
// Generated at container start from the environment — do not edit by hand.
\$ACCOUNTS = [];

const BASE_URL   = 'https://mydata.aade.gr/timologio';
const COOKIE_DIR = '${DATA_DIR}/.cookies';
const ENC_KEY_FILE = '${DATA_DIR}/.enckey';
const LOCAL_DB   = '${DATA_DIR}/.localdata.sqlite';
const ZERO_VAT_TYPES = ['22', '23'];

// Shared Postgres provisioned by Coolify. Falls back to the SQLite file above
// when DB_DSN is unset, so the image also runs standalone for a smoke test.
const DB_DSN  = $(php_str "${DB_DSN:-}");
const DB_USER = $(php_str "${DB_USER:-}");
const DB_PASS = $(php_str "${DB_PASS:-}");

const MASTER_ADMIN_EMAIL    = $(php_str "${MASTER_ADMIN_EMAIL:-admin@example.com}");
const MASTER_ADMIN_PASSWORD = $(php_str "${MASTER_ADMIN_PASSWORD:-}");

const MAIL_PROVIDER       = $(php_str "${MAIL_PROVIDER:-auto}");
const RESEND_API_KEY      = $(php_str "${RESEND_API_KEY:-}");
const RESEND_EMAIL_SENDER = $(php_str "${RESEND_EMAIL_SENDER:-}");
const SMTP_FROM           = $(php_str "${SMTP_FROM:-}");
const SMTP_HOST           = $(php_str "${SMTP_HOST:-}");
const SMTP_PORT           = ${SMTP_PORT:-587};
const SMTP_USER           = $(php_str "${SMTP_USER:-}");
const SMTP_PASS           = $(php_str "${SMTP_PASS:-}");
const APP_URL             = $(php_str "${APP_URL:-}");

const SCHED_TOKEN        = $(php_str "${SCHED_TOKEN:-}");
const APP_BASE_URL       = 'http://127.0.0.1:8080';
const NOTIFY_ADMIN_EMAIL = $(php_str "${NOTIFY_ADMIN_EMAIL:-}");
PHP

chown www-data:www-data /var/www/html/config.php
chmod 640 /var/www/html/config.php

# Scheduled issuance: one tick a minute, exactly like the Task Scheduler entry
# the standalone desktop install creates. Skipped when no token is configured,
# because the endpoint refuses service-auth without one anyway.
if [ -n "${SCHED_TOKEN:-}" ]; then
  ( while true; do
      su -s /bin/sh -c 'php /var/www/html/scheduler.php >/proc/1/fd/1 2>&1' www-data || true
      sleep 60
    done ) &
  echo "[entrypoint] scheduler tick every 60s"
else
  echo "[entrypoint] SCHED_TOKEN not set — scheduled issuance disabled"
fi

exec "$@"
