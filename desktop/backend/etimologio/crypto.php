<?php
// ============================================================================
// At-rest encryption for locally stored data (libsodium / XSalsa20-Poly1305).
// ----------------------------------------------------------------------------
// Sensitive fields (customer names, notes, amounts) are encrypted before they
// hit the SQLite file. Values are stored as `enc:1:<base64(nonce|cipher)>`.
// dec() transparently returns legacy/plaintext values unchanged, so enabling
// encryption never breaks an existing store.
//
// Key resolution order:
//   1. ENCRYPTION_KEY constant in config.php (base64 of 32 bytes — preferred)
//   2. Auto-generated key file (.enckey, gitignored) created on first use
// Keep the key OUT of the repo and backed up — losing it makes data unreadable.
// ============================================================================

function enc_key(): string {
    static $key = null;
    if ($key !== null) return $key;

    $need = SODIUM_CRYPTO_SECRETBOX_KEYBYTES; // 32

    if (defined('ENCRYPTION_KEY') && ENCRYPTION_KEY !== '') {
        $raw = base64_decode(ENCRYPTION_KEY, true);
        if ($raw !== false && strlen($raw) === $need) { return $key = $raw; }
        if (strlen(ENCRYPTION_KEY) === $need)         { return $key = ENCRYPTION_KEY; }
        return $key = hash('sha256', ENCRYPTION_KEY, true); // derive from passphrase
    }

    $file = defined('ENC_KEY_FILE') ? ENC_KEY_FILE : (__DIR__ . '/.enckey');
    if (is_file($file)) {
        $raw = base64_decode(trim((string)file_get_contents($file)), true);
        if ($raw !== false && strlen($raw) === $need) return $key = $raw;
    }
    $key = random_bytes($need);
    @file_put_contents($file, base64_encode($key));
    @chmod($file, 0600);
    return $key;
}

function enc(?string $plain): string {
    $plain = (string)$plain;
    if (!extension_loaded('sodium')) return $plain; // graceful fallback
    $nonce  = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $cipher = sodium_crypto_secretbox($plain, $nonce, enc_key());
    return 'enc:1:' . base64_encode($nonce . $cipher);
}

function dec(?string $stored): string {
    $stored = (string)$stored;
    if (strncmp($stored, 'enc:1:', 6) !== 0) return $stored; // plaintext/legacy
    if (!extension_loaded('sodium')) return '';
    $raw = base64_decode(substr($stored, 6), true);
    if ($raw === false || strlen($raw) <= SODIUM_CRYPTO_SECRETBOX_NONCEBYTES) return '';
    $nonce  = substr($raw, 0, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $cipher = substr($raw, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    $plain  = sodium_crypto_secretbox_open($cipher, $nonce, enc_key());
    return $plain === false ? '' : $plain;
}

// Convenience for numeric fields stored encrypted as text
function enc_num($n): string { return enc((string)(float)$n); }
function dec_num(?string $s): float { return (float)dec($s); }
