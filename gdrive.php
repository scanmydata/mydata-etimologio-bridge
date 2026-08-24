<?php
// ============================================================================
// gdrive.php — ανέβασμα αρχείων στο Google Drive του διαχειριστή
// ----------------------------------------------------------------------------
// Χωρίς SDK, μόνο cURL: το image είναι php:8.3-apache και δεν θέλουμε να
// σέρνει composer + τη βιβλιοθήκη της Google για τρεις κλήσεις REST.
//
// Ταυτοποίηση με **OAuth χρήστη** (client id/secret + refresh token), όπως το
// ScanmyData: το αρχείο ανεβαίνει στο Drive ΤΟΥ ΔΙΑΧΕΙΡΙΣΤΗ και μετράει στη
// δική του χωρητικότητα — ένας service account δεν έχει δικό του χώρο και τα
// αντίγραφα θα γίνονταν αόρατα σε αυτόν που τα χρειάζεται.
//
// Τα τρία κλειδιά έρχονται από το Infisical (δες infisical.php):
//     GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_DRIVE_REFRESH_TOKEN
// και προαιρετικά GOOGLE_DRIVE_FOLDER (όνομα φακέλου· default παρακάτω).
// ============================================================================

require_once __DIR__ . '/infisical.php';

const GDRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder';
const GDRIVE_DEFAULT_FOLDER = 'ScanmyData backups';

function gdrive_configured(): bool {
    foreach (['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_DRIVE_REFRESH_TOKEN'] as $k) {
        if (secret_get($k) === '') return false;
    }
    return true;
}

function gdrive_folder_name(): string {
    return secret_get('GOOGLE_DRIVE_FOLDER', GDRIVE_DEFAULT_FOLDER);
}

/**
 * Φρέσκο access token από το refresh token.
 *
 * Κρατιέται σε στατική μνήμη για όσο ζει το αίτημα: ένα ανέβασμα κάνει
 * τουλάχιστον δύο κλήσεις (φάκελος + αρχείο) και δεν έχει νόημα δεύτερο
 * ταξίδι στο oauth2.
 */
function gdrive_token(): array {
    static $tok = null;
    if ($tok !== null) return $tok;
    if (!gdrive_configured()) return $tok = ['ok' => false, 'error' => 'λείπουν τα κλειδιά Google'];

    $ch = curl_init('https://oauth2.googleapis.com/token');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 20,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query([
            'client_id'     => secret_get('GOOGLE_CLIENT_ID'),
            'client_secret' => secret_get('GOOGLE_CLIENT_SECRET'),
            'refresh_token' => secret_get('GOOGLE_DRIVE_REFRESH_TOKEN'),
            'grant_type'    => 'refresh_token',
        ]),
    ]);
    $body = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);
    if ($body === false) return $tok = ['ok' => false, 'error' => $err ?: 'δίκτυο'];
    $d = json_decode((string)$body, true);
    if ($code !== 200 || empty($d['access_token'])) {
        // Το μήνυμα της Google είναι χρήσιμο («invalid_grant» = ανακλήθηκε το
        // refresh token), γι' αυτό ταξιδεύει μέχρι την οθόνη του διαχειριστή.
        return $tok = ['ok' => false, 'error' => (string)($d['error_description'] ?? $d['error'] ?? "HTTP $code")];
    }
    return $tok = ['ok' => true, 'token' => (string)$d['access_token']];
}

/** Μία κλήση στο Drive API. */
function gdrive_call(string $method, string $url, array $headers = [], $body = null, int $timeout = 120): array {
    $t = gdrive_token();
    if (!$t['ok']) return ['ok' => false, 'error' => $t['error']];
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => $timeout,
        CURLOPT_CUSTOMREQUEST  => $method,
        CURLOPT_HTTPHEADER     => array_merge(['Authorization: Bearer ' . $t['token']], $headers),
    ]);
    if ($body !== null) curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    $resp = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);
    if ($resp === false) return ['ok' => false, 'error' => $err ?: 'δίκτυο'];
    $d = json_decode((string)$resp, true);
    if ($code >= 300) {
        return ['ok' => false, 'error' => (string)($d['error']['message'] ?? "HTTP $code")];
    }
    return ['ok' => true, 'data' => is_array($d) ? $d : [], 'raw' => (string)$resp];
}

/** Το id του φακέλου προορισμού — τον φτιάχνει αν λείπει. */
function gdrive_folder_id(): array {
    static $id = null;
    if ($id !== null) return $id;
    $name = gdrive_folder_name();
    $q = sprintf("mimeType='%s' and name='%s' and trashed=false",
                 GDRIVE_FOLDER_MIME, str_replace("'", "\\'", $name));
    $r = gdrive_call('GET', 'https://www.googleapis.com/drive/v3/files?'
        . http_build_query(['q' => $q, 'fields' => 'files(id,name)', 'pageSize' => 1]), [], null, 30);
    if (!$r['ok']) return $id = $r;
    if (!empty($r['data']['files'][0]['id'])) {
        return $id = ['ok' => true, 'id' => (string)$r['data']['files'][0]['id']];
    }
    $r = gdrive_call('POST', 'https://www.googleapis.com/drive/v3/files?fields=id',
        ['Content-Type: application/json'],
        json_encode(['name' => $name, 'mimeType' => GDRIVE_FOLDER_MIME]), 30);
    if (!$r['ok']) return $id = $r;
    return $id = ['ok' => true, 'id' => (string)($r['data']['id'] ?? '')];
}

/**
 * Ανεβάζει bytes ως αρχείο στον φάκελο των αντιγράφων.
 *
 * Multipart (metadata + περιεχόμενο σε ένα αίτημα): τα αντίγραφά μας είναι
 * μερικά MB, όπου το resumable upload θα πρόσθετε πολυπλοκότητα χωρίς όφελος.
 */
function gdrive_upload(string $name, string $bytes, string $mime = 'application/zip'): array {
    $folder = gdrive_folder_id();
    if (!$folder['ok']) return $folder;

    $boundary = 'etim' . bin2hex(random_bytes(8));
    $meta = json_encode(['name' => $name, 'parents' => [$folder['id']]]);
    $body = "--$boundary\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n$meta\r\n"
          . "--$boundary\r\nContent-Type: $mime\r\n\r\n" . $bytes . "\r\n--$boundary--";

    $r = gdrive_call('POST',
        'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size,webViewLink',
        ["Content-Type: multipart/related; boundary=$boundary"], $body, 300);
    if (!$r['ok']) return $r;
    return ['ok' => true, 'file' => $r['data']];
}

/** Τα αντίγραφα που ζουν ήδη στο Drive, νεότερο πρώτο. */
function gdrive_list(int $limit = 50): array {
    $folder = gdrive_folder_id();
    if (!$folder['ok']) return $folder;
    $q = sprintf("'%s' in parents and trashed=false", $folder['id']);
    $r = gdrive_call('GET', 'https://www.googleapis.com/drive/v3/files?' . http_build_query([
        'q' => $q, 'orderBy' => 'createdTime desc', 'pageSize' => $limit,
        'fields' => 'files(id,name,size,createdTime,webViewLink)',
    ]), [], null, 30);
    if (!$r['ok']) return $r;
    return ['ok' => true, 'files' => (array)($r['data']['files'] ?? [])];
}

function gdrive_delete(string $fileId): array {
    return gdrive_call('DELETE', 'https://www.googleapis.com/drive/v3/files/' . rawurlencode($fileId), [], null, 30);
}
