<?php
// ============================================================================
// migrate_to_server.php — one-off local (SQLite) → server (Postgres) copy
// ============================================================================
// Run once, when an office that started offline moves onto the shared VPS. This
// is deliberately a straight export/import and NOT continuous sync: two-way
// replication of encrypted rows would add a whole failure surface for a
// migration that happens once.
//
//   php tools/migrate_to_server.php --from /path/.localdata.sqlite \
//       --dsn "pgsql:host=db;port=5432;dbname=etimologio" --user u --pass p [--dry-run]
//
// Rows are copied verbatim, ciphertext included, so the SAME .enckey must be in
// place on the server — otherwise everything imports and nothing is readable.
// ----------------------------------------------------------------------------

$opts = getopt('', ['from:', 'dsn:', 'user::', 'pass::', 'dry-run']);
foreach (['from', 'dsn'] as $required) {
    if (empty($opts[$required])) {
        fwrite(STDERR, "Λείπει --$required\n");
        fwrite(STDERR, "Χρήση: php tools/migrate_to_server.php --from <sqlite> --dsn <pgsql-dsn> [--user u --pass p] [--dry-run]\n");
        exit(2);
    }
}
$dry = isset($opts['dry-run']);

$src = new PDO('sqlite:' . $opts['from'], null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$dst = new PDO($opts['dsn'], $opts['user'] ?? null, $opts['pass'] ?? null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);

// Order matters: parents before the rows that reference them.
$TABLES = [
    'users', 'aade_accounts', 'user_accounts', 'app_cache',
    'payments', 'customer_meta', 'cust_delivery',
    'scheduled_jobs', 'issue_notifications',
];

function columns(PDO $pdo, string $table): array {
    try {
        $st = $pdo->query("SELECT * FROM $table LIMIT 0");
        $out = [];
        for ($i = 0; $i < $st->columnCount(); $i++) $out[] = $st->getColumnMeta($i)['name'];
        return $out;
    } catch (Throwable $e) {
        return [];
    }
}

$total = 0; $skipped = [];
foreach ($TABLES as $table) {
    $srcCols = columns($src, $table);
    $dstCols = columns($dst, $table);
    if (!$srcCols) { $skipped[] = "$table (λείπει στην πηγή)"; continue; }
    if (!$dstCols) { $skipped[] = "$table (λείπει στον προορισμό — τρέξε πρώτα την εφαρμογή ώστε να δημιουργηθούν οι πίνακες)"; continue; }

    // Only columns both sides share: the schema may have moved on.
    $cols = array_values(array_intersect($srcCols, $dstCols));
    if (!$cols) { $skipped[] = "$table (καμία κοινή στήλη)"; continue; }

    $rows = $src->query("SELECT " . implode(',', $cols) . " FROM $table")->fetchAll(PDO::FETCH_ASSOC);
    if (!$rows) { echo str_pad($table, 22) . "0\n"; continue; }

    if (!$dry) {
        $place = implode(',', array_fill(0, count($cols), '?'));
        // ON CONFLICT DO NOTHING → the script is safe to re-run after a partial
        // failure; already-copied rows are simply left alone.
        $sql = "INSERT INTO $table (" . implode(',', $cols) . ") VALUES ($place) ON CONFLICT DO NOTHING";
        $ins = $dst->prepare($sql);
        $dst->beginTransaction();
        try {
            foreach ($rows as $r) $ins->execute(array_values($r));
            $dst->commit();
        } catch (Throwable $e) {
            $dst->rollBack();
            fwrite(STDERR, "ΣΦΑΛΜΑ στον πίνακα $table: " . $e->getMessage() . "\n");
            exit(1);
        }
    }
    $total += count($rows);
    echo str_pad($table, 22) . count($rows) . ($dry ? "  (dry-run)" : "") . "\n";
}

// Postgres identity sequences do not know about the ids we just forced in.
if (!$dry) {
    foreach ($TABLES as $table) {
        try {
            $dst->exec("SELECT setval(pg_get_serial_sequence('$table','id'), COALESCE((SELECT MAX(id) FROM $table),1))");
        } catch (Throwable $e) {
            // No id sequence on this table (join tables) — nothing to reset.
        }
    }
}

echo "\nΣύνολο: $total εγγραφές" . ($dry ? " (δεν γράφτηκε τίποτα)" : " μεταφέρθηκαν") . "\n";
if ($skipped) echo "Παραλείφθηκαν:\n  - " . implode("\n  - ", $skipped) . "\n";
echo "\nΘύμισε: αντέγραψε και το .enckey στον server, αλλιώς τα κρυπτογραφημένα πεδία δεν διαβάζονται.\n";
