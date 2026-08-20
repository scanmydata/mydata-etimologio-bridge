<?php
// Μετατρέπει το connection string της βάσης σε shell αναθέσεις (DB_DSN/DB_USER/
// DB_PASS) που κάνει eval το entrypoint.
//
// Γιατί υπάρχει: το Coolify (όπως και το Docker/Heroku στυλ) δίνει τη βάση ως
// ΕΝΑ URL — `postgres://χρήστης:κωδικός@host:5432/βάση` — ενώ το PDO θέλει DSN
// χωριστά από χρήστη/κωδικό. Έτσι η ρύθμιση της βάσης στο Coolify είναι μία
// επικόλληση, χωρίς να σπάει κανείς το URL στο χέρι (και χωρίς να αφήνει τον
// κωδικό σε δεύτερο πεδίο).
//
//   php deploy/dburl.php                  # διαβάζει DATABASE_URL / POSTGRES_URL
//   php deploy/dburl.php <url>            # ή ρητά
//
// Τυπώνει τίποτα (και βγαίνει με 0) αν δεν υπάρχει URL: τότε ισχύουν τα DB_DSN/
// DB_USER/DB_PASS του περιβάλλοντος, ή η τοπική SQLite.

$url = $argv[1] ?? (getenv('DATABASE_URL') ?: getenv('POSTGRES_URL'));
$url = trim((string)$url);
if ($url === '') exit(0);

$p = parse_url($url);
if (!$p || empty($p['host'])) {
    fwrite(STDERR, "[dburl] δεν αναγνώρισα το connection string της βάσης\n");
    exit(0);   // δεν ρίχνουμε τον container — μένει το DB_DSN του περιβάλλοντος
}

$scheme = strtolower($p['scheme'] ?? 'postgres');
$driver = in_array($scheme, ['postgres', 'postgresql', 'pgsql'], true) ? 'pgsql'
        : (in_array($scheme, ['mysql', 'mariadb'], true) ? 'mysql' : $scheme);

$dsn = $driver . ':host=' . $p['host']
     . ';port=' . (int)($p['port'] ?? ($driver === 'pgsql' ? 5432 : 3306))
     . ';dbname=' . ltrim(rawurldecode($p['path'] ?? ''), '/');

// Το `?sslmode=require` που δίνουν οι managed βάσεις είναι έγκυρο μέρος του DSN.
parse_str($p['query'] ?? '', $q);
if (!empty($q['sslmode'])) $dsn .= ';sslmode=' . preg_replace('/[^a-z-]/', '', strtolower($q['sslmode']));

// Ασφαλής παράθεση για το shell: κάθε ' γίνεται '\''.
$sq = static fn(string $v): string => "'" . str_replace("'", "'\''", $v) . "'";

echo 'DB_DSN=',  $sq($dsn), "\n";
echo 'DB_USER=', $sq(rawurldecode((string)($p['user'] ?? ''))), "\n";
echo 'DB_PASS=', $sq(rawurldecode((string)($p['pass'] ?? ''))), "\n";
echo "export DB_DSN DB_USER DB_PASS\n";
