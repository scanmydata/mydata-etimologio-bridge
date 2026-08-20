<?php
// ============================================================================
// bankimport.php — Parse bank statements (extrait) into normalised transactions
// so the UI can match each DEPOSIT/CHARGE to a customer/supplier and register a
// LOCAL payment. e-timologio stores no payments; these feed the local ledger.
//
// IMPORTANT (per user): a bank deposit amount is NOT necessarily equal to the
// customer's outstanding balance. We therefore NEVER auto-settle invoices or
// force the amount to any balance — each row becomes a standalone payment entry
// whose amount stays exactly as it came from the bank (fully editable in the UI,
// partial / over-payments allowed).
//
// Supported inputs (auto-detected, tolerant of layout since exact per-bank
// sample files are not always present):
//   • CSV  — Eurobank style: ';'-separated, Windows-1253, header row 1.
//   • XLSX — Optima / Εθνική style: read via ZipArchive + SimpleXML.
// Column mapping is done by HEADER-KEYWORD detection, not fixed indices, so it
// keeps working across banks and minor export changes.
// ============================================================================

// --- Encoding / low-level helpers -------------------------------------------

function bi_to_utf8(string $s): string {
    if ($s === '') return '';
    // Strip UTF-8 BOM
    if (substr($s, 0, 3) === "\xEF\xBB\xBF") $s = substr($s, 3);
    if (function_exists('mb_check_encoding') && mb_check_encoding($s, 'UTF-8')) return $s;
    // Greek bank exports are commonly Windows-1253 (ANSI Greek). This PHP build's
    // mbstring lacks the CP1253 codepage, so prefer iconv (which has it); fall
    // back to ISO-8859-7 (same Greek letter range) if iconv is unavailable.
    if (function_exists('iconv')) {
        $conv = @iconv('CP1253', 'UTF-8//TRANSLIT', $s);
        if ($conv !== false && $conv !== '') return $conv;
    }
    $conv = @mb_convert_encoding($s, 'UTF-8', 'ISO-8859-7');
    return $conv !== false ? $conv : $s;
}

// Greek money → float. Handles 1.234,56 / -1.500,00 / (1.234,56) / 1234.56
function bi_money(string $s): float {
    $s = trim($s);
    if ($s === '') return 0.0;
    $neg = false;
    if (preg_match('/^\((.*)\)$/', $s, $m)) { $neg = true; $s = $m[1]; } // (1.234,56) = negative
    if (strpos($s, '-') !== false) $neg = true;
    $s = preg_replace('/[^\d,.]/', '', $s);
    if ($s === '') return 0.0;
    // If both separators present, the LAST one is the decimal sep
    $lastComma = strrpos($s, ',');
    $lastDot   = strrpos($s, '.');
    if ($lastComma !== false && $lastDot !== false) {
        if ($lastComma > $lastDot) { $s = str_replace('.', '', $s); $s = str_replace(',', '.', $s); }
        else                       { $s = str_replace(',', '', $s); }
    } elseif ($lastComma !== false) {
        // comma only → decimal comma (unless it looks like a thousands grouping)
        $s = str_replace(',', '.', $s);
    }
    $v = (float)$s;
    return $neg ? -abs($v) : $v;
}

// Normalise a date cell to yyyy-mm-dd (accepts dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd,
// and Excel serial numbers).
function bi_date(string $s): string {
    $s = trim($s);
    if ($s === '') return '';
    if (preg_match('#^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})#', $s, $m)) {
        $y = $m[3]; if (strlen($y) === 2) $y = '20' . $y;
        return sprintf('%04d-%02d-%02d', (int)$y, (int)$m[2], (int)$m[1]);
    }
    if (preg_match('#^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})#', $s, $m)) {
        return sprintf('%04d-%02d-%02d', (int)$m[1], (int)$m[2], (int)$m[3]);
    }
    // Excel serial date (days since 1899-12-30)
    if (preg_match('/^\d{4,6}(\.\d+)?$/', $s)) {
        $days = (int)floor((float)$s);
        if ($days > 20000 && $days < 60000) { // ~1954..2064, sane range
            return date('Y-m-d', ($days - 25569) * 86400);
        }
    }
    return $s;
}

// --- CSV → matrix -----------------------------------------------------------

function bi_parse_csv(string $raw): array {
    $raw = bi_to_utf8($raw);
    $raw = str_replace(["\r\n", "\r"], "\n", $raw);
    $lines = array_values(array_filter(explode("\n", $raw), fn($l) => trim($l) !== ''));
    if (!$lines) return [];
    // Detect delimiter from the header line
    $probe = $lines[0];
    $delim = ';';
    $best = -1;
    foreach ([';', ',', "\t", '|'] as $d) {
        $c = substr_count($probe, $d);
        if ($c > $best) { $best = $c; $delim = $d; }
    }
    $rows = [];
    foreach ($lines as $line) {
        $rows[] = str_getcsv($line, $delim, '"');
    }
    return $rows;
}

// --- XLSX → matrix ----------------------------------------------------------

function bi_col_to_idx(string $ref): int {
    // "B7" → 1 (zero-based column index)
    if (!preg_match('/^([A-Z]+)\d+$/', $ref, $m)) return 0;
    $col = $m[1]; $n = 0;
    for ($i = 0, $L = strlen($col); $i < $L; $i++) $n = $n * 26 + (ord($col[$i]) - 64);
    return $n - 1;
}

function bi_parse_xlsx(string $raw): array {
    // Το .xlsx είναι ZIP: χωρίς την επέκταση `zip` δεν διαβάζεται. Υπάρχει στο
    // image του server· λείπει από τη φορητή PHP της εφαρμογής υπολογιστή, όπου
    // ο χρήστης πρέπει να δει τι να κάνει αντί για λευκή οθόνη.
    if (!class_exists('ZipArchive')) {
        throw new RuntimeException('Τα αρχεία .xlsx δεν διαβάζονται σε αυτή την εγκατάσταση — αποθηκεύστε το αντίγραφο κίνησης ως CSV και ανεβάστε το ξανά.');
    }
    $tmp = tempnam(sys_get_temp_dir(), 'bix');
    file_put_contents($tmp, $raw);
    $zip = new ZipArchive();
    if ($zip->open($tmp) !== true) { @unlink($tmp); return []; }

    // shared strings
    $shared = [];
    if (($ss = $zip->getFromName('xl/sharedStrings.xml')) !== false) {
        $xml = @simplexml_load_string($ss);
        if ($xml) {
            foreach ($xml->si as $si) {
                // <si> may hold <t> or several <r><t>
                $t = '';
                if (isset($si->t)) $t = (string)$si->t;
                foreach ($si->r as $r) $t .= (string)$r->t;
                $shared[] = $t;
            }
        }
    }
    // first worksheet (prefer sheet1, else first xl/worksheets/*.xml)
    $sheetXml = $zip->getFromName('xl/worksheets/sheet1.xml');
    if ($sheetXml === false) {
        for ($i = 0; $i < $zip->numFiles; $i++) {
            $n = $zip->getNameIndex($i);
            if (strpos($n, 'xl/worksheets/') === 0 && substr($n, -4) === '.xml') {
                $sheetXml = $zip->getFromName($n); break;
            }
        }
    }
    $zip->close(); @unlink($tmp);
    if (!$sheetXml) return [];

    $xml = @simplexml_load_string($sheetXml);
    if (!$xml) return [];
    $rows = [];
    foreach ($xml->sheetData->row as $row) {
        $cells = [];
        $maxIdx = -1;
        foreach ($row->c as $c) {
            $ref  = (string)($c['r'] ?? '');
            $idx  = $ref !== '' ? bi_col_to_idx($ref) : (count($cells));
            $type = (string)($c['t'] ?? '');
            $val  = '';
            if ($type === 's') {                       // shared string
                $val = $shared[(int)$c->v] ?? '';
            } elseif ($type === 'inlineStr') {
                $val = (string)($c->is->t ?? '');
            } else {
                $val = (string)($c->v ?? '');
            }
            $cells[$idx] = $val;
            if ($idx > $maxIdx) $maxIdx = $idx;
        }
        $line = [];
        for ($i = 0; $i <= $maxIdx; $i++) $line[] = $cells[$i] ?? '';
        $rows[] = $line;
    }
    return $rows;
}

// --- Column detection + normalisation ---------------------------------------

function bi_norm_header(string $s): string {
    $s = mb_strtolower(trim($s), 'UTF-8');
    // strip Greek accents so "ημ/νία" ~ "ημερομηνια" match
    $from = ['ά','έ','ή','ί','ό','ύ','ώ','ϊ','ϋ','ΐ','ΰ'];
    $to   = ['α','ε','η','ι','ο','υ','ω','ι','υ','ι','υ'];
    $s = str_replace($from, $to, $s);
    return $s;
}

// Find the header row (the one whose cells best match known keywords) within the
// first ~15 rows, then map logical fields → column indices.
function bi_detect_columns(array $matrix): array {
    $limit = min(15, count($matrix));
    $bestRow = -1; $bestScore = 0; $bestMap = [];
    for ($r = 0; $r < $limit; $r++) {
        $map = []; $score = 0;
        foreach ($matrix[$r] as $ci => $cell) {
            $h = bi_norm_header((string)$cell);
            if ($h === '') continue;
            $field = null;
            if (preg_match('/υπολοιπ|balance/', $h))                              $field = 'balance';
            elseif (preg_match('/αξιας|value ?date/', $h))                        $field = 'valuedate';
            elseif (preg_match('/ημ|ημερομ|date/', $h))                           $field = 'date';
            elseif (preg_match('/περιγραφ|αιτιολογ|descr|narrative|details/', $h)) $field = 'description';
            elseif (preg_match('/χρεωσ|debit|αναληψ|εξοδα/', $h))                  $field = 'debit';
            elseif (preg_match('/πιστωσ|credit|καταθεσ|εισπραξ/', $h))            $field = 'credit';
            elseif (preg_match('/ποσο|amount|κινησ/', $h))                        $field = 'amount';
            if ($field !== null && !isset($map[$field])) { $map[$field] = $ci; $score++; }
        }
        if ($score > $bestScore) { $bestScore = $score; $bestRow = $r; $bestMap = $map; }
    }
    return ['header_row' => $bestRow, 'map' => $bestMap, 'score' => $bestScore];
}

// Turn the raw matrix into normalised transactions.
function bi_normalize(array $matrix, string $bank = ''): array {
    if (!$matrix) return ['bank' => $bank, 'header_row' => -1, 'columns' => [], 'transactions' => []];
    $det = bi_detect_columns($matrix);
    $map = $det['map'];
    $hr  = $det['header_row'];
    $txs = [];

    // Fallback: if we could not find a header, assume the Eurobank CSV order
    // (date, valuedate, description, amount, balance) and start at row 0.
    if ($hr < 0 || $det['score'] < 2) {
        $map = ['date' => 0, 'valuedate' => 1, 'description' => 2, 'amount' => 3, 'balance' => 4];
        $hr  = 0; // no reliable header → treat row 0 as data unless it looks textual
        // if row 0 is clearly a header (non-numeric amount), skip it
        $a0 = $matrix[0][3] ?? '';
        if ($a0 !== '' && !preg_match('/[\d]/', $a0)) $hr = 0; else $hr = -1;
    }

    $start = $hr + 1;
    for ($r = $start, $R = count($matrix); $r < $R; $r++) {
        $row = $matrix[$r];
        $get = fn($k) => isset($map[$k]) && isset($row[$map[$k]]) ? trim((string)$row[$map[$k]]) : '';

        $date = bi_date($get('date') !== '' ? $get('date') : $get('valuedate'));
        $desc = $get('description');
        $balance = $get('balance') !== '' ? bi_money($get('balance')) : null;

        // amount: single signed column, or separate debit/credit
        $amount = 0.0; $direction = '';
        if (isset($map['amount'])) {
            $amount = bi_money($get('amount'));
            $direction = $amount >= 0 ? 'credit' : 'debit';
        } else {
            $cr = isset($map['credit']) ? bi_money($get('credit')) : 0.0;
            $db = isset($map['debit'])  ? bi_money($get('debit'))  : 0.0;
            if ($cr != 0.0) { $amount = abs($cr);  $direction = 'credit'; }
            elseif ($db != 0.0) { $amount = -abs($db); $direction = 'debit'; }
        }

        // A usable transaction needs a real (parsed) date. Rows whose date did
        // not normalise to yyyy-mm-dd are labels/summaries/footers → skip when
        // they also carry no amount.
        $hasRealDate = (bool)preg_match('/^\d{4}-\d{2}-\d{2}$/', $date);
        if (!$hasRealDate && $amount == 0.0) continue;
        if ($date === '' && $amount == 0.0 && $desc === '') continue;

        // Try to sniff an ΑΦΜ (9 digits) out of the description for auto-matching
        $vat = '';
        if (preg_match('/\b(\d{9})\b/', $desc, $vm)) $vat = $vm[1];

        $txs[] = [
            'row'         => $r + 1,
            'date'        => $date,
            'description' => $desc,
            'amount'      => round($amount, 2),
            'abs_amount'  => round(abs($amount), 2),
            'direction'   => $direction, // credit = money IN (customer payment); debit = money OUT (supplier)
            'balance'     => $balance === null ? null : round($balance, 2),
            'guess_vat'   => $vat,
        ];
    }

    return [
        'bank'        => $bank,
        'header_row'  => $hr,
        'columns'     => $map,
        'count'       => count($txs),
        'transactions'=> $txs,
    ];
}

// --- Public entry -----------------------------------------------------------

// $filename is used only to pick a parser and as a bank hint. $bankHint may be
// 'eurobank' | 'optima' | 'ethniki' | 'nbg' | '' (auto).
function bank_parse(string $raw, string $filename = '', string $bankHint = ''): array {
    $ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
    $bank = $bankHint;
    if ($bank === '') {
        $f = mb_strtolower($filename, 'UTF-8');
        if (strpos($f, 'eurobank') !== false)                         $bank = 'eurobank';
        elseif (strpos($f, 'optima') !== false || strpos($f, 'accounttransaction') !== false) $bank = 'optima';
        elseif (strpos($f, 'ibank') !== false || strpos($f, 'ethnik') !== false || strpos($f, 'nbg') !== false) $bank = 'ethniki';
    }

    if ($ext === 'xlsx' || (strlen($raw) > 2 && substr($raw, 0, 2) === "PK")) {
        $matrix = bi_parse_xlsx($raw);
    } else {
        $matrix = bi_parse_csv($raw);
    }
    return bi_normalize($matrix, $bank);
}
