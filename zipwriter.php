<?php
// ============================================================================
// zipwriter.php — minimal ZIP builder (pure PHP, needs only zlib)
// ============================================================================
// Why not ZipArchive: the `zip` extension is NOT guaranteed. It is absent from
// the portable PHP we run on the desktop and from slim container images, so a
// feature built on it would work on the VPS and quietly break offline. The ZIP
// container is simple enough to emit directly, and DEFLATE comes from zlib,
// which is always compiled in.
//
// Produces a standard, single-disk archive: [local header + data] per entry,
// then the central directory and the end-of-central-directory record.
// ----------------------------------------------------------------------------

/**
 * Build a ZIP archive in memory from `name => bytes`.
 *
 * Names are stored UTF-8 with the language-encoding flag set, so Greek
 * filenames survive in Explorer and in macOS Archive Utility alike.
 */
function zip_build(array $files): string
{
    $entries = [];      // central-directory records
    $out      = '';     // the archive as we stream it
    $offset   = 0;

    foreach ($files as $name => $data) {
        $name = str_replace('\\', '/', (string)$name);
        $data = (string)$data;
        $crc  = crc32($data);
        $size = strlen($data);

        // DEFLATE, falling back to STORE when compression does not pay off
        // (already-compressed PDFs often grow slightly).
        $compressed = gzdeflate($data, 6);
        if ($compressed === false || strlen($compressed) >= $size) {
            $compressed = $data;
            $method     = 0;   // stored
        } else {
            $method     = 8;   // deflated
        }
        $csize = strlen($compressed);

        [$dosTime, $dosDate] = zip_dos_time(time());
        // Bit 11 = filename is UTF-8.
        $flags = 0x0800;

        $local = "\x50\x4b\x03\x04"            // local file header signature
            . pack('v', 20)                    // version needed
            . pack('v', $flags)
            . pack('v', $method)
            . pack('v', $dosTime)
            . pack('v', $dosDate)
            . pack('V', $crc)
            . pack('V', $csize)
            . pack('V', $size)
            . pack('v', strlen($name))
            . pack('v', 0)                     // extra field length
            . $name;

        $out .= $local . $compressed;

        $entries[] = "\x50\x4b\x01\x02"        // central directory signature
            . pack('v', 0x031E)                // version made by (UNIX, 3.0)
            . pack('v', 20)
            . pack('v', $flags)
            . pack('v', $method)
            . pack('v', $dosTime)
            . pack('v', $dosDate)
            . pack('V', $crc)
            . pack('V', $csize)
            . pack('V', $size)
            . pack('v', strlen($name))
            . pack('v', 0)                     // extra
            . pack('v', 0)                     // comment
            . pack('v', 0)                     // disk number
            . pack('v', 0)                     // internal attributes
            . pack('V', 32)                    // external attributes (archive)
            . pack('V', $offset)
            . $name;

        $offset += strlen($local) + $csize;
    }

    $central     = implode('', $entries);
    $centralSize = strlen($central);
    $count       = count($entries);

    return $out . $central
        . "\x50\x4b\x05\x06"                   // end of central directory
        . pack('v', 0)                         // this disk
        . pack('v', 0)                         // disk with central directory
        . pack('v', $count)
        . pack('v', $count)
        . pack('V', $centralSize)
        . pack('V', $offset)
        . pack('v', 0);                        // comment length
}

/**
 * Read an archive built by `zip_build` back into `name => bytes`.
 *
 * NOT named `zip_read`: that is a REAL PHP function from ext/zip (the old
 * procedural API, alongside `zip_open`/`zip_entry_read`). The zip extension is
 * loaded here for reading .xlsx bank statements, so declaring `zip_read()`
 * fataled the whole application with «Cannot redeclare» — on the server, not
 * on the portable PHP, which is the worst place to find out.
 *
 * Walks the central directory (never the local headers): only the central
 * directory is authoritative about offsets and sizes. Every entry's CRC is
 * verified — a backup that unpacks to garbage without complaining is worse
 * than one that refuses to unpack.
 */
function zip_unpack(string $bytes): array
{
    $out = [];
    $p = 0;
    while (($p = strpos($bytes, "\x50\x4b\x01\x02", $p)) !== false) {
        $method  = unpack('v', substr($bytes, $p + 10, 2))[1];
        $crc     = unpack('V', substr($bytes, $p + 16, 4))[1];
        $csize   = unpack('V', substr($bytes, $p + 20, 4))[1];
        $size    = unpack('V', substr($bytes, $p + 24, 4))[1];
        $nameLen = unpack('v', substr($bytes, $p + 28, 2))[1];
        $extraLen = unpack('v', substr($bytes, $p + 30, 2))[1];
        $cmtLen  = unpack('v', substr($bytes, $p + 32, 2))[1];
        $offset  = unpack('V', substr($bytes, $p + 42, 4))[1];
        $name    = substr($bytes, $p + 46, $nameLen);
        $p += 46 + $nameLen + $extraLen + $cmtLen;

        if (substr($bytes, $offset, 4) !== "\x50\x4b\x03\x04") continue;
        // Το ΤΟΠΙΚΟ header έχει δικά του μήκη ονόματος/extra — και το extra
        // ΔΕΝ είναι πάντα ίδιο με του κεντρικού καταλόγου.
        $lNameLen  = unpack('v', substr($bytes, $offset + 26, 2))[1];
        $lExtraLen = unpack('v', substr($bytes, $offset + 28, 2))[1];
        $data = substr($bytes, $offset + 30 + $lNameLen + $lExtraLen, $csize);
        if ($method === 8) {
            $data = @gzinflate($data);
            if ($data === false) continue;
        }
        if (strlen($data) !== $size || sprintf('%u', crc32($data)) !== sprintf('%u', $crc)) continue;
        $out[$name] = $data;
    }
    return $out;
}

/** Convert a unix timestamp to the DOS (time, date) pair ZIP stores. */
function zip_dos_time(int $ts): array
{
    $y = (int)date('Y', $ts);
    if ($y < 1980) {
        return [0, 33];   // 1980-01-01, the earliest DOS can express
    }
    $time = ((int)date('H', $ts) << 11) | ((int)date('i', $ts) << 5) | ((int)date('s', $ts) >> 1);
    $date = (($y - 1980) << 9) | ((int)date('n', $ts) << 5) | (int)date('j', $ts);
    return [$time, $date];
}

/**
 * Filesystem-safe entry name for an invoice PDF: `<ημ/νία> <σειρά>-<ΑΑ> <ΜΑΡΚ>.pdf`
 * — the same shape the desktop app uses, so both halves produce identical ZIPs.
 */
function zip_invoice_name(array $row, string $mark): string
{
    $clean = static fn($v) => trim(preg_replace('~[\\\\/:*?"<>|]+~u', '-', (string)$v));
    $date   = str_replace('/', '-', $clean($row['issue_date'] ?? ''));
    $series = $clean($row['series'] ?? '');
    $aa     = $clean($row['aa'] ?? '');
    $sa     = trim($series . '-' . $aa, '-');
    $parts  = array_values(array_filter([$date, $sa, $clean($mark)], static fn($p) => $p !== ''));
    $stem   = $parts ? implode(' ', $parts) : ('παραστατικό-' . $mark);
    return mb_substr($stem, 0, 90) . '.pdf';
}
