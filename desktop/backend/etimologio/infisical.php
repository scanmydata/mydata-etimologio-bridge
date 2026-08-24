<?php
// ============================================================================
// infisical.php — τα μυστικά του server, από το Infisical
// ----------------------------------------------------------------------------
// Ίδιο μοτίβο με το ScanmyData (`infisical_bootstrap.py`): ένα διακριτικό στο
// περιβάλλον, ένα GET στο `/api/v3/secrets/raw`, και τα μυστικά μπαίνουν στο
// περιβάλλον της διεργασίας. Έτσι τα κλειδιά του Google Drive **δεν** ζουν
// ούτε στο repo, ούτε στην εικόνα, ούτε καν στα env του Coolify.
//
// Χρειάζονται τρία (τα βάζει ο διαχειριστής στο Coolify):
//     INFISICAL_TOKEN         service token με δικαίωμα ανάγνωσης
//     INFISICAL_PROJECT_ID    το workspace
//     INFISICAL_ENVIRONMENT   π.χ. prod
//     INFISICAL_BASE_URL      προαιρετικό (default https://app.infisical.com)
//
// ΤΙΠΟΤΑ δεν είναι υποχρεωτικό: χωρίς Infisical, το `secret_get()` πέφτει στα
// σκέτα env/constants. Ένας server χωρίς αντίγραφα στο Drive πρέπει να
// συνεχίζει να δουλεύει — απλώς το λέει στην οθόνη του διαχειριστή.
// ============================================================================

/** Μνήμη μιας εκτέλεσης: το Infisical ρωτιέται το πολύ μία φορά ανά αίτημα. */
function infisical_cache(): array {
    static $cache = null;
    if ($cache !== null) return $cache;
    $cache = infisical_fetch();
    return $cache;
}

function infisical_configured(): bool {
    foreach (['INFISICAL_TOKEN', 'INFISICAL_PROJECT_ID', 'INFISICAL_ENVIRONMENT'] as $k) {
        if (trim((string)env_or_const($k)) === '') return false;
    }
    return true;
}

/**
 * Μια τιμή από το περιβάλλον ή από σταθερά του `config.php`.
 *
 * Το `entrypoint.sh` γράφει σταθερές, όχι env — γι' αυτό κοιτάμε και τα δύο.
 */
function env_or_const(string $name): string {
    $v = getenv($name);
    if ($v !== false && $v !== '') return (string)$v;
    if (defined($name)) return (string)constant($name);
    return '';
}

function infisical_fetch(): array {
    if (!infisical_configured()) return [];
    $base = rtrim(env_or_const('INFISICAL_BASE_URL') ?: 'https://app.infisical.com', '/');
    $url  = $base . '/api/v3/secrets/raw?' . http_build_query([
        'workspaceId' => env_or_const('INFISICAL_PROJECT_ID'),
        'environment' => env_or_const('INFISICAL_ENVIRONMENT'),
        'secretPath'  => '/',
    ]);
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . env_or_const('INFISICAL_TOKEN'),
            'Accept: application/json',
        ],
    ]);
    $body = curl_exec($ch);
    $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($body === false || $code !== 200) {
        error_log("infisical: HTTP $code");
        return [];
    }
    $d = json_decode((string)$body, true);
    $out = [];
    foreach ((array)($d['secrets'] ?? []) as $item) {
        $k = (string)($item['secretKey'] ?? $item['key'] ?? '');
        if ($k === '') continue;
        $out[$k] = (string)($item['secretValue'] ?? $item['secret'] ?? '');
    }
    return $out;
}

/**
 * Ένα μυστικό, με σειρά προτεραιότητας: περιβάλλον/σταθερά → Infisical.
 *
 * Το ρητό env κερδίζει επίτηδες: έτσι ένας διαχειριστής μπορεί να παρακάμψει
 * μια τιμή για δοκιμή χωρίς να πειράξει το Infisical, και μια εγκατάσταση
 * χωρίς Infisical δουλεύει με σκέτα env.
 */
function secret_get(string $name, string $default = ''): string {
    $direct = env_or_const($name);
    if ($direct !== '') return $direct;
    $all = infisical_cache();
    return isset($all[$name]) && $all[$name] !== '' ? $all[$name] : $default;
}
