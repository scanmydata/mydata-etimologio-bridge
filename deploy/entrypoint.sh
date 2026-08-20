#!/bin/sh
# Container entrypoint: render config.php from the environment, wait for the
# database, then start the scheduler tick and hand over to Apache.
#
# config.php is generated at boot rather than baked in, so the image carries no
# secrets and Coolify stays the single place where they are set.
set -eu

DATA_DIR="${ETIM_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/.cookies"
chown -R www-data:www-data "$DATA_DIR" 2>/dev/null || true

php_str() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/\\\\'/g")"; }
log() { echo "[entrypoint] $*"; }

# --- Σύνδεση βάσης ----------------------------------------------------------
# Το Coolify δίνει τη Postgres του ως ΕΝΑ connection string (DATABASE_URL /
# POSTGRES_URL), όχι ως τρία χωριστά πεδία. Αν δεν έχει οριστεί ρητά DB_DSN, το
# σπάμε εδώ σε DSN + χρήστη + κωδικό, ώστε «κόλλα το URL που σου δίνει το
# Coolify» να είναι όλη κι όλη η ρύθμιση της βάσης.
if [ -z "${DB_DSN:-}" ] && [ -n "${DATABASE_URL:-}${POSTGRES_URL:-}" ]; then
    eval "$(php /usr/local/bin/dburl.php)"
    log "βάση από το connection string: ${DB_DSN:-<δεν αναγνωρίστηκε>}"
fi

# --- php.ini από το περιβάλλον ---------------------------------------------
# Μέγεθος/χρόνος ρυθμίζονται από το Coolify χωρίς rebuild. Τα defaults ζουν στο
# deploy/php.ini· εδώ μόνο τα ξαναγράφουμε όταν δοθούν.
cat > /usr/local/etc/php/conf.d/zz-etimologio-env.ini <<INI
memory_limit = ${PHP_MEMORY_LIMIT:-512M}
max_execution_time = ${PHP_MAX_EXECUTION_TIME:-300}
max_input_time = ${PHP_MAX_EXECUTION_TIME:-300}
upload_max_filesize = ${PHP_UPLOAD_MAX_FILESIZE:-32M}
post_max_size = ${PHP_POST_MAX_SIZE:-40M}
date.timezone = ${TZ:-Europe/Athens}
INI

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
// Το mail.php μιλά πλέον SMTP κανονικά (STARTTLS/SSL), αντί να καλεί mail():
// χωρίς αυτή τη σταθερά ο container έστελνε σε καθαρή σύνδεση στην 587 και ο
// server απαντούσε «530 must issue a STARTTLS command first».
const SMTP_SECURE         = $(php_str "${SMTP_SECURE:-tls}");
const SMTP_USER           = $(php_str "${SMTP_USER:-}");
const SMTP_PASS           = $(php_str "${SMTP_PASS:-}");
const APP_URL             = $(php_str "$(printf '%s' "${APP_URL:-}" | sed 's:/*$::')");

const SCHED_TOKEN        = $(php_str "${SCHED_TOKEN:-}");
const APP_BASE_URL       = 'http://127.0.0.1:8080';
const NOTIFY_ADMIN_EMAIL = $(php_str "${NOTIFY_ADMIN_EMAIL:-}");
PHP

# Κλειδί κρυπτογράφησης: κανονικά παράγεται μόνο του στο ${DATA_DIR}/.enckey.
# Αν δοθεί ως μυστικό (π.χ. από το Coolify), κερδίζει — έτσι τα δεδομένα
# διαβάζονται ακόμη κι αν χαθεί το volume. ΠΡΟΣΟΧΗ: αλλαγή του κλειδιού σε
# υπάρχουσα βάση κάνει τα ήδη κρυπτογραφημένα πεδία μη αναγνώσιμα.
if [ -n "${ENCRYPTION_KEY:-}" ]; then
    printf "const ENCRYPTION_KEY = %s;\n" "$(php_str "$ENCRYPTION_KEY")" >> /var/www/html/config.php
    log "ENCRYPTION_KEY from the environment (the .enckey file is ignored)"
fi

# Φωνή του βοηθού: μόνο αν ο χειριστής έβαλε τα binaries σε volume.
for v in PIPER_EXE PIPER_VOICE_EL PIPER_VOICE_EN WHISPER_EXE WHISPER_MODEL; do
    eval "val=\${$v:-}"
    [ -n "$val" ] || continue
    printf "const %s = %s;\n" "$v" "$(php_str "$val")" >> /var/www/html/config.php
done

chown www-data:www-data /var/www/html/config.php
chmod 640 /var/www/html/config.php

# --- Αναμονή της βάσης ------------------------------------------------------
# Το Coolify ξεκινά την εφαρμογή χωρίς να περιμένει την Postgres (το compose του
# repo έχει healthcheck, ένα deploy από UI δεν έχει). Χωρίς αναμονή, το πρώτο
# request σκάει στη δημιουργία των πινάκων και ο χρήστης βλέπει «500».
DB_PROBE='require "/var/www/html/config.php"; new PDO(DB_DSN, DB_USER ?: null, DB_PASS ?: null, [PDO::ATTR_TIMEOUT => 3]);'
case "${DB_DSN:-}" in
  pgsql:*|mysql:*)
    i=0
    until php -r "$DB_PROBE" 2>/dev/null; do
      i=$((i + 1))
      [ "$i" = 1 ] && log "αναμονή για τη βάση…"
      if [ "$i" -ge 30 ]; then
        log "η βάση δεν απάντησε σε 60 δευτερόλεπτα — ξεκινώ έτσι κι αλλιώς:"
        php -r "$DB_PROBE" 2>&1 | head -3
        break
      fi
      sleep 2
    done
    [ "$i" -lt 30 ] && log "η βάση απαντά"
    ;;
  *)
    log "χωρίς DB_DSN — τοπική SQLite στο ${DATA_DIR}/.localdata.sqlite"
    ;;
esac

# Scheduled issuance: one tick a minute, exactly like the Task Scheduler entry
# the standalone desktop install creates. Skipped when no token is configured,
# because the endpoint refuses service-auth without one anyway.
if [ -n "${SCHED_TOKEN:-}" ]; then
  ( while true; do
      su -s /bin/sh -c 'php /var/www/html/scheduler.php >/proc/1/fd/1 2>&1' www-data || true
      sleep 60
    done ) &
  log "scheduler tick every 60s"
else
  log "SCHED_TOKEN not set — scheduled issuance disabled"
fi

exec "$@"
