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
require_once __DIR__ . '/mail.php';     // Resend/SMTP transactional email
require_once __DIR__ . '/totp.php';     // authenticator 2FA (RFC 6238)
require_once __DIR__ . '/qrcode.php';   // ο κωδικός QR του 2FA, χωρίς δίκτυο

// --- Όταν η βάση δεν απαντά --------------------------------------------------
// Στον server η βάση είναι χωριστή υπηρεσία: μπορεί να είναι σε restart ή σε
// backup. Χωρίς αυτό, ένα PDOException βγαίνει ως γυμνό «500» — λευκή σελίδα
// για τον πελάτη και, αν κάποιος έχει αφήσει display_errors ανοιχτό, το DSN και
// ο χρήστης της βάσης μέσα στη σελίδα. Το μήνυμα του σφάλματος πάει στο log του
// container, στον χρήστη πάει μόνο «ξαναδοκίμασε».
set_exception_handler(static function (\Throwable $e): void {
    $isDb = $e instanceof \PDOException;
    error_log('[etimologio] ' . get_class($e) . ': ' . $e->getMessage()
              . ' @ ' . $e->getFile() . ':' . $e->getLine());
    if (headers_sent()) return;
    http_response_code($isDb ? 503 : 500);
    header('Retry-After: 15');
    $msg = $isDb
        ? 'Η βάση δεδομένων δεν είναι διαθέσιμη αυτή τη στιγμή. Δοκιμάστε ξανά σε λίγο.'
        : 'Παρουσιάστηκε σφάλμα. Δοκιμάστε ξανά σε λίγο.';
    if (strpos((string)($_SERVER['SCRIPT_NAME'] ?? ''), 'etimologio.php') !== false) {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['success' => false, 'error' => $msg], JSON_UNESCAPED_UNICODE);
        return;
    }
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><meta charset="utf-8"><title>e-Τιμολόγιο Pro</title>'
       . '<div style="font:16px/1.6 system-ui,sans-serif;max-width:520px;margin:18vh auto;'
       . 'padding:24px;border-radius:14px;background:#131f33;color:#e6edf7">'
       . '<h1 style="font-size:19px;margin:0 0 8px">Προσωρινά εκτός λειτουργίας</h1>'
       . '<p style="margin:0;color:#9fb3cd">' . htmlspecialchars($msg, ENT_QUOTES, 'UTF-8') . '</p></div>';
});

// --- Πίσω από proxy (cloudflared/Coolify) -----------------------------------
// Ο container μιλά καθαρό HTTP στη 8090· το TLS το τερματίζει η Cloudflare. Ό,τι
// ρωτά «είναι HTTPS;» πρέπει να κοιτά και την κεφαλίδα του proxy, αλλιώς το
// cookie μένει χωρίς Secure και οι σύνδεσμοι των email βγαίνουν http://.
function req_is_https(): bool {
    if (!empty($_SERVER['HTTPS']) && strtolower((string)$_SERVER['HTTPS']) !== 'off') return true;
    $proto = strtolower(trim((string)($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '')));
    if ($proto !== '') return explode(',', $proto)[0] === 'https';
    if (stripos((string)($_SERVER['HTTP_CF_VISITOR'] ?? ''), 'https') !== false) return true;
    return false;
}

/**
 * Ήρθε το αίτημα από τον ΙΔΙΟ τον υπολογιστή (loopback) και ΟΧΙ μέσα από proxy;
 *
 * Δύο δρόμοι εμπιστεύονται το loopback: το service-auth του χρονοπρογραμματιστή
 * και το αυτόματο login της εφαρμογής υπολογιστή. Η IP από μόνη της δεν αρκεί —
 * αν κάποια στιγμή μπει mod_remoteip ή παρόμοιο, ένα `X-Forwarded-For:
 * 127.0.0.1` από το internet θα έμοιαζε με loopback. Η παρουσία οποιασδήποτε
 * κεφαλίδας proxy σημαίνει «ήρθε από έξω».
 */
function req_is_loopback(): bool {
    $remote = $_SERVER['REMOTE_ADDR'] ?? '';
    if (!in_array($remote, ['127.0.0.1', '::1', ''], true)) return false;
    foreach (['HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_PROTO', 'HTTP_X_REAL_IP',
              'HTTP_CF_CONNECTING_IP', 'HTTP_FORWARDED'] as $h) {
        if (!empty($_SERVER[$h])) return false;
    }
    return true;
}

if (session_status() === PHP_SESSION_NONE) {
    session_name('ETIM_SID');
    // Secure μόνο όταν το αίτημα ΕΙΝΑΙ https: σταθερό «1» θα έσπαγε την τοπική
    // λειτουργία της εφαρμογής υπολογιστή σε http://127.0.0.1.
    session_set_cookie_params([
        'lifetime' => 0,
        'path'     => '/',
        'httponly' => true,
        'samesite' => 'Lax',
        'secure'   => req_is_https(),
    ]);
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

// "Staff" = accountant/admin roles with access to EVERY company:
//   master — full admin (user management, invitations, credentials, everything)
//   editor — accountant staff (all companies: issue/schedule/notifications) but
//            NOT user management / credential management.
function is_staff(?array $u = null): bool {
    $u = $u ?? current_user();
    return $u && in_array($u['role'], ['master', 'editor'], true);
}

function user_is_staff(array $u): bool {
    return in_array($u['role'] ?? '', ['master', 'editor'], true);
}

// --- Φρένο στις δοκιμές κωδικού --------------------------------------------
//
// Ο server είναι ΔΗΜΟΣΙΟΣ. Χωρίς φρένο, ένα script δοκιμάζει κωδικούς όσο θέλει:
// το `password_verify` είναι αργό για έναν άνθρωπο, όχι για δέκα χιλιάδες
// αιτήματα. Δύο μετρητές, γιατί καλύπτουν διαφορετικές επιθέσεις:
//   * ανά (email + IP) — επίμονη δοκιμή σε ΕΝΑΝ λογαριασμό,
//   * ανά IP — «password spraying»: ένας κωδικός σε πολλούς λογαριασμούς.
//
// Το κλείδωμα είναι ΧΡΟΝΙΚΟ, όχι μόνιμο: ένας πραγματικός χρήστης που ξέχασε
// τον κωδικό του δεν πρέπει να χρειάζεται διαχειριστή για να ξαναμπεί. Και
// μετριέται στη βάση, όχι στη συνεδρία — μια επίθεση δεν κρατά cookies.
const LOGIN_MAX_FAILS   = 6;      // δοκιμές πριν το κλείδωμα
const LOGIN_WINDOW_SEC  = 900;    // 15 λεπτά: τόσο «θυμάται» τις αποτυχίες
const LOGIN_LOCK_SEC    = 900;    // και τόσο κλειδώνει (διπλασιάζεται)
const LOGIN_LOCK_MAX    = 3600;
const LOGIN_IP_MAX      = 20;     // αποτυχίες ανά IP στο ίδιο παράθυρο

function login_gate_key(string $email, string $ip): string {
    return 'login.fail.' . substr(hash('sha256', strtolower($email) . '|' . $ip), 0, 32);
}

function login_gate_read(string $key): array {
    $raw = setting_get($key);
    $d = $raw !== '' ? json_decode($raw, true) : null;
    return is_array($d) ? $d + ['n' => 0, 'first' => 0, 'until' => 0] : ['n' => 0, 'first' => 0, 'until' => 0];
}

/** Πόσα δευτερόλεπτα μένουν στο κλείδωμα (0 = ελεύθερο). */
function login_locked_for(string $email, string $ip): int {
    foreach ([login_gate_key($email, $ip), login_gate_key('', $ip)] as $key) {
        $g = login_gate_read($key);
        $left = (int)$g['until'] - time();
        if ($left > 0) return $left;
    }
    return 0;
}

function login_note_failure(string $email, string $ip): void {
    $now = time();
    foreach ([[login_gate_key($email, $ip), LOGIN_MAX_FAILS], [login_gate_key('', $ip), LOGIN_IP_MAX]] as [$key, $max]) {
        $g = login_gate_read($key);
        // Παλιό παράθυρο: ξεκινά καθαρός μετρητής, αλλιώς μια αποτυχία τον
        // περασμένο μήνα θα μετρούσε μαζί με τη σημερινή.
        if ($now - (int)$g['first'] > LOGIN_WINDOW_SEC) { $g['n'] = 0; $g['first'] = $now; }
        $g['n'] = (int)$g['n'] + 1;
        if ($g['n'] >= $max) {
            $steps = (int)floor($g['n'] / $max);
            $g['until'] = $now + (int)min(LOGIN_LOCK_MAX, LOGIN_LOCK_SEC * $steps);
        }
        setting_set($key, json_encode($g));
    }
}

function login_note_success(string $email, string $ip): void {
    setting_set(login_gate_key($email, $ip), '');
}

function auth_login(string $email, string $password): array {
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
    $left = login_locked_for($email, $ip);
    if ($left > 0) {
        return ['success' => false, 'locked' => true,
                'error' => 'Πολλές αποτυχημένες προσπάθειες. Δοκιμάστε ξανά σε '
                           . max(1, (int)ceil($left / 60)) . ' λεπτά.'];
    }
    $u = user_by_email($email);
    if (!$u || !password_verify($password, $u['password_hash'])) {
        login_note_failure($email, $ip);
        return ['success' => false, 'error' => 'Λάθος email ή κωδικός'];
    }
    login_note_success($email, $ip);
    // Ανεπιβεβαίωτο email: μπλοκάρει ΠΡΙΝ από την έγκριση, γιατί μια εγγραφή με
    // λάθος (ή ξένο) email δεν πρέπει καν να φτάσει στον διαχειριστή. Ο έλεγχος
    // κοιτάζει και το token: λογαριασμοί που δημιουργήθηκαν πριν υπάρξει η
    // επαλήθευση δεν έχουν token, και συνεχίζουν να μπαίνουν κανονικά.
    if ((int)($u['email_verified'] ?? 1) === 0 && trim((string)($u['verify_token'] ?? '')) !== '') {
        return ['success' => false, 'needs_verification' => true, 'email' => $u['email'],
                'error' => 'Επιβεβαιώστε πρώτα το email σας — σας στείλαμε σύνδεσμο κατά την εγγραφή'];
    }
    if ($u['status'] === 'pending')  return ['success' => false, 'error' => 'Ο λογαριασμός εκκρεμεί έγκριση από τον διαχειριστή'];
    if ($u['status'] === 'invited')  return ['success' => false, 'error' => 'Ολοκληρώστε πρώτα την ενεργοποίηση από τον σύνδεσμο στο email σας'];
    if ($u['status'] === 'disabled') return ['success' => false, 'error' => 'Ο λογαριασμός είναι απενεργοποιημένος'];
    unset($_SESSION['uid']);
    // Optional 2FA: password OK but an authenticator code is still required. Park a
    // short-lived pending id in the session (never expose the uid to the client).
    if ((int)($u['totp_enabled'] ?? 0) === 1) {
        $_SESSION['pending_2fa_uid'] = (int)$u['id'];
        $_SESSION['pending_2fa_at']  = time();
        return ['success' => false, 'totp_required' => true];
    }
    // NB: we deliberately do NOT session_regenerate_id() here (see history): the fetch
    // login + location.href navigation can drop a regenerated cookie. Reusing the id
    // keeps login robust.
    $_SESSION['uid'] = (int)$u['id'];
    if (function_exists('audit_log_add')) audit_log_add((int)$u['id'], '', 'login');
    return ['success' => true, 'user' => user_public($u)];
}

// Second login step when 2FA is enabled: verify the authenticator code against
// the pending user parked by auth_login().
function auth_login_totp(string $code): array {
    $uid = (int)($_SESSION['pending_2fa_uid'] ?? 0);
    $at  = (int)($_SESSION['pending_2fa_at'] ?? 0);
    if ($uid <= 0 || $at <= 0 || (time() - $at) > 300) {
        unset($_SESSION['pending_2fa_uid'], $_SESSION['pending_2fa_at']);
        return ['success' => false, 'error' => 'Η συνεδρία επαλήθευσης έληξε — συνδεθείτε ξανά'];
    }
    $u = user_by_id($uid);
    if (!$u || (int)($u['totp_enabled'] ?? 0) !== 1) {
        unset($_SESSION['pending_2fa_uid'], $_SESSION['pending_2fa_at']);
        return ['success' => false, 'error' => 'Μη έγκυρη συνεδρία'];
    }
    if (!totp_verify(dec($u['totp_secret'] ?? ''), $code)) {
        return ['success' => false, 'error' => 'Λάθος κωδικός authenticator'];
    }
    unset($_SESSION['pending_2fa_uid'], $_SESSION['pending_2fa_at']);
    $_SESSION['uid'] = (int)$u['id'];
    if (function_exists('audit_log_add')) audit_log_add((int)$u['id'], '', 'login_2fa');
    return ['success' => true, 'user' => user_public($u)];
}

function auth_logout(): void {
    if (function_exists('audit_log_add') && !empty($_SESSION['uid'])) {
        audit_log_add((int)$_SESSION['uid'], '', 'logout');
    }
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $p = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'], $p['secure'], $p['httponly']);
    }
    session_destroy();
}

// --- Signup (public, pending approval) --------------------------------------
function auth_signup(string $email, string $password, string $businessName, string $joinToken = ''): array {
    $email = strtolower(trim($email));
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) return ['success' => false, 'error' => 'Μη έγκυρο email'];
    if (strlen($password) < 8) return ['success' => false, 'error' => 'Ο κωδικός πρέπει να έχει ≥ 8 χαρακτήρες'];
    if (trim($businessName) === '') return ['success' => false, 'error' => 'Λείπει η επωνυμία επιχείρησης'];
    if (user_by_email($email)) return ['success' => false, 'error' => 'Υπάρχει ήδη λογαριασμός με αυτό το email'];
    // Εγγραφή μέσα από σύνδεσμο κλειδιού: ο διαχειριστής έχει ήδη εγγυηθεί γι'
    // αυτόν τον χρήστη εκδίδοντας το κλειδί, οπότε δεν ξαναμπαίνει σε ουρά
    // έγκρισης — αρκεί να αποδείξει ότι το email είναι δικό του.
    $join = ($joinToken !== '' && function_exists('access_key_by_claim'))
        ? access_key_by_claim($joinToken) : null;
    $id = user_create($email, password_hash($password, PASSWORD_DEFAULT), 'business', 'pending', $businessName);
    if ($join) access_key_set_claimed((int)$join['id'], $id);
    // Πρώτα επαλήθευση email, ΜΕΤΑ έγκριση. Ο διαχειριστής ειδοποιείται μόνο
    // όταν αποδειχθεί ότι το email υπάρχει και ανήκει σε αυτόν που εγγράφηκε —
    // αλλιώς η ουρά εγκρίσεων γεμίζει με τυπογραφικά λάθη και ψεύτικες εγγραφές.
    $token = bin2hex(random_bytes(24));
    user_update($id, ['verify_token' => $token, 'verify_expires' => time() + 24 * 3600, 'email_verified' => 0]);
    $sent = auth_email_verification($email, trim($businessName), $token);
    return [
        'success' => true, 'id' => $id, 'verification_sent' => $sent,
        'note' => $sent
            ? 'Σας στείλαμε email επιβεβαίωσης. Ανοίξτε τον σύνδεσμο για να ολοκληρωθεί η εγγραφή.'
            : 'Η εγγραφή καταχωρήθηκε, αλλά δεν στάλθηκε email επιβεβαίωσης — επικοινωνήστε με τον διαχειριστή.',
    ];
}

// --- Email verification -----------------------------------------------------
// Ο σύνδεσμος οδηγεί στο app.php, που καλεί πίσω το `auth=verify_email`.
function auth_verify_link(string $token): string {
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    return $scheme . '://' . $host . dirname($_SERVER['SCRIPT_NAME'] ?? '/') . '/app.php?verify=' . urlencode($token);
}

function auth_verify_email(string $token): array {
    $token = trim($token);
    if ($token === '') return ['success' => false, 'error' => 'Λείπει το token'];
    $st = localdb()->prepare("SELECT * FROM users WHERE verify_token = :t");
    $st->execute([':t' => $token]);
    $u = $st->fetch();
    if (!$u) return ['success' => false, 'error' => 'Ο σύνδεσμος δεν ισχύει (ή έχει ήδη χρησιμοποιηθεί)'];
    if ((int)$u['verify_expires'] < time()) {
        return ['success' => false, 'expired' => true, 'email' => $u['email'],
                'error' => 'Ο σύνδεσμος έληξε — ζητήστε νέο'];
    }
    user_update((int)$u['id'], ['email_verified' => 1, 'verify_token' => '', 'verify_expires' => 0]);

    // Ήρθε από σύνδεσμο κλειδιού; Τότε η έγκριση έχει ήδη δοθεί — από τη στιγμή
    // που ο διαχειριστής εξέδωσε το κλειδί. Ενεργοποιείται αμέσως και παίρνει
    // ό,τι ανέβηκε στο όνομά του όσο περίμενε.
    $key = function_exists('access_key_by_claimed_uid') ? access_key_by_claimed_uid((int)$u['id']) : null;
    if ($key) {
        user_update((int)$u['id'], ['status' => 'active']);
        $moved = auth_claim_deliver((int)$u['id']);
        return ['success' => true, 'activated' => true, 'companies' => $moved,
                'note' => $moved > 0
                    ? ('Το email επιβεβαιώθηκε. Ο λογαριασμός είναι ενεργός και '
                       . $moved . ' εταιρεί' . ($moved === 1 ? 'α είναι' : 'ες είναι') . ' ήδη μέσα.')
                    : 'Το email επιβεβαιώθηκε. Ο λογαριασμός είναι ενεργός — μπες κανονικά.'];
    }

    // Τώρα, και μόνο τώρα, μπαίνει στην ουρά των εγκρίσεων.
    if ($u['status'] === 'pending') auth_email_admins_new_signup($u['email'], (string)$u['business_name']);
    return ['success' => true, 'note' => 'Το email επιβεβαιώθηκε. Ο λογαριασμός εκκρεμεί έγκριση από τον διαχειριστή.'];
}

// Νέος σύνδεσμος επαλήθευσης. Απαντά πάντα το ίδιο, ώστε να μην αποκαλύπτει
// ποια email υπάρχουν στο σύστημα.
function auth_resend_verification(string $email): array {
    $u = user_by_email(trim($email));
    if ($u && (int)($u['email_verified'] ?? 1) === 0) {
        $token = bin2hex(random_bytes(24));
        user_update((int)$u['id'], ['verify_token' => $token, 'verify_expires' => time() + 24 * 3600]);
        auth_email_verification($u['email'], (string)$u['business_name'], $token);
    }
    return ['success' => true, 'note' => 'Αν εκκρεμεί επαλήθευση, στάλθηκε νέος σύνδεσμος.'];
}

// --- Member invitations (admin/editor/business) -----------------------------
// A master admin invites a colleague by email for a given role. Creates the user
// in 'invited' status with an activation token and emails an activation link
// where they set their password. On activation the user becomes 'active'.
function auth_invite(string $email, string $role, string $displayName, int $invitedBy): array {
    $email = strtolower(trim($email));
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) return ['success' => false, 'error' => 'Μη έγκυρο email'];
    $role = in_array($role, ['master', 'editor', 'business'], true) ? $role : 'editor';
    if (user_by_email($email)) return ['success' => false, 'error' => 'Υπάρχει ήδη λογαριασμός με αυτό το email'];
    // A random throwaway password (the invitee sets their own via the token).
    $tmpHash = password_hash(bin2hex(random_bytes(16)), PASSWORD_DEFAULT);
    $name = $displayName !== '' ? $displayName : ($role === 'business' ? '' : 'Συνεργάτης');
    $id = user_create($email, $tmpHash, $role, 'invited', $name);
    $token = bin2hex(random_bytes(24));
    user_update($id, ['reset_token' => $token, 'reset_expires' => time() + 7 * 86400, 'invited_by' => $invitedBy]);
    $emailed = auth_email_invitation($email, $token, $role);
    return [
        'success'    => true,
        'id'         => $id,
        'emailed'    => $emailed,
        'invite_link' => auth_reset_link($token),   // shown to admin as an offline fallback
        'note'       => $emailed ? 'Η πρόσκληση στάλθηκε στο email.' : 'Η πρόσκληση δημιουργήθηκε (χωρίς email — δώστε τον σύνδεσμο χειροκίνητα).',
    ];
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
    // An 'invited' user completing this flow becomes active; a 'pending' signup
    // stays pending (still needs admin approval); others stay as-is.
    $newStatus = $u['status'];
    if ($u['status'] === 'invited') $newStatus = 'active';
    elseif ($u['status'] === 'pending') $newStatus = 'pending';
    else $newStatus = 'active';
    user_update((int)$u['id'], [
        'password_hash' => password_hash($newPassword, PASSWORD_DEFAULT),
        'reset_token' => '', 'reset_expires' => 0,
        'status' => $newStatus,
    ]);
    return ['success' => true, 'note' => 'Ο κωδικός ενημερώθηκε.', 'activated' => $u['status'] === 'invited'];
}

function auth_reset_link(string $token): string {
    // Μέσω app_base_url(): προτιμά το APP_URL της εγκατάστασης και πέφτει στο
    // τρέχον αίτημα μόνο αν λείπει. Το προηγούμενο «φτιάξ' το από το Host»
    // σήμαινε ότι ένας πλαστός Host σε αίτημα «ξέχασα τον κωδικό» έστελνε στο
    // θύμα σύνδεσμο επαναφοράς προς ξένο domain.
    return app_base_url() . '/app.php?reset=' . urlencode($token);
}

// ---------------------------------------------------------------------------
// Τα μηνύματα του λογαριασμού, στη γλώσσα σχεδίασης του ScanmyData: κουμπί,
// πλαίσιο «τι γίνεται μετά», πλαίσιο προσοχής με την προθεσμία, και πάντα το
// URL σε απλό κείμενο — αρκετοί email clients δεν εμφανίζουν κουμπιά.
// ---------------------------------------------------------------------------

function auth_send_reset_email(string $to, string $token): bool {
    $link = auth_reset_link($token);
    $inner = '<p>Λάβαμε αίτημα επαναφοράς του κωδικού σας στο <strong>e-Τιμολόγιο Pro</strong>.</p>'
        . '<p>Πατήστε το κουμπί για να ορίσετε νέο κωδικό:</p>'
        . mail_button('Επαναφορά κωδικού', $link)
        . mail_note('Η διαδικασία', [
            '1. Ανοίξτε τον σύνδεσμο',
            '2. Γράψτε νέο κωδικό (τουλάχιστον 8 χαρακτήρες)',
            '3. Συνδεθείτε με τα νέα στοιχεία',
          ])
        . mail_warn('Σημαντικό', [
            'Ο σύνδεσμος ισχύει για 1 ώρα από την αποστολή',
            'Αν δεν ζητήσατε επαναφορά, αγνοήστε το μήνυμα — ο κωδικός σας μένει ίδιος',
          ])
        . mail_link_fallback($link);
    return send_mail($to, 'Επαναφορά κωδικού — e-Τιμολόγιο Pro', mail_template('🔐 Επαναφορά κωδικού', $inner));
}

// Επαλήθευση email στην εγγραφή (ισχύς 24 ώρες).
function auth_email_verification(string $to, string $businessName, string $token): bool {
    if (!mail_enabled()) return false;
    $link = auth_verify_link($token);
    $who = trim($businessName) !== '' ? htmlspecialchars(trim($businessName), ENT_QUOTES) : 'στο e-Τιμολόγιο Pro';
    $inner = '<p>Καλώς ήρθατε, <strong>' . $who . '</strong>.</p>'
        . '<p>Για να ολοκληρωθεί η εγγραφή σας, επιβεβαιώστε ότι αυτή η διεύθυνση email είναι δική σας:</p>'
        . mail_button('Επιβεβαίωση email', $link)
        . mail_note('Τι θα γίνει μετά', [
            'Το email σας καταχωρείται ως επιβεβαιωμένο',
            'Η εγγραφή προωθείται στον διαχειριστή για έγκριση',
            'Θα λάβετε νέο μήνυμα μόλις ενεργοποιηθεί ο λογαριασμός',
          ])
        . mail_warn('Σημαντικό', [
            'Ο σύνδεσμος ισχύει για 24 ώρες',
            'Αν δεν κάνατε εσείς την εγγραφή, αγνοήστε αυτό το μήνυμα',
          ])
        . mail_link_fallback($link);
    return send_mail($to, 'Επιβεβαίωση email — e-Τιμολόγιο Pro', mail_template('✅ Επιβεβαίωση email', $inner));
}

// Activation link for an invited member (7-day validity — same token mechanism).
function auth_email_invitation(string $to, string $token, string $role): bool {
    $link = auth_reset_link($token);
    $roleL = ['master' => 'Διαχειριστής (πλήρη δικαιώματα)', 'editor' => 'Λογιστής/Επεξεργαστής', 'business' => 'Χρήστης επιχείρησης'][$role] ?? $role;
    $inner = '<p>Προσκληθήκατε στην εφαρμογή <strong>e-Τιμολόγιο Pro</strong>.</p>'
        . mail_kv([['Ρόλος', $roleL], ['Email σύνδεσης', $to]])
        . '<p>Ενεργοποιήστε τον λογαριασμό σας ορίζοντας κωδικό:</p>'
        . mail_button('Ενεργοποίηση λογαριασμού', $link)
        . mail_warn('Σημαντικό', [
            'Ο σύνδεσμος ισχύει για 7 ημέρες',
            'Αν δεν αναγνωρίζετε αυτή την πρόσκληση, αγνοήστε το μήνυμα',
          ])
        . mail_link_fallback($link);
    return send_mail($to, 'Πρόσκληση στο e-Τιμολόγιο Pro', mail_template('🤝 Πρόσκληση συνεργάτη', $inner));
}

// Notify the admins that a new signup awaits approval.
function auth_email_admins_new_signup(string $applicantEmail, string $businessName): void {
    if (!mail_enabled()) return;
    $inner = '<p>Μια νέα εγγραφή επιβεβαίωσε το email της και περιμένει έγκριση:</p>'
        . mail_kv([['Επωνυμία', $businessName], ['Email', $applicantEmail], ['Ημ/νία', date('d/m/Y H:i')]])
        . '<p>Εγκρίνετέ την από τη <strong>Διαχείριση</strong> της εφαρμογής.</p>'
        . mail_button('Άνοιγμα εφαρμογής', app_base_url() . '/app.php');
    foreach (auth_admin_emails() as $adminEmail) {
        send_mail($adminEmail, 'Νέα εγγραφή προς έγκριση — e-Τιμολόγιο Pro', mail_template('📥 Νέα εγγραφή', $inner));
    }
}

// Notify a user that their account was approved/activated by an admin.
function auth_email_account_approved(string $to, string $businessName): bool {
    if (!mail_enabled()) return false;
    $inner = '<p>Ο λογαριασμός της επιχείρησης <strong>' . htmlspecialchars($businessName, ENT_QUOTES) . '</strong> ενεργοποιήθηκε.</p>'
        . '<p>Μπορείτε πλέον να συνδεθείτε στην εφαρμογή.</p>'
        . mail_button('Σύνδεση', app_base_url() . '/app.php')
        . mail_note('Καλό ξεκίνημα', [
            'Καταχωρήστε τα διαπιστευτήρια ΑΑΔΕ στις Ρυθμίσεις',
            'Προσθέστε τους λογαριασμούς σας ώστε να μπαίνουν στα email καρτέλας',
            'Η «Ξενάγηση» στο πλαϊνό μενού δείχνει τα βασικά σε ένα λεπτό',
          ]);
    return send_mail($to, 'Ο λογαριασμός σας ενεργοποιήθηκε — e-Τιμολόγιο Pro', mail_template('🎉 Λογαριασμός ενεργός', $inner));
}

// Emails of all master/editor staff (for admin notifications). Falls back to
// MASTER_ADMIN_EMAIL / NOTIFY_ADMIN_EMAIL config.
function auth_admin_emails(): array {
    $out = [];
    foreach (users_all() as $u) {
        if (in_array($u['role'], ['master', 'editor'], true) && $u['status'] === 'active' && $u['email'] !== '') {
            $out[] = $u['email'];
        }
    }
    if (defined('NOTIFY_ADMIN_EMAIL') && trim(NOTIFY_ADMIN_EMAIL) !== '' && trim(NOTIFY_ADMIN_EMAIL) !== '-') $out[] = trim(NOTIFY_ADMIN_EMAIL);
    if (defined('MASTER_ADMIN_EMAIL') && trim(MASTER_ADMIN_EMAIL) !== '') $out[] = trim(MASTER_ADMIN_EMAIL);
    return array_values(array_unique(array_filter($out)));
}

// --- Optional 2FA (authenticator TOTP) --------------------------------------
// Begin enrollment: create (or reuse) a secret for the current user, stored
// encrypted but NOT yet enabled, and return the otpauth URI + manual key so the
// UI can render a QR. Enrollment is confirmed by auth_totp_enable().
function auth_totp_setup(): array {
    $u = current_user();
    if (!$u) return ['success' => false, 'error' => 'Απαιτείται σύνδεση'];
    if ((int)($u['totp_enabled'] ?? 0) === 1) return ['success' => false, 'error' => 'Το 2FA είναι ήδη ενεργό'];
    $secret = totp_generate_secret();
    user_update((int)$u['id'], ['totp_secret' => enc($secret), 'totp_enabled' => 0]);
    return [
        'success' => true,
        'secret'  => $secret,
        'otpauth' => totp_uri($secret, $u['email'], auth_totp_issuer()),
        // Ο ΚΩΔΙΚΑΣ ΕΡΧΕΤΑΙ ΕΤΟΙΜΟΣ. Τον έφτιαχνε ο browser με βιβλιοθήκη από
        // CDN, την οποία η πολιτική περιεχομένου του ίδιου του server
        // (`script-src 'self'`) δεν επέτρεπε να φορτώσει: ούτε σφάλμα, ούτε
        // κωδικός — ένα κενό τετράγωνο. Δες `qrcode.php`.
        'qr_svg'  => function_exists('qr_svg') ? qr_svg(totp_uri($secret, $u['email'], auth_totp_issuer())) : '',
        'issuer'  => auth_totp_issuer(),
    ];
}

/**
 * Το όνομα που θα δει ο χρήστης μέσα στην εφαρμογή authenticator.
 *
 * Σκέτο «e-Timologio Pro» είναι άχρηστο όταν έχεις δύο εγκαταστάσεις (π.χ. τον
 * υπολογιστή του γραφείου και τον server): δύο πανομοιότυπες γραμμές, και δεν
 * ξέρεις ποιος κωδικός πάει πού. Προσθέτουμε πού ζει η εγκατάσταση.
 */
function auth_totp_issuer(): string {
    if (defined('DESKTOP_TOKEN') && DESKTOP_TOKEN !== '') {
        $where = (string)(getenv('COMPUTERNAME') ?: gethostname());
    } else {
        $where = (string)(parse_url(function_exists('app_base_url') ? app_base_url() : '', PHP_URL_HOST)
                          ?: ($_SERVER['HTTP_HOST'] ?? ''));
    }
    // ΜΟΝΟ ASCII: το όνομα ταξιδεύει μέσα σε QR και το διαβάζουν εφαρμογές που
    // δεν χειρίζονται όλες σωστά ελληνικά ή τυπογραφικά σύμβολα. Το όνομα του
    // υπολογιστή (ή του host) είναι ούτως ή άλλως λατινικό και αρκεί για να
    // ξεχωρίσεις δύο εγκαταστάσεις μέσα στο authenticator.
    $where = trim(preg_replace('/[^A-Za-z0-9._-]+/', '', $where));
    return 'e-Timologio Pro' . ($where !== '' ? ' (' . $where . ')' : '');
}

function auth_totp_enable(string $code): array {
    $u = current_user();
    if (!$u) return ['success' => false, 'error' => 'Απαιτείται σύνδεση'];
    $secret = dec($u['totp_secret'] ?? '');
    if ($secret === '') return ['success' => false, 'error' => 'Ξεκινήστε πρώτα τη ρύθμιση 2FA'];
    if (!totp_verify($secret, $code)) return ['success' => false, 'error' => 'Λάθος κωδικός — δοκιμάστε ξανά'];
    user_update((int)$u['id'], ['totp_enabled' => 1]);
    return ['success' => true, 'note' => 'Το 2FA ενεργοποιήθηκε.'];
}

function auth_totp_disable(string $verify): array {
    $u = current_user();
    if (!$u) return ['success' => false, 'error' => 'Απαιτείται σύνδεση'];
    if ((int)($u['totp_enabled'] ?? 0) !== 1) return ['success' => true, 'note' => 'Το 2FA δεν ήταν ενεργό.'];
    // Accept either the current authenticator code or the account password.
    $ok = totp_verify(dec($u['totp_secret'] ?? ''), $verify) || password_verify($verify, $u['password_hash']);
    if (!$ok) return ['success' => false, 'error' => 'Απαιτείται έγκυρος κωδικός authenticator ή ο κωδικός σας'];
    user_update((int)$u['id'], ['totp_secret' => '', 'totp_enabled' => 0]);
    return ['success' => true, 'note' => 'Το 2FA απενεργοποιήθηκε.'];
}

/**
 * Οι εταιρείες που «βλέπει» ένας χρήστης, ΜΕ διαπιστευτήρια.
 *
 * Τρία επίπεδα, και η διαφορά τους είναι ολόκληρο το μοντέλο πρόσβασης:
 *   - **Διαχειριστής** (master): κάθε εταιρεία της εγκατάστασης.
 *   - **Λογιστής** (editor): μόνο όσες του έχουν ανατεθεί ρητά. Παλιότερα έβλεπε
 *     κι αυτός τα πάντα — σε γραφείο με πολλούς λογιστές αυτό σημαίνει ότι ο
 *     καθένας έβλεπε τους πελάτες των υπολοίπων.
 *   - **Επιχείρηση** (business): μόνο τις δικές της.
 */
function auth_accounts_in_scope(array $u): array {
    $role = (string)($u['role'] ?? 'business');
    if ($role === 'master')  return accounts_all_full();
    if ($role === 'editor')  return accounts_for_manager((int)$u['id']);
    return accounts_for_user((int)$u['id']);
}

/** Τα ΑΦΜ που βλέπει ο χρήστης — το φίλτρο για ειδοποιήσεις/προγραμματισμό. */
function auth_scope_vats(array $u): array {
    return array_values(array_map(fn($a) => (string)$a['vat'], auth_accounts_in_scope($u)));
}

/**
 * Το φίλτρο εταιρείας για τα τοπικά δεδομένα: `''` για τον διαχειριστή (όλα),
 * αλλιώς η λίστα των ΑΦΜ που δικαιούται ο χρήστης.
 */
function auth_data_scope(array $u) {
    return ((string)($u['role'] ?? '') === 'master') ? '' : auth_scope_vats($u);
}

/** Οι εταιρείες που βλέπει ο χρήστης, ΧΩΡΙΣ διαπιστευτήρια (ασφαλές για το UI). */
function auth_visible_accounts(array $u): array {
    return array_map(function ($a) {
        unset($a['subkey'], $a['username']);
        return $a;
    }, auth_accounts_in_scope($u));
}

/** Επιτρέπεται σε αυτόν τον χρήστη να δουλέψει με αυτό το ΑΦΜ; */
function auth_may_access_vat(array $u, string $vat): bool {
    $vat = preg_replace('/\D/', '', $vat);
    if ($vat === '') return false;
    foreach (auth_accounts_in_scope($u) as $a) {
        if ((string)$a['vat'] === $vat) return true;
    }
    return false;
}

// --- Active AADE account resolution (defines the bridge constants) ----------
// Called once per request after the user is known. Picks the account by the
// `account` param (VAT) among the user's own accounts, else the first.
function auth_resolve_account(): ?array {
    $u = current_user();
    if (!$u) return null;
    $accounts = auth_accounts_in_scope($u);
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

/**
 * Διεύθυνση στατικού αρχείου, με σφραγίδα έκδοσης.
 *
 * ⚠️ ΓΙΑΤΙ ΥΠΑΡΧΕΙ. Τα εικονίδια και τα λογότυπα σερβίρονται με
 * `Cache-Control: public, max-age=86400` (deploy/apache-etimologio.conf) και
 * μπροστά τους κάθεται η Cloudflare. Όταν άλλαξαν τα σήματα των δύο εφαρμογών,
 * οι διευθύνσεις έμειναν ίδιες — και το web συνέχισε να δείχνει το ΠΑΛΙΟ
 * λογότυπο: μια ολόκληρη μέρα από την άκρη του δικτύου (`cf-cache-status: HIT`)
 * και αόριστα σε κάθε browser που το είχε ήδη κατεβάσει. Ο κώδικας ήταν σωστός,
 * η εικόνα λάθος, και τίποτα στον server δεν το έδειχνε.
 *
 * Η σφραγίδα είναι ο χρόνος τροποποίησης του αρχείου: αλλάζει μόνη της μόλις
 * αλλάξει το σχέδιο και μένει σταθερή όσο δεν αλλάζει, οπότε η cache συνεχίζει
 * να δουλεύει κανονικά.
 */
function asset_url(string $path): string {
    static $stamps = [];
    if (!isset($stamps[$path])) {
        $full = __DIR__ . '/' . ltrim($path, '/');
        $stamps[$path] = is_file($full) ? (string)filemtime($full) : '0';
    }
    return $path . '?v=' . $stamps[$path];
}

/**
 * Αυτόματη σύνδεση της εφαρμογής υπολογιστή στο δικό της backend.
 *
 * Η desktop εφαρμογή φιλοξενεί ΤΟ ΙΔΙΟ `app.php` μέσα σε ενσωματωμένο browser,
 * πάνω στον PHP server που ξεκινά η ίδια. Ο χρήστης έχει ήδη ανοίξει την
 * εφαρμογή του — δεν υπάρχει λόγος να ξαναδώσει κωδικό, και ο κωδικός αυτός
 * παράγεται ούτως ή άλλως από την εφαρμογή (δες `bootstrap_credentials`).
 *
 * Τρεις φραγμοί, γιατί αυτό ΠΑΡΑΚΑΜΠΤΕΙ τη σύνδεση:
 *   1. Το `DESKTOP_TOKEN` υπάρχει μόνο στο config που γράφει η ίδια η εφαρμογή
 *      (ποτέ σε server εγκατάσταση — εκεί η σταθερά απλώς δεν ορίζεται).
 *   2. Ο καλών πρέπει να είναι loopback.
 *   3. Σύγκριση με `hash_equals`, όχι `==`.
 */
function auth_desktop_autologin(): void {
    if (!defined('DESKTOP_TOKEN') || DESKTOP_TOKEN === '') return;
    if (!empty($_SESSION['uid'])) return;
    $token = (string)($_GET['desktop_token'] ?? $_POST['desktop_token'] ?? '');
    if ($token === '' || !hash_equals((string)DESKTOP_TOKEN, $token)) return;
    if (!req_is_loopback()) return;
    // Μπαίνουμε ως ΛΟΓΙΣΤΗΣ, όχι ως διαχειριστής: η καθημερινή δουλειά δεν
    // χρειάζεται δικαιώματα που σβήνουν χρήστες και διαβάζουν κλειδιά. Ο
    // διαχειριστής μπαίνει ρητά, με κωδικό (και 2FA), από την «Αποσύνδεση».
    $uid = auth_desktop_workspace_user();
    if ($uid > 0) $_SESSION['uid'] = $uid;
}

//: Ο λογαριασμός εργασίας της τοπικής εγκατάστασης.
const DESKTOP_WORKSPACE_EMAIL = 'logistis@localhost';

/**
 * Ο λογιστής της τοπικής εγκατάστασης — δημιουργείται μία φορά και κρατιέται
 * συγχρονισμένος με τις εταιρείες.
 *
 * Ο ρόλος `editor` βλέπει **μόνο** όσες εταιρείες του έχουν ανατεθεί. Σε μια
 * εγκατάσταση ενός χρήστη αυτό θα σήμαινε άδεια εφαρμογή, γι' αυτό του
 * ανατίθενται όλες όσες υπάρχουν — και όποιες προστεθούν αργότερα, στην
 * επόμενη εκκίνηση του κελύφους.
 */
function auth_desktop_workspace_user(): int {
    $u = user_by_email(DESKTOP_WORKSPACE_EMAIL);
    if (!$u) {
        // Τυχαίος κωδικός: σε αυτόν τον λογαριασμό μπαίνει κανείς μόνο μέσα από
        // την ίδια την εφαρμογή, ποτέ με πληκτρολόγηση.
        $id = user_create(DESKTOP_WORKSPACE_EMAIL, password_hash(bin2hex(random_bytes(16)), PASSWORD_DEFAULT),
                          'editor', 'active', 'Λογιστής');
        $u = user_by_id($id);
    }
    if (!$u) return 0;
    if ($u['status'] === 'disabled') return 0;
    try {
        $all = [];
        foreach (localdb()->query("SELECT id FROM aade_accounts")->fetchAll() as $a) $all[] = (int)$a['id'];
        $have = manager_account_ids((int)$u['id']);
        if (array_diff($all, $have)) manager_set_accounts((int)$u['id'], $all);
    } catch (\Throwable $e) { /* η ανάθεση δεν είναι λόγος να μη σηκωθεί η εφαρμογή */ }
    return (int)$u['id'];
}

/**
 * Σύνδεση με **κλειδί πρόσβασης** (μηχανή προς μηχανή, χωρίς cookie).
 *
 * Το ίδιο κλειδί που δίνει ο διαχειριστής για να δεθεί μια εγκατάσταση γραφείου
 * (`access_keys`) χρησιμεύει και ως διαπιστευτήριο στις κλήσεις συγχρονισμού:
 * εκεί δεν υπάρχει browser για να κρατήσει συνεδρία. Δεν αντικαθιστά τη
 * σύνδεση χρήστη — απλώς ταυτίζει τον ίδιο λογαριασμό.
 */
function auth_access_key_login(): void {
    if (!empty($_SESSION['uid'])) return;                 // ήδη συνδεδεμένος
    $key = '';
    $hdr = (string)($_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '');
    if (stripos($hdr, 'bearer ') === 0) $key = trim(substr($hdr, 7));
    if ($key === '') $key = trim((string)($_POST['access_key'] ?? $_GET['access_key'] ?? ''));
    if ($key === '') return;

    $u = access_key_user($key);
    if (!$u || ($u['status'] ?? '') !== 'active') return;
    $_SESSION['uid'] = (int)$u['id'];
    $GLOBALS['__access_key_user'] = (int)$u['id'];
    // ΠΟΙΟ κλειδί, όχι μόνο ποιος χρήστης: όσα ανεβαίνουν μέσα από ένα κλειδί
    // πρέπει να μπορούν να παραδοθούν σε αυτόν που θα το διεκδικήσει, και
    // μόνο σε αυτόν. Χωρίς την ταυτότητα του κλειδιού δεν ξεχωρίζουν από τα
    // βιβλία των υπολοίπων πελατών του ίδιου διαχειριστή.
    $row = function_exists('access_key_row') ? access_key_row($key) : null;
    $GLOBALS['__access_key_id'] = (int)($row['id'] ?? 0);
}

/** Ταυτοποιήθηκε αυτό το αίτημα με κλειδί πρόσβασης; */
function auth_by_access_key(): bool { return !empty($GLOBALS['__access_key_user']); }

/** Με ΠΟΙΟ κλειδί πρόσβασης ήρθε αυτό το αίτημα (0 = με κανένα). */
function auth_access_key_id(): int { return (int)($GLOBALS['__access_key_id'] ?? 0); }

/**
 * Ο πελάτης ολοκλήρωσε την εγγραφή του — πάρε ό,τι ανέβηκε στο όνομά του.
 *
 * Μέχρι εδώ οι εταιρείες του ζούσαν κάτω από τον λογαριασμό που εξέδωσε το
 * κλειδί: **προσωρινή στέγη**, γιατί τα δεδομένα δεν επιτρέπεται να περιμένουν
 * σε καμία ουρά μέχρι να θυμηθεί κάποιος να κάνει εγγραφή. Τώρα αλλάζουν
 * κάτοχο, μία-μία, και μόνο όσες ήρθαν από ΑΥΤΟ το κλειδί.
 *
 * Καλείται από την επιβεβαίωση email: πριν από αυτήν δεν ξέρουμε καν ότι ο
 * παραλήπτης είναι εκείνος που λέει.
 */
function auth_claim_deliver(int $uid): int {
    if ($uid <= 0 || !function_exists('access_key_by_claimed_uid')) return 0;
    $key = access_key_by_claimed_uid($uid);
    if (!$key) return 0;
    $moved = 0;
    foreach (access_key_vats((int)$key['id']) as $vat) {
        $a = account_by_vat($vat);
        if (!$a) continue;
        account_set_owner((int)$a['id'], $uid);
        $moved++;
    }
    // Και το ίδιο το κλειδί δένει πια στον δικό του λογαριασμό: ο επόμενος
    // συγχρονισμός γράφει κατευθείαν εκεί, χωρίς ενδιάμεσο.
    access_key_bind((int)$key['id'], $uid);
    return $moved;
}

// Run bootstrap + migration + account resolution on include (safe, no output).
auth_bootstrap();
auth_migrate_legacy_accounts();
auth_desktop_autologin();
auth_access_key_login();
auth_resolve_account();
