<?php
// ============================================================================
// qrcode.php — κωδικοί QR χωρίς βιβλιοθήκη, χωρίς δίκτυο
// ----------------------------------------------------------------------------
// ΓΙΑΤΙ ΥΠΑΡΧΕΙ ΑΥΤΟ ΤΟ ΑΡΧΕΙΟ: το QR του 2FA το έφτιαχνε ο browser, με μια
// βιβλιοθήκη από CDN (`cdn.jsdelivr.net`). Στον server όμως η πολιτική
// περιεχομένου επιτρέπει scripts ΜΟΝΟ από τον ίδιο τον server
// (`script-src 'self'`), οπότε το αρχείο δεν φορτωνόταν ποτέ: καμία
// προειδοποίηση, κανένα σφάλμα στην οθόνη — απλώς ένα κενό τετράγωνο εκεί που
// έπρεπε να είναι ο κωδικός. Το ίδιο θα συνέβαινε και σε υπολογιστή χωρίς
// internet.
//
// Ο κώδικας παράγεται πλέον ΕΔΩ και ταξιδεύει ως SVG μέσα στην απάντηση: καμία
// εξωτερική εξάρτηση, καμία τρύπα στην πολιτική περιεχομένου, ίδια συμπεριφορά
// σε server και σε φορητό υπολογιστή χωρίς δίκτυο.
//
// Εύρος: επίπεδο διόρθωσης **M**, εκδόσεις 1–15, λειτουργία **byte** (UTF-8).
// Καλύπτει άνετα ένα `otpauth://` URI (~170 χαρακτήρες). Ό,τι δεν χωρά
// επιστρέφει κενό — ο καλών δείχνει τότε το κλειδί ως κείμενο, που είναι ούτως
// ή άλλως η εναλλακτική κάθε authenticator.
//
// Η υλοποίηση ακολουθεί κατά γράμμα το ISO/IEC 18004 όπως το εκθέτει η
// αναφορά του Project Nayuki (δημόσιος τομέας): ίδια σειρά πράξεων, ίδια
// τοποθέτηση bit. Δεν είναι ο τόπος για εξυπνάδες — ένα QR είτε διαβάζεται
// είτε όχι.
// ============================================================================

//: Κωδικές λέξεις διόρθωσης ανά μπλοκ, επίπεδο M, ανά έκδοση (1 → …).
const QR_ECC_PER_BLOCK_M = [
    1 => 10, 2 => 16, 3 => 26, 4 => 18, 5 => 24, 6 => 16, 7 => 18, 8 => 22,
    9 => 22, 10 => 26, 11 => 30, 12 => 22, 13 => 22, 14 => 24, 15 => 24,
];

//: Πλήθος μπλοκ διόρθωσης, επίπεδο M, ανά έκδοση.
const QR_BLOCKS_M = [
    1 => 1, 2 => 1, 3 => 1, 4 => 2, 5 => 2, 6 => 4, 7 => 4, 8 => 4,
    9 => 5, 10 => 5, 11 => 5, 12 => 8, 13 => 9, 14 => 9, 15 => 10,
];

const QR_MAX_VERSION = 15;

/** Οι θέσεις (μονάδες) των μοτίβων ευθυγράμμισης για μια έκδοση. */
function qr_align_positions(int $ver): array {
    if ($ver === 1) return [];
    $num  = intdiv($ver, 7) + 2;
    $size = $ver * 4 + 17;
    // ΠΡΟΣΟΧΗ: η διαίρεση είναι ακέραια ΠΡΙΝ τον πολλαπλασιασμό με 2 — αλλιώς
    // τα μοτίβα πέφτουν σε μισές μονάδες και ο κωδικός δεν διαβάζεται.
    $step = intdiv($ver * 4 + $num * 2 + 1, $num * 2 - 2) * 2;
    $out = array_fill(0, $num, 0);
    $out[0] = 6;
    for ($i = $num - 1, $pos = $size - 7; $i >= 1; $i--, $pos -= $step) $out[$i] = $pos;
    return $out;
}

/** Πόσες μονάδες δεδομένων (πριν τη διόρθωση) χωρά μια έκδοση, σε bit. */
function qr_raw_data_modules(int $ver): int {
    $result = (16 * $ver + 128) * $ver + 64;
    if ($ver >= 2) {
        $num = intdiv($ver, 7) + 2;
        $result -= (25 * $num - 10) * $num - 55;
        if ($ver >= 7) $result -= 36;
    }
    return $result;
}

/** Κωδικές λέξεις δεδομένων (χωρίς τη διόρθωση) για μια έκδοση, επίπεδο M. */
function qr_data_codewords(int $ver): int {
    return intdiv(qr_raw_data_modules($ver), 8)
         - QR_ECC_PER_BLOCK_M[$ver] * QR_BLOCKS_M[$ver];
}

// --- Galois field GF(256), γεννήτρια 0x11D ----------------------------------

function qr_gf_mul(int $a, int $b): int {
    $z = 0;
    for ($i = 7; $i >= 0; $i--) {
        $z = (($z << 1) ^ ((($z >> 7) & 1) * 0x11D)) & 0xFF;
        $z ^= (($b >> $i) & 1) * $a;
        $z &= 0xFF;
    }
    return $z;
}

/** Το πολυώνυμο-γεννήτρια Reed–Solomon βαθμού `$degree`. */
function qr_rs_divisor(int $degree): array {
    $result = array_fill(0, $degree, 0);
    $result[$degree - 1] = 1;
    $root = 1;
    for ($i = 0; $i < $degree; $i++) {
        for ($j = 0; $j < $degree; $j++) {
            $result[$j] = qr_gf_mul($result[$j], $root);
            if ($j + 1 < $degree) $result[$j] ^= $result[$j + 1];
        }
        $root = qr_gf_mul($root, 0x02);
    }
    return $result;
}

/** Οι κωδικές λέξεις διόρθωσης για ένα μπλοκ δεδομένων. */
function qr_rs_remainder(array $data, array $divisor): array {
    $degree = count($divisor);
    $result = array_fill(0, $degree, 0);
    foreach ($data as $b) {
        $factor = ($b ^ $result[0]) & 0xFF;
        array_shift($result);
        $result[] = 0;
        for ($i = 0; $i < $degree; $i++) $result[$i] ^= qr_gf_mul($divisor[$i], $factor);
    }
    return $result;
}

// --- Το πλέγμα ---------------------------------------------------------------

/**
 * Ο πίνακας μονάδων ενός QR: `[row][col] => bool` (true = σκούρο).
 *
 * Επιστρέφει κενό πίνακα όταν το κείμενο δεν χωρά ως την έκδοση 15.
 */
function qr_matrix(string $text): array {
    $bytes = array_values(unpack('C*', $text) ?: []);
    $n = count($bytes);
    if ($n === 0) return [];

    // 1. Η μικρότερη έκδοση που χωρά. Ο μετρητής χαρακτήρων είναι 8 bit ως την
    //    έκδοση 9 και 16 bit από τη 10 και πάνω — γι' αυτό ο έλεγχος γίνεται
    //    ανά έκδοση και όχι μία φορά.
    $ver = 0;
    for ($v = 1; $v <= QR_MAX_VERSION; $v++) {
        $countBits = $v <= 9 ? 8 : 16;
        if (4 + $countBits + $n * 8 <= qr_data_codewords($v) * 8) { $ver = $v; break; }
    }
    if ($ver === 0) return [];

    // 2. Η ροή bit: τρόπος (byte) + πλήθος + δεδομένα + τερματισμός + γέμισμα.
    $bits = [];
    $push = static function (int $val, int $len) use (&$bits): void {
        for ($i = $len - 1; $i >= 0; $i--) $bits[] = ($val >> $i) & 1;
    };
    $push(0b0100, 4);
    $push($n, $ver <= 9 ? 8 : 16);
    foreach ($bytes as $b) $push($b, 8);

    $capacityBits = qr_data_codewords($ver) * 8;
    $push(0, min(4, $capacityBits - count($bits)));
    $push(0, (8 - count($bits) % 8) % 8);
    for ($pad = 0xEC; count($bits) < $capacityBits; $pad ^= 0xEC ^ 0x11) $push($pad, 8);

    $data = [];
    for ($i = 0; $i < count($bits); $i += 8) {
        $b = 0;
        for ($j = 0; $j < 8; $j++) $b = ($b << 1) | $bits[$i + $j];
        $data[] = $b;
    }

    // 3. Διόρθωση σφαλμάτων ανά μπλοκ και πλέξιμο.
    $all = qr_interleave($data, $ver);

    // 4. Το πλέγμα: πρώτα τα μοτίβα λειτουργίας, μετά τα δεδομένα.
    $size = $ver * 4 + 17;
    $m    = array_fill(0, $size, array_fill(0, $size, false));
    $fn   = array_fill(0, $size, array_fill(0, $size, false));
    qr_draw_function_patterns($m, $fn, $ver, $size);
    qr_draw_codewords($m, $fn, $all, $size);

    // 5. Η μάσκα με τη μικρότερη ποινή. Το πρότυπο δεν αφήνει επιλογή εδώ:
    //    μια κακή μάσκα φτιάχνει μοτίβα που μπερδεύονται με τα σήματα θέσης.
    $best = -1; $bestScore = PHP_INT_MAX; $bestGrid = null;
    for ($mask = 0; $mask < 8; $mask++) {
        $try = $m;
        qr_apply_mask($try, $fn, $mask, $size);
        qr_draw_format_bits($try, $mask, $size);
        $score = qr_penalty($try, $size);
        if ($score < $bestScore) { $bestScore = $score; $best = $mask; $bestGrid = $try; }
    }
    return $bestGrid ?: [];
}

function qr_interleave(array $data, int $ver): array {
    $numBlocks   = QR_BLOCKS_M[$ver];
    $blockEccLen = QR_ECC_PER_BLOCK_M[$ver];
    $rawCodewords = intdiv(qr_raw_data_modules($ver), 8);
    $numShort     = $numBlocks - $rawCodewords % $numBlocks;
    $shortLen     = intdiv($rawCodewords, $numBlocks);
    $divisor      = qr_rs_divisor($blockEccLen);

    $blocks = [];
    $k = 0;
    for ($i = 0; $i < $numBlocks; $i++) {
        $len = $shortLen - $blockEccLen + ($i < $numShort ? 0 : 1);
        $dat = array_slice($data, $k, $len);
        $k  += $len;
        $ecc = qr_rs_remainder($dat, $divisor);
        // Τα «κοντά» μπλοκ αποκτούν μια κενή θέση ώστε το πλέξιμο να δουλεύει
        // με ορθογώνιο πίνακα· η θέση αυτή παραλείπεται στην έξοδο.
        if ($i < $numShort) $dat[] = null;
        $blocks[] = array_merge($dat, $ecc);
    }

    $out = [];
    $total = count($blocks[0]);
    for ($i = 0; $i < $total; $i++) {
        for ($j = 0; $j < $numBlocks; $j++) {
            if ($i === $shortLen - $blockEccLen && $j < $numShort) continue;
            $out[] = (int)$blocks[$j][$i];
        }
    }
    return $out;
}

function qr_set(array &$m, array &$fn, int $row, int $col, bool $dark): void {
    $m[$row][$col]  = $dark;
    $fn[$row][$col] = true;
}

function qr_draw_function_patterns(array &$m, array &$fn, int $ver, int $size): void {
    for ($i = 0; $i < $size; $i++) {          // χρονισμός
        qr_set($m, $fn, 6, $i, $i % 2 === 0);
        qr_set($m, $fn, $i, 6, $i % 2 === 0);
    }
    foreach ([[3, 3], [3, $size - 4], [$size - 4, 3]] as [$r, $c]) {
        for ($dy = -4; $dy <= 4; $dy++) {
            for ($dx = -4; $dx <= 4; $dx++) {
                $dist = max(abs($dx), abs($dy));
                $rr = $r + $dy; $cc = $c + $dx;
                if ($rr >= 0 && $rr < $size && $cc >= 0 && $cc < $size) {
                    qr_set($m, $fn, $rr, $cc, $dist !== 2 && $dist !== 4);
                }
            }
        }
    }
    $pos = qr_align_positions($ver);
    $num = count($pos);
    for ($i = 0; $i < $num; $i++) {
        for ($j = 0; $j < $num; $j++) {
            if (($i === 0 && $j === 0) || ($i === 0 && $j === $num - 1) || ($i === $num - 1 && $j === 0)) continue;
            for ($dy = -2; $dy <= 2; $dy++) {
                for ($dx = -2; $dx <= 2; $dx++) {
                    qr_set($m, $fn, $pos[$i] + $dy, $pos[$j] + $dx, max(abs($dx), abs($dy)) !== 1);
                }
            }
        }
    }
    // Οι θέσεις της μορφής δεσμεύονται τώρα (γράφονται μετά τη μάσκα).
    qr_draw_format_bits($m, 0, $size, $fn);
    if ($ver >= 7) {
        $rem = $ver;
        for ($i = 0; $i < 12; $i++) $rem = ($rem << 1) ^ (($rem >> 11) * 0x1F25);
        $bits = ($ver << 12) | $rem;
        for ($i = 0; $i < 18; $i++) {
            $bit = (($bits >> $i) & 1) === 1;
            $a = $size - 11 + $i % 3; $b = intdiv($i, 3);
            qr_set($m, $fn, $b, $a, $bit);
            qr_set($m, $fn, $a, $b, $bit);
        }
    }
}

/** Τα 15 bit της μορφής (επίπεδο M + μάσκα), και στα δύο αντίγραφά τους. */
function qr_draw_format_bits(array &$m, int $mask, int $size, ?array &$fn = null): void {
    $data = (0b00 << 3) | $mask;                       // επίπεδο M = 00
    $rem  = $data;
    for ($i = 0; $i < 10; $i++) $rem = ($rem << 1) ^ (($rem >> 9) * 0x537);
    $bits = (($data << 10) | $rem) ^ 0x5412;
    $put = static function (int $row, int $col, bool $dark) use (&$m, &$fn): void {
        $m[$row][$col] = $dark;
        if ($fn !== null) $fn[$row][$col] = true;
    };
    for ($i = 0; $i <= 5; $i++) $put($i, 8, (($bits >> $i) & 1) === 1);
    $put(7, 8, (($bits >> 6) & 1) === 1);
    $put(8, 8, (($bits >> 7) & 1) === 1);
    $put(8, 7, (($bits >> 8) & 1) === 1);
    for ($i = 9; $i < 15; $i++) $put(8, 14 - $i, (($bits >> $i) & 1) === 1);
    for ($i = 0; $i < 8; $i++)  $put(8, $size - 1 - $i, (($bits >> $i) & 1) === 1);
    for ($i = 8; $i < 15; $i++) $put($size - 15 + $i, 8, (($bits >> $i) & 1) === 1);
    $put($size - 8, 8, true);                          // πάντα σκούρο
}

function qr_draw_codewords(array &$m, array $fn, array $data, int $size): void {
    $i = 0;
    $total = count($data) * 8;
    for ($right = $size - 1; $right >= 1; $right -= 2) {
        if ($right === 6) $right = 5;
        for ($vert = 0; $vert < $size; $vert++) {
            for ($j = 0; $j < 2; $j++) {
                $col = $right - $j;
                $upward = ((($right + 1) & 2) === 0);
                $row = $upward ? $size - 1 - $vert : $vert;
                if (!$fn[$row][$col] && $i < $total) {
                    $m[$row][$col] = (($data[$i >> 3] >> (7 - ($i & 7))) & 1) === 1;
                    $i++;
                }
            }
        }
    }
}

function qr_apply_mask(array &$m, array $fn, int $mask, int $size): void {
    for ($row = 0; $row < $size; $row++) {
        for ($col = 0; $col < $size; $col++) {
            if ($fn[$row][$col]) continue;
            switch ($mask) {
                case 0: $inv = ($col + $row) % 2 === 0; break;
                case 1: $inv = $row % 2 === 0; break;
                case 2: $inv = $col % 3 === 0; break;
                case 3: $inv = ($col + $row) % 3 === 0; break;
                case 4: $inv = (intdiv($col, 3) + intdiv($row, 2)) % 2 === 0; break;
                case 5: $inv = ($col * $row) % 2 + ($col * $row) % 3 === 0; break;
                case 6: $inv = ((($col * $row) % 2) + (($col * $row) % 3)) % 2 === 0; break;
                default: $inv = (((($col + $row) % 2) + (($col * $row) % 3)) % 2) === 0; break;
            }
            if ($inv) $m[$row][$col] = !$m[$row][$col];
        }
    }
}

/** Η ποινή του προτύπου: όσο μικρότερη, τόσο ευκολότερα διαβάζεται. */
function qr_penalty(array $m, int $size): int {
    $score = 0;
    // Κανόνας 1: σειρές ίδιου χρώματος, οριζόντια και κάθετα.
    for ($row = 0; $row < $size; $row++) {
        $run = 1;
        for ($col = 1; $col < $size; $col++) {
            if ($m[$row][$col] === $m[$row][$col - 1]) {
                $run++;
                if ($run === 5) $score += 3; elseif ($run > 5) $score++;
            } else $run = 1;
        }
    }
    for ($col = 0; $col < $size; $col++) {
        $run = 1;
        for ($row = 1; $row < $size; $row++) {
            if ($m[$row][$col] === $m[$row - 1][$col]) {
                $run++;
                if ($run === 5) $score += 3; elseif ($run > 5) $score++;
            } else $run = 1;
        }
    }
    // Κανόνας 2: τετράγωνα 2×2 ίδιου χρώματος.
    for ($row = 0; $row < $size - 1; $row++) {
        for ($col = 0; $col < $size - 1; $col++) {
            $c = $m[$row][$col];
            if ($c === $m[$row][$col + 1] && $c === $m[$row + 1][$col] && $c === $m[$row + 1][$col + 1]) $score += 3;
        }
    }
    // Κανόνας 3: το μοτίβο 1:1:3:1:1 με κενό — μοιάζει με σήμα θέσης.
    $pat  = [true, false, true, true, true, false, true, false, false, false, false];
    $rpat = array_reverse($pat);
    for ($row = 0; $row < $size; $row++) {
        for ($col = 0; $col + 11 <= $size; $col++) {
            $a = true; $b = true;
            for ($k = 0; $k < 11; $k++) {
                if ($m[$row][$col + $k] !== $pat[$k])  $a = false;
                if ($m[$row][$col + $k] !== $rpat[$k]) $b = false;
            }
            if ($a || $b) $score += 40;
        }
    }
    for ($col = 0; $col < $size; $col++) {
        for ($row = 0; $row + 11 <= $size; $row++) {
            $a = true; $b = true;
            for ($k = 0; $k < 11; $k++) {
                if ($m[$row + $k][$col] !== $pat[$k])  $a = false;
                if ($m[$row + $k][$col] !== $rpat[$k]) $b = false;
            }
            if ($a || $b) $score += 40;
        }
    }
    // Κανόνας 4: απόκλιση από το 50/50 σκούρο-ανοιχτό.
    $dark = 0;
    for ($row = 0; $row < $size; $row++) foreach ($m[$row] as $v) if ($v) $dark++;
    $total = $size * $size;
    $k = (int)((abs($dark * 20 - $total * 10) + $total - 1) / $total) - 1;
    $score += max(0, $k) * 10;
    return $score;
}

/**
 * Ο κωδικός ως SVG, έτοιμος για `innerHTML`.
 *
 * Το SVG (και όχι PNG) γιατί δεν χρειάζεται καμία επέκταση εικόνας στην PHP —
 * η φορητή PHP που ταξιδεύει με την εφαρμογή δεν έχει GD — και γιατί μένει
 * καθαρό σε κάθε ανάλυση, από την οθόνη του κινητού ως την εκτύπωση.
 */
function qr_svg(string $text, int $px = 176, int $quiet = 4): string {
    $m = qr_matrix($text);
    if (!$m) return '';
    $size  = count($m);
    $total = $size + 2 * $quiet;
    $path  = '';
    for ($row = 0; $row < $size; $row++) {
        for ($col = 0; $col < $size; $col++) {
            if ($m[$row][$col]) $path .= 'M' . ($col + $quiet) . ' ' . ($row + $quiet) . 'h1v1h-1z';
        }
    }
    // Λευκό φόντο ΠΑΝΤΑ, ακόμη και σε σκοτεινό θέμα: οι σαρωτές περιμένουν
    // σκούρες μονάδες σε ανοιχτό φόντο, και η αντιστροφή δεν διαβάζεται από
    // όλες τις εφαρμογές.
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' . $px . '" height="' . $px . '" '
         . 'viewBox="0 0 ' . $total . ' ' . $total . '" shape-rendering="crispEdges" '
         . 'role="img" aria-label="Κωδικός QR για τον authenticator">'
         . '<rect width="' . $total . '" height="' . $total . '" fill="#ffffff"/>'
         . '<path d="' . $path . '" fill="#000000"/></svg>';
}
