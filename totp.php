<?php
// ============================================================================
// totp.php — RFC 6238 Time-based One-Time Passwords (authenticator 2FA)
// ----------------------------------------------------------------------------
// Self-contained (no external libraries): Base32 secret, HMAC-SHA1 codes and an
// otpauth:// URI that any authenticator app (Google Authenticator, Authy,
// Microsoft Authenticator, 1Password, …) can consume from a QR code.
// ============================================================================

const TOTP_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function totp_base32_encode(string $bin): string {
    if ($bin === '') return '';
    $out = ''; $bits = 0; $val = 0;
    for ($i = 0, $n = strlen($bin); $i < $n; $i++) {
        $val = ($val << 8) | ord($bin[$i]);
        $bits += 8;
        while ($bits >= 5) {
            $bits -= 5;
            $out .= TOTP_ALPHABET[($val >> $bits) & 31];
        }
    }
    if ($bits > 0) $out .= TOTP_ALPHABET[($val << (5 - $bits)) & 31];
    return $out;   // unpadded (accepted by authenticator apps)
}

function totp_base32_decode(string $b32): string {
    $b32 = strtoupper(preg_replace('/[^A-Z2-7]/', '', $b32));
    if ($b32 === '') return '';
    $out = ''; $bits = 0; $val = 0;
    for ($i = 0, $n = strlen($b32); $i < $n; $i++) {
        $val = ($val << 5) | strpos(TOTP_ALPHABET, $b32[$i]);
        $bits += 5;
        if ($bits >= 8) {
            $bits -= 8;
            $out .= chr(($val >> $bits) & 0xFF);
        }
    }
    return $out;
}

// A fresh Base32 secret (default 160-bit, the RFC 4226 recommendation).
function totp_generate_secret(int $bytes = 20): string {
    return totp_base32_encode(random_bytes($bytes));
}

// The 6-digit code for a given time step.
function totp_code(string $secret, ?int $time = null, int $period = 30, int $digits = 6): string {
    $key = totp_base32_decode($secret);
    if ($key === '') return '';
    $counter = intdiv($time ?? time(), $period);
    $bin = pack('N*', 0) . pack('N*', $counter);   // 8-byte big-endian counter
    $hash = hash_hmac('sha1', $bin, $key, true);
    $offset = ord($hash[strlen($hash) - 1]) & 0x0F;
    $part = (ord($hash[$offset]) & 0x7F) << 24
          | (ord($hash[$offset + 1]) & 0xFF) << 16
          | (ord($hash[$offset + 2]) & 0xFF) << 8
          | (ord($hash[$offset + 3]) & 0xFF);
    $code = $part % (10 ** $digits);
    return str_pad((string)$code, $digits, '0', STR_PAD_LEFT);
}

// Verify a user-entered code, tolerating ±$window time steps for clock drift.
function totp_verify(string $secret, string $code, int $window = 1, int $period = 30, int $digits = 6): bool {
    $code = preg_replace('/\D/', '', $code);
    if ($secret === '' || strlen($code) !== $digits) return false;
    $now = time();
    for ($i = -$window; $i <= $window; $i++) {
        $candidate = totp_code($secret, $now + ($i * $period), $period, $digits);
        if ($candidate !== '' && hash_equals($candidate, $code)) return true;
    }
    return false;
}

// otpauth:// URI to encode in a QR code.
function totp_uri(string $secret, string $account, string $issuer = 'e-Timologio Pro', int $period = 30, int $digits = 6): string {
    $label = rawurlencode($issuer) . ':' . rawurlencode($account);
    $params = http_build_query([
        'secret'    => $secret,
        'issuer'    => $issuer,
        'algorithm' => 'SHA1',
        'digits'    => $digits,
        'period'    => $period,
    ]);
    return 'otpauth://totp/' . $label . '?' . $params;
}
