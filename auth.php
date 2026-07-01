<?php
// ============================================================================
// Authentication & multi-client account resolution
// ----------------------------------------------------------------------------
// Layered on top of the e-timologio bridge to make it multi-tenant with logins:
//   • master admin  — manages businesses, approves signups, links AADE credentials
//   • business user — one login per company, owns one or more AADE accounts
//
// Each business's AADE credentials (e-timologio username + subscription key) live
// ENCRYPTED in the local SQLite DB (crypto.php). config.php only holds the master
// bootstrap + optional SMTP. The active AADE account (COMPANY_VAT / USERNAME /
// SUBSCRIPTION_KEY / COOKIE_FILE) is resolved from the logged-in user + `account`.
//
// This file is a LIBRARY (no output on include). The HTTP auth actions live in
// etimologio.php (?auth=...) and reuse the helpers here.
// ============================================================================

// config.php self-resolves COMPANY_VAT on include for the legacy single-tenant
// setup. When auth is in charge we resolve per-session instead, so suppress it.
if (!defined('SKIP_ACCOUNT_RESOLUTION')) define('SKIP_ACCOUNT_RESOLUTION', 1);

require_once __DIR__ . '/config.php';   // constants + legacy $ACCOUNTS
require_once __DIR__ . '/localdb.php';  // DB + crypto + user/account helpers

if (session_status() === PHP_SESSION_NONE) {
    session_name('ETIM_SID');
    session_start();
}

// --- Master bootstrap -------------------------------------------------------
// Ensure a master admin exists. Credentials come from config constants; the
// password is hashed into the DB on first run and never stored plaintext there.
function auth_bootstrap(): void {
    if (users_count_master() > 0) return;
    $email = defined('MASTER_ADMIN_EMAIL') ? trim(MASTER_ADMIN_EMAIL) : '';
    $pass  = defined('MASTER_ADMIN_PASSWORD') ? (string)MASTER_ADMIN_PASSWORD : '';
    if ($email === '' || $pass === '') return;   // not configured yet
    if (user_by_email($email)) { user_update(user_by_email($email)['id'], ['role' => 'master', 'status' => 'active']); return; }
    user_create($email, password_hash($pass, PASSWORD_DEFAULT), 'master', 'active', 'Διαχειριστής');
}

// --- Current session --------------------------------------------------------
function current_user(): ?array {
    if (empty($_SESSION['uid'])) return null;
    $u = user_by_id((int)$_SESSION['uid']);
    if (!$u || $u['status'] === 'disabled') { auth_logout(); return null; }
    return $u;
}

function is_master(): bool {
    $u = current_user();
    return $u && $u['role'] === 'master';
}

function auth_login(string $email, string $password): array {
    $u = user_by_email($email);
    if (!$u || !password_verify($password, $u['password_hash'])) {
        return ['success' => false, 'error' => 'Λάθος email ή κωδικός'];
    }
    if ($u['status'] === 'pending')  return ['success' => false, 'error' => 'Ο λογαριασμός εκκρεμεί έγκριση από τον διαχειριστή'];
    if ($u['status'] === 'disabled') return ['success' => false, 'error' => 'Ο λογαριασμός είναι απενεργοποιημένος'];
    session_regenerate_id(true);
    $_SESSION['uid'] = (int)$u['id'];
    return ['success' => true, 'user' => user_public($u)];
}

function auth_logout(): void {
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $p = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'], $p['secure'], $p['httponly']);
    }
    session_destroy();
}

// --- Signup (public, pending approval) --------------------------------------
function auth_signup(string $email, string $password, string $businessName): array {
    $email = strtolower(trim($email));
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) return ['success' => false, 'error' => 'Μη έγκυρο email'];
    if (strlen($password) < 8) return ['success' => false, 'error' => 'Ο κωδικός πρέπει να έχει ≥ 8 χαρακτήρες'];
    if (trim($businessName) === '') return ['success' => false, 'error' => 'Λείπει η επωνυμία επιχείρησης'];
    if (user_by_email($email)) return ['success' => false, 'error' => 'Υπάρχει ήδη λογαριασμός με αυτό το email'];
    $id = user_create($email, password_hash($password, PASSWORD_DEFAULT), 'business', 'pending', $businessName);
    return ['success' => true, 'id' => $id, 'note' => 'Η εγγραφή καταχωρήθηκε και εκκρεμεί έγκριση από τον διαχειριστή.'];
}

// --- Password reset ---------------------------------------------------------
// Generates a token (valid 1h). Emails a link if SMTP/mail is configured;
// the token is also retrievable by the master admin (offline flow).
function auth_forgot(string $email): array {
    $u = user_by_email($email);
    // Always report success (do not reveal whether the email exists).
    if ($u) {
        $token = bin2hex(random_bytes(24));
        user_update((int)$u['id'], ['reset_token' => $token, 'reset_expires' => time() + 3600]);
        auth_send_reset_email($u['email'], $token);
    }
    return ['success' => true, 'note' => 'Αν υπάρχει λογαριασμός, στάλθηκαν οδηγίες επαναφοράς.'];
}

function auth_reset(string $token, string $newPassword): array {
    if (strlen($newPassword) < 8) return ['success' => false, 'error' => 'Ο κωδικός πρέπει να έχει ≥ 8 χαρακτήρες'];
    $token = trim($token);
    if ($token === '') return ['success' => false, 'error' => 'Λείπει το token'];
    $st = localdb()->prepare("SELECT * FROM users WHERE reset_token = :t");
    $st->execute([':t' => $token]);
    $u = $st->fetch();
    if (!$u || (int)$u['reset_expires'] < time()) return ['success' => false, 'error' => 'Άκυρο ή ληγμένο token'];
    user_update((int)$u['id'], [
        'password_hash' => password_hash($newPassword, PASSWORD_DEFAULT),
        'reset_token' => '', 'reset_expires' => 0,
        'status' => $u['status'] === 'pending' ? 'pending' : 'active',
    ]);
    return ['success' => true, 'note' => 'Ο κωδικός ενημερώθηκε.'];
}

function auth_reset_link(string $token): string {
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    return $scheme . '://' . $host . dirname($_SERVER['SCRIPT_NAME'] ?? '/') . '/app.php?reset=' . urlencode($token);
}

function auth_send_reset_email(string $to, string $token): bool {
    $link = auth_reset_link($token);
    $subject = 'Επαναφορά κωδικού - e-Τιμολόγιο';
    $body = "Ζητήσατε επαναφορά κωδικού.\r\n\r\nΑνοίξτε τον παρακάτω σύνδεσμο (ισχύει για 1 ώρα):\r\n$link\r\n\r\nΑν δεν το ζητήσατε, αγνοήστε το μήνυμα.";
    if (!defined('SMTP_FROM') || SMTP_FROM === '') {
        // No mail configured — the master admin will hand the token over manually.
        return false;
    }
    $headers = 'From: ' . SMTP_FROM . "\r\n" . 'Content-Type: text/plain; charset=UTF-8' . "\r\n";
    return @mail($to, '=?UTF-8?B?' . base64_encode($subject) . '?=', $body, $headers);
}

// --- Active AADE account resolution (defines the bridge constants) ----------
// Called once per request after the user is known. Picks the account by the
// `account` param (VAT) among the user's own accounts, else the first.
function auth_resolve_account(): ?array {
    $u = current_user();
    if (!$u) return null;
    $accounts = accounts_for_user((int)$u['id']);
    // Master admin with no own accounts may still act on a business account it
    // manages by passing ?account_id=… (validated in the admin handlers).
    if (empty($accounts)) return null;

    $reqVat = preg_replace('/\D/', '', $_GET['account'] ?? $_POST['account'] ?? '');
    $active = null;
    foreach ($accounts as $a) {
        if ($reqVat !== '' && $a['vat'] === $reqVat) { $active = $a; break; }
    }
    if ($active === null) $active = $accounts[0];

    if (!defined('COMPANY_VAT')) {
        define('COMPANY_VAT',      (string)$active['vat']);
        define('USERNAME',         (string)$active['username']);
        define('SUBSCRIPTION_KEY', (string)$active['subkey']);
        if (!is_dir(COOKIE_DIR)) @mkdir(COOKIE_DIR, 0700, true);
        define('COOKIE_FILE', COOKIE_DIR . '/etimologio_' . preg_replace('/\D/', '', COMPANY_VAT) . '.txt');
    }
    return $active;
}

// One-time migration: import legacy config.php $ACCOUNTS into the DB (attached to
// the master admin) so existing setups keep working after logins are enabled.
function auth_migrate_legacy_accounts(): void {
    global $ACCOUNTS;
    if (!isset($ACCOUNTS) || !is_array($ACCOUNTS) || empty($ACCOUNTS)) return;
    if ((int)localdb()->query("SELECT COUNT(*) FROM aade_accounts")->fetchColumn() > 0) return;
    $master = localdb()->query("SELECT id FROM users WHERE role='master' ORDER BY id ASC LIMIT 1")->fetchColumn();
    if (!$master) return;
    foreach ($ACCOUNTS as $a) {
        if (empty($a['vat'])) continue;
        account_add((int)$master, (string)$a['vat'], (string)($a['label'] ?? $a['vat']),
                    (string)($a['username'] ?? ''), (string)($a['subscription_key'] ?? ''));
    }
}

// Run bootstrap + migration + account resolution on include (safe, no output).
auth_bootstrap();
auth_migrate_legacy_accounts();
auth_resolve_account();
