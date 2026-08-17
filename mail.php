<?php
// ============================================================================
// mail.php — outbound email (Resend API preferred, SMTP/mail() fallback)
// ----------------------------------------------------------------------------
// One entry point, send_mail(), used by every transactional email in the app:
// signup acknowledgement, admin approval/activation, forgot/reset, member
// invitations, and issuance notifications.
//
// Provider selection (config.php):
//   MAIL_PROVIDER = 'auto' | 'resend' | 'smtp'   (default 'auto')
//     auto  → Resend if RESEND_API_KEY set, else SMTP if SMTP_FROM set, else none
//   RESEND_API_KEY      — Resend API key (re_...). https://resend.com/api-keys
//   RESEND_EMAIL_SENDER — verified sender, e.g. 'e-Τιμολόγιο <no-reply@yourdomain.gr>'
//   SMTP_FROM           — From: address for the PHP mail() fallback
//   APP_URL             — public base URL of the app (for links in emails)
//
// All constants are optional; when nothing is configured send_mail() no-ops and
// returns false so the caller can fall back (e.g. show the reset token in-app).
// ============================================================================

require_once __DIR__ . '/config.php';

/**
 * Μια ρύθμιση email: **από τη βάση πρώτα**, μετά από το `config.php`.
 *
 * Έτσι ο διαχειριστής ορίζει SMTP ή Resend από τις Ρυθμίσεις, χωρίς να αγγίξει
 * αρχείο — και μια εγκατάσταση που έχει ήδη σταθερές συνεχίζει να δουλεύει.
 */
function mail_conf(string $name, string $default = ''): string {
    if (function_exists('setting_get')) {
        $stored = setting_get('mail.' . $name);
        if ($stored !== '') return trim($stored);
    }
    return defined($name) ? trim((string)constant($name)) : $default;
}

// Which provider will actually be used ('resend' | 'smtp' | '').
function mail_provider(): string {
    $pref = strtolower(mail_conf('MAIL_PROVIDER', 'auto'));
    $hasResend = mail_conf('RESEND_API_KEY') !== '';
    $hasSmtp   = mail_conf('SMTP_FROM') !== '';
    if ($pref === 'resend') return $hasResend ? 'resend' : ($hasSmtp ? 'smtp' : '');
    if ($pref === 'smtp')   return $hasSmtp ? 'smtp' : ($hasResend ? 'resend' : '');
    // auto
    if ($hasResend) return 'resend';
    if ($hasSmtp)   return 'smtp';
    return '';
}

function mail_enabled(): bool { return mail_provider() !== ''; }

// Public base URL of the app, for building links. Prefers APP_URL / APP_BASE_URL,
// else derives from the current request.
function app_base_url(): string {
    $u = mail_conf('APP_URL');
    if ($u === '') $u = mail_conf('APP_BASE_URL');
    if ($u !== '') return rtrim($u, '/');
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    return $scheme . '://' . $host . rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? '/'), '/\\');
}

// Send an email. Returns true on success. $html is the full HTML body (use
// mail_template() to wrap content); $text is an optional plain-text alternative.
function send_mail(string $to, string $subject, string $html, string $text = ''): bool {
    $to = trim($to);
    if ($to === '' || !filter_var($to, FILTER_VALIDATE_EMAIL)) return false;
    $provider = mail_provider();
    if ($provider === 'resend') {
        if (send_mail_resend($to, $subject, $html, $text)) return true;
        // fall through to SMTP if Resend failed and SMTP is available
        if (mail_conf('SMTP_FROM') !== '') return send_mail_smtp($to, $subject, $html, $text);
        return false;
    }
    if ($provider === 'smtp') return send_mail_smtp($to, $subject, $html, $text);
    return false;   // nothing configured
}

// --- Resend ------------------------------------------------------------------
function send_mail_resend(string $to, string $subject, string $html, string $text = ''): bool {
    $key = mail_conf('RESEND_API_KEY');
    if ($key === '') return false;
    $from = mail_conf('RESEND_EMAIL_SENDER');
    if ($from === '') $from = mail_conf('SMTP_FROM');
    if ($from === '') $from = 'onboarding@resend.dev';   // Resend test sender (verified-recipients only)
    $payload = [
        'from'    => $from,
        'to'      => [$to],
        'subject' => $subject,
        'html'    => $html,
    ];
    if ($text !== '') $payload['text'] = $text;
    $ch = curl_init('https://api.resend.com/emails');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 20,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . $key,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
    ]);
    $resp = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);
    if ($code >= 200 && $code < 300) return true;
    error_log('[mail] Resend failed (' . $code . '): ' . ($err ?: substr((string)$resp, 0, 300)));
    return false;
}

// --- SMTP --------------------------------------------------------------------
//
// Τα πεδία SMTP_HOST/PORT/USER/PASS τα ζητούσε η οθόνη ρυθμίσεων αλλά **κανείς
// δεν τα διάβαζε**: η αποστολή γινόταν με `mail()`, που στα Windows και στη
// φορητή PHP δεν έχει καν ρυθμισμένο server. Ο διαχειριστής συμπλήρωνε σωστά
// στοιχεία Gmail και δεν έφευγε τίποτα, χωρίς μήνυμα λάθους. Εδώ μιλάμε SMTP
// κανονικά· το `mail()` μένει μόνο για εγκαταστάσεις χωρίς host (π.χ. hosting
// που έχει ήδη ρυθμισμένο τοπικό relay).

/** Η διεύθυνση μέσα σε «Όνομα <mail@dom>» — ο φάκελος MAIL FROM θέλει σκέτη. */
function mail_addr(string $value): string {
    if (preg_match('/<([^>]+)>/', $value, $m)) return trim($m[1]);
    return trim($value);
}

function mail_mime(string $subject, string $from, string $to, string $html, string $text): string {
    $boundary = 'b' . bin2hex(random_bytes(8));
    if ($text === '') $text = trim(preg_replace('/\s+/', ' ', strip_tags($html)));
    $head  = 'From: ' . $from . "\r\n";
    $head .= 'To: ' . $to . "\r\n";
    $head .= 'Subject: =?UTF-8?B?' . base64_encode($subject) . "?=\r\n";
    $head .= 'Date: ' . date('r') . "\r\n";
    $head .= 'MIME-Version: 1.0' . "\r\n";
    $head .= 'Content-Type: multipart/alternative; boundary="' . $boundary . '"' . "\r\n";
    $body  = "\r\n--" . $boundary . "\r\n";
    $body .= "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           . chunk_split(base64_encode($text)) . "\r\n";
    $body .= '--' . $boundary . "\r\n";
    $body .= "Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           . chunk_split(base64_encode($html)) . "\r\n";
    $body .= '--' . $boundary . "--\r\n";
    return $head . $body;
}

function send_mail_smtp(string $to, string $subject, string $html, string $text = ''): bool {
    $from = mail_conf('SMTP_FROM');
    if ($from === '') return false;
    $host = mail_conf('SMTP_HOST');
    if ($host === '') return send_mail_php($to, $subject, $html, $text);

    $port   = (int)(mail_conf('SMTP_PORT') ?: '587');
    $secure = strtolower(mail_conf('SMTP_SECURE', $port === 465 ? 'ssl' : 'tls'));
    $user   = mail_conf('SMTP_USER');
    $pass   = mail_conf('SMTP_PASS');
    $target = ($secure === 'ssl' ? 'ssl://' : '') . $host . ':' . $port;

    $sock = @stream_socket_client($target, $errno, $errstr, 20);
    if (!$sock) { error_log("[mail] SMTP connect $target: $errstr"); return false; }
    stream_set_timeout($sock, 20);

    $read = function () use ($sock): string {
        $out = '';
        while (($line = fgets($sock, 1024)) !== false) {
            $out .= $line;
            // Το τελευταίο μιας πολύγραμμης απάντησης έχει κενό μετά τον κωδικό.
            if (strlen($line) >= 4 && $line[3] === ' ') break;
        }
        return $out;
    };
    $cmd = function (string $line, string $expect) use ($sock, $read): bool {
        if ($line !== '') fwrite($sock, $line . "\r\n");
        $resp = $read();
        if (strncmp($resp, $expect, strlen($expect)) === 0) return true;
        error_log('[mail] SMTP «' . substr($line, 0, 20) . '» → ' . trim(substr($resp, 0, 160)));
        return false;
    };

    $ok = $cmd('', '220');
    $ehlo = 'EHLO ' . (parse_url(app_base_url(), PHP_URL_HOST) ?: 'localhost');
    $ok = $ok && $cmd($ehlo, '250');
    if ($ok && $secure === 'tls') {
        $ok = $cmd('STARTTLS', '220')
           && @stream_socket_enable_crypto($sock, true, STREAM_CRYPTO_METHOD_TLS_CLIENT)
           && $cmd($ehlo, '250');
    }
    if ($ok && $user !== '') {
        $ok = $cmd('AUTH LOGIN', '334')
           && $cmd(base64_encode($user), '334')
           && $cmd(base64_encode($pass), '235');
    }
    $ok = $ok
       && $cmd('MAIL FROM:<' . mail_addr($from) . '>', '250')
       && $cmd('RCPT TO:<' . mail_addr($to) . '>', '250')
       && $cmd('DATA', '354');
    if ($ok) {
        $message = mail_mime($subject, $from, $to, $html, $text);
        // Η τελεία στην αρχή γραμμής τερματίζει το DATA — διπλασιάζεται.
        $message = preg_replace('/^\./m', '..', $message);
        fwrite($sock, $message . "\r\n.\r\n");
        $ok = strncmp($read(), '250', 3) === 0;
    }
    @fwrite($sock, "QUIT\r\n");
    @fclose($sock);
    return $ok;
}

/** Εφεδρεία για εγκαταστάσεις με ρυθμισμένο relay στο ίδιο το PHP. */
function send_mail_php(string $to, string $subject, string $html, string $text = ''): bool {
    $from = mail_conf('SMTP_FROM');
    $boundary = 'b' . bin2hex(random_bytes(8));
    $headers  = 'From: ' . $from . "\r\n";
    $headers .= 'MIME-Version: 1.0' . "\r\n";
    $headers .= 'Content-Type: multipart/alternative; boundary="' . $boundary . '"' . "\r\n";
    if ($text === '') $text = trim(preg_replace('/\s+/', ' ', strip_tags($html)));
    $body  = '--' . $boundary . "\r\n";
    $body .= 'Content-Type: text/plain; charset=UTF-8' . "\r\n\r\n" . $text . "\r\n\r\n";
    $body .= '--' . $boundary . "\r\n";
    $body .= 'Content-Type: text/html; charset=UTF-8' . "\r\n\r\n" . $html . "\r\n\r\n";
    $body .= '--' . $boundary . "--";
    return @mail($to, '=?UTF-8?B?' . base64_encode($subject) . '?=', $body, $headers);
}

// --- Branded HTML template ---------------------------------------------------
// Embeds the app icon as a data: URI so it shows even when remote images are
// blocked. Matches the app's navy/blue palette.
function mail_icon_data_uri(): string {
    static $uri = null;
    if ($uri !== null) return $uri;
    $path = __DIR__ . '/assets/icons/app-icon-192.png';
    if (is_file($path)) {
        $raw = @file_get_contents($path);
        if ($raw !== false) { $uri = 'data:image/png;base64,' . base64_encode($raw); return $uri; }
    }
    $uri = '';
    return $uri;
}

// Wrap an HTML fragment in the standard transactional layout.
//   $title      — headline shown in the top band
//   $innerHtml  — HTML fragment (can include a CTA button via mail_button())
//   $footer     — optional small footer line
function mail_template(string $title, string $innerHtml, string $footer = ''): string {
    $icon = mail_icon_data_uri();
    $logo = $icon !== '' ? '<img src="' . $icon . '" alt="e-Τιμολόγιο" style="height:72px;width:72px;display:block;margin:0 auto;border-radius:16px">' : '';
    $foot = $footer !== '' ? $footer : 'Αυτό το μήνυμα στάλθηκε αυτόματα από την εφαρμογή e-Τιμολόγιο Pro.';
    return '<!DOCTYPE html><html><body style="margin:0;padding:32px 16px;background:#eef3fa;font-family:Segoe UI,Tahoma,Arial,sans-serif;color:#1a2637">'
        . '<div style="max-width:600px;margin:0 auto">'
        . '<div style="text-align:center;margin-bottom:16px">' . $logo . '</div>'
        . '<div style="background:#0b1220;color:#e6edf6;padding:16px 22px;border-radius:12px 12px 0 0;text-align:center">'
        . '<strong style="font-size:18px">' . htmlspecialchars($title, ENT_QUOTES) . '</strong></div>'
        . '<div style="background:#ffffff;padding:24px;border-radius:0 0 12px 12px;box-shadow:0 6px 20px rgba(15,23,42,.08);line-height:1.55;font-size:15px">'
        . $innerHtml
        . '</div>'
        . '<div style="text-align:center;margin-top:18px;color:#5b6b84;font-size:12px">' . htmlspecialchars($foot, ENT_QUOTES) . '</div>'
        . '</div></body></html>';
}

// A styled CTA button for use inside mail_template().
function mail_button(string $label, string $url): string {
    return '<div style="text-align:center;margin:22px 0">'
        . '<a href="' . htmlspecialchars($url, ENT_QUOTES) . '" '
        . 'style="display:inline-block;background:#0ea5e9;color:#ffffff;text-decoration:none;'
        . 'padding:12px 26px;border-radius:10px;font-weight:600;font-size:15px">'
        . htmlspecialchars($label, ENT_QUOTES) . '</a></div>'
        . '<div style="text-align:center;color:#5b6b84;font-size:12px;word-break:break-all">'
        . htmlspecialchars($url, ENT_QUOTES) . '</div>';
}
