<?php
// ============================================================================
// scheduler.php — background runner for scheduled issuance (TODO 90)
// ----------------------------------------------------------------------------
// Polls the scheduled_jobs store and issues every due παραστατικό automatically
// by REPLAYING the queued request against this same app over loopback HTTP
// (authenticated with SCHED_TOKEN as the owning user). This reuses the entire
// existing issue pipeline (login per account, myDATA submit, ΜΑΡΚ, notifications)
// without duplicating any of it.
//
// Run it once per minute from the OS scheduler:
//   Windows Task Scheduler:  php C:\path\to\scheduler.php     (trigger: every 1 min)
//   cron:                    * * * * * php /path/to/scheduler.php
//
// Each invocation processes all jobs whose run_at (Greek local wall-clock) is due,
// then exits. Recurring jobs are re-queued for their next occurrence.
//
// Flags:  --dry-run   list what would run, change nothing
//         --verbose   print per-job detail
// ============================================================================

if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit("scheduler.php is a CLI script.\n");
}

date_default_timezone_set('Europe/Athens');   // run_at is stored as Greek local time

define('SKIP_ACCOUNT_RESOLUTION', 1);          // we don't want config's legacy resolver
require __DIR__ . '/config.php';               // constants (SCHED_TOKEN, APP_BASE_URL, …)
require __DIR__ . '/localdb.php';              // job store + crypto

$argvv   = $argv ?? [];
$DRY     = in_array('--dry-run', $argvv, true);
$VERBOSE = in_array('--verbose', $argvv, true) || $DRY;

function slog(string $m): void { fwrite(STDOUT, '[' . date('Y-m-d H:i:s') . '] ' . $m . PHP_EOL); }

if (!defined('SCHED_TOKEN') || SCHED_TOKEN === '') {
    slog('Scheduled issuance is disabled (SCHED_TOKEN empty in config.php). Nothing to do.');
    exit(0);
}
$BASE = defined('APP_BASE_URL') ? rtrim(APP_BASE_URL, '/') : '';
if ($BASE === '') { slog('APP_BASE_URL not set in config.php — cannot reach the app. Aborting.'); exit(1); }
$ENDPOINT = $BASE . '/etimologio.php';

// --- Single-instance lock so overlapping cron ticks don't double-issue ------
// Το lock ζει δίπλα στα δεδομένα, όχι μέσα στο web root: στον container ο
// φάκελος της εφαρμογής είναι σκόπιμα μη εγγράψιμος από τον χρήστη του web.
$lockDir  = (defined('LOCAL_DB') && LOCAL_DB !== '') ? dirname(LOCAL_DB) : __DIR__;
if (!is_dir($lockDir) || !is_writable($lockDir)) $lockDir = sys_get_temp_dir();
$lockPath = $lockDir . '/.scheduler.lock';
$lock = @fopen($lockPath, 'c');
if ($lock && !flock($lock, LOCK_EX | LOCK_NB)) {
    slog('Another scheduler run is in progress — skipping this tick.');
    exit(0);
}

$now = date('Y-m-d H:i:s');
$due = sched_due($now);
if (!$due) { if ($VERBOSE) slog('No due jobs at ' . $now . '.'); exit(0); }

slog('Found ' . count($due) . ' due job(s) at ' . $now . '.');

$okCount = 0; $failCount = 0;

foreach ($due as $job) {
    $id     = (int)$job['id'];
    $uid    = (int)$job['user_id'];
    $acct   = (string)$job['account_vat'];
    $rec    = (string)$job['recurrence'];
    $title  = $job['title'] !== '' ? $job['title'] : ('#' . $id);
    $payload = is_array($job['payload'] ?? null) ? $job['payload'] : [];

    if (empty($payload)) {
        sched_record_result($id, 'failed', ['error' => 'Κενό payload', 'at' => date('c')]);
        slog("Job #$id ($title): empty payload → failed.");
        $failCount++;
        continue;
    }

    if ($DRY) {
        slog("DRY-RUN would issue job #$id ($title) for account $acct [kind={$job['kind']}, recurrence=$rec].");
        continue;
    }

    // Claim the job so a parallel run can't repick it.
    sched_set_status($id, 'running');

    // Build the replay request: the stored params + service authentication.
    $fields = $payload;
    $fields['live']        = 1;                 // scheduled issue is always real
    $fields['account']     = $acct;             // drives per-account AADE login
    $fields['sched_token'] = SCHED_TOKEN;
    $fields['sched_uid']   = $uid;

    [$httpCode, $body, $curlErr] = sched_http_post($ENDPOINT, $fields);
    $resp = $body !== '' ? json_decode($body, true) : null;

    $success = is_array($resp) && !empty($resp['success']) && !empty($resp['mark']);
    // Bulk jobs report per-item; treat as success if at least one issued.
    if (!$success && is_array($resp) && isset($resp['results']) && !empty($resp['ok'])) $success = true;

    $result = [
        'at'        => date('c'),
        'http'      => $httpCode,
        'success'   => $success,
        'mark'      => $resp['mark'] ?? null,
        'aa'        => $resp['aa'] ?? null,
        'ok'        => $resp['ok'] ?? null,
        'failed'    => $resp['failed'] ?? null,
        'error'     => $success ? null : ($resp['error'] ?? ($curlErr ?: ('HTTP ' . $httpCode))),
    ];

    // Recurrence: re-queue for the next occurrence regardless of this outcome, so a
    // one-off transient failure doesn't kill a recurring schedule.
    $next = sched_next_run($job['run_at'], $rec);

    if ($success) {
        sched_record_result($id, 'done', $result, $next);
        $okCount++;
        slog("Job #$id ($title): issued OK" . (isset($result['mark']) ? " (ΜΑΡΚ {$result['mark']})" : '')
             . ($next ? " · next run $next" : '') . '.');
    } else {
        sched_record_result($id, 'failed', $result, $next);
        $failCount++;
        slog("Job #$id ($title): FAILED — " . ($result['error'] ?? 'unknown')
             . ($next ? " · will retry at next run $next" : '') . '.');
    }
}

slog("Done. issued=$okCount failed=$failCount.");
exit($failCount > 0 ? 2 : 0);

// --- helpers ----------------------------------------------------------------
function sched_http_post(string $url, array $fields): array {
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => $url,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query($fields),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_TIMEOUT        => 120,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/x-www-form-urlencoded'],
    ]);
    $body = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);
    return [$code, $body === false ? '' : (string)$body, $err];
}
