<?php
// ============================================================================
// tools/pg_smoke.php — «δουλεύει ο server;» σε ένα τρέξιμο
// ----------------------------------------------------------------------------
// Ελέγχει ΤΗΝ ΠΡΑΓΜΑΤΙΚΗ εγκατάσταση (το config.php που έγραψε το entrypoint
// από τα env του Coolify): επεκτάσεις PHP, σύνδεση στη βάση, δημιουργία των
// πινάκων, και μετά έναν πλήρη κύκλο των δεδομένων που πονάνε — κυρίως τη
// **σύνδεση εταιρείας με τα κλειδιά ΑΑΔΕ** (username + subscription key), που
// αποθηκεύονται ΚΡΥΠΤΟΓΡΑΦΗΜΕΝΑ και πρέπει να ξαναδιαβάζονται σωστά.
//
// Γιατί χωριστό εργαλείο: το επίπεδο δεδομένων είναι διπλής διαλέκτου (SQLite
// τοπικά, Postgres στον server). Ό,τι δούλεψε σε SQLite δεν αποδεικνύει τίποτα
// για την Postgres — αυτό το σενάριο το αποδεικνύει, πάνω στη βάση που τρέχει.
//
//   docker compose exec etimologio php tools/pg_smoke.php
//   php tools/pg_smoke.php --keep        # μη σβήσεις τα δοκιμαστικά δεδομένα
//
// Καθαρίζει ό,τι δημιουργεί, δεν αγγίζει υπάρχουσες εγγραφές και ΔΕΝ στέλνει
// τίποτα στην ΑΑΔΕ.
// ============================================================================

if (PHP_SAPI !== 'cli') { http_response_code(403); exit("CLI only\n"); }

$KEEP = in_array('--keep', $argv, true);
$ROOT = dirname(__DIR__);

define('SKIP_ACCOUNT_RESOLUTION', 1);
require $ROOT . '/config.php';
require $ROOT . '/localdb.php';

$FAIL = 0; $STEP = 0;
function ok(string $what, string $detail = ''): void {
    global $STEP; $STEP++;
    fwrite(STDOUT, sprintf("  [OK] %-44s %s\n", $what, $detail));
}
function bad(string $what, string $detail = ''): void {
    global $FAIL, $STEP; $FAIL++; $STEP++;
    fwrite(STDOUT, sprintf("  [--] %-44s %s\n", $what, $detail));
}
function check(string $what, bool $cond, string $detail = ''): bool {
    $cond ? ok($what, $detail) : bad($what, $detail);
    return $cond;
}
function section(string $t): void { fwrite(STDOUT, "\n" . $t . "\n"); }

// --- 1. Περιβάλλον ----------------------------------------------------------
section('1. Επεκτάσεις PHP');
$needDriver = (defined('DB_DSN') && DB_DSN !== '') ? explode(':', DB_DSN)[0] : 'sqlite';
check('PDO driver «' . $needDriver . '»', in_array($needDriver, PDO::getAvailableDrivers(), true),
      implode(', ', PDO::getAvailableDrivers()));
foreach (['sodium' => 'κρυπτογράφηση δεδομένων', 'curl' => 'κλήσεις προς ΑΑΔΕ',
          'mbstring' => 'ελληνικά'] as $ext => $why) {
    check('επέκταση ' . $ext, extension_loaded($ext), $why);
}
extension_loaded('zip')
    ? ok('επέκταση zip', 'ανάγνωση .xlsx στην εισαγωγή τραπέζης')
    : ok('επέκταση zip (προαιρετική)', 'απούσα — μόνο CSV στην εισαγωγή τραπέζης');

// --- 2. Σύνδεση + σχήμα -----------------------------------------------------
section('2. Βάση δεδομένων');
try {
    $pdo = localdb();                       // δημιουργεί/αναβαθμίζει τους πίνακες
    ok('σύνδεση', db_dialect() . ' — ' . ((defined('DB_DSN') && DB_DSN !== '') ? DB_DSN : LOCAL_DB));
} catch (Throwable $e) {
    bad('σύνδεση', $e->getMessage());
    fwrite(STDOUT, "\nΧωρίς βάση δεν έχει νόημα να συνεχίσω.\n");
    exit(1);
}
foreach (['users', 'aade_accounts', 'account_managers', 'payments', 'app_cache',
          'app_settings', 'customer_meta', 'scheduled_jobs', 'issue_notifications'] as $t) {
    try { $pdo->query("SELECT COUNT(*) FROM $t")->fetchColumn(); ok('πίνακας ' . $t); }
    catch (Throwable $e) { bad('πίνακας ' . $t, $e->getMessage()); }
}

// --- 3. Κρυπτογράφηση -------------------------------------------------------
section('3. Κρυπτογράφηση στα αποθηκευμένα');
$probe  = 'ΑΑΔΕ κλειδί δοκιμής ' . bin2hex(random_bytes(4));
$cipher = enc($probe);
check('enc()/dec() κάνουν κύκλο', dec($cipher) === $probe);
check('το κρυπτογράφημα δεν είναι το καθαρό κείμενο', strpos($cipher, $probe) === false,
      substr($cipher, 0, 22) . '…');

// --- 4. Σύνδεση εταιρείας με τα κλειδιά ΑΑΔΕ --------------------------------
section('4. Σύνδεση εταιρείας με τα κλειδιά ΑΑΔΕ (η καρδιά του server)');
$stamp  = date('YmdHis');
$email  = "smoke.$stamp@etimologio.invalid";
$vat    = '000000001';                        // δεν αντιστοιχεί σε υπαρκτό ΑΦΜ
$user   = 'smoke_user_' . $stamp;
$subkey = 'sk_' . bin2hex(random_bytes(12));
$uid = $aid = $mgrId = $payId = $jobId = $notifId = 0;

try {
    $uid = user_create($email, password_hash('x', PASSWORD_DEFAULT), 'business', 'active', 'Δοκιμή');
    check('δημιουργία χρήστη-επιχείρησης', $uid > 0, 'id=' . $uid);

    $aid = account_add($uid, $vat, 'Δοκιμαστική ΑΕ', $user, $subkey);
    check('καταχώριση εταιρείας + κλειδιών', $aid > 0, 'id=' . $aid);

    $back = account_get($aid);
    check('το username διαβάζεται πίσω', ($back['username'] ?? '') === $user);
    check('το subscription key διαβάζεται πίσω', ($back['subkey'] ?? '') === $subkey);

    $raw = $pdo->prepare('SELECT username_enc, subkey_enc FROM aade_accounts WHERE id = :id');
    $raw->execute([':id' => $aid]);
    $rawRow = $raw->fetch() ?: [];
    check('στη βάση είναι κρυπτογραφημένα',
          strpos((string)($rawRow['subkey_enc'] ?? ''), $subkey) === false
          && strpos((string)($rawRow['username_enc'] ?? ''), $user) === false);

    account_update($aid, ['vat' => $vat, 'label' => 'Δοκιμαστική ΑΕ 2',
                          'username' => $user, 'subkey' => $subkey . 'X']);
    check('ενημέρωση κλειδιών', (account_get($aid)['subkey'] ?? '') === $subkey . 'X');

    check('αναζήτηση εταιρείας με ΑΦΜ', (int)(account_by_vat($vat)['id'] ?? 0) === $aid);
    check('οι εταιρείες του χρήστη', count(accounts_for_user($uid)) === 1);

    // Ανάθεση σε λογιστή (0.4.1) — ο πίνακας account_managers.
    $mgrId = user_create("smoke.acc.$stamp@etimologio.invalid",
                         password_hash('x', PASSWORD_DEFAULT), 'editor', 'active', 'Λογιστής δοκιμής');
    manager_set_accounts($mgrId, [$aid]);
    $mine = accounts_for_manager($mgrId);
    check('ανάθεση εταιρείας σε λογιστή', count($mine) === 1 && (int)$mine[0]['id'] === $aid);
} catch (Throwable $e) {
    bad('ροή λογαριασμών/κλειδιών', $e->getMessage());
}

// --- 5. Τοπικά δεδομένα -----------------------------------------------------
section('5. Πληρωμές, cache, ρυθμίσεις');
try {
    $payId = payment_add($vat, ['customer_vat' => '000000002', 'customer_name' => 'Πελάτης Δοκιμής',
                                'amount' => 123.45, 'method' => 3, 'pay_date' => date('Y-m-d'),
                                'notes' => 'smoke']);
    check('εγγραφή πληρωμής (INSERT … RETURNING id)', $payId > 0, 'id=' . $payId);
    $rows = payments_list($vat);
    check('ανάγνωση + αποκρυπτογράφηση ποσού',
          count($rows) === 1 && abs((float)$rows[0]['amount'] - 123.45) < 0.005);
    check('σύνολο πληρωμών', abs(payments_total($vat) - 123.45) < 0.005);

    cache_set($vat, 'customers', [['vat' => '000000002', 'name' => 'Πελάτης']]);
    cache_set($vat, 'customers', [['vat' => '000000002', 'name' => 'Πελάτης 2']]);   // upsert
    $c = cache_get($vat, 'customers');
    check('cache upsert (ON CONFLICT)', ($c['rows'][0]['name'] ?? '') === 'Πελάτης 2');

    setting_set('smoke.' . $stamp, 'τιμή');
    setting_set('smoke.' . $stamp, 'τιμή 2');
    check('app_settings upsert', setting_get('smoke.' . $stamp) === 'τιμή 2');

    customer_meta_set($vat, '000000002', ['customer_name' => 'Πελάτης',
                                          'opening_balance' => 10.5, 'notes' => 'ν']);
    check('customer_meta upsert',
          abs((float)(customer_meta_get($vat, '000000002')['opening_balance'] ?? 0) - 10.5) < 0.005);
} catch (Throwable $e) {
    bad('τοπικά δεδομένα', $e->getMessage());
}

// --- 6. Ειδοποιήσεις + χρονοπρογραμματισμός ---------------------------------
section('6. Ειδοποιήσεις & χρονοπρογραμματισμός');
try {
    $notifId = notification_add($vat, ['actor_user_id' => $uid, 'actor_email' => $email,
        'doc_type' => '2.1', 'doc_label' => 'Τιμολόγιο', 'series' => 'Α', 'aa' => '1',
        'mark' => '400000000000000', 'buyer_vat' => '000000002', 'buyer_name' => 'Πελάτης',
        'amount_total' => 179.80, 'source' => 'manual']);
    check('εγγραφή ειδοποίησης', $notifId > 0, 'id=' . $notifId);
    check('αδιάβαστες με εύρος πίνακα ΑΦΜ', notifications_unread_count([$vat]) >= 1);
    check('κενό εύρος = τίποτα (όχι «τα πάντα»)', notifications_unread_count([]) === 0);
    notification_mark_read($notifId, [$vat]);
    check('σήμανση ως διαβασμένη', notifications_unread_count([$vat]) === 0);

    $jobId = sched_add($vat, $uid, ['title' => 'Δοκιμή', 'kind' => 'invoice',
        'payload' => ['amount' => 1], 'run_at' => date('Y-m-d H:i:s', time() - 60),
        'recurrence' => 'none']);
    check('προγραμματισμένη εργασία', $jobId > 0, 'id=' . $jobId);
    $due = array_filter(sched_due(date('Y-m-d H:i:s')), fn($j) => (int)$j['id'] === $jobId);
    check('η εργασία βρίσκεται ως ληξιπρόθεσμη', count($due) === 1);
    check('λίστα με εύρος λογιστή',
          count(array_filter(sched_list([$vat]), fn($j) => (int)$j['id'] === $jobId)) === 1);
    check('ακύρωση εργασίας', sched_cancel($jobId, [$vat]));
} catch (Throwable $e) {
    bad('ειδοποιήσεις/χρονοπρογραμματισμός', $e->getMessage());
}

// --- 7. Έξοδος προς ΑΑΔΕ ----------------------------------------------------
section('7. Δίκτυο προς την ΑΑΔΕ (πιστοποιητικά)');
if (!extension_loaded('curl')) {
    bad('curl', 'χωρίς curl δεν γίνεται καμία κλήση στην ΑΑΔΕ');
} else {
    // Χωρίς follow: το e-Τιμολόγιο ανακατευθύνει σε βρόχο τον ανώνυμο επισκέπτη.
    // Εδώ μας ενδιαφέρει μόνο ότι η σύνδεση TLS ΓΙΝΕΤΑΙ (δηλαδή ότι ο container
    // έχει πιστοποιητικά CA) — οτιδήποτε απαντήσει ο server είναι απόδειξη.
    $ch = curl_init(defined('BASE_URL') ? BASE_URL : 'https://mydata.aade.gr/timologio');
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20,
                            CURLOPT_NOBODY => true, CURLOPT_FOLLOWLOCATION => false]);
    curl_exec($ch);
    $err  = curl_error($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);
    check('HTTPS προς mydata.aade.gr', $err === '' && $code > 0,
          $err !== '' ? $err : ('HTTP ' . $code));
}

// --- 8. Καθαρισμός ----------------------------------------------------------
section('8. Καθαρισμός');
if ($KEEP) {
    ok('παρακάμφθηκε (--keep)', 'ΑΦΜ ' . $vat . ', χρήστες ' . $uid . '/' . $mgrId);
} else {
    try {
        if ($payId)   payment_delete($vat, $payId);
        if ($jobId)   sched_delete($jobId, [$vat]);
        if ($notifId) $pdo->prepare('DELETE FROM issue_notifications WHERE id = :id')->execute([':id' => $notifId]);
        $pdo->prepare('DELETE FROM app_cache WHERE account_vat = :v')->execute([':v' => $vat]);
        $pdo->prepare('DELETE FROM customer_meta WHERE account_vat = :v')->execute([':v' => $vat]);
        $pdo->prepare('DELETE FROM app_settings WHERE key = :k')->execute([':k' => 'smoke.' . $stamp]);
        if ($aid)   account_delete($aid);
        if ($uid)   user_delete($uid);
        if ($mgrId) user_delete($mgrId);
        ok('τα δοκιμαστικά δεδομένα διαγράφηκαν');
    } catch (Throwable $e) {
        bad('καθαρισμός', $e->getMessage() . ' — σβήστε χειροκίνητα το ΑΦΜ ' . $vat);
    }
}

fwrite(STDOUT, "\n" . str_repeat('-', 62) . "\n");
if ($FAIL === 0) {
    fwrite(STDOUT, "Ολα εντάξει — $STEP έλεγχοι, καμία αποτυχία.\n");
    exit(0);
}
fwrite(STDOUT, "$FAIL από $STEP έλεγχοι ΑΠΕΤΥΧΑΝ.\n");
exit(1);
