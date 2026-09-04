<?php
// ============================================================================
// serverlink.php — η τοπική εγκατάσταση απέναντι στον web server
// ----------------------------------------------------------------------------
// Ό,τι χρειάζεται μια εγκατάσταση γραφείου για να ζήσει δίπλα σε έναν κοινό
// server: να δεθεί μαζί του με κλειδί, να συγχρονιστεί αμφίδρομα, και να κρατά
// τα δικά της αντίγραφα ασφαλείας.
//
// Ζει σε ΔΙΚΟ του αρχείο και όχι μέσα στο `etimologio.php`, ώστε να μπορεί να
// δοκιμαστεί χωρίς να σηκωθεί ολόκληρη η εφαρμογή: το `tools/pg_smoke.php` το
// φορτώνει σκέτο και ελέγχει, π.χ., τη μορφή του κλειδιού.
//
// Απαιτεί: crypto.php + localdb.php (ρυθμίσεις, πληρωμές, καρτέλες) και
// zipwriter.php (αντίγραφα). Δεν παράγει καμία έξοδο.
// ============================================================================

require_once __DIR__ . '/localdb.php';
require_once __DIR__ . '/zipwriter.php';

// ===========================================================================
// ΣΥΝΔΕΣΗ ΕΓΚΑΤΑΣΤΑΣΗΣ ΓΡΑΦΕΙΟΥ ↔ WEB SERVER (κλειδιά σύνδεσης)
// ---------------------------------------------------------------------------
// Το γραφείο δουλεύει τοπικά (SQLite, δικό του PHP). Ο web server είναι
// ΠΡΟΑΙΡΕΤΙΚΟΣ: όταν η εγκατάσταση δεθεί μαζί του, τα δεδομένα ζουν ΕΚΕΙ και ο
// λογιστής έχει έναν σύνδεσμο να δώσει στον πελάτη του — web εφαρμογή, χωρίς
// καμία εγκατάσταση στη μεριά του πελάτη.
//
// Το δέσιμο γίνεται με το **κλειδί πρόσβασης** που φτιάχνει ο διαχειριστής του
// server (Ρυθμίσεις → Κλειδιά πρόσβασης). Το κλειδί κουβαλά μέσα του και τη
// διεύθυνση (`etim1_<base64 host>_<μυστικό>`), οπότε ο λογιστής δεν χρειάζεται
// να ξέρει πού ζει ο server: επικολλά και τελείωσε.
//
// Πού γράφεται τι:
//   service.json  → `mode: thin` + `server_url` — από εκεί το διαβάζει η ίδια η
//                   εφαρμογή υπολογιστή στο επόμενο άνοιγμα
//   app_settings  → `link.label` (ποιον λογαριασμό αναγνώρισε το κλειδί) και
//                   `link.since` (πότε δέθηκε), για να τα δείχνει η οθόνη
// ---------------------------------------------------------------------------

/** Τρέχει σε εγκατάσταση γραφείου (όχι στον server); */
function link_is_local(): bool {
    return defined('DESKTOP_TOKEN') && DESKTOP_TOKEN !== '';
}

function link_url(): string { return rtrim((string)(link_service_conf()['server_url'] ?? ''), '/'); }

/**
 * Το `service.json` της εγκατάστασης — το ίδιο αρχείο που διαβάζει η εφαρμογή
 * υπολογιστή για να αποφασίσει αν σηκώνει τοπικό backend ή μιλά σε server.
 *
 * Ζει δίπλα στα δεδομένα (ο φάκελος του `LOCAL_DB`), όχι στο web root.
 */
function link_service_path(): string {
    $dir = (defined('LOCAL_DB') && LOCAL_DB !== '') ? dirname(LOCAL_DB) : __DIR__;
    return $dir . '/service.json';
}

function link_service_conf(): array {
    $raw = @file_get_contents(link_service_path());
    $d = $raw !== false ? json_decode($raw, true) : null;
    return is_array($d) ? $d : [];
}

/**
 * Γράφει ΜΟΝΟ τα κλειδιά που του δίνεις, κρατώντας τα υπόλοιπα.
 *
 * Στο ίδιο αρχείο ζουν τα διαπιστευτήρια εκκίνησης και τα tokens της
 * εγκατάστασης: ένα ολικό ξαναγράψιμο θα τα έσβηνε και η εφαρμογή δεν θα
 * ξανάνοιγε.
 */
function link_service_write(array $patch): bool {
    $conf = array_merge(link_service_conf(), $patch);
    $json = json_encode($conf, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return @file_put_contents(link_service_path(), $json) !== false;
}

/**
 * Σπάει το κλειδί πρόσβασης `etim1_<base64 host>_<μυστικό>` σε (URL, μυστικό).
 *
 * Η διεύθυνση ταξιδεύει ΜΕΣΑ στο κλειδί επίτηδες — αλλιώς ο λογιστής θα έπρεπε
 * να ξέρει και να πληκτρολογεί τον server, που ήταν ακριβώς αυτό που έπρεπε να
 * φύγει από τη μέση. Τοπικές διευθύνσεις μιλούν http, όλες οι άλλες https.
 */
function link_decode_key(string $token): array {
    $parts = explode('_', trim($token));
    if (count($parts) !== 3 || $parts[0] !== 'etim1' || $parts[2] === '') return ['', ''];
    // ΠΡΟΣΟΧΗ: το `%` της PHP δίνει ΑΡΝΗΤΙΚΟ για αρνητικό αριστερό μέλος, οπότε
    // το «(-μήκος) % 4» έσκαγε στο str_repeat(). Το padding υπολογίζεται θετικά.
    $pad  = (4 - strlen($parts[1]) % 4) % 4;
    $host = base64_decode(strtr($parts[1], '-_', '+/') . str_repeat('=', $pad), true);
    if ($host === false || trim($host) === '') return ['', ''];
    $local  = preg_match('#^(127\.0\.0\.1|localhost)(:|$)#i', $host) === 1;
    return [($local ? 'http://' : 'https://') . rtrim($host, '/'), $parts[2]];
}

/**
 * Μία κλήση προς τον web server.
 *
 * Επιστρέφει πάντα πίνακα: `['ok'=>bool, 'data'=>?array, 'error'=>string]`. Ο
 * καλών δεν πρέπει ποτέ να δει HTML σφάλματος ή γυμνό timeout — η σύνδεση με
 * τον server είναι προαιρετική και η αποτυχία της δεν σταματά τη δουλειά.
 */
function link_call(string $url, array $params, array $post = [], int $timeout = 30, string $key = ''): array {
    $url = rtrim($url, '/');
    if ($url === '') return ['ok' => false, 'data' => null, 'error' => 'Δεν έχει οριστεί διεύθυνση server'];
    $endpoint = $url . '/etimologio.php?' . http_build_query($params);

    $ch = curl_init($endpoint);
    $opts = [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => $timeout,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTPHEADER     => $key !== ''
            ? ['Accept: application/json', 'Authorization: Bearer ' . $key]
            : ['Accept: application/json'],
    ];
    if ($post) {
        // ΤΟ ΚΛΕΙΔΙ ΤΑΞΙΔΕΥΕΙ ΚΑΙ ΩΣ ΠΕΔΙΟ, όχι μόνο ως κεφαλίδα. Η
        // `Authorization` είναι η καθαρή διαδρομή, αλλά είναι και η πιο εύθραυστη
        // στη μέση: ο Apache την κόβει από το περιβάλλον CGI/FastCGI χωρίς
        // `CGIPassAuth On`, και κάθε ενδιάμεσος (proxy, CDN, load balancer) έχει
        // το δικαίωμα να μην την προωθήσει. Το αποτέλεσμα ήταν 401 σε ΚΑΘΕ
        // εταιρεία και ένα «Ανέβηκαν 0 εταιρείες» χωρίς καμία εξήγηση.
        //
        // Ο server δέχεται ήδη το `access_key` ως πεδίο (`auth_access_key_login`),
        // οπότε αυτό δεν είναι νέα επιφάνεια — είναι η ίδια πόρτα, χωρίς την
        // κεφαλίδα που μπορεί να χαθεί.
        if ($key !== '' && !isset($post['access_key'])) $post['access_key'] = $key;
        $opts[CURLOPT_POST] = true;
        $opts[CURLOPT_POSTFIELDS] = http_build_query($post);
    }
    curl_setopt_array($ch, $opts);
    $body = curl_exec($ch);
    $err  = curl_error($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);

    if ($body === false || $err !== '') {
        return ['ok' => false, 'data' => null, 'http' => $code,
                'error' => 'Δεν απαντά ο server: ' . $err];
    }
    $data = json_decode((string)$body, true);
    if (!is_array($data)) {
        return ['ok' => false, 'data' => null, 'http' => $code,
                'error' => 'Ο server απάντησε κάτι που δεν είναι JSON (HTTP ' . $code . ')'];
    }
    if (empty($data['success'])) {
        return ['ok' => false, 'data' => $data, 'http' => $code,
                'error' => (string)($data['error'] ?? ('HTTP ' . $code))];
    }
    return ['ok' => true, 'data' => $data, 'http' => $code, 'error' => ''];
}

// --- Αντίγραφα ασφαλείας της τοπικής εγκατάστασης ---------------------------
//
// Ο δίσκος που χάλασε παίρνει μαζί του και τα κλειδιά ΑΑΔΕ κάθε πελάτη, που δεν
// ανακτώνται από πουθενά. Το zip περιέχει **και** τη βάση **και** το κλειδί
// κρυπτογράφησης: χωριστά, κανένα από τα δύο δεν είναι χρήσιμο.
//
// Ζει εδώ (PHP) και όχι στον Πίνακα ελέγχου του Downloader, γιατί είναι ρύθμιση
// του e-Τιμολόγιο: ο χρήστης τη ζητά όσο βρίσκεται μέσα στο e-Τιμολόγιο Pro.

/** Ο φάκελος των δεδομένων της εγκατάστασης (εκεί ζει η βάση και το κλειδί). */
function link_data_dir(): string {
    return (defined('LOCAL_DB') && LOCAL_DB !== '') ? dirname(LOCAL_DB) : __DIR__;
}

function link_backup_dir(): string {
    $dir = link_data_dir() . '/backups';
    if (!is_dir($dir)) @mkdir($dir, 0700, true);
    return $dir;
}

/** Τα αντίγραφα, νεότερο πρώτο. */
function link_backup_files(): array {
    $files = glob(link_backup_dir() . '/etimologio-*.zip') ?: [];
    usort($files, static fn($a, $b) => filemtime($b) <=> filemtime($a));
    return $files;
}

/**
 * Φτιάχνει ένα αντίγραφο και κρατά τα 14 νεότερα.
 *
 * Το ZIP χτίζεται με το `zipwriter.php` (zlib), όχι με `ZipArchive`: η φορητή
 * PHP που πακετάρει η εφαρμογή δεν έχει την επέκταση `zip`, και ένα αντίγραφο
 * ασφαλείας που δουλεύει «μόνο σε πλήρη εγκατάσταση PHP» δεν είναι αντίγραφο
 * ασφαλείας.
 */
function link_backup_run(int $keep = 14): array {
    $data = link_data_dir();
    $files = [];
    // Το WAL κρατά εγγραφές που δεν πέρασαν ακόμη στο κύριο αρχείο — χωρίς αυτό,
    // ένα αντίγραφο «εν ώρα εργασίας» χάνει τις τελευταίες κινήσεις.
    foreach (['local.sqlite', 'local.sqlite-wal', 'local.sqlite-shm', '.enckey', 'service.json'] as $name) {
        $path = $data . '/' . $name;
        if (is_file($path)) {
            $bytes = @file_get_contents($path);
            if ($bytes !== false) $files[$name] = $bytes;
        }
    }
    if (!isset($files['local.sqlite'])) return ['ok' => false, 'error' => 'δεν βρέθηκε η βάση'];

    $archive = link_backup_dir() . '/etimologio-' . date('Ymd-His') . '.zip';
    $bytes   = zip_build($files);
    if (@file_put_contents($archive, $bytes) === false) {
        return ['ok' => false, 'error' => 'δεν γράφτηκε το αρχείο'];
    }
    $pruned = 0;
    foreach (array_slice(link_backup_files(), $keep) as $old) {
        if (@unlink($old)) $pruned++;
    }
    return ['ok' => true, 'name' => basename($archive), 'size' => strlen($bytes),
            'folder' => link_backup_dir(), 'pruned' => $pruned, 'members' => array_keys($files)];
}

/**
 * Το ημερήσιο αντίγραφο της ΤΟΠΙΚΗΣ εγκατάστασης.
 *
 * Μέχρι τώρα το αντίγραφο γινόταν μόνο με το κουμπί «Αντίγραφο τώρα»: δηλαδή
 * όποτε το θυμόταν κανείς, που για ένα αντίγραφο ασφαλείας σημαίνει «σχεδόν
 * ποτέ, και σίγουρα όχι τη μέρα που χάλασε ο δίσκος».
 *
 * Ο φύλακας είναι η ΗΜΕΡΟΜΗΝΙΑ και όχι χρονόμετρο: η εφαρμογή ανοίγει και
 * κλείνει πολλές φορές τη μέρα, και ένα «κάθε 24 ώρες» μετρημένο από την
 * εκκίνηση θα έπαιρνε αντίγραφο σε κάθε άνοιγμα. Με τη σφραγίδα ημέρας το
 * αντίγραφο είναι **ένα**, το πρώτο άνοιγμα κάθε μέρας.
 *
 * Επιστρέφει πάντα πίνακα με `ran`: ψευδές σημαίνει «δεν χρειαζόταν», όχι
 * αποτυχία.
 */
function link_backup_tick(): array {
    if (setting_get('link.backup.auto', '1') !== '1') {
        return ['ran' => false, 'why' => 'off'];
    }
    $today = date('Y-m-d');
    if (setting_get('link.backup.day') === $today) {
        return ['ran' => false, 'why' => 'done_today'];
    }
    // Η σφραγίδα μπαίνει ΠΡΙΝ τη δουλειά: μια αποτυχία που επαναλαμβάνεται σε
    // κάθε τικ θα γέμιζε τον δίσκο με μισογραμμένα zip και τα logs με το ίδιο
    // σφάλμα κάθε λεπτό. Ξαναδοκιμάζει αύριο.
    setting_set('link.backup.day', $today);
    $r = link_backup_run();
    if (empty($r['ok'])) {
        setting_set('link.backup.last_error', (string)($r['error'] ?? 'απέτυχε'));
        return ['ran' => true, 'ok' => false, 'error' => (string)($r['error'] ?? 'απέτυχε')];
    }
    setting_set('link.backup.last_error', '');
    setting_set('link.backup.last_auto', date('Y-m-d H:i'));
    return ['ran' => true, 'ok' => true, 'name' => $r['name'], 'size' => $r['size']];
}

// --- Αμφίδρομος συγχρονισμός: τι ταξιδεύει και πώς αναγνωρίζεται -------------
//
// Δύο βάσεις (τοπική SQLite ↔ Postgres του server) πρέπει να καταλήγουν με τα
// ΙΔΙΑ δεδομένα, χωρίς κεντρικό «αφεντικό» και χωρίς να διπλογράφεται τίποτα
// όταν ο ίδιος συγχρονισμός τρέξει δέκα φορές.
//
// Ο κανόνας ανά πίνακα:
//   • πληρωμές    — καθαρή προσθήκη. Ταυτότητα = αποτύπωμα του περιεχομένου
//                   (πελάτης+ημερομηνία+ποσό+ΜΑΡΚ+σημείωση). Ό,τι λείπει, μπαίνει.
//   • καρτέλες    — μεταβλητές, με κλειδί το (ΑΦΜ, πελάτης): κερδίζει η
//                   **νεότερη** `updated_at`. Ίδια ώρα → μένει ό,τι υπάρχει.
// Οι διαγραφές ΔΕΝ ταξιδεύουν: χωρίς ταφόπλακες, μια διαγραφή στη μία πλευρά
// θα ξαναγύριζε από την άλλη. Είναι συνειδητό όριο, γραμμένο και στο DEPLOY.md.

/** Το αποτύπωμα μιας πληρωμής — δύο ίδιες πληρωμές είναι η ίδια πληρωμή. */
function sync_pay_fingerprint(array $p): string {
    return sha1(implode('|', [
        (string)($p['customer_vat'] ?? ''), (string)($p['pay_date'] ?? ''),
        number_format((float)($p['amount'] ?? 0), 2, '.', ''),
        (string)($p['mark'] ?? ''), (string)($p['notes'] ?? ''),
    ]));
}

/** Οι πληρωμές μιας εταιρείας, αποκρυπτογραφημένες, έτοιμες να ταξιδέψουν. */
function sync_payments(string $vat): array {
    return array_map(static fn($p) => [
        'customer_vat'  => (string)($p['customer_vat'] ?? ''),
        'customer_code' => (string)($p['customer_code'] ?? ''),
        'customer_name' => (string)($p['customer_name'] ?? ''),
        'amount'        => (float)($p['amount'] ?? 0),
        'method'        => (int)($p['method'] ?? 3),
        'pay_date'      => (string)($p['pay_date'] ?? ''),
        // Ταξιδεύουν κι αυτά: αλλιώς η άλλη πλευρά κρατά την πληρωμή αλλά χάνει
        // το «σε ποια τράπεζα ήρθε» — και το αποτύπωμα δεν αλλάζει, οπότε δεν
        // ξαναγράφεται ποτέ.
        'bank'          => (string)($p['bank'] ?? ''),
        'bank_account'  => (string)($p['bank_account'] ?? ''),
        'mark'          => (string)($p['mark'] ?? ''),
        'notes'         => (string)($p['notes'] ?? ''),
    ], payments_list($vat));
}

/** Οι καρτέλες πελατών μιας εταιρείας, με την ώρα τους (για το «ποιος νικά»). */
function sync_customer_meta(string $vat): array {
    $st = localdb()->prepare("SELECT * FROM customer_meta WHERE account_vat = :a");
    $st->execute([':a' => $vat]);
    $out = [];
    foreach ($st->fetchAll() as $r) {
        $out[] = [
            'customer_vat'    => (string)$r['customer_vat'],
            'customer_name'   => dec($r['customer_name']),
            'opening_balance' => dec_num($r['opening_balance']),
            'notes'           => dec($r['notes']),
            'updated_at'      => (string)($r['updated_at'] ?? ''),
        ];
    }
    return $out;
}

/**
 * Γράφει ό,τι ήρθε από την άλλη πλευρά και επιστρέφει τι πραγματικά άλλαξε.
 *
 * Ίδια συνάρτηση και στις δύο άκρες — γι' αυτό ο συγχρονισμός είναι συμμετρικός:
 * ο server δεν είναι «πιο σωστός» από το γραφείο, απλώς είναι η άλλη πλευρά.
 */
function sync_apply(string $vat, array $payments, array $meta): array {
    $seen = [];
    foreach (payments_list($vat) as $p) $seen[sync_pay_fingerprint($p)] = true;
    $added = 0;
    foreach ($payments as $p) {
        $row = [
            'customer_vat'  => (string)($p['customer_vat'] ?? ''),
            'customer_code' => (string)($p['customer_code'] ?? ''),
            'customer_name' => (string)($p['customer_name'] ?? ''),
            'amount'        => (float)($p['amount'] ?? 0),
            'method'        => (int)($p['method'] ?? 3),
            'pay_date'      => (string)($p['pay_date'] ?? ''),
            'bank'          => (string)($p['bank'] ?? ''),
            'bank_account'  => (string)($p['bank_account'] ?? ''),
            'mark'          => (string)($p['mark'] ?? ''),
            'notes'         => (string)($p['notes'] ?? ''),
        ];
        if ($row['pay_date'] === '') continue;
        $fp = sync_pay_fingerprint($row);
        if (isset($seen[$fp])) continue;
        payment_add($vat, $row);
        $seen[$fp] = true;
        $added++;
    }

    // Καρτέλες: κρατιέται η νεότερη εγγραφή, όχι η τελευταία που έφτασε.
    $mine = [];
    foreach (sync_customer_meta($vat) as $m) $mine[$m['customer_vat']] = $m;
    $updated = 0;
    foreach ($meta as $m) {
        $cv = preg_replace('/\D/', '', (string)($m['customer_vat'] ?? ''));
        if ($cv === '') continue;
        // Ίδιο περιεχόμενο = τίποτα να γίνει, ΟΤΙΔΗΠΟΤΕ κι αν λένε οι ώρες.
        // Χωρίς αυτόν τον έλεγχο οι δύο πλευρές ξαναγράφουν αιώνια η μία την
        // άλλη (κάθε γράψιμο ανανεώνει το `updated_at` και γίνεται «νεότερο»),
        // και κάθε συγχρονισμός θα ανέφερε αλλαγές που δεν έγιναν ποτέ.
        $same = isset($mine[$cv])
            && (string)$mine[$cv]['customer_name'] === (string)($m['customer_name'] ?? '')
            && abs((float)$mine[$cv]['opening_balance'] - (float)($m['opening_balance'] ?? 0)) < 0.005
            && (string)$mine[$cv]['notes'] === (string)($m['notes'] ?? '');
        if ($same) continue;
        $theirs = (string)($m['updated_at'] ?? '');
        $ours   = (string)($mine[$cv]['updated_at'] ?? '');
        if ($ours !== '' && $theirs !== '' && strcmp($theirs, $ours) <= 0) continue;
        customer_meta_set($vat, $cv, [
            'customer_name'   => (string)($m['customer_name'] ?? ''),
            'opening_balance' => (float)($m['opening_balance'] ?? 0),
            'notes'           => (string)($m['notes'] ?? ''),
        ]);
        $updated++;
    }
    return ['payments_added' => $added, 'customer_meta_updated' => $updated];
}

/**
 * Συγχρονίζει ΟΛΕΣ τις ορατές εταιρείες του χρήστη με τον server.
 *
 * Ζει εδώ και όχι μέσα στο `?auth=link_sync`, γιατί τον καλούν ΔΥΟ διαδρομές:
 * το κουμπί «Συγχρονισμός τώρα» και η πρώτη καταχώρηση κλειδιού — εκείνη
 * πρέπει να αφήσει τον server με δεδομένα μέσα, αλλιώς ο λογιστής συνδέεται
 * και βλέπει άδειο πρόγραμμα.
 */
function link_sync_all(array $me): array {
    [$keyBase, $key] = link_decode_key(setting_get('link.key'));
    $url = link_url() ?: $keyBase;
    if ($key === '' || $url === '') return ['ok' => false, 'error' => 'χωρίς κλειδί',
                                            'companies' => 0, 'errors' => ['Δεν έχει καταχωρηθεί κλειδί πρόσβασης.']];
    $sent = 0; $recv = 0; $companies = 0; $errors = [];
    $visible = auth_visible_accounts($me);
    // «Ανέβηκαν 0» χωρίς λόγο είναι η χειρότερη απάντηση. Αν δεν υπάρχει καμία
    // εταιρεία, αυτό ΕΙΝΑΙ ο λόγος και πρέπει να ειπωθεί.
    if (!$visible) {
        return ['ok' => false, 'companies' => 0, 'sent' => 0, 'recv' => 0,
                'errors' => ['Δεν υπάρχει καμία εταιρεία σε αυτή την εγκατάσταση για να ανέβει.']];
    }
    foreach ($visible as $a) {
        $vat  = (string)$a['vat'];
        $full = account_by_vat($vat) ?: [];
        $payload = [
            'vat'           => $vat,
            'label'         => (string)($full['label'] ?? ''),
            'username'      => (string)($full['username'] ?? ''),
            'subkey'        => (string)($full['subkey'] ?? ''),
            'payments'      => sync_payments($vat),
            'customer_meta' => sync_customer_meta($vat),
        ];
        $r = link_call($url, ['api' => 'sync'],
                       ['payload' => json_encode($payload, JSON_UNESCAPED_UNICODE)], 120, $key);
        if (!$r['ok']) { $errors[] = $vat . ': ' . $r['error']; continue; }
        $back = sync_apply($vat, (array)($r['data']['payments'] ?? []),
                                 (array)($r['data']['customer_meta'] ?? []));
        $applied = (array)($r['data']['applied'] ?? []);
        $sent += (int)($applied['payments_added'] ?? 0);
        $recv += (int)($back['payments_added'] ?? 0);
        $companies++;
    }
    setting_set('link.last_sync', date('Y-m-d H:i'));
    return ['ok' => empty($errors), 'companies' => $companies,
            'sent' => $sent, 'recv' => $recv, 'errors' => $errors];
}

