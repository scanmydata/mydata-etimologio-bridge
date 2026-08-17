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

function auth_login(string $email, string $password): array {
    $u = user_by_email($email);
    if (!$u || !password_verify($password, $u['password_hash'])) {
        return ['success' => false, 'error' => 'Λάθος email ή κωδικός'];
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
    // Acknowledge to the applicant + notify the admins that an approval is pending.
    auth_email_signup_ack($email, trim($businessName));
    auth_email_admins_new_signup($email, trim($businessName));
    return ['success' => true, 'id' => $id, 'note' => 'Η εγγραφή καταχωρήθηκε και εκκρεμεί έγκριση από τον διαχειριστή.'];
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
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    return $scheme . '://' . $host . dirname($_SERVER['SCRIPT_NAME'] ?? '/') . '/app.php?reset=' . urlencode($token);
}

function auth_send_reset_email(string $to, string $token): bool {
    $link = auth_reset_link($token);
    $inner = '<p>Λάβαμε αίτημα επαναφοράς του κωδικού σας.</p>'
        . '<p>Πατήστε το κουμπί για να ορίσετε νέο κωδικό (ο σύνδεσμος ισχύει για 1 ώρα):</p>'
        . mail_button('Επαναφορά κωδικού', $link)
        . '<p style="color:#5b6b84;font-size:13px;margin-top:18px">Αν δεν ζητήσατε επαναφορά, αγνοήστε αυτό το μήνυμα — ο κωδικός σας παραμένει ίδιος.</p>';
    return send_mail($to, 'Επαναφορά κωδικού — e-Τιμολόγιο Pro', mail_template('Επαναφορά κωδικού', $inner));
}

// Activation link for an invited member (7-day validity — same token mechanism).
function auth_email_invitation(string $to, string $token, string $role): bool {
    $link = auth_reset_link($token);
    $roleL = ['master' => 'Διαχειριστής (πλήρη δικαιώματα)', 'editor' => 'Λογιστής/Επεξεργαστής', 'business' => 'Χρήστης επιχείρησης'][$role] ?? $role;
    $inner = '<p>Προσκληθήκατε στην εφαρμογή <strong>e-Τιμολόγιο Pro</strong>.</p>'
        . '<p>Ρόλος: <strong>' . htmlspecialchars($roleL, ENT_QUOTES) . '</strong></p>'
        . '<p>Ενεργοποιήστε τον λογαριασμό σας ορίζοντας κωδικό (ο σύνδεσμος ισχύει για 7 ημέρες):</p>'
        . mail_button('Ενεργοποίηση λογαριασμού', $link)
        . '<p style="color:#5b6b84;font-size:13px;margin-top:18px">Αν δεν αναγνωρίζετε αυτή την πρόσκληση, αγνοήστε το μήνυμα.</p>';
    return send_mail($to, 'Πρόσκληση στο e-Τιμολόγιο Pro', mail_template('Πρόσκληση συνεργάτη', $inner));
}

// Acknowledge a public signup to the applicant.
function auth_email_signup_ack(string $to, string $businessName): bool {
    if (!mail_enabled()) return false;
    $inner = '<p>Λάβαμε την εγγραφή της επιχείρησης <strong>' . htmlspecialchars($businessName, ENT_QUOTES) . '</strong>.</p>'
        . '<p>Ο λογαριασμός σας <strong>εκκρεμεί έγκριση</strong> από τον διαχειριστή. Θα ειδοποιηθείτε μόλις ενεργοποιηθεί.</p>';
    return send_mail($to, 'Λάβαμε την εγγραφή σας — e-Τιμολόγιο Pro', mail_template('Εγγραφή σε εκκρεμότητα', $inner));
}

// Notify the admins that a new signup awaits approval.
function auth_email_admins_new_signup(string $applicantEmail, string $businessName): void {
    if (!mail_enabled()) return;
    $inner = '<p>Νέα εγγραφή εκκρεμεί έγκριση:</p>'
        . '<p><strong>' . htmlspecialchars($businessName, ENT_QUOTES) . '</strong><br>'
        . htmlspecialchars($applicantEmail, ENT_QUOTES) . '</p>'
        . '<p>Εγκρίνετέ την από τη Διαχείριση της εφαρμογής.</p>';
    foreach (auth_admin_emails() as $adminEmail) {
        send_mail($adminEmail, 'Νέα εγγραφή προς έγκριση — e-Τιμολόγιο Pro', mail_template('Νέα εγγραφή', $inner));
    }
}

// Notify a user that their account was approved/activated by an admin.
function auth_email_account_approved(string $to, string $businessName): bool {
    if (!mail_enabled()) return false;
    $inner = '<p>Ο λογαριασμός της επιχείρησης <strong>' . htmlspecialchars($businessName, ENT_QUOTES) . '</strong> ενεργοποιήθηκε.</p>'
        . '<p>Μπορείτε πλέον να συνδεθείτε στην εφαρμογή.</p>'
        . mail_button('Σύνδεση', app_base_url() . '/app.php');
    return send_mail($to, 'Ο λογαριασμός σας ενεργοποιήθηκε — e-Τιμολόγιο Pro', mail_template('Λογαριασμός ενεργός', $inner));
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
        'otpauth' => totp_uri($secret, $u['email']),
    ];
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
    $remote = $_SERVER['REMOTE_ADDR'] ?? '';
    if (!in_array($remote, ['127.0.0.1', '::1', ''], true)) return;
    $uid = (int)localdb()->query("SELECT id FROM users WHERE role='master' ORDER BY id ASC LIMIT 1")->fetchColumn();
    if ($uid > 0) $_SESSION['uid'] = $uid;
}

// Run bootstrap + migration + account resolution on include (safe, no output).
auth_bootstrap();
auth_migrate_legacy_accounts();
auth_desktop_autologin();
auth_resolve_account();
