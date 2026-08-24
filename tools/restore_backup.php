<?php
// ============================================================================
// tools/restore_backup.php — ανοίγει ένα αντίγραφο του server
// ----------------------------------------------------------------------------
//   php tools/restore_backup.php <αρχείο.zip.enc> [φάκελος-εξόδου]
//
// Η φράση-κλειδί διαβάζεται από το `BACKUP_PASSPHRASE` (env ή Infisical) ή
// δίνεται στο stdin. Βγάζει το zip και, αν ζητηθεί, το ξεπακετάρει.
//
// ΓΙΑΤΙ ΥΠΑΡΧΕΙ: ένα αντίγραφο που δεν ξέρεις να ανοίξεις δεν είναι αντίγραφο.
// Το σενάριο της επαναφοράς πρέπει να δοκιμάζεται ΠΡΙΝ το χρειαστείς, και να
// μη χρειάζεται τίποτα από την ίδια την εφαρμογή που μόλις χάθηκε.
//
// Επαναφορά μετά την εξαγωγή:
//   pg_restore -d "$DATABASE_URL" --clean --no-owner db.dump   (Postgres)
//   cp local.sqlite /data/.localdata.sqlite   (SQLite)
//   cp .enckey /data/.enckey             ΚΡΙΣΙΜΟ — χωρίς αυτό τα κρυπτογραφημένα
//                                        πεδία δεν διαβάζονται ποτέ ξανά.
// ============================================================================

if (PHP_SAPI !== 'cli') { http_response_code(403); exit("CLI only\n"); }

$root = dirname(__DIR__);
$src  = $argv[1] ?? '';
$dest = $argv[2] ?? '';

if ($src === '' || !is_file($src)) {
    fwrite(STDERR, "Χρήση: php tools/restore_backup.php <αρχείο.zip.enc> [φάκελος]\n");
    exit(2);
}

$bytes = file_get_contents($src);
if ($bytes === false) { fwrite(STDERR, "δεν διαβάζεται το αρχείο\n"); exit(1); }

if (str_starts_with($bytes, 'etimbk1')) {
    if (!function_exists('sodium_crypto_secretbox_open')) {
        fwrite(STDERR, "λείπει η επέκταση sodium\n"); exit(1);
    }
    $pass = getenv('BACKUP_PASSPHRASE') ?: '';
    if ($pass === '' && is_file($root . '/infisical.php')) {
        require_once $root . '/config.php';
        require_once $root . '/infisical.php';
        $pass = secret_get('BACKUP_PASSPHRASE');
    }
    if ($pass === '') {
        fwrite(STDOUT, "Φράση-κλειδί: ");
        $pass = trim((string)fgets(STDIN));
    }
    $off   = strlen('etimbk1');
    $salt  = substr($bytes, $off, SODIUM_CRYPTO_PWHASH_SALTBYTES);
    $nonce = substr($bytes, $off + SODIUM_CRYPTO_PWHASH_SALTBYTES, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $cipher = substr($bytes, $off + SODIUM_CRYPTO_PWHASH_SALTBYTES + SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $key = sodium_crypto_pwhash(
        SODIUM_CRYPTO_SECRETBOX_KEYBYTES, $pass, $salt,
        SODIUM_CRYPTO_PWHASH_OPSLIMIT_INTERACTIVE,
        SODIUM_CRYPTO_PWHASH_MEMLIMIT_INTERACTIVE
    );
    $plain = sodium_crypto_secretbox_open($cipher, $nonce, $key);
    sodium_memzero($key);
    if ($plain === false) {
        fwrite(STDERR, "λάθος φράση-κλειδί (ή χαλασμένο αρχείο)\n"); exit(1);
    }
    $bytes = $plain;
    fwrite(STDOUT, "αποκρυπτογραφήθηκε: " . number_format(strlen($bytes)) . " bytes\n");
}

// Ο φάκελος φτιάχνεται αν λείπει: βρέθηκε στη δοκιμή επαναφοράς, όπου το
// εργαλείο αποκρυπτογραφούσε σωστά και μετά δεν είχε πού να γράψει.
$outDir = $dest !== '' ? rtrim($dest, "/\\") : dirname($src);
if (!is_dir($outDir)) @mkdir($outDir, 0700, true);
$zipPath = $outDir . '/' . basename($src, '.enc');
if (!str_ends_with($zipPath, '.zip')) $zipPath .= '.zip';
if (file_put_contents($zipPath, $bytes) === false) {
    fwrite(STDERR, "δεν γράφτηκε το $zipPath\n"); exit(1);
}
fwrite(STDOUT, "γράφτηκε: $zipPath\n");

// Περιεχόμενα, χωρίς ZipArchive (η φορητή PHP δεν το έχει πάντα): διαβάζουμε
// τον κεντρικό κατάλογο του ZIP όσο χρειάζεται για να δείξουμε τα ονόματα.
$names = [];
$p = 0;
while (($p = strpos($bytes, "PK\x01\x02", $p)) !== false) {
    $len = unpack('v', substr($bytes, $p + 28, 2))[1];
    $names[] = substr($bytes, $p + 46, $len);
    $p += 46 + $len;
}
fwrite(STDOUT, "περιέχει: " . ($names ? implode(', ', $names) : '—') . "\n");
