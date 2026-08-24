<?php
// ============================================================================
// serverbackup.php — αντίγραφα ασφαλείας ΤΟΥ SERVER
// ----------------------------------------------------------------------------
// Τι μπαίνει μέσα, και γιατί και τα δύο:
//   * η **βάση** (pg_dump για Postgres, το αρχείο για SQLite) — τα δεδομένα,
//   * το **.enckey** — χωρίς αυτό τα κρυπτογραφημένα πεδία (username και
//     subscription key κάθε εταιρείας στην ΑΑΔΕ) δεν ξαναδιαβάζονται ΠΟΤΕ.
// Ένα αντίγραφο με μόνο το ένα από τα δύο δεν είναι αντίγραφο.
//
// Ακριβώς γι' αυτό το αρχείο **κρυπτογραφείται** πριν φύγει για το Drive: μέσα
// του κάθεται η βάση ΜΑΖΙ με το κλειδί της. Η φράση-κλειδί
// (`BACKUP_PASSPHRASE`) έρχεται από το Infisical και ΔΕΝ αποθηκεύεται πουθενά
// αλλού — χωρίς αυτήν το αντίγραφο δεν ανοίγει, ούτε από εμάς.
// Αν λείπει, το αντίγραφο μένει τοπικά και ΔΕΝ ανεβαίνει: καλύτερα να λείπει
// αντίγραφο στο cloud, παρά να ταξιδεύουν κλειδιά ΑΑΔΕ ασφράγιστα.
//
// Τοπικά κρατιούνται τα τελευταία αρχεία στο /data/backups — για γρήγορη
// επαναφορά χωρίς δίκτυο.
// ============================================================================

require_once __DIR__ . '/zipwriter.php';
require_once __DIR__ . '/gdrive.php';

const SRV_BACKUP_KEEP_LOCAL = 7;
const SRV_BACKUP_KEEP_DRIVE = 30;

function srv_backup_dir(): string {
    $dir = (defined('LOCAL_DB') && LOCAL_DB !== '') ? dirname(LOCAL_DB) . '/backups' : sys_get_temp_dir();
    if (!is_dir($dir)) @mkdir($dir, 0700, true);
    return $dir;
}

function srv_backup_files(): array {
    $files = glob(srv_backup_dir() . '/server-*.zip*') ?: [];
    usort($files, static fn($a, $b) => filemtime($b) <=> filemtime($a));
    return $files;
}

/** Είναι Postgres ή σκέτο αρχείο SQLite; */
function srv_backup_is_pg(): bool {
    return defined('DB_DSN') && stripos((string)DB_DSN, 'pgsql:') === 0;
}

/**
 * Το dump της βάσης ως bytes.
 *
 * Για Postgres τρέχει `pg_dump`. Δεν περνά ΠΟΤΕ ο κωδικός στη γραμμή εντολών
 * (τη βλέπει όλο το μηχάνημα στο `ps`): μπαίνει στο περιβάλλον της διεργασίας
 * ως `PGPASSWORD`.
 */
function srv_backup_dump(): array {
    if (!srv_backup_is_pg()) {
        $path = defined('LOCAL_DB') ? (string)LOCAL_DB : '';
        if ($path === '' || !is_file($path)) return ['ok' => false, 'error' => 'δεν βρέθηκε η βάση'];
        $bytes = @file_get_contents($path);
        if ($bytes === false) return ['ok' => false, 'error' => 'η βάση δεν διαβάζεται'];
        return ['ok' => true, 'name' => 'local.sqlite', 'bytes' => $bytes];
    }

    $dsn = [];
    foreach (explode(';', substr((string)DB_DSN, strlen('pgsql:'))) as $part) {
        [$k, $v] = array_pad(explode('=', $part, 2), 2, '');
        if ($k !== '') $dsn[trim($k)] = trim($v);
    }
    $cmd = sprintf('pg_dump --no-owner --no-privileges -h %s -p %s -U %s -d %s 2>&1',
        escapeshellarg($dsn['host'] ?? 'localhost'),
        escapeshellarg((string)($dsn['port'] ?? '5432')),
        escapeshellarg((string)(defined('DB_USER') ? DB_USER : '')),
        escapeshellarg((string)($dsn['dbname'] ?? 'postgres')));

    $env = $_ENV;
    $env['PGPASSWORD'] = defined('DB_PASS') ? (string)DB_PASS : '';
    $descriptors = [1 => ['pipe', 'w'], 2 => ['pipe', 'w']];
    $proc = @proc_open($cmd, $descriptors, $pipes, null, $env);
    if (!is_resource($proc)) return ['ok' => false, 'error' => 'δεν ξεκίνησε το pg_dump'];
    $out = stream_get_contents($pipes[1]); fclose($pipes[1]);
    $err = stream_get_contents($pipes[2]); fclose($pipes[2]);
    $code = proc_close($proc);
    if ($code !== 0 || $out === '' || $out === false) {
        return ['ok' => false, 'error' => 'pg_dump: ' . trim(substr((string)($err ?: $out), 0, 300))];
    }
    return ['ok' => true, 'name' => 'db.sql', 'bytes' => (string)$out];
}

function srv_backup_passphrase(): string {
    return secret_get('BACKUP_PASSPHRASE');
}

/**
 * Κρυπτογράφηση με sodium, κλειδί από τη φράση.
 *
 * `crypto_pwhash` και όχι σκέτο hash: η φράση μπορεί να είναι ανθρώπινη, και
 * το KDF είναι αυτό που κάνει ασύμφορη τη δοκιμή λέξεων. Το αλάτι ταξιδεύει
 * μπροστά από το αρχείο — δεν είναι μυστικό, αλλά πρέπει να είναι μοναδικό.
 */
function srv_backup_encrypt(string $plain, string $passphrase): array {
    if (!function_exists('sodium_crypto_secretbox')) {
        return ['ok' => false, 'error' => 'λείπει η επέκταση sodium'];
    }
    $salt = random_bytes(SODIUM_CRYPTO_PWHASH_SALTBYTES);
    $key  = sodium_crypto_pwhash(
        SODIUM_CRYPTO_SECRETBOX_KEYBYTES, $passphrase, $salt,
        SODIUM_CRYPTO_PWHASH_OPSLIMIT_INTERACTIVE,
        SODIUM_CRYPTO_PWHASH_MEMLIMIT_INTERACTIVE
    );
    $nonce = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $cipher = sodium_crypto_secretbox($plain, $nonce, $key);
    sodium_memzero($key);
    // «etimbk1» + salt + nonce + κρυπτογράφημα. Το πρόθεμα λέει στο εργαλείο
    // επαναφοράς τι κρατά στα χέρια του.
    return ['ok' => true, 'bytes' => 'etimbk1' . $salt . $nonce . $cipher];
}

/**
 * Φτιάχνει αντίγραφο, το κρατά τοπικά και το ανεβάζει στο Drive.
 *
 * `$reason` γράφεται στο όνομα του αρχείου: «auto», «manual», «pre-deploy».
 * Όταν ψάχνεις ποιο αντίγραφο να επαναφέρεις, το «πριν από ποια ενημέρωση»
 * είναι η πληροφορία που θέλεις.
 */
function srv_backup_run(string $reason = 'manual'): array {
    $dump = srv_backup_dump();
    if (!$dump['ok']) return $dump;

    $files = [$dump['name'] => $dump['bytes']];
    $keyFile = defined('ENC_KEY_FILE') ? (string)ENC_KEY_FILE : '';
    if ($keyFile !== '' && is_file($keyFile)) {
        $k = @file_get_contents($keyFile);
        if ($k !== false) $files['.enckey'] = $k;
    }
    $files['manifest.json'] = json_encode([
        'at'      => date('c'),
        'reason'  => $reason,
        'engine'  => srv_backup_is_pg() ? 'postgres' : 'sqlite',
        'app_url' => function_exists('app_base_url') ? app_base_url() : '',
        'has_enckey' => isset($files['.enckey']),
    ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

    $stamp = date('Ymd-His');
    $zip   = zip_build($files);
    $pass  = srv_backup_passphrase();
    $name  = "server-$stamp-$reason.zip";
    $bytes = $zip;
    $encrypted = false;
    if ($pass !== '') {
        $enc = srv_backup_encrypt($zip, $pass);
        if (!$enc['ok']) return $enc;
        $bytes = $enc['bytes'];
        $name .= '.enc';
        $encrypted = true;
    }

    $path = srv_backup_dir() . '/' . $name;
    if (@file_put_contents($path, $bytes) === false) {
        return ['ok' => false, 'error' => 'δεν γράφτηκε τοπικά'];
    }
    foreach (array_slice(srv_backup_files(), SRV_BACKUP_KEEP_LOCAL) as $old) @unlink($old);

    $out = ['ok' => true, 'name' => $name, 'size' => strlen($bytes),
            'encrypted' => $encrypted, 'reason' => $reason, 'uploaded' => false];

    if (!$encrypted) {
        // Δες το σχόλιο στην κορυφή: ασφράγιστο αντίγραφο δεν φεύγει από εδώ.
        $out['error'] = 'Χωρίς BACKUP_PASSPHRASE το αντίγραφο μένει μόνο τοπικά.';
        setting_set('srvbackup.last', json_encode($out));
        return $out;
    }
    if (!gdrive_configured()) {
        $out['error'] = 'Λείπουν τα κλειδιά Google Drive — το αντίγραφο έμεινε τοπικά.';
        setting_set('srvbackup.last', json_encode($out));
        return $out;
    }

    $up = gdrive_upload($name, $bytes, 'application/octet-stream');
    if (!$up['ok']) {
        $out['error'] = 'Drive: ' . $up['error'];
        setting_set('srvbackup.last', json_encode($out));
        return $out;
    }
    $out['uploaded'] = true;
    $out['drive_id'] = (string)($up['file']['id'] ?? '');
    $out['link']     = (string)($up['file']['webViewLink'] ?? '');
    setting_set('srvbackup.last', json_encode($out));
    setting_set('srvbackup.last_at', date('Y-m-d H:i'));

    srv_backup_prune_drive();
    return $out;
}

/** Κρατά τα νεότερα στο Drive — αλλιώς ο δίσκος του διαχειριστή γεμίζει. */
function srv_backup_prune_drive(): void {
    $list = gdrive_list(200);
    if (!$list['ok']) return;
    $files = $list['files'];
    if (count($files) <= SRV_BACKUP_KEEP_DRIVE) return;
    foreach (array_slice($files, SRV_BACKUP_KEEP_DRIVE) as $f) {
        if (!empty($f['id'])) gdrive_delete((string)$f['id']);
    }
}

/** Κατάσταση για την οθόνη του διαχειριστή. */
function srv_backup_status(): array {
    $local = [];
    foreach (srv_backup_files() as $f) {
        $local[] = ['name' => basename($f), 'size' => filesize($f),
                    'at' => date('Y-m-d H:i', filemtime($f))];
    }
    $drive = ['ok' => false, 'files' => []];
    if (gdrive_configured()) {
        $r = gdrive_list(20);
        $drive = $r['ok']
            ? ['ok' => true, 'files' => array_map(fn($f) => [
                    'name' => (string)($f['name'] ?? ''),
                    'size' => (int)($f['size'] ?? 0),
                    'at'   => substr((string)($f['createdTime'] ?? ''), 0, 16),
                    'link' => (string)($f['webViewLink'] ?? ''),
               ], $r['files'])]
            : ['ok' => false, 'error' => $r['error']];
    }
    $lastRaw = setting_get('srvbackup.last');
    return [
        'engine'      => srv_backup_is_pg() ? 'postgres' : 'sqlite',
        'encrypted'   => srv_backup_passphrase() !== '',
        'drive_ready' => gdrive_configured(),
        'infisical'   => infisical_configured(),
        'folder'      => gdrive_folder_name(),
        'auto_on'     => setting_get('srvbackup.auto', '1') === '1',
        'auto_hour'   => (int)setting_get('srvbackup.hour', '3'),
        'last'        => $lastRaw !== '' ? json_decode($lastRaw, true) : null,
        'last_at'     => setting_get('srvbackup.last_at'),
        'local'       => $local,
        'drive'       => $drive,
    ];
}

/**
 * Το ημερήσιο αντίγραφο, από τον χρονοπρογραμματιστή.
 *
 * Τρέχει μία φορά την ημέρα, την ώρα που όρισε ο διαχειριστής, και κρατά
 * σημάδι με την ημερομηνία — ο tick είναι ανά λεπτό και χωρίς αυτό θα έπαιρνε
 * εξήντα αντίγραφα μέσα στην ώρα.
 */
function srv_backup_tick(): void {
    if (setting_get('srvbackup.auto', '1') !== '1') return;
    $hour = (int)setting_get('srvbackup.hour', '3');
    if ((int)date('G') !== $hour) return;
    if (setting_get('srvbackup.auto_day') === date('Y-m-d')) return;
    setting_set('srvbackup.auto_day', date('Y-m-d'));
    $r = srv_backup_run('auto');
    if (empty($r['ok']) || !empty($r['error'])) {
        error_log('srv_backup auto: ' . (string)($r['error'] ?? 'απέτυχε'));
    }
}
