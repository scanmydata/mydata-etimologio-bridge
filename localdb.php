<?php
// ============================================================================
// Local data store (SQLite) — for data e-timologio does NOT keep.
// ----------------------------------------------------------------------------
// Multi-tenant: every row is scoped by `account_vat` (the issuing company) so a
// single database file can serve many e-timologio accounts, each with many
// customers. Payments here are LOCAL ONLY — they are never sent to AADE.
//
// Sensitive content (customer name, notes, amounts) is encrypted at rest via
// crypto.php. Identifier/index fields (VATs, dates, method, mark) stay plain so
// the app can still filter and scope. Aggregation is done in PHP after decrypt.
// ============================================================================

require_once __DIR__ . '/crypto.php';

function localdb(): \PDO {
    static $pdo = null;
    if ($pdo !== null) return $pdo;

    $pdo = new \PDO('sqlite:' . LOCAL_DB);
    $pdo->setAttribute(\PDO::ATTR_ERRMODE, \PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(\PDO::ATTR_DEFAULT_FETCH_MODE, \PDO::FETCH_ASSOC);
    $pdo->exec('PRAGMA journal_mode = WAL');

    // Encrypted fields are stored as TEXT (ciphertext). Index/date fields plain.
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS payments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            account_vat   TEXT NOT NULL,
            customer_vat  TEXT NOT NULL DEFAULT '',
            customer_code TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',   -- encrypted
            amount        TEXT NOT NULL DEFAULT '',    -- encrypted
            method        INTEGER NOT NULL DEFAULT 3,
            pay_date      TEXT NOT NULL,
            mark          TEXT NOT NULL DEFAULT '',
            notes         TEXT NOT NULL DEFAULT '',    -- encrypted
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_pay_acc_cust ON payments(account_vat, customer_vat)");

    // Encrypted snapshot cache of AADE data (customers/products/invoices) so the
    // UI can render instantly and only re-fetch/compare in the background.
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS app_cache (
            account_vat TEXT NOT NULL,
            kind        TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '',  -- encrypted JSON snapshot
            hash        TEXT NOT NULL DEFAULT '',
            synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (account_vat, kind)
        )
    ");

    $pdo->exec("
        CREATE TABLE IF NOT EXISTS customer_meta (
            account_vat     TEXT NOT NULL,
            customer_vat    TEXT NOT NULL,
            customer_name   TEXT NOT NULL DEFAULT '',  -- encrypted
            opening_balance TEXT NOT NULL DEFAULT '',  -- encrypted
            notes           TEXT NOT NULL DEFAULT '',  -- encrypted
            deliv_meta      TEXT NOT NULL DEFAULT '',  -- encrypted JSON: branch + delivery address
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (account_vat, customer_vat)
        )
    ");
    // Upgrade path for DBs created before deliv_meta existed.
    try { $pdo->exec("ALTER TABLE customer_meta ADD COLUMN deliv_meta TEXT NOT NULL DEFAULT ''"); } catch (\Throwable $e) {}

    // --- Auth: application users (master admin + business accounts) ----------
    // email is the login identifier (kept plaintext so it can be queried).
    // role: 'master' | 'business'.  status: 'pending' | 'active' | 'disabled'.
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'business',
            status        TEXT NOT NULL DEFAULT 'pending',
            business_name TEXT NOT NULL DEFAULT '',
            reset_token   TEXT NOT NULL DEFAULT '',
            reset_expires INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");

    // AADE (e-timologio) credentials per business user. vat/label plaintext (used
    // for scoping local data + cookie file + account switching); the e-timologio
    // username and subscription key are encrypted at rest.
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS aade_accounts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            vat           TEXT NOT NULL,
            label         TEXT NOT NULL DEFAULT '',
            username_enc  TEXT NOT NULL DEFAULT '',   -- encrypted
            subkey_enc    TEXT NOT NULL DEFAULT '',   -- encrypted
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_acc_user ON aade_accounts(user_id)");

    return $pdo;
}

// --- Auth: users ------------------------------------------------------------

function user_public(array $r): array {
    return [
        'id'            => (int)$r['id'],
        'email'         => $r['email'],
        'role'          => $r['role'],
        'status'        => $r['status'],
        'business_name' => $r['business_name'],
        'created_at'    => $r['created_at'] ?? '',
    ];
}

function user_by_email(string $email): ?array {
    $st = localdb()->prepare("SELECT * FROM users WHERE email = :e");
    $st->execute([':e' => strtolower(trim($email))]);
    return $st->fetch() ?: null;
}

function user_by_id(int $id): ?array {
    $st = localdb()->prepare("SELECT * FROM users WHERE id = :id");
    $st->execute([':id' => $id]);
    return $st->fetch() ?: null;
}

function user_create(string $email, string $passwordHash, string $role, string $status, string $businessName): int {
    $st = localdb()->prepare("
        INSERT INTO users (email, password_hash, role, status, business_name)
        VALUES (:e, :p, :r, :s, :b)
    ");
    $st->execute([
        ':e' => strtolower(trim($email)), ':p' => $passwordHash,
        ':r' => $role, ':s' => $status, ':b' => trim($businessName),
    ]);
    return (int)localdb()->lastInsertId();
}

function user_update(int $id, array $fields): void {
    $allowed = ['password_hash', 'role', 'status', 'business_name', 'reset_token', 'reset_expires', 'email'];
    $sets = []; $args = [':id' => $id];
    foreach ($fields as $k => $v) {
        if (!in_array($k, $allowed, true)) continue;
        $sets[] = "$k = :$k"; $args[":$k"] = $v;
    }
    if (!$sets) return;
    $st = localdb()->prepare("UPDATE users SET " . implode(', ', $sets) . " WHERE id = :id");
    $st->execute($args);
}

function users_all(): array {
    $rows = localdb()->query("SELECT * FROM users ORDER BY (role='master') DESC, created_at DESC")->fetchAll();
    return array_map('user_public', $rows);
}

function users_count_master(): int {
    return (int)localdb()->query("SELECT COUNT(*) FROM users WHERE role='master'")->fetchColumn();
}

// --- Auth: AADE accounts ----------------------------------------------------

function account_row(array $r): array {
    return [
        'id'       => (int)$r['id'],
        'user_id'  => (int)$r['user_id'],
        'vat'      => $r['vat'],
        'label'    => $r['label'],
        'username' => dec($r['username_enc']),
        'subkey'   => dec($r['subkey_enc']),
        'created_at' => $r['created_at'] ?? '',
    ];
}

function accounts_for_user(int $userId): array {
    $st = localdb()->prepare("SELECT * FROM aade_accounts WHERE user_id = :u ORDER BY id ASC");
    $st->execute([':u' => $userId]);
    return array_map('account_row', $st->fetchAll());
}

function account_get(int $id): ?array {
    $st = localdb()->prepare("SELECT * FROM aade_accounts WHERE id = :id");
    $st->execute([':id' => $id]);
    $r = $st->fetch();
    return $r ? account_row($r) : null;
}

function account_add(int $userId, string $vat, string $label, string $username, string $subkey): int {
    $st = localdb()->prepare("
        INSERT INTO aade_accounts (user_id, vat, label, username_enc, subkey_enc)
        VALUES (:u, :v, :l, :un, :sk)
    ");
    $st->execute([
        ':u' => $userId, ':v' => preg_replace('/\D/', '', $vat), ':l' => trim($label),
        ':un' => enc(trim($username)), ':sk' => enc(trim($subkey)),
    ]);
    return (int)localdb()->lastInsertId();
}

function account_update(int $id, array $d): void {
    $st = localdb()->prepare("
        UPDATE aade_accounts SET vat = :v, label = :l, username_enc = :un, subkey_enc = :sk WHERE id = :id
    ");
    $st->execute([
        ':id' => $id, ':v' => preg_replace('/\D/', '', $d['vat'] ?? ''), ':l' => trim($d['label'] ?? ''),
        ':un' => enc(trim($d['username'] ?? '')), ':sk' => enc(trim($d['subkey'] ?? '')),
    ]);
}

function account_delete(int $id): bool {
    $st = localdb()->prepare("DELETE FROM aade_accounts WHERE id = :id");
    $st->execute([':id' => $id]);
    return $st->rowCount() > 0;
}

// --- Payments ---------------------------------------------------------------

// Map a raw DB row to a decrypted, app-friendly array
function payment_row(array $r): array {
    return [
        'id'            => (int)$r['id'],
        'account_vat'   => $r['account_vat'],
        'customer_vat'  => $r['customer_vat'],
        'customer_code' => $r['customer_code'],
        'customer_name' => dec($r['customer_name']),
        'amount'        => round(dec_num($r['amount']), 2),
        'method'        => (int)$r['method'],
        'pay_date'      => $r['pay_date'],
        'mark'          => $r['mark'],
        'notes'         => dec($r['notes']),
        'created_at'    => $r['created_at'],
    ];
}

function payments_list(string $accountVat, string $customerVat = '', string $from = '', string $to = ''): array {
    $sql = "SELECT * FROM payments WHERE account_vat = :acc";
    $args = [':acc' => $accountVat];
    if ($customerVat !== '') { $sql .= " AND customer_vat = :cv"; $args[':cv'] = $customerVat; }
    if ($from !== '')        { $sql .= " AND pay_date >= :from"; $args[':from'] = $from; }
    if ($to !== '')          { $sql .= " AND pay_date <= :to";   $args[':to']   = $to; }
    $sql .= " ORDER BY pay_date DESC, id DESC";
    $st = localdb()->prepare($sql);
    $st->execute($args);
    return array_map('payment_row', $st->fetchAll());
}

function payment_add(string $accountVat, array $d): int {
    $st = localdb()->prepare("
        INSERT INTO payments (account_vat, customer_vat, customer_code, customer_name, amount, method, pay_date, mark, notes)
        VALUES (:acc, :cv, :cc, :cn, :amt, :m, :dt, :mk, :nt)
    ");
    $st->execute([
        ':acc' => $accountVat,
        ':cv'  => trim($d['customer_vat']  ?? ''),
        ':cc'  => trim($d['customer_code'] ?? ''),
        ':cn'  => enc(trim($d['customer_name'] ?? '')),
        ':amt' => enc_num(round((float)($d['amount'] ?? 0), 2)),
        ':m'   => (int)($d['method'] ?? 3),
        ':dt'  => trim($d['pay_date'] ?? date('Y-m-d')),
        ':mk'  => trim($d['mark'] ?? ''),
        ':nt'  => enc(trim($d['notes'] ?? '')),
    ]);
    return (int)localdb()->lastInsertId();
}

function payment_delete(string $accountVat, int $id): bool {
    $st = localdb()->prepare("DELETE FROM payments WHERE account_vat = :acc AND id = :id");
    $st->execute([':acc' => $accountVat, ':id' => $id]);
    return $st->rowCount() > 0;
}

function payments_total(string $accountVat, string $customerVat = ''): float {
    $sum = 0.0;
    foreach (payments_list($accountVat, $customerVat) as $p) $sum += $p['amount'];
    return round($sum, 2);
}

// --- Snapshot cache ---------------------------------------------------------

function cache_get(string $accountVat, string $kind): ?array {
    $st = localdb()->prepare("SELECT payload, hash, synced_at FROM app_cache WHERE account_vat = :a AND kind = :k");
    $st->execute([':a' => $accountVat, ':k' => $kind]);
    $r = $st->fetch();
    if (!$r) return null;
    $rows = json_decode(dec($r['payload']), true);
    return ['rows' => is_array($rows) ? $rows : [], 'hash' => $r['hash'], 'synced_at' => $r['synced_at']];
}

function cache_set(string $accountVat, string $kind, array $rows): string {
    $json = json_encode($rows, JSON_UNESCAPED_UNICODE);
    $hash = md5($json);
    $st = localdb()->prepare("
        INSERT INTO app_cache (account_vat, kind, payload, hash, synced_at)
        VALUES (:a, :k, :p, :h, datetime('now'))
        ON CONFLICT(account_vat, kind) DO UPDATE SET
            payload = excluded.payload, hash = excluded.hash, synced_at = excluded.synced_at
    ");
    $st->execute([':a' => $accountVat, ':k' => $kind, ':p' => enc($json), ':h' => $hash]);
    return $hash;
}

// --- Customer meta (opening balance + notes) --------------------------------

function customer_meta_get(string $accountVat, string $customerVat): array {
    $st = localdb()->prepare("SELECT * FROM customer_meta WHERE account_vat = :acc AND customer_vat = :cv");
    $st->execute([':acc' => $accountVat, ':cv' => $customerVat]);
    $r = $st->fetch();
    if (!$r) return ['opening_balance' => 0.0, 'notes' => '', 'customer_name' => ''];
    return [
        'customer_name'   => dec($r['customer_name']),
        'opening_balance' => round(dec_num($r['opening_balance']), 2),
        'notes'           => dec($r['notes']),
        'updated_at'      => $r['updated_at'],
    ];
}

function customer_meta_set(string $accountVat, string $customerVat, array $d): void {
    $st = localdb()->prepare("
        INSERT INTO customer_meta (account_vat, customer_vat, customer_name, opening_balance, notes, updated_at)
        VALUES (:acc, :cv, :cn, :ob, :nt, datetime('now'))
        ON CONFLICT(account_vat, customer_vat) DO UPDATE SET
            customer_name   = excluded.customer_name,
            opening_balance = excluded.opening_balance,
            notes           = excluded.notes,
            updated_at      = datetime('now')
    ");
    $st->execute([
        ':acc' => $accountVat,
        ':cv'  => $customerVat,
        ':cn'  => enc(trim($d['customer_name'] ?? '')),
        ':ob'  => enc_num(round((float)($d['opening_balance'] ?? 0), 2)),
        ':nt'  => enc(trim($d['notes'] ?? '')),
    ]);
}

// --- Per-customer delivery-note settings (branch + delivery address) --------
// Stored as encrypted JSON in customer_meta.deliv_meta so repeat delivery notes
// to the same customer prefill the last-used branch/address. Touches ONLY the
// deliv_meta column (does not disturb opening_balance/notes).

function customer_deliv_get(string $accountVat, string $customerVat): array {
    $st = localdb()->prepare("SELECT deliv_meta FROM customer_meta WHERE account_vat = :acc AND customer_vat = :cv");
    $st->execute([':acc' => $accountVat, ':cv' => $customerVat]);
    $raw = $st->fetchColumn();
    if ($raw === false || $raw === null || $raw === '') return [];
    $json = dec($raw);
    $d = $json !== '' ? json_decode($json, true) : null;
    return is_array($d) ? $d : [];
}

function customer_deliv_set(string $accountVat, string $customerVat, array $d): void {
    $st = localdb()->prepare("
        INSERT INTO customer_meta (account_vat, customer_vat, deliv_meta, updated_at)
        VALUES (:acc, :cv, :dm, datetime('now'))
        ON CONFLICT(account_vat, customer_vat) DO UPDATE SET
            deliv_meta = excluded.deliv_meta,
            updated_at = datetime('now')
    ");
    $st->execute([
        ':acc' => $accountVat,
        ':cv'  => $customerVat,
        ':dm'  => enc(json_encode($d, JSON_UNESCAPED_UNICODE)),
    ]);
}
