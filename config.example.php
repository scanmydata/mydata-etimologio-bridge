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

// ----------------------------------------------------------------------------
// EMAIL — transactional mail for signup/activation/forgot-password, member
// invitations, and issuance notifications. Two providers are supported:
//   • Resend (HTTPS API, recommended)  — set RESEND_API_KEY + a verified sender
//   • SMTP (PHP mail())                — set SMTP_FROM
// MAIL_PROVIDER selects: 'auto' (Resend if key set, else SMTP), 'resend', 'smtp'.
// Leave everything empty to disable email (reset/invite links are then shown
// in-app to the admin as a manual fallback).
// ----------------------------------------------------------------------------
const MAIL_PROVIDER      = 'auto';
// Resend — https://resend.com/api-keys ; the sender domain must be verified.
const RESEND_API_KEY     = '';        // e.g. 're_xxxxxxxxxxxxxxxxxxxx'
const RESEND_EMAIL_SENDER = '';       // e.g. 'e-Τιμολόγιο <no-reply@yourdomain.gr>'
// SMTP fallback (PHP mail()). Leave SMTP_FROM empty to disable the SMTP path.
const SMTP_FROM = '';                 // e.g. 'no-reply@yourdomain.gr'
const SMTP_HOST = '';
const SMTP_PORT = 587;
const SMTP_USER = '';
const SMTP_PASS = '';
// Public base URL of the app — used to build links inside emails (activation,
// reset, "open the app"). No trailing slash. Falls back to APP_BASE_URL, then
// to the current request host.
const APP_URL = '';                   // e.g. 'https://timologio.yourdomain.gr'

// ----------------------------------------------------------------------------
// SCHEDULED ISSUANCE (χρονοπρογραμματισμός) — TODO 90
// ----------------------------------------------------------------------------
// The UI can queue a παραστατικό (single or bulk) to be issued automatically at
// a future date/time. A background runner (scheduler.php) polls the job store
// and replays each due job against this same app over loopback HTTP.
//
//  • SCHED_TOKEN  — a shared secret the runner presents to authenticate as a
//                   service. Generate: php -r "echo bin2hex(random_bytes(24)).PHP_EOL;"
//                   Leave empty to DISABLE scheduled issuance entirely.
//  • APP_BASE_URL — the loopback origin the runner calls (this app's own URL as
//                   seen from the machine running the cron/Task Scheduler entry),
//                   e.g. 'http://127.0.0.1/mydata-etimologio-bridge' or
//                   'http://127.0.0.1:8080'. No trailing slash.
//
// Then schedule scheduler.php to run every minute, e.g.:
//   Windows Task Scheduler:  php C:\path\to\scheduler.php   (trigger: every 1 min)
//   cron:                    * * * * * php /path/to/scheduler.php
const SCHED_TOKEN  = '';
const APP_BASE_URL = 'http://127.0.0.1';

// ----------------------------------------------------------------------------
// ISSUANCE NOTIFICATIONS (ειδοποίηση λογιστή/admin) — TODO 91
// ----------------------------------------------------------------------------
// Every real issue (ΜΑΡΚ obtained), EXCEPT δελτία αποστολής (9.x), is recorded
// in an in-app feed for the master admin (and the issuing business). If SMTP is
// configured above and NOTIFY_ADMIN_EMAIL is set, a copy is emailed too.
// Leave empty to fall back to MASTER_ADMIN_EMAIL, or set to '-' to disable email.
const NOTIFY_ADMIN_EMAIL = '';

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
