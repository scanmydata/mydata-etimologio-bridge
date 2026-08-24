#!/bin/sh
# ============================================================================
# Αντίγραφο ΠΡΙΝ από κάθε deploy.
# ----------------------------------------------------------------------------
# Μπαίνει στο Coolify: Configuration → General → Pre/Post Deployment Commands →
# **Pre-deployment**:
#
#     sh /var/www/html/deploy/pre-deploy-backup.sh
#
# Γιατί εδώ και όχι στο entrypoint: το entrypoint τρέχει ΑΦΟΥ έχει ήδη χτιστεί
# και ξεκινήσει ο νέος container — δηλαδή αφού η αλλαγή έχει ήδη γίνει. Ένα
# αντίγραφο «πριν την αναβάθμιση» πρέπει να τρέξει πριν, με τον ΠΑΛΙΟ κώδικα
# και την παλιά βάση ακόμη στη θέση τους.
#
# Δεν ρίχνει ποτέ το deploy: αν το αντίγραφο αποτύχει (δεν απαντά το Drive,
# λείπει κλειδί) βγάζει προειδοποίηση και επιστρέφει 0. Ένα χαλασμένο αντίγραφο
# δεν είναι λόγος να μείνει ο server στην παλιά έκδοση με ανοιχτό σφάλμα.
# Αν θέλεις το ΑΝΤΙΘΕΤΟ (κανένα deploy χωρίς αντίγραφο), βάλε
# PREDEPLOY_BACKUP_STRICT=1 στα env.
# ============================================================================
set -u

cd /var/www/html 2>/dev/null || cd "$(dirname "$0")/.." || exit 0

if [ ! -f config.php ]; then
    echo "[pre-deploy] χωρίς config.php — παραλείπεται το αντίγραφο"
    exit 0
fi

echo "[pre-deploy] αντίγραφο της βάσης πριν την αναβάθμιση…"
OUT=$(php -r '
    define("SKIP_ACCOUNT_RESOLUTION", 1);
    require "config.php";
    require "localdb.php";
    require "serverbackup.php";
    $r = srv_backup_run("pre-deploy");
    echo json_encode($r, JSON_UNESCAPED_UNICODE), "\n";
' 2>&1)
CODE=$?

echo "[pre-deploy] $OUT"

if [ "$CODE" -ne 0 ] || ! printf '%s' "$OUT" | grep -q '"ok":true'; then
    if [ "${PREDEPLOY_BACKUP_STRICT:-0}" = "1" ]; then
        echo "[pre-deploy] ΑΠΕΤΥΧΕ και PREDEPLOY_BACKUP_STRICT=1 — σταματώ το deploy" >&2
        exit 1
    fi
    echo "[pre-deploy] το αντίγραφο απέτυχε — το deploy συνεχίζει" >&2
fi

exit 0
