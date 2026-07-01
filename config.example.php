<?php
// ============================================================================
// e-Timologio API — Configuration
// ============================================================================
// Copy this file to config.php and fill in your credentials.
// NEVER commit config.php to version control.
//
// MULTI-TENANT: add one entry per e-timologio account. The bridge selects the
// active account from the `account` request param (matched by `vat`), or falls
// back to the first entry. Each account keeps its own session cookie, and all
// local data (payments/ledgers) is scoped by the account VAT.
// ============================================================================

$ACCOUNTS = [
    [
        'label'            => 'Η Επιχείρησή μου',     // shown in the UI account switcher
        'vat'              => 'YOUR_COMPANY_VAT',      // ΑΦΜ εταιρείας
        'username'         => 'YOUR_USERNAME',         // e-timologio username
        'subscription_key' => 'YOUR_SUBSCRIPTION_KEY', // Ρυθμίσεις → Στοιχεία Χρήστη
    ],
    // [
    //     'label'            => 'Δεύτερη Επιχείρηση',
    //     'vat'              => '123456789',
    //     'username'         => 'username2',
    //     'subscription_key' => 'key2',
    // ],
];

// Base URL — do not change
const BASE_URL   = 'https://mydata.aade.gr/timologio';

// Directory for per-account session cookie jars (must be writable by web server)
const COOKIE_DIR = __DIR__ . '/.cookies';

// SQLite database for LOCAL data e-timologio does not keep (payments, ledgers).
const LOCAL_DB   = __DIR__ . '/.localdata.sqlite';

// At-rest encryption (crypto.php). Set a base64 32-byte key, or leave it unset
// and a key file (.enckey) is auto-generated on first use. Keep the key secret
// and backed up — losing it makes stored data unreadable.
// Generate: php -r "echo base64_encode(random_bytes(32)).PHP_EOL;"
// const ENCRYPTION_KEY = 'paste-base64-32-byte-key-here';
const ENC_KEY_FILE = __DIR__ . '/.enckey';

// Invoice types that carry 0% VAT (non-EU clients)
const ZERO_VAT_TYPES = ['22', '23'];

// ----------------------------------------------------------------------------
// MULTI-CLIENT LOGIN (auth.php)
// ----------------------------------------------------------------------------
// The app is multi-tenant with logins: a master admin manages businesses and
// approves signups; each business logs in and owns its AADE accounts (stored
// ENCRYPTED in the DB, not here). Set the master admin bootstrap credentials —
// on first run they are hashed into the DB, then you can remove the password.
const MASTER_ADMIN_EMAIL    = 'admin@example.com';
const MASTER_ADMIN_PASSWORD = 'change-this-strong-password';

// Optional SMTP for password-reset emails. Leave SMTP_FROM empty to disable email
// (the master admin can then hand reset tokens over manually from the admin panel).
const SMTP_FROM = '';                 // e.g. 'no-reply@yourdomain.gr'
const SMTP_HOST = '';
const SMTP_PORT = 587;
const SMTP_USER = '';
const SMTP_PASS = '';

// ----------------------------------------------------------------------------
// Legacy single-tenant account resolution — used ONLY when auth.php is not in
// charge (SKIP_ACCOUNT_RESOLUTION not defined), e.g. direct CLI/testing. With
// logins enabled the active account is resolved per-session from the DB instead.
// ----------------------------------------------------------------------------
if (!defined('SKIP_ACCOUNT_RESOLUTION') && !defined('COMPANY_VAT')) {
    $reqAcc = trim($_GET['account'] ?? $_POST['account'] ?? '');
    $active = null;
    foreach ($ACCOUNTS as $a) {
        if ($reqAcc !== '' && (string)$a['vat'] === $reqAcc) { $active = $a; break; }
    }
    if ($active === null) $active = $ACCOUNTS[0] ?? null;
    if ($active === null) {
        http_response_code(500);
        header('Content-Type: application/json');
        echo json_encode(['success' => false, 'error' => 'No accounts configured in config.php']);
        exit;
    }
    define('COMPANY_VAT',      (string)$active['vat']);
    define('USERNAME',         (string)$active['username']);
    define('SUBSCRIPTION_KEY', (string)$active['subscription_key']);
    if (!is_dir(COOKIE_DIR)) @mkdir(COOKIE_DIR, 0700, true);
    define('COOKIE_FILE', COOKIE_DIR . '/etimologio_' . preg_replace('/\D/', '', COMPANY_VAT) . '.txt');
}
