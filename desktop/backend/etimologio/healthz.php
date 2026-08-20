<?php
// Liveness probe for the container/orchestrator. Deliberately dependency-free:
// it must answer even when the database or the ΑΑΔΕ are unreachable, otherwise a
// transient upstream outage would make the platform restart a healthy app.
//
//   GET /healthz.php        → 'ok'                (ζει η εφαρμογή)
//   GET /healthz.php?db=1   → 'ok' | 'db-down'    (απαντά και η βάση)
//
// Το `?db=1` είναι για ΤΟΝ ΔΙΑΧΕΙΡΙΣΤΗ μετά από deploy — όχι για το healthcheck
// του container. Δεν αποκαλύπτει τίποτα: ούτε DSN, ούτε χρήστη, ούτε μήνυμα
// σφάλματος (αυτά πάνε στο log), μόνο «απαντά / δεν απαντά».
header('Content-Type: text/plain; charset=utf-8');
header('Cache-Control: no-store');

if (empty($_GET['db'])) { echo 'ok'; exit; }

try {
    define('SKIP_ACCOUNT_RESOLUTION', 1);
    require __DIR__ . '/config.php';
    $dsn = (defined('DB_DSN') && DB_DSN !== '') ? DB_DSN : ('sqlite:' . LOCAL_DB);
    $pdo = new PDO($dsn,
        (defined('DB_USER') && DB_USER !== '') ? DB_USER : null,
        (defined('DB_PASS') && DB_PASS !== '') ? DB_PASS : null,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 5]);
    $pdo->query('SELECT 1')->fetchColumn();
    echo 'ok';
} catch (Throwable $e) {
    error_log('[healthz] database unreachable: ' . $e->getMessage());
    http_response_code(503);
    echo 'db-down';
}
