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
        // `VACUUM INTO` πρώτα: γράφει ΣΥΜΠΥΚΝΩΜΕΝΟ αντίγραφο, χωρίς τις τρύπες
        // που αφήνουν οι διαγραφές, και χωρίς να πειράξει την τρέχουσα βάση.
        // Σε μεγάλες βάσεις κόβει εύκολα το μισό μέγεθος.
        $tmp = sys_get_temp_dir() . '/etim-vac-' . bin2hex(random_bytes(4)) . '.sqlite';
        try {
            localdb()->exec("VACUUM INTO " . localdb()->quote($tmp));
            $bytes = @file_get_contents($tmp);
            @unlink($tmp);
            if ($bytes !== false) return ['ok' => true, 'name' => 'local.sqlite', 'bytes' => $bytes];
        } catch (Throwable $e) {
            @unlink($tmp);   // παλιά SQLite χωρίς VACUUM INTO: συνεχίζουμε απλά
        }
        $bytes = @file_get_contents($path);
        if ($bytes === false) return ['ok' => false, 'error' => 'η βάση δεν διαβάζεται'];
        return ['ok' => true, 'name' => 'local.sqlite', 'bytes' => $bytes];
    }

    $dsn = [];
    foreach (explode(';', substr((string)DB_DSN, strlen('pgsql:'))) as $part) {
        [$k, $v] = array_pad(explode('=', $part, 2), 2, '');
        if ($k !== '') $dsn[trim($k)] = trim($v);
    }
    // `-Fc -Z9`: το custom format της Postgres, συμπιεσμένο στο μέγιστο. Ένα
    // απλό SQL dump είναι κείμενο και φουσκώνει — εδώ το αρχείο βγαίνει
    // πολλαπλάσια μικρότερο, και η επαναφορά γίνεται με `pg_restore`.
    $cmd = sprintf('pg_dump --no-owner --no-privileges -Fc -Z 9 -h %s -p %s -U %s -d %s',
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
    return ['ok' => true, 'name' => 'db.dump', 'bytes' => (string)$out];
}

function srv_backup_passphrase(): string {
    return suite_secret('BACKUP_PASSPHRASE');
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
    // Μικρό επίτηδες: ό,τι χρειάζεται για να ξέρεις τι κρατάς, τίποτα άλλο.
    $files['manifest.json'] = json_encode([
        'at'      => date('c'),
        'reason'  => $reason,
        'engine'  => srv_backup_is_pg() ? 'postgres' : 'sqlite',
        'app_url' => function_exists('app_base_url') ? app_base_url() : '',
        'has_enckey' => isset($files['.enckey']),
    ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

    $stamp = date('Ymd-His');
    // Το zip κρατά τα τρία αρχεία μαζί· η συμπίεσή του είναι σχεδόν δωρεάν όταν
    // το dump έρχεται ήδη συμπιεσμένο από την Postgres, και ουσιαστική για το
    // SQLite. Το κόστος είναι λίγα bytes κεφαλίδας — αξίζει για να ταξιδεύουν
    // βάση, κλειδί και manifest σαν ΕΝΑ πράγμα.
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
        //
        // Μαζί με το «λείπει», λέμε και ΠΟΥ κόλλησε: το μυστικό δεν ήρθε επειδή
        // δεν υπάρχει στο Infisical, ή επειδή το Infisical δεν απάντησε
        // καθόλου; Χωρίς αυτό, ο διαχειριστής κοιτάζει ένα «λείπει» και δεν
        // ξέρει αν φταίει η ρύθμιση ή το δίκτυο. Μετράμε ΠΛΗΘΟΣ μυστικών, ποτέ
        // τιμές — αυτό το κείμενο καταλήγει σε logs.
        $out['error'] = 'Χωρίς BACKUP_PASSPHRASE το αντίγραφο μένει μόνο τοπικά.';
        $out['infisical'] = infisical_configured();
        $out['infisical_secrets'] = count(infisical_cache());
        // ΠΟΙΑ λείπουν, ονομαστικά. Η διαφορά ανάμεσα σε «πήγαινε πρόσθεσε ένα
        // μυστικό» και «πήγαινε ψάξε» είναι ακριβώς αυτή η γραμμή.
        $missing = [];
        foreach (['BACKUP_PASSPHRASE', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                  'GOOGLE_DRIVE_REFRESH_TOKEN'] as $k) {
            // Δείχνουμε ΚΑΙ ΤΑ ΔΥΟ ονόματα που ψάξαμε: αλλιώς ο διαχειριστής
            // βλέπει «λείπει το BACKUP_PASSPHRASE» ενώ το έχει βάλει με επίθεμα.
            if (suite_secret($k) === '') $missing[] = implode(' ή ', suite_secret_names($k));
        }
        $out['missing_secrets'] = $missing;
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

/** Το αντίστροφο του `srv_backup_encrypt`. */
function srv_backup_decrypt(string $blob, string $passphrase): array {
    if (!function_exists('sodium_crypto_secretbox_open')) {
        return ['ok' => false, 'error' => 'λείπει η επέκταση sodium'];
    }
    if ($passphrase === '') {
        return ['ok' => false, 'error' => 'Το αντίγραφο είναι κρυπτογραφημένο και λείπει η φράση-κλειδί.'];
    }
    $off    = strlen('etimbk1');
    $salt   = substr($blob, $off, SODIUM_CRYPTO_PWHASH_SALTBYTES);
    $nonce  = substr($blob, $off + SODIUM_CRYPTO_PWHASH_SALTBYTES, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $cipher = substr($blob, $off + SODIUM_CRYPTO_PWHASH_SALTBYTES + SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $key = sodium_crypto_pwhash(
        SODIUM_CRYPTO_SECRETBOX_KEYBYTES, $passphrase, $salt,
        SODIUM_CRYPTO_PWHASH_OPSLIMIT_INTERACTIVE,
        SODIUM_CRYPTO_PWHASH_MEMLIMIT_INTERACTIVE
    );
    $plain = sodium_crypto_secretbox_open($cipher, $nonce, $key);
    sodium_memzero($key);
    if ($plain === false) {
        // Η ίδια απάντηση για λάθος φράση και για χαλασμένο αρχείο — από έξω
        // δεν ξεχωρίζουν, και δεν έχει νόημα να μαντεύουμε.
        return ['ok' => false, 'error' => 'Λάθος φράση-κλειδί, ή χαλασμένο αρχείο.'];
    }
    return ['ok' => true, 'bytes' => $plain];
}

/**
 * Επαναφορά της βάσης ΤΟΥ SERVER από αντίγραφο.
 *
 * `$source` = «local» (αρχείο στο /data/backups), «drive» (id αρχείου), ή
 * «upload» (bytes που μόλις ανέβασε ο διαχειριστής από τον υπολογιστή του —
 * η περίπτωση «ο server χάθηκε ολόκληρος και κρατάω το zip στο laptop»).
 *
 * Η σειρά των βημάτων είναι όλη η ουσία:
 *   1. **αντίγραφο ΤΟΥ ΤΩΡΑ** («pre-restore») — η επαναφορά είναι η πιο
 *      επικίνδυνη ενέργεια της εφαρμογής, και ένα λάθος αρχείο θα έσβηνε
 *      δουλειά που δεν ζήτησε κανείς να σβηστεί,
 *   2. αποκρυπτογράφηση + άνοιγμα + ΕΛΕΓΧΟΣ ότι μέσα υπάρχει βάση — πριν
 *      πειραχτεί οτιδήποτε,
 *   3. το `.enckey` ΠΡΩΤΑ και η βάση μετά: αν κάτι κοπεί ενδιάμεσα, μια βάση
 *      χωρίς το κλειδί της είναι θόρυβος, ενώ ένα κλειδί χωρίς τη βάση του
 *      είναι απλώς αχρησιμοποίητο.
 */
function srv_backup_restore(string $source, string $ref, string $blob = ''): array {
    // --- 1. δίχτυ ---------------------------------------------------------
    $safety = srv_backup_run('pre-restore');
    $safetyName = (string)($safety['name'] ?? '');

    // --- 2. τα bytes ------------------------------------------------------
    if ($source === 'upload') {
        if ($blob === '') return ['ok' => false, 'error' => 'Το αρχείο δεν έφτασε.'];
    } elseif ($source === 'drive') {
        if (!gdrive_configured()) return ['ok' => false, 'error' => 'Το Google Drive δεν είναι ρυθμισμένο.'];
        $d = gdrive_download($ref);
        if (!$d['ok']) return ['ok' => false, 'error' => 'Drive: ' . $d['error']];
        $blob = $d['bytes'];
    } else {
        $name = basename($ref);
        if (!preg_match('/^server-[\w.\-]+\.zip(\.enc)?$/', $name)) {
            return ['ok' => false, 'error' => 'Μη έγκυρο όνομα αρχείου.'];
        }
        $path = srv_backup_dir() . '/' . $name;
        if (!is_file($path)) return ['ok' => false, 'error' => 'Το αντίγραφο δεν βρέθηκε.'];
        $blob = (string)@file_get_contents($path);
        if ($blob === '') return ['ok' => false, 'error' => 'Το αντίγραφο δεν διαβάζεται.'];
    }

    if (strncmp($blob, 'etimbk1', 7) === 0) {
        $dec = srv_backup_decrypt($blob, srv_backup_passphrase());
        if (!$dec['ok']) return $dec;
        $blob = $dec['bytes'];
    }

    $files = zip_unpack($blob);
    if (!$files) return ['ok' => false, 'error' => 'Το αρχείο δεν είναι αντίγραφο αυτής της εφαρμογής.'];

    $isPg   = srv_backup_is_pg();
    $member = $isPg ? 'db.dump' : 'local.sqlite';
    if (!isset($files[$member])) {
        // Το ανάποδο ζευγάρι είναι το συνηθισμένο λάθος: αντίγραφο από
        // εγκατάσταση SQLite πάνω σε server Postgres, ή το αντίστροφο.
        $has = isset($files['db.dump']) ? 'Postgres' : (isset($files['local.sqlite']) ? 'SQLite' : 'άγνωστη');
        return ['ok' => false, 'error' =>
            "Το αντίγραφο είναι $has, ο server τρέχει " . ($isPg ? 'Postgres' : 'SQLite') . '.'];
    }

    // --- 3. το κλειδί ------------------------------------------------------
    $keyFile = defined('ENC_KEY_FILE') ? (string)ENC_KEY_FILE : '';
    $keyBack = false;
    if (isset($files['.enckey']) && $keyFile !== '') {
        if (is_file($keyFile)) @copy($keyFile, $keyFile . '.pre-restore');
        $keyBack = @file_put_contents($keyFile, $files['.enckey']) !== false;
        if (!$keyBack) return ['ok' => false, 'error' => 'Δεν γράφτηκε το .enckey — τίποτα δεν άλλαξε.'];
    }

    // --- 4. η βάση ---------------------------------------------------------
    if ($isPg) {
        $dsn = [];
        foreach (explode(';', substr((string)DB_DSN, strlen('pgsql:'))) as $part) {
            [$k, $v] = array_pad(explode('=', $part, 2), 2, '');
            if ($k !== '') $dsn[trim($k)] = trim($v);
        }
        // `--clean --if-exists`: το dump γράφεται ΠΑΝΩ σε βάση που ήδη έχει
        // πίνακες. Χωρίς αυτά, το pg_restore σκάει σε κάθε «already exists»
        // και αφήνει τη βάση μισή.
        $cmd = sprintf('pg_restore --clean --if-exists --no-owner --no-privileges -h %s -p %s -U %s -d %s',
            escapeshellarg($dsn['host'] ?? 'localhost'),
            escapeshellarg((string)($dsn['port'] ?? '5432')),
            escapeshellarg((string)(defined('DB_USER') ? DB_USER : '')),
            escapeshellarg((string)($dsn['dbname'] ?? 'postgres')));
        $env = $_ENV;
        $env['PGPASSWORD'] = defined('DB_PASS') ? (string)DB_PASS : '';
        $proc = @proc_open($cmd, [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']],
                           $pipes, null, $env);
        if (!is_resource($proc)) return ['ok' => false, 'error' => 'δεν ξεκίνησε το pg_restore'];
        fwrite($pipes[0], $files['db.dump']);
        fclose($pipes[0]);
        $out = stream_get_contents($pipes[1]); fclose($pipes[1]);
        $err = stream_get_contents($pipes[2]); fclose($pipes[2]);
        $code = proc_close($proc);
        // Το pg_restore βγάζει προειδοποιήσεις («does not exist, skipping»)
        // ακόμη και όταν πετυχαίνει απόλυτα — γι' αυτό κρίνει ο κωδικός εξόδου.
        if ($code !== 0) {
            return ['ok' => false, 'error' => 'pg_restore: ' . trim(substr((string)($err ?: $out), 0, 400)),
                    'safety' => $safetyName];
        }
    } else {
        $path = defined('LOCAL_DB') ? (string)LOCAL_DB : '';
        if ($path === '') return ['ok' => false, 'error' => 'δεν βρέθηκε η βάση'];
        // Δύο πράγματα, με αυτή τη σειρά, και τα δύο υποχρεωτικά:
        //   1. το WAL της ΠΑΛΙΑΣ βάσης να μπει μέσα της και να αδειάσει —
        //      αλλιώς ξαναπαίζεται πάνω στη νέα και τη χαλάει,
        //   2. η σύνδεση να **κλείσει**. Γράψιμο πάνω σε ανοιχτή SQLite αφήνει
        //      τη βάση «malformed» για το ίδιο αίτημα: η επαναφορά λέει
        //      «επιτυχία» και η επόμενη οθόνη λέει «η βάση δεν είναι
        //      διαθέσιμη».
        try { localdb()->exec('PRAGMA wal_checkpoint(TRUNCATE)'); } catch (Throwable $e) {}
        localdb(true);
        if (@file_put_contents($path, $files['local.sqlite']) === false) {
            return ['ok' => false, 'error' => 'δεν γράφτηκε η βάση', 'safety' => $safetyName];
        }
        foreach (['-wal', '-shm'] as $suffix) @unlink($path . $suffix);
    }

    $manifest = isset($files['manifest.json']) ? json_decode($files['manifest.json'], true) : null;
    setting_set('srvbackup.restored_at', date('Y-m-d H:i'));
    return ['ok' => true,
            'engine'   => $isPg ? 'postgres' : 'sqlite',
            'enckey'   => $keyBack,
            'from'     => ['drive' => 'Google Drive', 'upload' => 'ανεβασμένο αρχείο'][$source] ?? 'τοπικό αρχείο',
            'taken_at' => (string)($manifest['at'] ?? ''),
            'reason'   => (string)($manifest['reason'] ?? ''),
            'safety'   => $safetyName];
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
                    'id'   => (string)($f['id'] ?? ''),
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
        'restored_at' => setting_get('srvbackup.restored_at'),
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
