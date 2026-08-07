<?php
// ============================================================================
// e-Timologio API — ΑΑΔΕ myDATA
// ============================================================================
//
// CUSTOMER LOOKUP (find or auto-create in e-timologio):
//   ?afm=801725430
//
// DRAFT INVOICE (saved to Προσωρινά Αποθηκευμένα, NOT submitted to AADE):
//   ?amount=500&type=58
//
// DRAFT INVOICE + CUSTOMER (auto find/create customer first):
//   ?afm=801725430&amount=500&type=58
//
// FULL EXAMPLE:
//   ?afm=801725430&amount=500&type=58&payment=6&name=ACME SA&city=Athens&zip=10432
//
// ----------------------------------------------------------------------------
// PARAMETERS
// ----------------------------------------------------------------------------
//
// afm         Greek tax number — 9 digits for GR clients (optional for invoices,
//             required for customer lookup). For type 22 (non-EU), pass the
//             foreign VAT string (e.g. afm=FOREIGN) or leave empty.
//             If provided for GR clients, customer is auto found/created.
//
// amount      Net amount in EUR, excluding VAT (required for invoice).
//             VAT 24% is calculated automatically except for type 22 (0% VAT).
//             e.g. amount=500 → net 500€ + VAT 120€ = total 620€
//
// type        Invoice type code (required for invoice):
//               20  → 2.1  Τιμολόγιο Παροχής Υπηρεσιών (B2B, GR)
//               21  → 2.2  Τιμολόγιο Παροχής / Ενδοκοινοτική (B2B, EU)
//               22  → 2.3  Τιμολόγιο Παροχής Υπηρεσιών - Τρίτες Χώρες (0% ΦΠΑ)
//               57  → 11.1 ΑΛΠ (Απόδειξη Λιανικής Πώλησης)
//               58  → 11.2 ΑΠΥ (Απόδειξη Παροχής Υπηρεσιών)
//
// payment     Payment method code (optional, default 3):
//               1   → Επαγγελματικός Λογαριασμός Πληρωμών Ημεδαπής
//               2   → Επαγγελματικός Λογαριασμός Πληρωμών Αλλοδαπής
//               3   → Μετρητά
//               4   → Επιταγή
//               5   → Επί πιστώσει
//               6   → Web Banking
//               7   → POS / e-POS
//               8   → Άμεσες Πληρωμές IRIS
//
// name        Customer name (optional — auto-populated from Taxisnet if GR afm given,
//             or from e-timologio database if foreign afm given)
// address     Customer street address (optional — auto-populated as above)
// city        Customer city (optional — auto-populated as above)
// zip         Customer postal code (optional — auto-populated as above)
// country     Customer country ISO code (optional, default GR)
//             Auto-populated from e-timologio database for foreign clients
// branch      Customer branch number (optional, default 0)
// description Product/service code from your e-timologio catalogue
//             (optional, default ΥΠ001)
//
// withholding_category  Withholding tax category (optional, B2B invoices only):
//               1   → Περ. β' - Τόκοι 15%
//               2   → Περ. γ' - Δικαιώματα 20%
//               3   → Περ. δ' - Αμοιβές Συμβούλων Διοίκησης 20%
//               4   → Περ. δ' - Τεχνικά Έργα 3%
//               7   → Παροχή Υπηρεσιών 8%
//
// withholding_amount    Withheld tax amount in EUR (required if withholding_category set)
//
// mark        MARK number of an already-issued invoice (optional).
//             If provided, all other parameters are ignored and the PDF
//             of that invoice is returned directly in the browser.
//
// live        Set to 1 to actually submit the invoice to AADE and get a MARK.
//             Without this parameter, invoice is saved as draft only (safe for testing).
//             e.g. &live=1
//
// ----------------------------------------------------------------------------
// EXAMPLES
// ----------------------------------------------------------------------------
//
// Anonymous cash receipt:
//   ?amount=500&type=58&payment=3
//
// Web banking receipt with customer name and address:
//   ?amount=500&type=58&payment=6&name=PAPADOPOULOS GEORGIOS&address=ΣΤΑΔΙΟΥ 10&city=ΑΘΗΝΑ&zip=10564
//
// Full receipt with AFM (auto-creates customer, auto-populates name/address):
//   ?afm=801725430&amount=500&type=58&payment=6
//
// Service invoice (τιμολόγιο) to business client:
//   ?afm=801725430&amount=1000&type=20&payment=5&description=ΥΠ002
//
// Service invoice with withholding tax (20% on fees):
//   ?afm=801725430&amount=1000&type=20&payment=5&withholding_category=3&withholding_amount=200
//
// Invoice to non-EU client (0% VAT, auto-populated from e-timologio database):
//   ?amount=1000&type=22&payment=6&afm=FOREIGN
//
// Retrieve PDF of issued invoice by MARK:
//   ?mark=400000000000001
//
// Retrieve PDF as raw binary (browser-friendly):
//   ?mark=400000000000001&pdf_raw=1
//
// LIVE invoice (actually submitted to AADE, MARK assigned):
//   ?afm=801725430&amount=500&type=58&payment=6&live=1
//
// ============================================================================

require __DIR__ . '/auth.php';   // session + config + localdb + account resolution
require __DIR__ . '/bankimport.php'; // bank statement (extrait) parsing → local payments

// --- RESPONSE HELPERS --------------------------------------------------------

function jsonResponse(array $data, int $status = 200): void {
    http_response_code($status);
    header('Content-Type: application/json');
    // JSON_INVALID_UTF8_SUBSTITUTE: never emit an empty body if a stored value
    // has a stray non-UTF-8 byte — substitute it instead of failing silently.
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function jsonError(string $message, int $status = 400): void {
    jsonResponse(['success' => false, 'error' => $message], $status);
}

// --- CURL HELPERS ------------------------------------------------------------

function curlGet(\CurlHandle $ch, string $url): string {
    curl_setopt($ch, CURLOPT_URL,            $url);
    curl_setopt($ch, CURLOPT_HTTPGET,        true);
    curl_setopt($ch, CURLOPT_POST,           false);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    return curl_exec($ch);
}

function curlPost(\CurlHandle $ch, string $url, array $fields): string {
    curl_setopt($ch, CURLOPT_URL,            $url);
    curl_setopt($ch, CURLOPT_POST,           true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS,     http_build_query($fields));
    return curl_exec($ch);
}

function curlPostInvoice(\CurlHandle $ch, string $url, array $data): string {
    curl_setopt($ch, CURLOPT_URL,            $url);
    curl_setopt($ch, CURLOPT_POST,           true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS,     http_build_query(['inv' => $data]));
    curl_setopt($ch, CURLOPT_HTTPHEADER,     [
        'Content-Type: application/x-www-form-urlencoded',
        'X-Requested-With: XMLHttpRequest',
        'Accept: application/json, text/javascript, */*; q=0.01',
    ]);
    return curl_exec($ch);
}

function getToken(\CurlHandle $ch, string $url): string {
    $html = curlGet($ch, $url);
    preg_match('/name="__RequestVerificationToken".*?value="([^"]+)"/', $html, $m);
    return $m[1] ?? '';
}

// --- LOGIN -------------------------------------------------------------------

function login(): \CurlHandle {
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_COOKIEJAR,      COOKIE_FILE);
    curl_setopt($ch, CURLOPT_COOKIEFILE,     COOKIE_FILE);
    curl_setopt($ch, CURLOPT_USERAGENT,      'Mozilla/5.0');

    $token = getToken($ch, BASE_URL . '/Account/Login');
    if (!$token) jsonError('Could not reach e-timologio', 503);

    curlPost($ch, BASE_URL . '/Account/Login', [
        'UserName'                   => USERNAME,
        'VatNumber'                  => COMPANY_VAT,
        'SubscriptionKey'            => SUBSCRIPTION_KEY,
        'ReturnUrl'                  => '/timologio',
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (strpos($finalUrl, 'Login') !== false) jsonError('Login failed', 401);

    return $ch;
}

// --- 1. SEARCH CUSTOMER ------------------------------------------------------

function searchCustomer(\CurlHandle $ch, string $afm): ?array {
    $token = getToken($ch, BASE_URL . '/customer/ListCustomers');

    $html = curlPost($ch, BASE_URL . '/customer/SearchCustomers', [
        'Language'                            => 'el-GR',
        'CompanyVat'                          => COMPANY_VAT,
        'CustomerVat'                         => $afm,
        'CustomerCode'                        => '',
        'CustomerName'                        => '',
        'NextPartitionKey'                    => '',
        'NextRowKey'                          => '',
        'continuationToken.continuationToken' => '',
        'totalFechedRows'                     => '10',
        'PrevCustomerCode'                    => '',
        'PrevCustomerVat'                     => '',
        'PrevCustomerName'                    => '',
        'btnSearch'                           => 'btnSearch',
        '__RequestVerificationToken'          => $token,
    ]);

    if (preg_match('/<td[^>]*>\s*' . preg_quote($afm, '/') . '\s*<\/td>/', $html)) {
        preg_match('/<tr>.*?<td[^>]*>\s*(\d+)\s*<\/td>.*?<td[^>]*>\s*(\d+)\s*<\/td>.*?' . preg_quote($afm, '/') . '/s', $html, $row);
        return ['code' => $row[2] ?? null, 'vat' => $afm];
    }
    return null;
}

// --- 2. GET FROM TAXISNET ----------------------------------------------------

function getFromTaxisnet(\CurlHandle $ch, string $afm): ?array {
    $response = curlGet($ch, BASE_URL . '/Customer/GetCustomerByTaxis?' . http_build_query([
        'companyVat'  => COMPANY_VAT,
        'customerVat' => $afm,
    ]));

    $data = json_decode($response, true);
    if (!$data || !empty($data['errorDescr'])) return null;

    return [
        'name'    => $data['n']  ?? '',
        'address' => $data['a']  ?? '',
        'city'    => $data['ct'] ?? '',
        'zip'     => $data['z']  ?? '',
        'doy'     => $data['do'] ?? '',
    ];
}

// --- 2b. GET CUSTOMER FROM E-TIMOLOGIO DATABASE (for foreign clients) --------

function getCustomerFromDatabase(\CurlHandle $ch, string $term, string $invoiceType): ?array {
    $url = BASE_URL . '/Customer/GetProposedCustomersByName/?' . http_build_query([
        'companyVat' => COMPANY_VAT,
        'invType'    => $invoiceType,
        'term'       => $term,
    ]);
    $response = curlGet($ch, $url);
    $data = json_decode($response, true);
    if (empty($data[0])) return null;

    $c = $data[0];
    return [
        'name'    => $c['n']   ?? '',
        'address' => $c['a']   ?? '',
        'city'    => $c['ct']  ?? '',
        'zip'     => $c['z']   ?? '',
        'country' => $c['cod'] ?? '',
        'vat'     => $c['v']   ?? '',
    ];
}

// --- 3. CREATE CUSTOMER ------------------------------------------------------

function createCustomer(\CurlHandle $ch, string $afm, array $info): bool {
    $token = getToken($ch, BASE_URL . '/customer/NewCustomer');
    if (!$token) return false;

    curlPost($ch, BASE_URL . '/customer/NewCustomer', [
        'CompanyVAT'                 => COMPANY_VAT,
        'Language'                   => 'el-GR',
        'OldCustomerVat'             => $afm,
        'CustomerType'               => '2',
        'Country'                    => 'GR',
        'isB2GCustomer'              => 'false',
        'CustomerCode'               => '',
        'CustomerVat'                => $afm,
        'CustomerName'               => strtoupper($info['name']),
        'JobDescription'             => '',
        'CustomerAddress'            => $info['address'],
        'CustomerCity'               => $info['city'],
        'CustomerZipCode'            => $info['zip'],
        'Doy'                        => $info['doy'],
        'CustomerEmail'              => '',
        'CustomerPhone1'             => '',
        'CustomerPhone2'             => '',
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    return strpos($finalUrl, 'NewCustomer') === false;
}

// --- 3.5 CREATE PERSONAL CUSTOMER (without AFM) --------------------------------

function createPersonalCustomer(
    \CurlHandle $ch,
    string $name,
    string $address,
    string $city,
    string $zip,
    string $doy = 'ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ',
    string $country = 'GR',
    string $jobDescription = 'ΙΔΙΩΤΗΣ',
    string $email = '',
    string $phone1 = '',
    string $phone2 = '',
    string $language = 'el-GR',
    bool $isB2GCustomer = false,
    string $customerCode = '',
    string $customerVat = '',
    string $oldCustomerVat = ''
): array {
    if ($name === '' || $city === '' || $zip === '') {
        return ['success' => false, 'error' => 'Name, city, and zip are required'];
    }

    $jobDescription = trim($jobDescription);
    if ($jobDescription === '') {
        $jobDescription = 'ΙΔΙΩΤΗΣ';
    }

    $token = getToken($ch, BASE_URL . '/customer/NewCustomer');
    if (!$token) {
        return ['success' => false, 'error' => 'Could not load customer form'];
    }

    // Mirror browser payload for personal customer creation (no VAT required)
    $formData = [
        'CompanyVAT'                 => COMPANY_VAT,
        'Language'                   => $language,
        'OldCustomerVat'             => $oldCustomerVat,
        'CustomerType'               => '1',
        'Country'                    => $country,
        'isB2GCustomer'              => $isB2GCustomer ? 'true' : 'false',
        'CustomerCode'               => $customerCode,
        'CustomerVat'                => $customerVat,
        'CustomerName'               => $name,
        'JobDescription'             => $jobDescription,
        'CustomerAddress'            => $address,
        'CustomerCity'               => $city,
        'CustomerZipCode'            => $zip,
        'Doy'                        => $doy,
        'CustomerEmail'              => $email,
        'CustomerPhone1'             => $phone1,
        'CustomerPhone2'             => $phone2,
        '__RequestVerificationToken' => $token,
    ];

    $response = curlPost($ch, BASE_URL . '/customer/NewCustomer', $formData);
    
    // Check if response is JSON success response
    $decoded = json_decode($response, true);
    if (is_array($decoded) && isset($decoded['success'])) {
        if ($decoded['success'] === true || $decoded['success'] === 'true') {
            return ['success' => true, 'message' => 'Personal customer created successfully', 'data' => $decoded];
        }
    }

    // Browser behavior: successful save returns 302 -> /Customer/ViewCustomer?... 
    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (strpos($finalUrl, 'ViewCustomer') !== false) {
        return [
            'success'   => true,
            'message'   => 'Personal customer created successfully',
            'final_url' => $finalUrl,
        ];
    }

    if (strpos($finalUrl, 'NewCustomer') === false) {
        return [
            'success'   => true,
            'message'   => 'Personal customer created successfully',
            'final_url' => $finalUrl,
        ];
    }

    return [
        'success' => false,
        'error' => $decoded['error'] ?? 'Failed to create personal customer',
        'raw' => substr((string)$response, 0, 200),
    ];
}

// --- 4. FIND OR CREATE CUSTOMER ----------------------------------------------

function findOrCreateCustomer(\CurlHandle $ch, string $afm): array {
    $existing = searchCustomer($ch, $afm);
    if ($existing) {
        return ['success' => true, 'status' => 'found', 'code' => $existing['code'], 'vat' => $afm];
    }

    $info = getFromTaxisnet($ch, $afm);
    if (!$info) {
        return ['success' => false, 'status' => 'error', 'error' => 'AFM not found in Taxisnet'];
    }

    $created = createCustomer($ch, $afm, $info);
    if (!$created) {
        return ['success' => false, 'status' => 'error', 'error' => 'Failed to create customer'];
    }

    $new = searchCustomer($ch, $afm);
    return ['success' => true, 'status' => 'created', 'code' => $new['code'] ?? null, 'vat' => $afm, 'info' => $info];
}

// --- 4b. CUSTOMER/INVOICE LIST HELPERS --------------------------------------

function htmlText(string $html): string {
    $text = html_entity_decode(strip_tags($html), ENT_QUOTES | ENT_HTML5, 'UTF-8');
    $text = preg_replace('/\s+/u', ' ', $text ?? '');
    return trim((string)$text);
}

function htmlInputValue(string $html, string $name): string {
    $qName = preg_quote($name, '/');

    if (preg_match('/<input[^>]*name="' . $qName . '"[^>]*value="([^"]*)"[^>]*>/i', $html, $m)) {
        return html_entity_decode($m[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    }
    if (preg_match('/<input[^>]*value="([^"]*)"[^>]*name="' . $qName . '"[^>]*>/i', $html, $m)) {
        return html_entity_decode($m[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    }
    return '';
}

function extractTableRows(string $html, string $tableId): array {
    $qId = preg_quote($tableId, '/');
    if (!preg_match('/<table[^>]*id="' . $qId . '"[^>]*>(.*?)<\/table>/is', $html, $tableMatch)) {
        return [];
    }

    $tableHtml = $tableMatch[1];
    
    // First try to extract from tbody (standard case)
    if (preg_match('/<tbody[^>]*>(.*?)<\/tbody>/is', $tableHtml, $tbodyMatch)) {
        $bodyContent = $tbodyMatch[1];
    } else {
        // Fallback: extract all tr elements directly from table
        $bodyContent = $tableHtml;
    }

    preg_match_all('/<tr[^>]*>(.*?)<\/tr>/is', $bodyContent, $rowMatches);
    $rows = [];
    foreach ($rowMatches[1] as $rowHtml) {
        preg_match_all('/<td[^>]*>(.*?)<\/td>/is', $rowHtml, $cellMatches);
        if (!empty($cellMatches[1])) {
            // Skip header rows (those with only 1-2 cells or containing <th> instead of <td>)
            if (count($cellMatches[1]) > 2 && !preg_match('/<th/i', $rowHtml)) {
                $rows[] = [
                    'html'  => $rowHtml,
                    'cells' => $cellMatches[1],
                ];
            }
        }
    }
    return $rows;
}

function toSearchDate(string $value, string $fallback): string {
    $value = trim($value);
    if ($value === '') return $fallback;

    if (preg_match('/^\d{2}\/\d{2}\/\d{4}$/', $value)) {
        return $value;
    }
    if (preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $value, $m)) {
        return $m[3] . '/' . $m[2] . '/' . $m[1];
    }
    return $fallback;
}

function listCustomers(
    \CurlHandle $ch,
    string $customerVat = '',
    string $customerCode = '',
    string $customerName = '',
    bool $all = false,
    int $pageSize = 1000,
    int $maxPages = 20
): array {
    $pageSize = max(1, min(1000, $pageSize));
    $maxPages = max(1, min(200, $maxPages));

    $state = [
        'NextPartitionKey'                    => '',
        'NextRowKey'                          => '',
        'continuationToken.continuationToken' => '',
        'PrevCustomerCode'                    => '',
        'PrevCustomerVat'                     => '',
        'PrevCustomerName'                    => '',
    ];

    $token = getToken($ch, BASE_URL . '/customer/ListCustomers');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load customer search form'];
    }

    $seen = [];
    $customers = [];
    $pages = 0;

    while ($pages < $maxPages) {
        $pages++;

        $html = curlPost($ch, BASE_URL . '/customer/SearchCustomers', [
            'Language'                            => 'el-GR',
            'CompanyVat'                          => COMPANY_VAT,
            'CustomerVat'                         => $customerVat,
            'CustomerCode'                        => $customerCode,
            'CustomerName'                        => $customerName,
            'NextPartitionKey'                    => $state['NextPartitionKey'],
            'NextRowKey'                          => $state['NextRowKey'],
            'continuationToken.continuationToken' => $state['continuationToken.continuationToken'],
            'totalFechedRows'                     => (string)$pageSize,
            'PrevCustomerCode'                    => $state['PrevCustomerCode'],
            'PrevCustomerVat'                     => $state['PrevCustomerVat'],
            'PrevCustomerName'                    => $state['PrevCustomerName'],
            'btnSearch'                           => 'btnSearch',
            '__RequestVerificationToken'          => $token,
        ]);

        $rows = extractTableRows($html, 'tblCustomers');
        foreach ($rows as $row) {
            $cols = array_map('htmlText', $row['cells']);
            if (count($cols) < 7) continue;

            $customer = [
                'row_no'  => $cols[0],
                'code'    => $cols[1],
                'type'    => $cols[2],
                'vat'     => $cols[3],
                'name'    => $cols[4],
                'address' => $cols[5],
                'city'    => $cols[6],
            ];

            if (preg_match('/deleteCustomer\(\'([^\']+)\',\s*\'([^\']+)\'\)/', $row['html'], $m)) {
                $customer['company_vat'] = $m[1];
                $customer['delete_code'] = $m[2];
            }

            $key = $customer['code'] . '|' . $customer['vat'];
            if (!isset($seen[$key])) {
                $seen[$key] = true;
                $customers[] = $customer;
            }
        }

        $nextState = [
            'NextPartitionKey'                    => htmlInputValue($html, 'NextPartitionKey'),
            'NextRowKey'                          => htmlInputValue($html, 'NextRowKey'),
            'continuationToken.continuationToken' => htmlInputValue($html, 'continuationToken.continuationToken'),
            'PrevCustomerCode'                    => htmlInputValue($html, 'PrevCustomerCode'),
            'PrevCustomerVat'                     => htmlInputValue($html, 'PrevCustomerVat'),
            'PrevCustomerName'                    => htmlInputValue($html, 'PrevCustomerName'),
        ];

        $hasNext = $nextState['NextPartitionKey'] !== ''
            || $nextState['NextRowKey'] !== ''
            || $nextState['continuationToken.continuationToken'] !== '';

        if (!$all || !$hasNext || $nextState === $state) {
            $state = $nextState;
            break;
        }

        $state = $nextState;
    }

    return [
        'success'       => true,
        'count'         => count($customers),
        'pages_fetched' => $pages,
        'has_next_page' => ($state['NextPartitionKey'] !== ''
            || $state['NextRowKey'] !== ''
            || $state['continuationToken.continuationToken'] !== ''),
        'customers'     => $customers,
    ];
}

function htmlSelectedValue(string $html, string $selectName): string {
    $qName = preg_quote($selectName, '/');
    if (!preg_match('/<select[^>]*name="' . $qName . '"[^>]*>(.*?)<\/select>/is', $html, $m)) {
        return '';
    }
    $block = $m[1];
    if (preg_match('/<option[^>]*selected[^>]*value="([^"]*)"/i', $block, $o)) {
        return html_entity_decode($o[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    }
    return '';
}

function findCustomerViewUrl(
    \CurlHandle $ch,
    string $customerVat = '',
    string $customerCode = ''
): array {
    if ($customerVat === '' && $customerCode === '') {
        return ['success' => false, 'error' => 'Customer VAT or customer code is required'];
    }

    $token = getToken($ch, BASE_URL . '/customer/ListCustomers');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load customer search form'];
    }

    $html = curlPost($ch, BASE_URL . '/customer/SearchCustomers', [
        'Language'                            => 'el-GR',
        'CompanyVat'                          => COMPANY_VAT,
        'CustomerVat'                         => $customerVat,
        'CustomerCode'                        => $customerCode,
        'CustomerName'                        => '',
        'NextPartitionKey'                    => '',
        'NextRowKey'                          => '',
        'continuationToken.continuationToken' => '',
        'totalFechedRows'                     => '1000',
        'PrevCustomerCode'                    => '',
        'PrevCustomerVat'                     => '',
        'PrevCustomerName'                    => '',
        'btnSearch'                           => 'btnSearch',
        '__RequestVerificationToken'          => $token,
    ]);

    $rows = extractTableRows($html, 'tblCustomers');
    $matches = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 4) continue;

        $code = trim($cols[1] ?? '');
        $vat  = trim($cols[3] ?? '');
        if ($customerCode !== '' && $code !== $customerCode) continue;
        if ($customerVat !== '' && $vat !== $customerVat) continue;

        if (!preg_match('/href="([^\"]*\/Customer\/viewcustomer\?[^\"]+)"/i', $row['html'], $m)) {
            continue;
        }

        $viewUrl = html_entity_decode($m[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
        if (strpos($viewUrl, 'http') !== 0) {
            $viewUrl = 'https://mydata.aade.gr' . $viewUrl;
        }

        $matches[] = [
            'customer_code' => $code,
            'customer_vat'  => $vat,
            'view_url'      => $viewUrl,
        ];
    }

    if (count($matches) === 0) {
        return [
            'success' => false,
            'error' => 'Customer not found in search results',
            'target_vat' => $customerVat,
            'target_code' => $customerCode,
        ];
    }

    if (count($matches) > 1) {
        return [
            'success' => false,
            'error' => 'Ambiguous customer selection: multiple exact matches found',
            'target_vat' => $customerVat,
            'target_code' => $customerCode,
            'matches' => array_slice($matches, 0, 10),
            'match_count' => count($matches),
        ];
    }

    return ['success' => true] + $matches[0];
}

function deleteCustomerBySelector(
    \CurlHandle $ch,
    string $customerVat = '',
    string $customerCode = ''
): array {
    $located = findCustomerViewUrl($ch, $customerVat, $customerCode);
    if (empty($located['success'])) {
        return $located;
    }

    $resolvedCode = (string)($located['customer_code'] ?? '');
    $resolvedVat  = (string)($located['customer_vat'] ?? '');
    $viewUrl      = (string)($located['view_url'] ?? '');

    if ($resolvedCode === '' || $viewUrl === '') {
        return ['success' => false, 'error' => 'Could not resolve customer identity for deletion'];
    }

    $viewHtml = curlGet($ch, $viewUrl);
    $viewCode = htmlInputValue($viewHtml, 'customer.CustomerCode');
    $viewVat  = htmlInputValue($viewHtml, 'customer.CustomerVat');

    if ($customerCode !== '' && $viewCode !== $customerCode) {
        return [
            'success' => false,
            'error' => 'Guard check failed: mismatched customer code before delete',
            'expected_code' => $customerCode,
            'found_code' => $viewCode,
        ];
    }
    if ($customerVat !== '' && $viewVat !== $customerVat) {
        return [
            'success' => false,
            'error' => 'Guard check failed: mismatched customer VAT before delete',
            'expected_vat' => $customerVat,
            'found_vat' => $viewVat,
        ];
    }

    $deleted = deleteCustomerByCode($ch, $resolvedCode);
    $deleted['customer_code'] = $resolvedCode;
    $deleted['customer_vat'] = $resolvedVat;
    $deleted['view_code'] = $viewCode;
    $deleted['view_vat'] = $viewVat;
    return $deleted;
}

function updateCustomer(
    \CurlHandle $ch,
    string $customerVat = '',
    string $customerCode = '',
    string $phone1 = '',
    string $phone2 = '',
    string $email = '',
    string $jobDescription = '',
    string $address = '',
    string $city = '',
    string $zip = '',
    string $doy = '',
    string $name = ''
): array {
    $hasChanges = $phone1 !== '' || $phone2 !== '' || $email !== '' || $jobDescription !== ''
        || $address !== '' || $city !== '' || $zip !== '' || $doy !== '' || $name !== '';
    if (!$hasChanges) {
        return ['success' => false, 'error' => 'At least one update field is required'];
    }

    $located = findCustomerViewUrl($ch, $customerVat, $customerCode);
    if (empty($located['success'])) {
        return $located;
    }

    $viewUrl = $located['view_url'];
    $viewBefore = curlGet($ch, $viewUrl);
    $beforeVat = htmlInputValue($viewBefore, 'customer.CustomerVat');
    $beforeCode = htmlInputValue($viewBefore, 'customer.CustomerCode');
    if ($customerVat !== '' && $beforeVat !== $customerVat) {
        return [
            'success' => false,
            'error'   => 'Guard check failed: mismatched customer VAT',
            'expected_vat' => $customerVat,
            'found_vat'    => $beforeVat,
        ];
    }
    if ($customerCode !== '' && $beforeCode !== $customerCode) {
        return [
            'success' => false,
            'error'   => 'Guard check failed: mismatched customer code',
            'expected_code' => $customerCode,
            'found_code'    => $beforeCode,
        ];
    }

    if (!preg_match('/href="([^\"]*\/customer\/editcustomer\?[^\"]+)"/i', $viewBefore, $m)) {
        return ['success' => false, 'error' => 'Could not find customer edit link'];
    }
    $editUrl = html_entity_decode($m[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    if (strpos($editUrl, 'http') !== 0) {
        $editUrl = 'https://mydata.aade.gr' . $editUrl;
    }

    $editHtml = curlGet($ch, $editUrl);
    if (!preg_match('/<form[^>]*id="myform"[^>]*action="([^"]+)"/i', $editHtml, $f)) {
        return ['success' => false, 'error' => 'Could not find customer update form action'];
    }

    $action = html_entity_decode($f[1], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    if (strpos($action, 'http') !== 0) {
        $action = 'https://mydata.aade.gr' . $action;
    }

    $payload = [
        'customer.CompanyVAT'       => htmlInputValue($editHtml, 'customer.CompanyVAT'),
        'customer.EncrCustomerCode' => htmlInputValue($editHtml, 'customer.EncrCustomerCode'),
        'customer.Language'         => htmlInputValue($editHtml, 'customer.Language') !== '' ? htmlInputValue($editHtml, 'customer.Language') : 'el-GR',
        'customer.CustomerType'     => htmlSelectedValue($editHtml, 'customer.CustomerType') !== '' ? htmlSelectedValue($editHtml, 'customer.CustomerType') : htmlInputValue($editHtml, 'customer.CustomerType'),
        'customer.Country'          => htmlSelectedValue($editHtml, 'customer.Country') !== '' ? htmlSelectedValue($editHtml, 'customer.Country') : htmlInputValue($editHtml, 'customer.Country'),
        'customer.isB2GCustomer'    => htmlInputValue($editHtml, 'customer.isB2GCustomer') !== '' ? htmlInputValue($editHtml, 'customer.isB2GCustomer') : 'false',
        'customer.CustomerCode'     => htmlInputValue($editHtml, 'customer.CustomerCode'),
        'customer.CustomerVat'      => htmlInputValue($editHtml, 'customer.CustomerVat'),
        'customer.CustomerName'     => htmlInputValue($editHtml, 'customer.CustomerName'),
        'customer.JobDescription'   => htmlInputValue($editHtml, 'customer.JobDescription'),
        'customer.CustomerAddress'  => htmlInputValue($editHtml, 'customer.CustomerAddress'),
        'customer.CustomerCity'     => htmlInputValue($editHtml, 'customer.CustomerCity'),
        'customer.CustomerZipCode'  => htmlInputValue($editHtml, 'customer.CustomerZipCode'),
        'customer.Doy'              => htmlInputValue($editHtml, 'customer.Doy'),
        'customer.CustomerEmail'    => htmlInputValue($editHtml, 'customer.CustomerEmail'),
        'customer.CustomerPhone1'   => htmlInputValue($editHtml, 'customer.CustomerPhone1'),
        'customer.CustomerPhone2'   => htmlInputValue($editHtml, 'customer.CustomerPhone2'),
        '__RequestVerificationToken'=> getToken($ch, $editUrl),
    ];

    if ($phone1 !== '') $payload['customer.CustomerPhone1'] = $phone1;
    if ($phone2 !== '') $payload['customer.CustomerPhone2'] = $phone2;
    if ($email !== '') $payload['customer.CustomerEmail'] = $email;
    if ($jobDescription !== '') $payload['customer.JobDescription'] = $jobDescription;
    if ($address !== '') $payload['customer.CustomerAddress'] = $address;
    if ($city !== '') $payload['customer.CustomerCity'] = $city;
    if ($zip !== '') $payload['customer.CustomerZipCode'] = $zip;
    if ($doy !== '') $payload['customer.Doy'] = $doy;
    if ($name !== '') $payload['customer.CustomerName'] = $name;

    $response = curlPost($ch, $action, $payload);
    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);

    $viewAfter = curlGet($ch, $viewUrl);

    $after = [
        'customer_code' => htmlInputValue($viewAfter, 'customer.CustomerCode'),
        'customer_vat'  => htmlInputValue($viewAfter, 'customer.CustomerVat'),
        'name'          => htmlInputValue($viewAfter, 'customer.CustomerName'),
        'phone1'        => htmlInputValue($viewAfter, 'customer.CustomerPhone1'),
        'phone2'        => htmlInputValue($viewAfter, 'customer.CustomerPhone2'),
        'email'         => htmlInputValue($viewAfter, 'customer.CustomerEmail'),
        'address'       => htmlInputValue($viewAfter, 'customer.CustomerAddress'),
        'city'          => htmlInputValue($viewAfter, 'customer.CustomerCity'),
        'zip'           => htmlInputValue($viewAfter, 'customer.CustomerZipCode'),
        'doy'           => htmlInputValue($viewAfter, 'customer.Doy'),
    ];

    $ok = stripos($finalUrl, '/Customer/ViewCustomer') !== false;
    if ($customerVat !== '' && $after['customer_vat'] !== $customerVat) {
        $ok = false;
    }
    if ($customerCode !== '' && $after['customer_code'] !== $customerCode) {
        $ok = false;
    }

    return [
        'success'      => $ok,
        'message'      => $ok ? 'Customer updated successfully' : 'Customer update could not be verified',
        'view_url'     => $viewUrl,
        'edit_url'     => $editUrl,
        'action'       => $action,
        'final_url'    => $finalUrl,
        'target_vat'   => $customerVat,
        'target_code'  => $customerCode,
        'after'        => $after,
        'raw'          => $ok ? null : substr((string)$response, 0, 500),
    ];
}

function deleteCustomerByVat(\CurlHandle $ch, string $customerVat): array {
    if ($customerVat === '') {
        return ['success' => false, 'error' => 'Missing customer VAT'];
    }

    return deleteCustomerBySelector($ch, $customerVat, '');
}

function searchInvoices(
    \CurlHandle $ch,
    string $issueDateFrom = '',
    string $issueDateTo = '',
    string $invoiceType = '',
    string $mark = '',
    string $series = '',
    string $buyerVat = '',
    string $invoiceStatus = '0',
    bool $searchCounterpart = false,
    bool $searchB2G = false
): array {
    $today = date('d/m/Y');
    $fromDefault = date('01/m/Y');
    $issueDateFrom = toSearchDate($issueDateFrom, $fromDefault);
    $issueDateTo   = toSearchDate($issueDateTo, $today);

    $token = getToken($ch, BASE_URL . '/invoice/ListInvoices');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load invoice search form'];
    }

    $html = curlPost($ch, BASE_URL . '/invoice/SearchInvoices', [
        'invoiveFormat'              => '1',
        'Mark'                       => $mark,
        'IssueDateFrom'              => $issueDateFrom,
        'IssueDateTo'                => $issueDateTo,
        'InvoiceType'                => $invoiceType,
        'Series'                     => $series,
        'BuyerVatNumber'             => $buyerVat,
        'searchCancelledInvoices'    => in_array($invoiceStatus, ['0', '1', '2'], true) ? $invoiceStatus : '0',
        'searchB2GInvoices'          => $searchB2G ? 'true' : 'false',
        'searchCounterpart'          => $searchCounterpart ? 'true' : 'false',
        'btnSearch'                  => 'btnSearch',
        '__RequestVerificationToken' => $token,
    ]);

    $rows = extractTableRows($html, 'tblInvoices');
    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 11) continue;

        $markValue = $cols[1] ?? '';
        if (preg_match('/PrintInvoice2PdfNew\?mark=([0-9]+)/', $row['html'], $m)) {
            $markValue = $m[1];
        }

        $items[] = [
            'row_no'      => $cols[0] ?? '',
            'mark'        => $markValue,
            'type'        => $cols[2] ?? '',
            'issue_date'  => ($cols[4] ?? '') !== '' ? ($cols[4] ?? '') : ($cols[3] ?? ''),
            'series'      => $cols[5] ?? '',
            'aa'          => $cols[6] ?? '',
            'buyer_vat'   => $cols[7] ?? '',
            'net_value'   => $cols[8] ?? '',
            'vat_value'   => $cols[9] ?? '',
            'total'       => $cols[10] ?? '',
            'status'      => $invoiceStatus,
            'columns'    => $cols,
        ];
    }

    return [
        'success'         => true,
        'count'           => count($items),
        'issue_date_from' => $issueDateFrom,
        'issue_date_to'   => $issueDateTo,
        'invoice_type'    => $invoiceType,
        'invoice_status'  => $invoiceStatus,
        'invoices'        => $items,
    ];
}

function searchTempInvoices(
    \CurlHandle $ch,
    string $saveDateFrom = '',
    string $saveDateTo = '',
    string $invoiceType = '',
    string $buyerVat = '',
    string $tempInvoiceId = ''
): array {
    $today = date('d/m/Y');
    $fromDefault = date('01/m/Y');
    $saveDateFrom = toSearchDate($saveDateFrom, $fromDefault);
    $saveDateTo   = toSearchDate($saveDateTo, $today);

    // The temp-invoice list page (/tempinvoice/TempInvoices) already server-renders
    // the FULL table (DataTables paginates client-side). The POST /SearchTempInvoices
    // filter returns an empty grid, so we parse the GET page and filter here.
    $html = curlGet($ch, BASE_URL . '/tempinvoice/TempInvoices');
    $rows = extractTableRows($html, 'tblTempInvoices');

    $fromTs = strtotime(str_replace('/', '-', $saveDateFrom) . ' 00:00:00');
    $toTs   = strtotime(str_replace('/', '-', $saveDateTo)   . ' 23:59:59');

    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 6) continue;

        $item = [
            'row_no'    => $cols[0] ?? '',
            'temp_id'   => $cols[1] ?? '',
            'save_date' => $cols[2] ?? '',
            'buyer_vat' => $cols[3] ?? '',
            'type'      => $cols[4] ?? '',
            'series'    => $cols[5] ?? '',
            'columns'   => $cols,
        ];

        if (preg_match('/deleteTempInvoice\(\'([^\']+)\',\s*\'([^\']+)\'\)/', $row['html'], $m)) {
            $item['temp_id'] = $m[1];
            $item['seller_vat'] = $m[2];
        }
        // The row's "edit" link carries the ENCRYPTED tempInvoiceId token — needed to
        // fetch the draft's model (/Invoice/TempInvoice?encTempInvoiceId=…) for a universal
        // preview that works for ANY draft, incl. ones created directly in e-timologio.
        if (preg_match('/NewInvoiceByTmpInvoice\?tempInvoiceId=([A-Za-z0-9_\-]+)/', $row['html'], $me)) {
            $item['enc_id'] = $me[1];
        }

        // Client-side filters (save-date range, buyer VAT, type, temp id).
        $sd = strtotime(str_replace('/', '-', $item['save_date']));
        if ($sd !== false && (($fromTs && $sd < $fromTs) || ($toTs && $sd > $toTs))) continue;
        if ($buyerVat !== '' && strpos($item['buyer_vat'], $buyerVat) === false) continue;
        if ($invoiceType !== '' && strpos($item['type'], $invoiceType) === false) continue;
        if ($tempInvoiceId !== '' && $item['temp_id'] !== $tempInvoiceId) continue;

        $items[] = $item;
    }

    return [
        'success'        => true,
        'count'          => count($items),
        'save_date_from' => $saveDateFrom,
        'save_date_to'   => $saveDateTo,
        'temp_invoices'  => $items,
    ];
}

// UNIVERSAL preview of ANY saved draft (incl. ones created directly in e-timologio):
// 1) fetch the draft's stored model via /Invoice/TempInvoice?encTempInvoiceId=<encId>
//    (the same JSON the edit page loads), 2) reshape that DB model into the exact
// «postable» model PrintPreviewInvoice2PdfNew expects (a whitelist — the raw model
// carries extra fields that trigger a stricter validation demanding BtgRequestId /
// *Countries / … which our clean shape never sends), 3) POST it → real AADE PDF.
// Verified by capturing the endpoint + replaying the transform against a live draft.
function previewTempInvoice(\CurlHandle $ch, string $encId): array {
    if ($encId === '') return ['success' => false, 'error' => 'Λείπει το αναγνωριστικό προχείρου'];
    $resp = curlGet($ch, BASE_URL . '/Invoice/TempInvoice?encTempInvoiceId=' . rawurlencode($encId));
    $data = json_decode($resp, true);
    if (!is_array($data) || empty($data['invoice']) || !is_array($data['invoice'])) {
        return ['success' => false, 'error' => 'Δεν βρέθηκε το μοντέλο του προχείρου', 'raw' => substr((string)$resp, 0, 300)];
    }
    $raw = $data['invoice'];
    $h   = is_array($raw['invoiceHeader'] ?? null) ? $raw['invoiceHeader'] : [];
    $sum = is_array($raw['invoiceSummary'] ?? null) ? $raw['invoiceSummary'] : [];
    $dn  = in_array($raw['isDeliveryNote'] ?? false, [true, 'true', 1, '1'], true);
    $sv  = static fn($v) => $v === null ? '' : (is_bool($v) ? ($v ? 'true' : 'false') : (string)$v);
    $today = date('Y-n-j');

    $clean = [
        '_invoiceType'              => $sv($raw['_invoiceType'] ?? ($h['invoiceType'] ?? '')),
        'CorrelatedInvoice'         => $sv($raw['correlatedInvoice'] ?? ''),
        'selfPricing'               => 'false',
        'toWeigh'                   => $sv($raw['toWeigh'] ?? 'false'),
        'paymentType'               => $dn ? '' : $sv($raw['paymentType'] ?? ''),
        'invoiceFormat'             => '1',
        'DispatchTime'              => $dn ? $sv($raw['dispatchTime'] ?? ($h['dispatchTime'] ?? '')) : '',
        'isDeliveryNote'            => $dn ? 'true' : 'false',
        'trans'                     => $dn ? 'true' : 'false',
        'isB2G'                     => 'false',
        'timologioIssueLanguage'    => $sv($raw['language'] ?? 'el') === 'en' ? 'en' : 'el',
        'ccr_totalNetValueWithDisc' => $dn ? '' : $sv($sum['totalNetValue']   ?? ''),
        'ccr_grossValue'            => $dn ? '' : $sv($sum['totalGrossValue']  ?? ''),
        'invoiceHeader' => [
            'series'                     => $sv($h['series'] ?? ''),
            'aa'                         => '',
            'issueDate'                  => $today,
            'vehicleNumber'              => $sv($h['vehicleNumber'] ?? ''),
            'movePurpose'                => $dn ? $sv($h['movePurpose'] ?? '') : '',
            'vatPaymentSuspension'       => $sv($h['vatPaymentSuspension'] ?? 'false'),
            'currency'                   => $dn ? '' : $sv($h['currency'] ?? '0'),
            'exchangeRate'               => $sv($h['exchangeRate'] ?? ''),
            'specialInvoiceCategoryType' => $sv($h['specialInvoiceCategoryType'] ?? ''),
            'dispatchDate'               => $dn ? $sv($h['dispatchDate'] ?? '') : '',
            'reverseDeliveryNotePurpose' => $sv($h['reverseDeliveryNotePurpose'] ?? ''),
        ],
        'issuer'       => ['vatNumber' => '', 'branch' => '0', 'country' => 'GR'],
        'counterpart'  => is_array($raw['counterpart'] ?? null) ? $raw['counterpart'] : [],
        'invoiceLines' => is_array($raw['invoiceLines'] ?? null) ? array_values($raw['invoiceLines']) : [],
    ];
    if ($dn && is_array($h['otherDeliveryNoteHeader'] ?? null)) {
        $clean['invoiceHeader']['otherDeliveryNoteHeader'] = $h['otherDeliveryNoteHeader'];
    }

    curlGet($ch, BASE_URL . '/invoice/newinvoice');
    $pdf = curlPostInvoice($ch, BASE_URL . '/Invoice/PrintPreviewInvoice2PdfNew', $clean);
    if (substr($pdf, 0, 4) === '%PDF') {
        return ['success' => true, 'preview' => true, 'pdf_b64' => base64_encode($pdf)];
    }
    $d2p = json_decode($pdf, true);
    return [
        'success' => false,
        'error'   => is_array($d2p) ? ($d2p['message'] ?? $d2p['genericMsg'] ?? 'render failed')
                                    : (trim($pdf) !== '' ? substr(strip_tags($pdf), 0, 300) : 'render failed'),
    ];
}

function deleteTempInvoiceById(\CurlHandle $ch, string $tempInvoiceId, string $sellerVat = ''): array {
    if ($tempInvoiceId === '') {
        return ['success' => false, 'error' => 'Missing temp invoice id'];
    }

    $response = curlPost($ch, BASE_URL . '/TempInvoice/DeleteTempInvoice', [
        'TempInvoiceId' => $tempInvoiceId,
        'SellerVAT'     => $sellerVat !== '' ? $sellerVat : COMPANY_VAT,
    ]);

    $decoded = json_decode($response, true);
    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function deleteCustomerByCode(\CurlHandle $ch, string $customerCode): array {
    if ($customerCode === '') {
        return ['success' => false, 'error' => 'Missing customer code'];
    }

    $response = curlPost($ch, BASE_URL . '/Customer/DeleteCustomer', [
        'CustomerCode' => $customerCode,
        'companyVat'   => COMPANY_VAT,
    ]);

    $decoded = json_decode($response, true);
    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function listSeries(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/series/ListSeries');
    $rows = extractTableRows($html, 'tblSeries');

    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 6) continue;

        $item = [
            'row_no'       => $cols[0] ?? '',
            'invoice_type' => $cols[1] ?? '',
            'series_id'    => $cols[2] ?? '',
            'series_code'  => $cols[3] ?? '',
            'start_aa'     => $cols[4] ?? '',
            'description'  => $cols[5] ?? '',
        ];

        if (preg_match('/data-bound-id="([^"]+)"/', $row['html'], $m)) {
            $item['invoice_type_code'] = $m[1];
        }

        if (preg_match('/deleteSeries\(\'([^\']+)\',\s*\'([^\']+)\'\)/', $row['html'], $m)) {
            $item['company_vat'] = $m[1];
            $item['delete_id']   = $m[2];
        }

        $items[] = $item;
    }

    return [
        'success' => true,
        'count'   => count($items),
        'series'  => $items,
    ];
}

function createSeries(
    \CurlHandle $ch,
    string $invoiceType,
    string $seriesCode,
    string $startAa = '1',
    string $description = '',
    bool $isTransFailure = false,
    string $language = 'el-GR'
): array {
    if ($invoiceType === '' || $seriesCode === '') {
        return ['success' => false, 'error' => 'Invoice type and series code are required'];
    }

    $token = getToken($ch, BASE_URL . '/series/NewSeries');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load series form'];
    }

    $response = curlPost($ch, BASE_URL . '/series/NewSeries', [
        'companyVAT'                 => COMPANY_VAT,
        'Language'                   => $language,
        '_invoiceType'               => $invoiceType,
        'code'                       => $seriesCode,
        'aa'                         => $startAa,
        'description'                => $description,
        'isTransFailure'             => $isTransFailure ? 'true' : 'false',
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (stripos($finalUrl, '/series/listseries') !== false) {
        return [
            'success'      => true,
            'message'      => 'Series created successfully',
            'series_code'  => $seriesCode,
            'invoice_type' => $invoiceType,
        ];
    }

    return [
        'success' => false,
        'error'   => 'Failed to create series',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function updateSeries(
    \CurlHandle $ch,
    string $seriesId,
    string $invoiceType = '',
    string $seriesCode = '',
    string $startAa = '',
    string $description = '',
    string $language = 'el-GR'
): array {
    if ($seriesId === '') {
        return ['success' => false, 'error' => 'Missing series id'];
    }

    $seriesData = listSeries($ch);
    if (empty($seriesData['series']) || !is_array($seriesData['series'])) {
        return ['success' => false, 'error' => 'Could not load series list'];
    }

    $current = null;
    foreach ($seriesData['series'] as $row) {
        if (($row['series_id'] ?? '') === $seriesId) {
            $current = $row;
            break;
        }
    }

    if (!$current) {
        return ['success' => false, 'error' => 'Series id not found'];
    }

    $invoiceType = $invoiceType !== '' ? $invoiceType : (string)($current['invoice_type_code'] ?? '');
    $seriesCode  = $seriesCode  !== '' ? $seriesCode  : (string)($current['series_code'] ?? '');
    $startAa     = $startAa     !== '' ? $startAa     : (string)($current['start_aa'] ?? '1');
    $description = $description !== '' ? $description : (string)($current['description'] ?? '');

    if ($invoiceType === '' || $seriesCode === '') {
        return ['success' => false, 'error' => 'Could not resolve required series fields for update'];
    }

    $token = getToken($ch, BASE_URL . '/series/ListSeries');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load series update token'];
    }

    $response = curlPost($ch, BASE_URL . '/series/updateseries', [
        'series.companyVAT'          => COMPANY_VAT,
        'series.id'                  => $seriesId,
        'series.Language'            => $language,
        'series._invoiceType'        => $invoiceType,
        'series.code'                => $seriesCode,
        'series.aa'                  => $startAa,
        'series.description'         => $description,
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (stripos($finalUrl, '/series/listseries') !== false) {
        return [
            'success'      => true,
            'message'      => 'Series updated successfully',
            'series_id'    => $seriesId,
            'series_code'  => $seriesCode,
            'invoice_type' => $invoiceType,
        ];
    }

    return [
        'success' => false,
        'error'   => 'Failed to update series',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function deleteSeriesById(\CurlHandle $ch, string $id): array {
    if ($id === '') {
        return ['success' => false, 'error' => 'Missing series id'];
    }

    $response = curlPost($ch, BASE_URL . '/Series/DeleteSeries', ['id' => $id]);
    $decoded = json_decode($response, true);

    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function listDeductions(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/deduction/ListDeductions');
    $rows = extractTableRows($html, 'tblDeductions');

    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 5) continue;

        $item = [
            'row_no'               => $cols[0] ?? '',
            'description'          => $cols[1] ?? '',
            'percentage_or_value'  => $cols[2] ?? '',
            'value'                => $cols[3] ?? '',
            'decrease_total_paid'  => $cols[4] ?? '',
        ];

        if (preg_match('/deleteDeduction\(\'([^\']+)\'\)/', $row['html'], $m)) {
            $item['deduction_code'] = $m[1];
        }

        $items[] = $item;
    }

    return [
        'success'    => true,
        'count'      => count($items),
        'deductions' => $items,
    ];
}

function deleteDeductionByCode(\CurlHandle $ch, string $deductionCode): array {
    if ($deductionCode === '') {
        return ['success' => false, 'error' => 'Missing deduction code'];
    }

    $response = curlPost($ch, BASE_URL . '/Deduction/DeleteDeduction', [
        'DeductionCode' => $deductionCode,
    ]);
    $decoded = json_decode($response, true);

    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function createDeduction(
    \CurlHandle $ch,
    string $description,
    string $amountType,
    string $amount,
    string $decreaseTotalPaid,
    string $language = 'el-GR'
): array {
    if ($description === '' || $amountType === '' || $amount === '' || $decreaseTotalPaid === '') {
        return ['success' => false, 'error' => 'Description, amount type, amount, and decrease_total_paid are required'];
    }

    $token = getToken($ch, BASE_URL . '/deduction/NewDeduction');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load deduction form'];
    }

    $response = curlPost($ch, BASE_URL . '/deduction/NewDeduction', [
        'CompanyVAT'                 => COMPANY_VAT,
        'Language'                   => $language,
        'DeductionCode'              => '',
        'DeductionDescription'       => $description,
        'DeductionAmountType'        => $amountType,
        'DeductionAmount'            => $amount,
        'DecreaseTotalPaid'          => $decreaseTotalPaid,
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (stripos($finalUrl, '/deduction/listdeductions') !== false) {
        return [
            'success'     => true,
            'message'     => 'Deduction created successfully',
            'description' => $description,
        ];
    }

    return [
        'success' => false,
        'error'   => 'Failed to create deduction',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function updateDeduction(
    \CurlHandle $ch,
    string $deductionCode,
    string $description,
    string $amountType,
    string $amount,
    string $decreaseTotalPaid,
    string $language = 'el-GR'
): array {
    if ($deductionCode === '' || $description === '' || $amountType === '' || $amount === '' || $decreaseTotalPaid === '') {
        return ['success' => false, 'error' => 'Deduction code, description, amount type, amount, and decrease_total_paid are required'];
    }

    $token = getToken($ch, BASE_URL . '/deduction/NewDeduction');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load deduction form'];
    }

    $response = curlPost($ch, BASE_URL . '/deduction/NewDeduction', [
        'CompanyVAT'                 => COMPANY_VAT,
        'Language'                   => $language,
        'DeductionCode'              => $deductionCode,
        'DeductionDescription'       => $description,
        'DeductionAmountType'        => $amountType,
        'DeductionAmount'            => $amount,
        'DecreaseTotalPaid'          => $decreaseTotalPaid,
        '__RequestVerificationToken' => $token,
    ]);

    $finalUrl = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
    if (stripos($finalUrl, '/deduction/listdeductions') !== false) {
        return [
            'success'        => true,
            'message'        => 'Deduction updated successfully',
            'deduction_code' => $deductionCode,
        ];
    }

    return [
        'success' => false,
        'error'   => 'Failed to update deduction',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function listProducts(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/product/products');
    $rows = extractTableRows($html, 'tblProducts');

    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 10) continue;

        $item = [
            'row_no'           => $cols[0] ?? '',
            'type'             => $cols[3] ?? '',
            'category_id'      => $cols[4] ?? '',
            'category'         => $cols[5] ?? '',
            'product_code'     => $cols[6] ?? '',
            'description'      => $cols[8] ?? '',
            'unit_price'       => $cols[9] ?? '',
            'vat'              => $cols[10] ?? '',
            'measurement_unit' => $cols[11] ?? '',
        ];

        if (preg_match('/btnDeleteProduct[^>]*data-id="([^"]+)"/', $row['html'], $m)) {
            $item['delete_code'] = $m[1];
        }

        $items[] = $item;
    }

    return [
        'success'  => true,
        'count'    => count($items),
        'products' => $items,
    ];
}

function deleteProductByCode(\CurlHandle $ch, string $productCode): array {
    if ($productCode === '') {
        return ['success' => false, 'error' => 'Missing product code'];
    }

    $response = curlPost($ch, BASE_URL . '/Product/Delete', [
        'PrdCode' => $productCode,
    ]);
    $decoded = json_decode($response, true);

    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function listProductCategories(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/product/productCategories');
    $rows = extractTableRows($html, 'tblPrdCategories');

    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        if (count($cols) < 4) continue;

        $item = [
            'row_no'      => $cols[0] ?? '',
            'category_id' => $cols[1] ?? '',
            'company_vat' => $cols[2] ?? '',
            'name'        => $cols[3] ?? '',
        ];

        if (preg_match('/btnDeletePrdCategory[^>]*data-id="([^"]+)"/', $row['html'], $m)) {
            $item['delete_id'] = $m[1];
        }

        $items[] = $item;
    }

    return [
        'success'            => true,
        'count'              => count($items),
        'product_categories' => $items,
    ];
}

function deleteProductCategoryById(\CurlHandle $ch, string $id): array {
    if ($id === '') {
        return ['success' => false, 'error' => 'Missing product category id'];
    }

    $response = curlPost($ch, BASE_URL . '/Product/DeleteCategory', ['id' => $id]);
    $decoded = json_decode($response, true);

    if (is_array($decoded)) {
        return ['success' => true, 'result' => $decoded];
    }

    return [
        'success' => true,
        'note'    => 'Delete request sent',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

function getCompanyProfile(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/company/company');

    $profile = [
        'name'                    => htmlInputValue($html, 'company.Name'),
        'job_description'         => htmlInputValue($html, 'company.JobDescription'),
        'address'                 => htmlInputValue($html, 'company.Address'),
        'phone'                   => htmlInputValue($html, 'company.Phone'),
        'doy'                     => htmlInputValue($html, 'company.Doy'),
        'language'                => htmlInputValue($html, 'company.Language'),
        'logo_name'               => htmlInputValue($html, 'company.LogoName'),
        'send_email_on_issuing'   => htmlInputValue($html, 'company.SendEmailOnIssuing') === 'true',
        'digital_client'          => htmlInputValue($html, 'company.DigitalClient') === 'true',
        'websrv_taxis_username'   => htmlInputValue($html, 'company.WebSrvTaxisUserName'),
        'websrv_taxis_password'   => htmlInputValue($html, 'company.WebSrvTaxisPassoword'),
        'has_accepted_terms'      => htmlInputValue($html, 'company.HasAcceptedTerms') === 'true',
    ];

    return [
        'success' => true,
        'company' => $profile,
    ];
}

function getCompanyFromTaxis(\CurlHandle $ch): array {
    $response = curlGet($ch, BASE_URL . '/Company/GetCompanyByTaxis?' . http_build_query([
        'companyVat' => COMPANY_VAT,
    ]));

    $decoded = json_decode($response, true);
    if (is_array($decoded)) {
        return [
            'success' => true,
            'company' => $decoded,
        ];
    }

    return [
        'success' => false,
        'error'   => 'Could not decode company response',
        'raw'     => substr((string)$response, 0, 500),
    ];
}

// --- PRODUCT CRUD -------------------------------------------------------

function createProduct(
    \CurlHandle $ch,
    string $productType,
    string $productCode,
    string $productDescription,
    string $productCategory = '',
    string $taricCode = '',
    string $unitPrice = '0',
    string $vatCategory = '1',
    string $unit = '',
    string $specialType = '',
    string $feesWithVAT = '',
    string $otherTaxesWithVAT = ''
): array {
    if ($productCode === '' || $productType === '' || $productDescription === '') {
        return ['success' => false, 'error' => 'Product code, type, and description are required'];
    }

    $token = getToken($ch, BASE_URL . '/product/products');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load product form'];
    }

    $formData = [
        'productType'           => $productType,
        'productCode'           => $productCode,
        'productCategory'       => $productCategory,
        'taricCode'             => $taricCode,
        'productDescription'    => $productDescription,
        'unitPrice'             => $unitPrice,
        'vatCategory'           => $vatCategory,
        'unit'                  => $unit,
        'specialType'           => $specialType,
        'feesWithVAT'           => $feesWithVAT,
        'otherTaxesWithVAT'     => $otherTaxesWithVAT,
        '__RequestVerificationToken' => $token,
    ];

    $response = curlPost($ch, BASE_URL . '/product/create', $formData);
    $decoded = json_decode($response, true);
    
    // Server returns JSON with success=true when product is created
    if (is_array($decoded) && ($decoded['success'] === true || $decoded['success'] === 'true')) {
        return ['success' => true, 'message' => 'Product created successfully', 'code' => $productCode];
    }

    return [
        'success' => false,
        'error'   => $decoded['message'] ?? 'Failed to create product',
        'raw'     => $decoded,
    ];
}

function updateProduct(
    \CurlHandle $ch,
    string $productCode,
    string $productType,
    string $productDescription,
    string $productCategory = '',
    string $taricCode = '',
    string $unitPrice = '0',
    string $vatCategory = '1',
    string $unit = '',
    string $specialType = '',
    string $feesWithVAT = '',
    string $otherTaxesWithVAT = ''
): array {
    if ($productCode === '' || $productType === '' || $productDescription === '') {
        return ['success' => false, 'error' => 'Product code, type, and description are required'];
    }

    $token = getToken($ch, BASE_URL . '/product/products');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load product form'];
    }

    $formData = [
        'productCode'           => $productCode,
        'productType'           => $productType,
        'productCategory'       => $productCategory,
        'taricCode'             => $taricCode,
        'productDescription'    => $productDescription,
        'unitPrice'             => $unitPrice,
        'vatCategory'           => $vatCategory,
        'unit'                  => $unit,
        'specialType'           => $specialType,
        'feesWithVAT'           => $feesWithVAT,
        'otherTaxesWithVAT'     => $otherTaxesWithVAT,
        '__RequestVerificationToken' => $token,
    ];

    $response = curlPost($ch, BASE_URL . '/product/create', $formData);
    $decoded = json_decode($response, true);
    
    // Server returns JSON with success=true when product is updated
    if (is_array($decoded) && ($decoded['success'] === true || $decoded['success'] === 'true')) {
        return ['success' => true, 'message' => 'Product updated successfully', 'code' => $productCode];
    }

    return [
        'success' => false,
        'error'   => $decoded['message'] ?? 'Failed to update product',
        'raw'     => $decoded,
    ];
}

// --- PRODUCT CATEGORY CRUD -------------------------------------------------------

function createProductCategory(
    \CurlHandle $ch,
    string $categoryName
): array {
    if ($categoryName === '') {
        return ['success' => false, 'error' => 'Category name is required'];
    }

    $token = getToken($ch, BASE_URL . '/product/productCategories');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load category form'];
    }

    $formData = [
        'prdCategoryName'       => $categoryName,
        '__RequestVerificationToken' => $token,
    ];

    $response = curlPost($ch, BASE_URL . '/product/createCategory', $formData);
    $decoded = json_decode($response, true);
    
    // Server returns JSON with success=true when category is created
    if (is_array($decoded) && ($decoded['success'] === true || $decoded['success'] === 'true')) {
        return ['success' => true, 'message' => 'Category created successfully', 'name' => $categoryName];
    }

    return [
        'success' => false,
        'error'   => $decoded['message'] ?? 'Failed to create category',
        'raw'     => $decoded,
    ];
}

function updateProductCategory(
    \CurlHandle $ch,
    string $categoryId,
    string $categoryName
): array {
    if ($categoryId === '' || $categoryName === '') {
        return ['success' => false, 'error' => 'Category id and name are required'];
    }

    $token = getToken($ch, BASE_URL . '/product/productCategories');
    if ($token === '') {
        return ['success' => false, 'error' => 'Could not load category form'];
    }

    $formData = [
        'prdCategoryId'         => $categoryId,
        'prdCategoryName'       => $categoryName,
        '__RequestVerificationToken' => $token,
    ];

    $response = curlPost($ch, BASE_URL . '/product/createCategory', $formData);
    $decoded = json_decode($response, true);
    
    // Server returns JSON with success=true when category is updated
    if (is_array($decoded) && ($decoded['success'] === true || $decoded['success'] === 'true')) {
        return ['success' => true, 'message' => 'Category updated successfully', 'id' => $categoryId];
    }

    return [
        'success' => false,
        'error'   => $decoded['message'] ?? 'Failed to update category',
        'raw'     => $decoded,
    ];
}

// --- CATEGORY-LEVEL CLASSIFICATIONS (χαρακτηρισμοί ανά κατηγορία, manual §9) ---
// e-timologio lets you attach default classifications to a product CATEGORY, one
// per invoice type (+ optional self-pricing variant). These are applied to items of
// that category. The real UI posts a nested `prdCategory` object to create/updateCategory.

// The invoice-type dropdown (value => label) as rendered on the ProductCategories page.
function getClassificationInvoiceTypes(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/product/productCategories');
    $types = [];
    if (preg_match('/id="clsInvoiceType"(.*?)<\/select>/s', $html, $m)) {
        if (preg_match_all('/<option[^>]*value="([^"]*)"[^>]*>(.*?)<\/option>/s', $m[1], $opts, PREG_SET_ORDER)) {
            foreach ($opts as $o) {
                $val = trim($o[1]);
                if ($val === '') continue;
                $types[] = ['value' => $val, 'label' => html_entity_decode(trim(strip_tags($o[2])), ENT_QUOTES, 'UTF-8')];
            }
        }
    }
    return $types;
}

// Invoice taxes (Νέος Φόρος): the 5 taxType category lists as rendered in the
// new-invoice form. taxType: 1=Παρακρατούμενοι, 2=Τέλη, 3=Άλλοι φόροι,
// 4=Ψηφιακό Τέλος Συναλλαγής, 5=Κρατήσεις (account-specific, from Deductions CRUD).
function getTaxCategories(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/invoice/newinvoice');
    $extract = function (string $selectId) use ($html): array {
        if (!preg_match('/<select[^>]*id=["\']' . preg_quote($selectId, '/') . '["\'][^>]*>(.*?)<\/select>/s', $html, $m)) return [];
        $out = [];
        if (preg_match_all('/<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)<\/option>/s', $m[1], $o, PREG_SET_ORDER)) {
            foreach ($o as $opt) {
                $val = trim($opt[1]);
                $label = trim(html_entity_decode(strip_tags($opt[2]), ENT_QUOTES, 'UTF-8'));
                if ($val === '' || stripos($label, 'Διεγράφη') !== false) continue;  // skip placeholder + deleted deductions
                $out[] = ['code' => $val, 'label' => $label];
            }
        }
        return $out;
    };
    return [
        'success'  => true,
        'withheld' => $extract('withheldList'),      // taxType 1
        'fees'     => $extract('feesList'),           // taxType 2
        'other'    => $extract('othertaxesList'),     // taxType 3
        'digital'  => $extract('stampList'),          // taxType 4 (Ψηφιακό Τέλος Συναλλαγής)
        'deductions' => $extract('deductionsList'),   // taxType 5 (account-specific)
    ];
}

// Allowed income classification categories + codes for an invoice type (from the
// myDATA validation document that drives the UI's dynamic dropdowns).
function getClassificationOptions(\CurlHandle $ch, string $invType, bool $selfPrice = false): array {
    if ($invType === '') return ['success' => false, 'error' => 'Λείπει ο τύπος παραστατικού (type)'];
    $url = BASE_URL . '/Product/GetValidationDoc?' . http_build_query([
        'invType'   => $invType,
        'selfPrice' => $selfPrice ? 'true' : 'false',
    ]);
    $doc = json_decode(curlGet($ch, $url), true);
    if (!is_array($doc) || !isset($doc['IncomeClassificationCategories'])) {
        return ['success' => false, 'error' => $doc['message'] ?? 'Δεν βρέθηκαν κανόνες χαρακτηρισμού για τον τύπο ' . $invType];
    }
    $strip = function (string $s): string {                 // "Label (E3_xxx)" -> "Label"
        return trim(preg_replace('/\s*\([^()]*\)\s*$/', '', $s));
    };
    $cats = [];
    foreach ($doc['IncomeClassificationCategories'] as $c) {
        if (!empty($c['isDisabled'])) continue;
        $codes = [];
        $tiles = $c['incomeCategoryCodesTiles'] ?? [];
        foreach (($c['classificationCodes_E3_VAT'] ?? []) as $i => $code) {
            if ($code === '') continue;
            $codes[] = ['code' => $code, 'title' => $strip((string)($tiles[$i] ?? $code))];
        }
        $cats[] = [
            'category' => $c['classificationCategory_9'] ?? '',
            'title'    => $c['classificationCategory_9_Title'] ?? ($c['classificationCategory_9'] ?? ''),
            'codes'    => $codes,
        ];
    }
    return ['success' => true, 'invoice_type' => $invType, 'self_pricing' => $selfPrice, 'categories' => $cats];
}

// List product categories together with their existing classifications (parsed
// from each row's data-classifications attribute on the ProductCategories page).
function listCategoryClassifications(\CurlHandle $ch): array {
    $html = curlGet($ch, BASE_URL . '/product/productCategories');
    $rows = extractTableRows($html, 'tblPrdCategories');
    $items = [];
    foreach ($rows as $row) {
        $cols = array_map('htmlText', $row['cells']);
        $id   = $cols[1] ?? '';
        $name = $cols[3] ?? '';
        $cls  = [];
        if (preg_match('/data-classifications=(["\'])(.*?)\1/s', $row['html'], $m)) {
            $decoded = json_decode(html_entity_decode($m[2], ENT_QUOTES, 'UTF-8'), true);
            if (is_array($decoded)) {
                foreach ($decoded as $c) {
                    $cls[] = [
                        'invoice_type'       => (string)($c['i'] ?? ''),
                        'invoice_type_label' => $c['it'] ?? '',
                        'self_pricing'       => !empty($c['sp']),
                        'category'           => $c['cc'] ?? '',
                        'category_title'     => $c['ct'] ?? '',
                        'code'               => $c['tc'] ?? '',
                        'code_title'         => $c['tt'] ?? '',
                    ];
                }
            }
        }
        if ($id === '' && $name === '') continue;
        $items[] = ['category_id' => $id, 'name' => $name, 'classifications' => $cls];
    }
    return ['success' => true, 'count' => count($items), 'categories' => $items];
}

// Create/update a product category WITH its classifications. $cls entries:
//   {invoice_type, category, code, self_pricing}. id=0/'' => create, else update.
function saveCategoryClassifications(\CurlHandle $ch, string $id, string $name, array $cls): array {
    if (trim($name) === '') return ['success' => false, 'error' => 'Λείπει η ονομασία κατηγορίας'];
    $token = getToken($ch, BASE_URL . '/product/productCategories');
    if ($token === '') return ['success' => false, 'error' => 'Δεν φορτώθηκε η φόρμα κατηγοριών'];

    $categoryClassifications = [];
    foreach ($cls as $c) {
        $it = trim((string)($c['invoice_type'] ?? ''));
        $cc = trim((string)($c['category'] ?? ''));
        if ($it === '' || $cc === '') continue;
        $entry = [
            '_invoiceType'             => $it,
            'selfPricing'              => !empty($c['self_pricing']) ? 'true' : 'false',
            'classificationCategoryCode' => $cc,
        ];
        $tc = trim((string)($c['code'] ?? ''));
        if ($tc !== '') $entry['classificationTypeCode'] = $tc;
        $categoryClassifications[] = $entry;
    }

    $isUpdate = ((int)$id) > 0;
    $prdCategory = [
        'id'                      => $isUpdate ? (int)$id : 0,
        'name'                    => trim($name),
        'categoryClassifications' => $categoryClassifications,
    ];
    // jQuery posts the object as `prdCategory[...]`; http_build_query matches that shape.
    $fields = ['prdCategory' => $prdCategory, '__RequestVerificationToken' => $token];
    $action = $isUpdate ? '/Product/updateCategory' : '/Product/createCategory';

    $response = curlPost($ch, BASE_URL . $action, $fields);
    $decoded  = json_decode($response, true);
    // On validation failure the controller returns JSON `{message:"err1~err2"}`.
    // On success it returns a plain body (e.g. "0") — anything without a message is OK.
    $err = (is_array($decoded) && !empty($decoded['message'])) ? (string)$decoded['message'] : '';
    if ($err === '') {
        return ['success' => true, 'id' => $id, 'name' => trim($name), 'count' => count($categoryClassifications)];
    }
    return ['success' => false, 'error' => str_replace('~', ' · ', $err),
            'raw' => substr((string)$response, 0, 400)];
}

// --- 5. GET PRODUCT DATA (classifications, description) ----------------------

function getProductData(\CurlHandle $ch, string $productCode, string $invoiceType): ?array {
    $url = BASE_URL . '/Product/GetProduct?' . http_build_query([
        'sCompanyVat' => COMPANY_VAT,
        'productCode' => $productCode,
        'invoiceType' => $invoiceType,
        'selfPrice'   => 'false',
    ]);
    $response = curlGet($ch, $url);
    return json_decode($response, true) ?: null;
}

// --- Classifications (χαρακτηρισμοί) for a product within an invoice type -----
// myDATA requires each line to carry income (E3_*) and, where applicable, VAT
// classifications. e-timologio derives them per product+type via GetProduct.
function getInvoiceClassifications(\CurlHandle $ch, string $productCode, string $invoiceType): array {
    $p = getProductData($ch, $productCode, $invoiceType);
    if ($p === null) return ['success' => false, 'error' => 'Δεν βρέθηκε είδος ' . $productCode];
    $cls = [];
    foreach (($p['cl'] ?? []) as $cl) {
        $cls[] = [
            'kind'          => isset($cl['k']) ? (int)$cl['k'] : 1,
            'category'      => $cl['cc'] ?? '',
            'category_name' => $cl['ct'] ?? '',
            'code'          => $cl['tc'] ?? '',
            'code_name'     => $cl['tt'] ?? '',
        ];
    }
    return [
        'success'         => true,
        'product'         => $productCode,
        'type'            => $invoiceType,
        'vat_category'    => $p['v'] ?? null,
        'classifications' => $cls,
    ];
}

// myDATA VAT category code -> effective rate
function vatRateFromCategory(int $cat): float {
    $map = [1 => 0.24, 2 => 0.13, 3 => 0.06, 4 => 0.17, 5 => 0.09, 6 => 0.04, 7 => 0.0, 8 => 0.0];
    return $map[$cat] ?? 0.24;
}

// Build a single invoice line (with per-line product classifications + VAT).
// quantity is sent only when != 1 (some invoice types forbid it for services).
// $disc = per-line discount: percentage (0-100) when $discIsPct, else absolute €.
// $clsOverride = explicit classifications [{k?,cc,tc}] replacing the product defaults.
function buildInvoiceLine(
    \CurlHandle $ch, int $n, string $code, float $qty, float $unitNet,
    string $invoiceType, float $rateOverride = -1.0, int $catOverride = 0,
    float $disc = 0.0, bool $discIsPct = true, array $clsOverride = [],
    bool $isDeliveryNote = false, int $deliveryMovePurpose = 1
): array {
    $isZeroType = in_array($invoiceType, ZERO_VAT_TYPES);
    $product = getProductData($ch, $code, $invoiceType);
    $descr = (is_array($product) && isset($product['d'])) ? $code . ' - ' . $product['d'] : $code;

    if ($rateOverride >= 0) {
        $rate = $rateOverride; $cat = $catOverride > 0 ? $catOverride : vatCategoryFromRate($rate);
    } elseif ($isZeroType) {
        $rate = 0.0; $cat = 7;
    } elseif (is_array($product) && !empty($product['v'])) {
        $cat = (int)$product['v']; $rate = vatRateFromCategory($cat);
    } else {
        $cat = $catOverride > 0 ? $catOverride : 1; $rate = vatRateFromCategory($cat);
    }
    $isZero = ($rate == 0.0);
    if ($qty <= 0) $qty = 1.0;

    // Gross (before discount) → discount → net (after discount) → VAT.
    $gross = round($unitNet * $qty, 2);
    $discAmount = 0.0;
    if ($disc > 0) {
        $discAmount = $discIsPct ? round($gross * $disc / 100.0, 2) : round($disc, 2);
        if ($discAmount > $gross) $discAmount = $gross;   // never discount below zero
    }
    $net   = round($gross - $discAmount, 2);
    $vat   = round($net * $rate, 2);
    $total = round($net + $vat, 2);

    // A δελτίο διακίνησης (dispatch note) is a pure GOODS-MOVEMENT document: it must
    // NOT carry monetary values — only the item and its quantity. Zero every amount.
    if ($isDeliveryNote) {
        $unitNet = 0.0; $gross = 0.0; $net = 0.0; $vat = 0.0; $total = 0.0; $discAmount = 0.0; $disc = 0.0;
    }

    // Classifications: explicit override wins, else product defaults, else a sane fallback.
    // Each carries the line's *net (post-discount)* amount, as myDATA expects.
    $cls = [];
    $clsTrusted = false;   // true = explicit override OR the product's AADE per-type classification
    if (!empty($clsOverride)) {
        foreach ($clsOverride as $cl) {
            if (empty($cl['cc']) || empty($cl['tc'])) continue;
            $cls[] = [
                'classificationKind'     => isset($cl['k']) && (int)$cl['k'] > 0 ? (int)$cl['k'] : 1,
                'classificationCategory' => $cl['cc'],
                'classificationType'     => $cl['tc'],
                'amount'                 => $net,
            ];
        }
        if (!empty($cls)) $clsTrusted = true;
    }
    if (empty($cls)) {
        // GetProduct is queried with invoiceType=$invoiceType, so $product['cl'] is the
        // AADE-authoritative classification FOR THIS type — trust it verbatim.
        foreach (((is_array($product) ? ($product['cl'] ?? null) : null) ?? []) as $cl) {
            if (empty($cl['cc'])) continue;
            $cls[] = [
                'classificationKind'     => isset($cl['k']) && (int)$cl['k'] > 0 ? (int)$cl['k'] : 1,
                'classificationCategory' => $cl['cc'],
                'classificationType'     => $cl['tc'] ?? '',
                'amount'                 => $net,
            ];
        }
        if (!empty($cls)) $clsTrusted = true;
    }
    if (empty($cls)) {
        $cls[] = ['classificationKind' => 1, 'classificationCategory' => 'category1_3',
                  'classificationType' => $isZero ? 'E3_561_006' : 'E3_561_003', 'amount' => $net];
    }
    // The income classification CODE must match the invoice type: wholesale/B2B
    // documents accept E3_561_001/002, retail (11.x → 57..61) accept E3_561_003/006.
    // A code valid for one type is rejected by the other (generic «Αδυναμία
    // προεπισκόπησης»), and a product may carry a wholesale code while being billed on
    // a retail receipt — so remap any plain sale code to the type-appropriate one.
    // Remap the sale code to the type-appropriate one ONLY when we guessed (no explicit /
    // per-type classification). Never touch an authoritative classification — that would
    // corrupt legitimately different codes (e.g. E3_561_007 «Λοιπά»).
    if (!$isDeliveryNote && !$clsTrusted) {
        $retail = in_array($invoiceType, ['57', '58', '59', '60', '61'], true);
        $incomeCode = $isZero ? ($retail ? 'E3_561_006' : 'E3_561_002')
                              : ($retail ? 'E3_561_003' : 'E3_561_001');
        foreach ($cls as &$c) {
            if (isset($c['classificationType']) && strncmp((string)$c['classificationType'], 'E3_561_00', 9) === 0) {
                $c['classificationType'] = $incomeCode;
            }
        }
        unset($c);
    }
    // A δελτίο διακίνησης uses the movement classification category «category3»
    // (Διακίνηση), which carries NO E3 income code — the income categories/codes
    // (category1_*/E3_561_*) are invalid for it and make AADE reject the preview.
    if ($isDeliveryNote) {
        $cls = [['classificationKind' => 1, 'classificationCategory' => 'category3', 'classificationType' => '', 'amount' => $net]];
    }

    // discountType: 1 = percentage, 2 = absolute value (e-timologio convention).
    $line = [
        'lineNumber'                   => $n,
        'itemId'                       => $n,
        'itemCode'                     => $code,
        'itemDescr'                    => $descr,
        'unitPrice'                    => $unitNet,
        'vatCategory'                  => $cat,
        'vatExemptionCategory'         => $isZero ? 4 : '',
        'netValueWithoutDiscount'      => $gross,
        'discountValue'                => $disc > 0 ? ($discIsPct ? $disc : $discAmount) : 0,
        'netValueWithDiscount'         => $net,
        'vatAmount'                    => $vat,
        'totalValue'                   => $total,
        'otherMeasurementUnitTitle'    => '',
        'otherMeasurementUnitQuantity' => '',
        // Per-line tax buckets — the real e-timologio form posts these (all 0 for a
        // plain line). Their absence makes PrintPreviewInvoice2PdfNew reject the model.
        'withheldAmount'               => 0,
        'stampAmount'                  => 0,
        'feesAmount'                   => 0,
        'otherTaxesAmount'             => 0,
        'deductionsAmount'             => 0,
        'discountAmount'               => $discAmount,
        'discountType'                 => $discIsPct ? 1 : 2,
        'isGiftVoucher'                => 'false',
        'classifications'              => $cls,
    ];
    // Quantity + measurement unit: delivery notes (δελτίο διακίνησης) REQUIRE a
    // measurement unit ("η μονάδα μέτρησης είναι υποχρεωτική"), but pure service
    // invoices (e.g. ΤΠΥ/type 20) FORBID quantity/unit (myDATA forbiddenFields) and
    // reject the preview if present. So only emit them for delivery notes or when the
    // quantity is not the implicit 1 (goods lines). 1 = τεμάχια (default unit).
    if ($isDeliveryNote || $qty != 1.0) {
        $line['quantity']        = $qty;
        $line['measurementUnit'] = 1;
    }
    // Delivery-note lines carry NO VAT — vatCategory 8 (Άνευ ΦΠΑ) — and each line needs a
    // movement purpose. Captured verbatim from a WORKING 9.3 PrintPreview request; sending
    // the product's real vatCategory (e.g. 1=24%) makes AADE reject the δελτίο generically.
    if ($isDeliveryNote) {
        $line['vatCategory']     = 8;
        $line['movePurposeLine'] = (int)$deliveryMovePurpose;
    }

    return ['line' => $line, 'net' => $net, 'vat' => $vat, 'total' => $total, 'discount' => $discAmount, 'gross' => $gross];
}

// --- 6. CREATE INVOICE (draft by default, live if $live=true) ----------------

function createInvoice(
    \CurlHandle $ch,
    float $amount,
    string $invoiceType = '58',
    int $paymentType = 3,
    string $description = 'ΥΠ001',
    string $issueDate = '',
    string $afm = '',
    string $name = '',
    string $address = '',
    string $city = '',
    string $zip = '',
    string $country = 'GR',
    string $branch = '0',
    int $withholdingCategory = 0,
    float $withholdingAmount = 0.0,
    bool $live = false,
    string $correlatedMark = '',
    string $invoiceNotes = '',
    float $vatRateOverride = -1.0,
    int $vatCategoryOverride = 0,
    array $delivery = [],
    array $lines = [],
    string $series = 'A',
    array $taxes = [],
    bool $preview = false,
    string $issueLang = 'el',
    array $paymentMethods = [],
    string $reuseTempId = ''
): array {

    if ($issueDate === '') {
        // Live issue uses the form's canonical Y-n-j (no zero-padding, e.g. 2026-7-3);
        // temp/draft saves accept d-m-Y. Preview saves the draft first (d-m-Y) and then
        // re-stamps the header to Y-n-j just before PrintPreviewInvoice2PdfNew below.
        $issueDate = $live ? date('Y-n-j') : date('d-m-Y');
    }

    // VAT rate: explicit override (e.g. mirroring an original invoice) wins,
    // otherwise 0% for non-EU types, else the standard 24%.
    $isZeroVat = in_array($invoiceType, ZERO_VAT_TYPES);
    if ($vatRateOverride >= 0) {
        $vatRate   = $vatRateOverride;
        $isZeroVat = ($vatRateOverride == 0.0);
    } else {
        $vatRate   = $isZeroVat ? 0.0 : 0.24;
    }
    $netValue  = round($amount, 2);
    $vatAmount = round($netValue * $vatRate, 2);
    $total     = round($netValue + $vatAmount, 2);
    // myDATA VAT category code (24%=1,13%=2,6%=3,17%=4,9%=5,4%=6,0%=7)
    $vatCatCode = $vatCategoryOverride > 0
        ? $vatCategoryOverride
        : vatCategoryFromRate($vatRate, $isZeroVat);

    // Enrich counterpart — Taxisnet for GR clients, e-timologio database for foreign
    if ($afm !== '') {
        if (preg_match('/^\d{9}$/', $afm)) {
            // Greek client — fetch from Taxisnet
            $taxisData = getFromTaxisnet($ch, $afm);
            if ($taxisData) {
                if ($name    === '') $name    = $taxisData['name'];
                if ($address === '') $address = $taxisData['address'];
                if ($city    === '') $city    = $taxisData['city'];
                if ($zip     === '') $zip     = $taxisData['zip'];
            }
        } else {
            // Foreign client — fetch from e-timologio customer database
            $dbData = getCustomerFromDatabase($ch, $afm, $invoiceType);
            if ($dbData) {
                if ($name    === '') $name    = $dbData['name'];
                if ($address === '') $address = $dbData['address'];
                if ($city    === '') $city    = $dbData['city'];
                if ($zip     === '') $zip     = $dbData['zip'];
                if ($country === 'GR') $country = $dbData['country'];
            }
        }
    }

    // Normalise to a list of lines. Single-amount calls become one line (qty 1).
    if (empty($lines)) {
        $lines = [[
            'code'  => $description,
            'qty'   => 1,
            'price' => round($amount, 2),
            'rate'  => $vatRateOverride,
            'cat'   => $vatCategoryOverride,
        ]];
    }
    $invoiceLines = [];
    $netValue = 0.0; $vatAmount = 0.0; $total = 0.0; $discountTotal = 0.0;
    $ln = 1;
    $isDN = !empty($delivery);
    foreach ($lines as $row) {
        // Discount: `disc` = percentage (default) or absolute € when discType='amount'/2.
        $disc      = (float)($row['disc'] ?? 0);
        $discIsPct = !in_array((string)($row['discType'] ?? 'pct'), ['amount', '2', 'eur'], true);
        $built = buildInvoiceLine(
            $ch, $ln++,
            (string)($row['code'] ?? $description),
            (float)($row['qty'] ?? 1),
            (float)($row['price'] ?? 0),
            $invoiceType,
            isset($row['rate']) ? (float)$row['rate'] : -1.0,
            (int)($row['cat'] ?? 0),
            $disc, $discIsPct,
            (is_array($row['cls'] ?? null)) ? $row['cls'] : [],
            $isDN,
            $isDN ? (int)($delivery['movePurpose'] ?? 1) : 1
        );
        $invoiceLines[]  = $built['line'];
        $netValue       += $built['net'];
        $vatAmount      += $built['vat'];
        $total          += $built['total'];
        $discountTotal  += $built['discount'];
    }
    $discountTotal = round($discountTotal, 2);
    $netValue  = round($netValue, 2);
    $vatAmount = round($vatAmount, 2);
    $total     = round($total, 2);

    // Build invoice taxes. Legacy single withholding params still work; the general
    // $taxes array carries any mix of withheld/fees/other/digital/deductions.
    $invoiceTaxes = [];
    $tid = 1;
    if ($withholdingCategory > 0 && $withholdingAmount > 0) {
        $invoiceTaxes[] = [
            'id'              => $tid++,
            'taxType'         => 1,
            'taxCategory'     => $withholdingCategory,
            'underlyingValue' => $netValue,
            'taxAmount'       => (string)round($withholdingAmount, 2),
            'taxNotes'        => '',
        ];
    }
    foreach ($taxes as $t) {
        $ttype = (int)($t['type'] ?? 0);
        $tamt  = round((float)($t['amount'] ?? 0), 2);
        if ($ttype < 1 || $ttype > 5 || $tamt <= 0) continue;
        $invoiceTaxes[] = [
            'id'              => $tid++,
            'taxType'         => $ttype,
            'taxCategory'     => (string)($t['category'] ?? ''),
            'underlyingValue' => $netValue,
            'taxAmount'       => (string)$tamt,
            'taxNotes'        => (string)($t['notes'] ?? ''),
        ];
    }

    $invoice = [
        '_invoiceType'              => $invoiceType,
        'CorrelatedInvoice'         => $correlatedMark,
        'selfPricing'               => 'false',
        'toWeigh'                   => 'false',
        'paymentType'               => (string)$paymentType,
        'invoiceFormat'             => 1,
        'DispatchTime'              => '',
        'isDeliveryNote'            => 'false',
        'trans'                     => 'false',
        'isB2G'                     => 'false',
        'tempInvoiceId'             => '',
        'timologioIssueLanguage'    => ($issueLang === 'en' ? 'en' : 'el'),
        'invoiceNotes'              => $invoiceNotes,
        'transmissionFailure'       => '',
        // Document totals the form always posts: total net (with discount) + gross.
        // For a CREDIT NOTE these are REQUIRED — with them empty the server cannot
        // compare the credit's payable against the correlated invoice and rejects with
        // «Το πληρωτέο/η καθαρή αξία του πιστωτικού δεν μπορεί να είναι μεγαλύτερη του
        // συσχετιζόμενου». (Confirmed by diffing our request against the live form's
        // working PrintPreview body — these two empty fields were the ONLY difference.)
        'ccr_totalNetValueWithDisc' => (string)$netValue,
        'ccr_grossValue'            => (string)$total,

        'invoiceHeader' => [
            'series'                     => ($series !== '' ? $series : 'A'),
            'aa'                         => '',
            'issueDate'                  => $issueDate,
            'vehicleNumber'              => '',
            'movePurpose'                => '',
            'vatPaymentSuspension'       => 'false',
            'currency'                   => '0',
            'exchangeRate'               => '',
            'specialInvoiceCategoryType' => '',
            'otherCorrelatedEntities'    => [],
        ],

        // The real form posts an EMPTY issuer (only branch/country); the server fills
        // the full company identity from the authenticated session for both the saved
        // draft and the rendered PDF. Sending a populated issuer block made
        // PrintPreviewInvoice2PdfNew reject the model.
        'issuer' => [
            'vatNumber' => '',
            'branch'    => '0',
            'country'   => 'GR',
        ],

        'counterpart' => [
            'vatNumber'         => $afm,
            'branch'            => $branch,
            'country'           => $country,
            'name'              => $name,
            'documentIdNo'      => '',
            'countryDocumentId' => '',
            'customerCode'      => '',
            'emailAddress'      => '',
            'address'           => [
                'street'     => $address,
                'postalCode' => $zip,
                'city'       => $city,
                'number'     => '0',
            ],
        ],

        'invoiceTaxes' => $invoiceTaxes,

        'invoiceLines' => $invoiceLines,
    ];

    // Payment methods (paymentMethodDetails) — needed by credit notes so their
    // «πληρωτέο» (payable) matches the correlated invoice's; each entry {type, amount}.
    if (!empty($paymentMethods)) {
        $invoice['paymentMethods'] = ['paymentMethodDetails' => $paymentMethods];
    }

    // Delivery note (δελτίο αποστολής/επιστροφής) header — applied when $delivery set
    if (!empty($delivery)) {
        $invoice['isDeliveryNote'] = 'true';
        $invoice['trans']          = 'true';
        // A δελτίο διακίνησης carries NO payment / currency / document-total fields. A
        // WORKING 9.3 PrintPreview posts paymentType, invoiceHeader.currency and both
        // ccr_* totals as EMPTY strings. Our defaults (paymentType=3, currency='0',
        // ccr_*='0') make AADE reject the preview generically, so blank them here.
        $invoice['paymentType']               = '';
        $invoice['invoiceHeader']['currency'] = '';
        $invoice['ccr_totalNetValueWithDisc'] = '';
        $invoice['ccr_grossValue']            = '';
        $invoice['DispatchTime']   = $delivery['dispatchTime'] ?? '';
        $invoice['invoiceHeader']['vehicleNumber'] = $delivery['vehicleNumber'] ?? '';
        $invoice['invoiceHeader']['movePurpose']   = (string)($delivery['movePurpose'] ?? '1');
        if (!empty($delivery['dispatchDate'])) {
            // dispatchDate must be Y-n-j (e.g. 2026-7-7), exactly like issueDate — this is
            // what the e-timologio form posts (verified by capturing a WORKING 9.3 preview).
            // Accept dd/mm/yyyy, dd-mm-yyyy or yyyy-mm-dd on input and normalize.
            $dd = trim((string)$delivery['dispatchDate']);
            $ts = false;
            if (preg_match('#^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$#', $dd, $mD)) {
                $ts = mktime(0, 0, 0, (int)$mD[2], (int)$mD[1], (int)$mD[3]);
            } elseif (preg_match('#^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$#', $dd, $mD)) {
                $ts = mktime(0, 0, 0, (int)$mD[2], (int)$mD[3], (int)$mD[1]);
            }
            $invoice['invoiceHeader']['dispatchDate'] = $ts ? date('Y-n-j', $ts) : $dd;
        }
        $invoice['invoiceHeader']['otherDeliveryNoteHeader'] = [
            'loadingAddress'  => [
                'street'     => $delivery['load_street'] ?? '',
                'number'     => $delivery['load_number'] ?? '',
                'postalCode' => $delivery['load_zip'] ?? '',
                'city'       => $delivery['load_city'] ?? '',
            ],
            'deliveryAddress' => [
                'street'     => $delivery['deliv_street'] ?? '',
                'number'     => $delivery['deliv_number'] ?? '',
                'postalCode' => $delivery['deliv_zip'] ?? '',
                'city'       => $delivery['deliv_city'] ?? '',
            ],
            // Branches: the working request leaves them empty when it's the central
            // establishment (0); send '' rather than '0' to match.
            'startShippingBranch'    => ((string)($delivery['load_branch']  ?? '0') === '0') ? '' : (string)$delivery['load_branch'],
            'completeShippingBranch' => ((string)($delivery['deliv_branch'] ?? '0') === '0') ? '' : (string)$delivery['deliv_branch'],
        ];
        // 9.x delivery notes always carry the reverse-delivery flag + purpose (the
        // real form posts them unconditionally for δελτίο 9.3); leaving them out makes
        // the preview fail with a generic "Αδυναμία προεπισκόπησης".
        $isReverse = !empty($delivery['reverse']);
        $invoice['reverseDeliveryNote'] = $isReverse ? 'true' : 'false';
        $invoice['invoiceHeader']['reverseDeliveryNotePurpose'] = $isReverse ? (string)($delivery['movePurpose'] ?? '') : '';
    }

    curlGet($ch, BASE_URL . '/invoice/newinvoice');

    if ($preview) {
        // PREVIEW = "πάτα προεπισκόπηση → αποθηκεύεται στο e-timologio + PDF".
        // 1) Persist the draft (savetempinvoice) so it stays saved in e-timologio.
        // 2) POST the SAME model to /Invoice/PrintPreviewInvoice2PdfNew. Contrary to
        //    our earlier assumption, this endpoint does NOT return a `data2print` JSON
        //    for client-side rendering — the AADE server renders the real PDF itself
        //    and returns it directly as `application/pdf` (verified against a captured
        //    browser request). We just base64 it back to the UI to display.
        // REUSE an existing draft when the caller passes its id: setting tempInvoiceId in
        // the model makes e-timologio UPDATE that draft in place instead of creating a new
        // one, so repeated previews/saves of the same document don't pile up in Πρόχειρα.
        if ($reuseTempId !== '') {
            $invoice['tempInvoiceId'] = $reuseTempId;
        }
        $saveResp = curlPostInvoice($ch, BASE_URL . '/TempInvoice/savetempinvoice', $invoice);
        $saveData = json_decode($saveResp, true);
        $tempId   = $saveData['resultData'][0] ?? '';
        if ($tempId === '' && $reuseTempId !== '') {
            $tempId = $reuseTempId;   // some update responses don't echo the id back
        }
        if ($tempId === '') {
            return [
                'success' => false,
                'error'   => $saveData['message'] ?? 'Η αποθήκευση για προεπισκόπηση απέτυχε',
                'raw'     => substr($saveResp, 0, 400),
            ];
        }
        // The preview endpoint validates the issue date like a live issue: it must be
        // "today" in Greece and in the form's Y-n-j shape (no zero-padding).
        $invoice['tempInvoiceId']              = $tempId;
        $invoice['invoiceHeader']['issueDate'] = date('Y-n-j');
        $resp = curlPostInvoice($ch, BASE_URL . '/Invoice/PrintPreviewInvoice2PdfNew', $invoice);
        if (substr($resp, 0, 4) === '%PDF') {
            // Real AADE PDF.
            return ['success' => true, 'preview' => true, 'saved' => true, 'temp_id' => $tempId, 'pdf_b64' => base64_encode($resp)];
        }
        // Anything non-PDF is an error payload — the draft is still saved.
        $d2p = json_decode($resp, true);
        return [
            'success' => true, 'preview' => true, 'saved' => true, 'temp_id' => $tempId,
            'preview_error' => is_array($d2p) ? ($d2p['message'] ?? $d2p['genericMsg'] ?? 'render failed') : (trim($resp) !== '' ? substr(strip_tags($resp), 0, 300) : 'render failed'),
            'type' => $invoiceType, 'amount_net' => $netValue, 'amount_vat' => $vatAmount, 'amount_total' => $total,
        ];
    }

    if ($live) {
        // LIVE — submit to AADE, get MARK
        $response = curlPostInvoice($ch, BASE_URL . '/Invoice/create', $invoice);
        $data     = json_decode($response, true);

        if (!$data) {
            return [
                'success' => false,
                'error'   => 'Invalid JSON response',
                'raw'     => substr($response, 0, 500),
            ];
        }

        if (isset($data['mark'])) {
            return [
                'success'      => true,
                'live'         => true,
                'mark'         => $data['mark'],
                'aa'           => $data['aa']    ?? '',
                'qrUrl'        => $data['qrUrl'] ?? '',
                'type'         => $invoiceType,
                'amount_net'   => $netValue,
                'amount_vat'   => $vatAmount,
                'amount_total' => $total,
                'amount_discount' => $discountTotal,
            ];
        }

        return [
            'success' => false,
            'error'   => $data['genericMsg'] ?? $data['message'] ?? 'Unknown error',
            'raw'     => $data,
        ];

    } else {
        // DRAFT — safe for testing, nothing submitted to AADE
        $response = curlPostInvoice($ch, BASE_URL . '/TempInvoice/savetempinvoice', $invoice);
        $data     = json_decode($response, true);

        if (!$data) {
            return [
                'success' => false,
                'error'   => 'Invalid JSON response',
                'raw'     => substr($response, 0, 500),
            ];
        }

        if (isset($data['resultData'][0])) {
            return [
                'success'      => true,
                'live'         => false,
                'temp_id'      => $data['resultData'][0],
                'type'         => $invoiceType,
                'amount_net'   => $netValue,
                'amount_vat'   => $vatAmount,
                'amount_total' => $total,
                'amount_discount' => $discountTotal,
                'note'         => 'DRAFT only - not submitted to AADE, no MARK assigned',
            ];
        }

        return [
            'success' => false,
            'error'   => $data['message'] ?? 'Unknown error',
            'raw'     => $data,
        ];
    }
}

// --- 6b. CREDIT NOTE / CANCELLATION (πιστωτικό συσχετιζόμενο) -----------------
// In myDATA you cannot "delete" an issued invoice — you cancel it by issuing a
// CORRELATED credit note that references the original MARK:
//   • B2B invoices (1.x / 2.x)  → 5.1 Πιστωτικό Τιμολόγιο (Συσχετιζόμενο)  = type 50
//   • Retail (11.x ΑΛΠ/ΑΠΥ)     → 11.4 Πιστωτικό Στοιχείο Λιανικής (Συσχ.) = type 61
// The credit note mirrors the original net amount; CorrelatedInvoice = MARK.

function findInvoiceByMark(\CurlHandle $ch, string $mark): ?array {
    $res = searchInvoices($ch, '01/01/2010', date('d/m/Y'), '', $mark, '', '', '0');
    foreach (($res['invoices'] ?? []) as $iv) {
        if ((string)($iv['mark'] ?? '') === (string)$mark) return $iv;
    }
    return $res['invoices'][0] ?? null;
}

// Fetch the FULL original (correlated) invoice by MARK via the same endpoint the
// e-timologio form calls when you set a credit note's correlated MARK. Returns the
// `correlatedInvoice` object (issuer/counterpart/invoiceLines/…) or null.
function getCorrelatedInvoice(\CurlHandle $ch, string $mark, string $creditType): ?array {
    $q = http_build_query(['invType' => $creditType, 'selfPrice' => 'false', 'correlatedMark' => $mark, 'fromNewInvoice' => 'true']);
    $doc = json_decode(curlGet($ch, BASE_URL . '/Invoice/GetValidationDoc?' . $q), true);
    return (is_array($doc) && !empty($doc['correlatedInvoice']) && is_array($doc['correlatedInvoice'])) ? $doc['correlatedInvoice'] : null;
}

function createCreditNote(
    \CurlHandle $ch,
    string $originalMark,
    bool $live = false,
    string $reason = '',
    string $description = 'ΥΠ001',
    float $amountOverride = 0.0,
    bool $preview = false,
    string $issueLang = 'el',
    string $reuseTempId = ''
): array {
    $orig = findInvoiceByMark($ch, $originalMark);
    if (!$orig) {
        return ['success' => false, 'error' => 'Δεν βρέθηκε παραστατικό με ΜΑΡΚ ' . $originalMark];
    }

    $typeLabel  = (string)($orig['type'] ?? '');
    $isRetail   = (bool)preg_match('#(^|\s)11\.#', $typeLabel);
    $creditType = $isRetail ? '61' : '50';

    $origNet = parseMoney((string)($orig['net_value'] ?? '0'));
    $origVat = parseMoney((string)($orig['vat_value'] ?? '0'));

    $net = $amountOverride > 0 ? $amountOverride : $origNet;
    if ($net <= 0) {
        $total = parseMoney((string)($orig['total'] ?? '0'));
        $net = $total > 0 ? round($total / 1.24, 2) : 0.0;
    }
    if ($net <= 0) {
        return ['success' => false, 'error' => 'Δεν προσδιορίστηκε ποσό για το πιστωτικό (δώσε amount)'];
    }

    // Mirror the EXACT VAT rate of the original (vat/net), instead of assuming 24%.
    $rate = ($origNet > 0) ? round($origVat / $origNet, 2) : -1.0;
    $vatCat = $rate >= 0 ? vatCategoryFromRate($rate) : 0;

    $buyer = trim((string)($orig['buyer_vat'] ?? ''));
    $notes = $reason !== '' ? $reason : ('Ακύρωση/Πιστωτικό για ΜΑΡΚ ' . $originalMark);

    // Pick a registered series for the credit type (50 = πιστωτικό, 61 = λιανικό
    // πιστωτικό). Posting a non-existent series makes the preview/issue fail, so we
    // resolve it from the account's series list instead of hardcoding 'A'.
    $creditSeries = 'A';
    $seriesList = listSeries($ch);
    foreach (($seriesList['series'] ?? []) as $s) {
        if ((string)($s['invoice_type_code'] ?? '') === $creditType) {
            $creditSeries = (string)($s['series_code'] ?? 'A');
            break;
        }
    }

    // Mirror the ORIGINAL invoice's exact line(s) — item, values and classifications —
    // exactly like the e-timologio credit-note form does. A generic single line makes
    // AADE reject with «το πληρωτέο/η καθαρή αξία του πιστωτικού δεν μπορεί να είναι
    // μεγαλύτερη του συσχετιζόμενου». For a partial credit the lines are scaled pro-rata.
    $corr = getCorrelatedInvoice($ch, $originalMark, $creditType);
    $mirrorLines = [];
    $counterName = '';
    // Mirror the ORIGINAL's payment TYPE (5=επί πιστώσει, 3=μετρητά …). The credit note
    // is correlated to the original via the top-level `CorrelatedInvoice` = MARK scalar,
    // which is what lets AADE validate «πληρωτέο ≤ συσχετιζόμενο». It just needs a
    // paymentType set.
    $payType = ($corr && !empty($corr['paymentType'])) ? (int)$corr['paymentType'] : 3;
    // NOTE: do NOT send a `paymentMethods` block. Captured live from the e-timologio
    // credit-note form (PrintPreviewInvoice2PdfNew), the WORKING request carries only
    // `paymentType` and NO paymentMethods at all. Our earlier attempt to mirror
    // paymentMethodDetails is what triggered the «TId/PaymentMethodInfo required» chain
    // (and did nothing for «πληρωτέο», which is governed by CorrelatedInvoice + matching
    // line values). So we pass an empty paymentMethods to createInvoice.
    if ($corr) {
        $cp = $corr['counterpart'] ?? [];
        $counterName = (string)($cp['name'] ?? '');
        if ($buyer === '') $buyer = (string)($cp['vatNumber'] ?? '');
        $factor = ($amountOverride > 0 && $origNet > 0) ? min(1.0, round($amountOverride / $origNet, 6)) : 1.0;
        foreach (($corr['invoiceLines'] ?? []) as $ol) {
            $lnNet = round((float)($ol['netValueWithDiscount'] ?? 0) * $factor, 2);
            $lnVat = round((float)($ol['vatAmount'] ?? 0) * $factor, 2);
            $lrate = $lnNet > 0 ? round($lnVat / $lnNet, 2) : 0.0;
            $cls = [];
            foreach (($ol['classifications'] ?? []) as $c) {
                if (empty($c['classificationCategory'])) continue;
                $cls[] = ['cc' => $c['classificationCategory'], 'tc' => (string)($c['classificationType'] ?? ''), 'k' => (int)($c['classificationKind'] ?? 1)];
            }
            $mirrorLines[] = [
                'code'  => (string)($ol['itemCode'] ?? $description),
                'qty'   => 1,
                'price' => $lnNet,
                'rate'  => $lrate,
                'cat'   => (int)($ol['vatCategory'] ?? 0),
                'cls'   => $cls,
            ];
        }
    }

    $result = createInvoice(
        $ch, round($net, 2), $creditType, $payType, $description, '',
        $buyer, $counterName, '', '', '', 'GR', '0',
        0, 0.0, $live, $originalMark, $notes, $rate, $vatCat,
        [], $mirrorLines, $creditSeries, [], $preview, $issueLang, [], $reuseTempId
    );

    $result['credit_note']     = true;
    $result['credit_type']     = $creditType;
    $result['correlated_mark'] = $originalMark;
    $result['original']        = [
        'type'      => $typeLabel,
        'buyer_vat' => $buyer,
        'net'       => round($net, 2),
        'vat'       => round($origVat, 2),
        'vat_rate'  => $rate >= 0 ? $rate : null,
    ];
    return $result;
}

// --- 7. GET INVOICE PDF BY MARK ----------------------------------------------

// Fetch raw PDF bytes for a MARK (null if not a valid PDF)
function fetchInvoicePdfBytes(\CurlHandle $ch, string $mark): ?string {
    $resp = curlGet($ch, BASE_URL . '/Invoice/PrintInvoice2PdfNew?' . http_build_query(['mark' => $mark]));
    if (!$resp || substr($resp, 0, 4) !== '%PDF') return null;
    return $resp;
}

// Stream a ZIP of multiple invoice PDFs (bulk / per-customer download)
function streamInvoicesZip(\CurlHandle $ch, array $marks, string $zipName = 'invoices.zip'): void {
    if (!class_exists('ZipArchive')) jsonError('Το PHP zip extension δεν είναι ενεργό', 500);
    $tmp = tempnam(sys_get_temp_dir(), 'etz');
    $zip = new \ZipArchive();
    $zip->open($tmp, \ZipArchive::OVERWRITE);
    $ok = 0; $fail = [];
    foreach ($marks as $m) {
        $m = trim((string)$m);
        if ($m === '') continue;
        $pdf = fetchInvoicePdfBytes($ch, $m);
        if ($pdf !== null) { $zip->addFromString("invoice-$m.pdf", $pdf); $ok++; }
        else { $fail[] = $m; }
    }
    if (!empty($fail)) $zip->addFromString('_missing.txt', "Δεν βρέθηκαν PDF για:\n" . implode("\n", $fail));
    $zip->close();
    if ($ok === 0) { @unlink($tmp); jsonError('Κανένα έγκυρο PDF για συμπίεση'); }
    $data = file_get_contents($tmp);
    @unlink($tmp);
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . $zipName . '"');
    header('Content-Length: ' . strlen($data));
    echo $data;
    exit;
}

function getInvoicePdf(\CurlHandle $ch, string $mark): void {
    $url      = BASE_URL . '/Invoice/PrintInvoice2PdfNew?' . http_build_query(['mark' => $mark]);
    $response = curlGet($ch, $url);

    if (!$response || substr($response, 0, 4) !== '%PDF') {
        jsonError('PDF not found or invalid MARK');
    }

    // ?pdf_raw=1 → stream binary directly (browser/download use)
    // default    → return base64 JSON (API use)
    if (isset($_GET['pdf_raw'])) {
        header('Content-Type: application/pdf');
        header('Content-Disposition: inline; filename="invoice-' . $mark . '.pdf"');
        header('Content-Length: ' . strlen($response));
        echo $response;
        exit;
    }

    jsonResponse([
        'success'    => true,
        'mark'       => $mark,
        'filename'   => 'invoice-' . $mark . '.pdf',
        'mime'       => 'application/pdf',
        'size'       => strlen($response),
        'pdf_base64' => base64_encode($response),
    ]);
}

// --- 8. STATISTICS ----------------------------------------------------------
// The e-timologio dashboard reports GROSS turnover (net + VAT). For statistics we
// want the NET turnover (καθαρή αξία) per document type, so we aggregate the net
// values of the issued invoices in the period ourselves. (The καρτέλα deliberately
// keeps GROSS totals — that's the amount actually owed/paid.)
function getStatistics(\CurlHandle $ch, string $period = 'month'): array {
    $period = in_array($period, ['month', 'preMonth', 'year'], true) ? $period : 'month';
    if ($period === 'year') {
        $from = '01/01/' . date('Y');  $to = '31/12/' . date('Y');
    } elseif ($period === 'preMonth') {
        $ts = strtotime('first day of previous month');
        $from = date('01/m/Y', $ts);   $to = date('t/m/Y', $ts);
    } else { // current month
        $from = date('01/m/Y');        $to = date('t/m/Y');
    }

    $res = searchInvoices($ch, $from, $to, '', '', '', '', '0');
    $invoices = $res['invoices'] ?? [];

    $agg = [];  // dotted code => ['count'=>, 'value'=> net]
    $totalCount = 0; $totalNet = 0.0;
    foreach ($invoices as $iv) {
        $net = parseMoney((string)($iv['net_value'] ?? '0'));
        // type comes as "2.1 - Τιμολόγιο …"; key the breakdown by the dotted code.
        $label = (string)($iv['type'] ?? '');
        $code  = preg_match('/^\s*([\d.]+)/', $label, $m) ? $m[1] : $label;
        if (!isset($agg[$code])) $agg[$code] = ['count' => 0, 'value' => 0.0];
        $agg[$code]['count']++;
        $agg[$code]['value'] += $net;
        $totalCount++;
        $totalNet += $net;
    }

    $breakdown = [];
    foreach ($agg as $code => $a) {
        $breakdown[] = ['type' => (string)$code, 'count' => $a['count'], 'value' => round($a['value'], 2)];
    }
    usort($breakdown, fn($x, $y) => $y['value'] <=> $x['value']);

    return [
        'success'      => true,
        'period'       => $period,
        'from'         => $from,
        'to'           => $to,
        'breakdown'    => $breakdown,
        'total_count'  => $totalCount,
        'total_value'  => round($totalNet, 2),   // NET turnover
    ];
}

// --- 9. CUSTOMER LEDGER / ΚΑΡΤΕΛΑ -------------------------------------------
// Combines issued invoices (from e-timologio) with LOCAL payments to produce a
// running balance. e-timologio itself stores neither payments nor balances.
// Map an effective VAT rate (0.24, 0.13, …) to the myDATA vatCategory code.
function vatCategoryFromRate(float $rate, bool $isZeroVat = false): int {
    if ($isZeroVat || $rate == 0.0) return 7;
    $pct = (int)round($rate * 100);
    $map = [24 => 1, 13 => 2, 6 => 3, 17 => 4, 9 => 5, 4 => 6, 0 => 7];
    return $map[$pct] ?? 1;
}

function parseMoney(string $s): float {
    $s = trim($s);
    if ($s === '') return 0.0;
    // Greek format: 1.234,56 -> 1234.56 ; also tolerate 1234.56
    $s = preg_replace('/[^\d,.\-]/', '', $s);
    if (strpos($s, ',') !== false) {
        $s = str_replace('.', '', $s);   // remove thousands sep
        $s = str_replace(',', '.', $s);  // decimal comma -> dot
    }
    return (float)$s;
}

function buildLedger(\CurlHandle $ch, string $buyerVat, string $from, string $to): array {
    $inv = searchInvoices($ch, $from, $to, '', '', '', $buyerVat, '0');
    $invoices = $inv['invoices'] ?? [];

    $entries = [];
    $totalDebit = 0.0; // invoiced (customer owes)
    foreach ($invoices as $iv) {
        $amt = parseMoney((string)($iv['total'] ?? '0'));
        $totalDebit += $amt;
        $entries[] = [
            'kind'   => 'invoice',
            'date'   => $iv['issue_date'] ?? '',
            'mark'   => $iv['mark'] ?? '',
            'type'   => $iv['type'] ?? '',
            'series' => $iv['series'] ?? '',
            'aa'     => $iv['aa'] ?? '',
            'debit'  => round($amt, 2),
            'credit' => 0.0,
        ];
    }

    $payments = payments_list(COMPANY_VAT, $buyerVat, toDbDate($from), toDbDate($to));
    $totalCredit = 0.0;
    foreach ($payments as $p) {
        $totalCredit += (float)$p['amount'];
        $entries[] = [
            'kind'       => 'payment',
            'date'       => $p['pay_date'],
            'payment_id' => (int)$p['id'],
            'method'     => (int)$p['method'],
            'notes'      => $p['notes'],
            'debit'      => 0.0,
            'credit'     => round((float)$p['amount'], 2),
        ];
    }

    $meta    = customer_meta_get(COMPANY_VAT, $buyerVat);
    $opening = (float)($meta['opening_balance'] ?? 0);

    // Sort entries by date ascending, then compute running balance
    usort($entries, fn($a, $b) => strcmp(normDate($a['date']), normDate($b['date'])));
    $running = $opening;
    foreach ($entries as &$e) {
        $running += $e['debit'] - $e['credit'];
        $e['balance'] = round($running, 2);
    }
    unset($e);

    return [
        'success'         => true,
        'account_vat'     => COMPANY_VAT,
        'customer_vat'    => $buyerVat,
        'customer_name'   => $meta['customer_name'] ?? '',
        'opening_balance' => round($opening, 2),
        'total_invoiced'  => round($totalDebit, 2),
        'total_paid'      => round($totalCredit, 2),
        'balance'         => round($opening + $totalDebit - $totalCredit, 2),
        'notes'           => $meta['notes'] ?? '',
        'entries'         => $entries,
    ];
}

// Normalise a display date (dd/mm/yyyy or yyyy-mm-dd) to yyyy-mm-dd for sorting
function normDate(string $d): string {
    $d = trim($d);
    if (preg_match('#^(\d{2})/(\d{2})/(\d{4})#', $d, $m)) return "$m[3]-$m[2]-$m[1]";
    if (preg_match('#^(\d{4})-(\d{2})-(\d{2})#', $d, $m)) return "$m[1]-$m[2]-$m[3]";
    return $d;
}
// Convert a search date (yyyy-mm-dd or dd/mm/yyyy) to yyyy-mm-dd for the local DB
function toDbDate(string $d): string {
    $d = trim($d);
    if ($d === '') return '';
    return normDate($d);
}

// --- Issuance notifications (TODO 91) ---------------------------------------
// Human label for an e-timologio invoice-type id (numeric). Falls back to the
// raw code. δελτία αποστολής (9.x → ids 50x) are handled by the caller (never
// notified) but mapped here for completeness.
function docTypeLabel(string $code): string {
    static $m = [
        '1'  => 'Τιμολόγιο Πώλησης (1.1)',   '2'  => 'Τιμολόγιο Ενδοκοινοτικό (1.2)',
        '3'  => 'Τιμολόγιο Τρίτων Χωρών (1.3)',
        '20' => 'Τιμολόγιο Παροχής Υπηρεσιών (2.1)', '21' => 'ΤΠΥ Ενδοκοινοτικό (2.2)',
        '22' => 'ΤΠΥ Τρίτων Χωρών (2.3)',    '23' => 'ΤΠΥ Τρίτων Χωρών',
        '57' => 'ΑΛΠ (11.1)',               '58' => 'ΑΠΥ (11.2)',
        '59' => 'Απόδειξη Λιανικής (11.3)',  '60' => 'Απόδειξη (11.4)',
        '61' => 'Απόδειξη (11.5)',
        '50' => 'Πιστωτικό Τιμολόγιο (5.1)',
    ];
    return $m[$code] ?? ('Παραστατικό τύπου ' . $code);
}

// Movement category for notification email filtering: 'invoice' | 'receipt' | 'credit'.
function notif_category(string $docType, string $docLabel = ''): string {
    if (mb_stripos($docLabel, 'Πιστωτικ') !== false || mb_stripos($docLabel, 'Ακύρωσ') !== false) return 'credit';
    if (in_array($docType, ['57', '58', '59', '60', '61'], true)) return 'receipt';
    if (in_array($docType, ['50', '51'], true)) return 'credit';
    return 'invoice';
}

// Record a notification (and optionally email the admin) after a successful REAL
// issue. NEVER call this for δελτία αποστολής (9.x). Safe to call with a draft/
// failed result — it no-ops unless a ΜΑΡΚ was obtained.
function notifyIssue(array $result, array $ctx): void {
    if (empty($result['success']) || empty($result['mark'])) return;
    $accountVat = defined('COMPANY_VAT') ? COMPANY_VAT : (string)($ctx['account_vat'] ?? '');
    if ($accountVat === '') return;
    $u = function_exists('current_user') ? current_user() : null;
    $docType = (string)($ctx['doc_type'] ?? '');
    $label   = (string)($ctx['doc_label'] ?? docTypeLabel($docType));
    $data = [
        'actor_user_id' => (int)($u['id'] ?? 0),
        'actor_email'   => (string)($u['email'] ?? ''),
        'actor_name'    => (string)($u['business_name'] ?? ''),
        'doc_type'      => $docType,
        'doc_label'     => $label,
        'series'        => (string)($ctx['series'] ?? ''),
        'aa'            => (string)($result['aa'] ?? ''),
        'mark'          => (string)$result['mark'],
        'buyer_vat'     => (string)($ctx['buyer_vat'] ?? ''),
        'buyer_name'    => (string)($ctx['buyer_name'] ?? ''),
        'amount_total'  => (float)($result['amount_total'] ?? 0),
        'source'        => (string)($ctx['source'] ?? ($GLOBALS['__issueSource'] ?? 'manual')),
    ];
    try { notification_add($accountVat, $data); } catch (\Throwable $e) { /* never block issuance */ }
    try { notifyIssueEmail($accountVat, $data); } catch (\Throwable $e) {}
}

// Best-effort branded email of an issuance notification to the accountant/admins
// (Resend or SMTP, per config). Each active staff member is emailed only if their
// personal preferences opt them in for this company + movement type. Config
// fallback addresses (MASTER_ADMIN_EMAIL / NOTIFY_ADMIN_EMAIL) always receive it.
function notifyIssueEmail(string $accountVat, array $d): void {
    if (!function_exists('mail_enabled') || !mail_enabled()) return;   // no email provider
    $category = notif_category((string)($d['doc_type'] ?? ''), (string)($d['doc_label'] ?? ''));
    $recipients = [];
    foreach (users_all() as $u) {
        if (!in_array($u['role'], ['master', 'editor'], true) || $u['status'] !== 'active' || $u['email'] === '') continue;
        if (notify_prefs_match(notify_prefs_get((int)$u['id']), $accountVat, $category)) $recipients[] = $u['email'];
    }
    // Config fallback addresses have no per-user prefs — always include them.
    if (defined('NOTIFY_ADMIN_EMAIL') && trim(NOTIFY_ADMIN_EMAIL) !== '' && trim(NOTIFY_ADMIN_EMAIL) !== '-') $recipients[] = trim(NOTIFY_ADMIN_EMAIL);
    if (defined('MASTER_ADMIN_EMAIL') && trim(MASTER_ADMIN_EMAIL) !== '') $recipients[] = trim(MASTER_ADMIN_EMAIL);
    $recipients = array_values(array_unique(array_filter($recipients)));
    if (empty($recipients)) return;
    $amount = number_format((float)$d['amount_total'], 2, ',', '.');
    $srcL = $d['source'] === 'scheduled' ? 'προγραμματισμένη έκδοση' : ($d['source'] === 'bulk' ? 'μαζική έκδοση' : 'χειροκίνητη');
    $subject = 'Νέο παραστατικό: ' . $d['doc_label'] . ' · ΜΑΡΚ ' . $d['mark'];
    $rows = [
        ['Επιχείρηση (ΑΦΜ)', $accountVat],
        ['Χρήστης', $d['actor_name'] ?: $d['actor_email']],
        ['Τύπος', $d['doc_label']],
        ['Σειρά / ΑΑ', ($d['series'] !== '' ? $d['series'] . ' / ' : '') . $d['aa']],
        ['Πελάτης', $d['buyer_name'] ?: $d['buyer_vat']],
        ['Σύνολο', $amount . ' €'],
        ['ΜΑΡΚ', $d['mark']],
        ['Τρόπος', $srcL],
        ['Ημ/νία', date('d/m/Y H:i')],
    ];
    $trs = '';
    foreach ($rows as [$k, $v]) {
        $trs .= '<tr><td style="padding:4px 10px 4px 0;color:#5b6b84;white-space:nowrap">' . htmlspecialchars($k, ENT_QUOTES)
             . '</td><td style="padding:4px 0;font-weight:600">' . htmlspecialchars((string)$v, ENT_QUOTES) . '</td></tr>';
    }
    $inner = '<p>Εκδόθηκε νέο παραστατικό.</p><table style="border-collapse:collapse;font-size:14px">' . $trs . '</table>';
    $html = mail_template('Νέο παραστατικό', $inner);
    foreach ($recipients as $to) { try { send_mail($to, $subject, $html); } catch (\Throwable $e) {} }
}

// --- API ENTRY POINT ---------------------------------------------------------

// ===========================================================================
// AUTH ACTIONS (?auth=…) — public ones reachable without a session; the rest
// (and every other action below) require login. Master-only actions checked too.
// ===========================================================================
$authAction = trim($_GET['auth'] ?? $_POST['auth'] ?? '');
if ($authAction !== '') {
    switch ($authAction) {
        case 'login':
            jsonResponse(auth_login(trim($_POST['email'] ?? $_GET['email'] ?? ''), (string)($_POST['password'] ?? $_GET['password'] ?? '')));
        case 'signup':
            jsonResponse(auth_signup(trim($_POST['email'] ?? ''), (string)($_POST['password'] ?? ''), trim($_POST['business_name'] ?? '')));
        case 'forgot':
            jsonResponse(auth_forgot(trim($_POST['email'] ?? $_GET['email'] ?? '')));
        case 'reset':
            jsonResponse(auth_reset(trim($_POST['token'] ?? $_GET['token'] ?? ''), (string)($_POST['password'] ?? '')));
        case 'login_totp':   // second login step when 2FA is enabled
            jsonResponse(auth_login_totp(trim($_POST['code'] ?? $_GET['code'] ?? '')));
        case 'logout':
            auth_logout(); jsonResponse(['success' => true]);
        // ---- 2FA enrollment (logged-in user) ----
        case 'totp_setup': {
            if (!current_user()) jsonError('Απαιτείται σύνδεση', 401);
            jsonResponse(auth_totp_setup());
        }
        case 'totp_enable': {
            if (!current_user()) jsonError('Απαιτείται σύνδεση', 401);
            jsonResponse(auth_totp_enable(trim($_POST['code'] ?? $_GET['code'] ?? '')));
        }
        case 'totp_disable': {
            if (!current_user()) jsonError('Απαιτείται σύνδεση', 401);
            jsonResponse(auth_totp_disable((string)($_POST['verify'] ?? $_GET['verify'] ?? '')));
        }
        // ---- Per-admin email notification preferences (staff only) ----
        case 'notif_prefs_get': {
            $u = current_user();
            if (!$u) jsonError('Απαιτείται σύνδεση', 401);
            if (!user_is_staff($u)) jsonError('Μόνο για λογιστή/διαχειριστή', 403);
            jsonResponse([
                'success' => true,
                'prefs'   => notify_prefs_get((int)$u['id']),
                'companies' => array_map(fn($a) => ['vat' => (string)$a['vat'], 'label' => $a['label'] ?: $a['vat']], accounts_all()),
            ]);
        }
        case 'notif_prefs_set': {
            $u = current_user();
            if (!$u) jsonError('Απαιτείται σύνδεση', 401);
            if (!user_is_staff($u)) jsonError('Μόνο για λογιστή/διαχειριστή', 403);
            $companiesRaw = trim((string)($_POST['companies'] ?? $_GET['companies'] ?? '*'));
            $typesRaw     = trim((string)($_POST['types'] ?? $_GET['types'] ?? '*'));
            $split = fn($s) => ($s === '' || $s === '*') ? ['*'] : array_values(array_filter(array_map('trim', explode(',', $s))));
            notify_prefs_set((int)$u['id'], [
                'email_enabled' => !in_array(strtolower((string)($_POST['email_enabled'] ?? $_GET['email_enabled'] ?? '1')), ['0','false','no',''], true),
                'companies'     => $split($companiesRaw),
                'types'         => $split($typesRaw),
            ]);
            jsonResponse(['success' => true, 'prefs' => notify_prefs_get((int)$u['id'])]);
        }
        case 'me': {
            $u = current_user();
            if (!$u) jsonResponse(['success' => true, 'authenticated' => false]);
            $staff = user_is_staff($u);
            $accts = $staff ? accounts_all() : accounts_for_user((int)$u['id']);
            jsonResponse([
                'success' => true, 'authenticated' => true, 'user' => user_public($u),
                'is_staff' => $staff,
                'accounts' => array_map(fn($a) => ['vat' => $a['vat'], 'label' => $a['label'] ?: $a['vat']], $accts),
                'active' => defined('COMPANY_VAT') ? COMPANY_VAT : '',
            ]);
        }
        case 'change_password': {
            $u = current_user();
            if (!$u) jsonError('Απαιτείται σύνδεση', 401);
            if (!password_verify((string)($_POST['old_password'] ?? ''), $u['password_hash'])) jsonError('Λάθος τρέχων κωδικός');
            $np = (string)($_POST['password'] ?? '');
            if (strlen($np) < 8) jsonError('Ο νέος κωδικός πρέπει να έχει ≥ 8 χαρακτήρες');
            user_update((int)$u['id'], ['password_hash' => password_hash($np, PASSWORD_DEFAULT)]);
            jsonResponse(['success' => true]);
        }
        // ---- Master-admin only ----
        case 'admin_users': case 'admin_approve': case 'admin_set_status':
        case 'admin_reset_pw': case 'admin_add_account': case 'admin_update_account':
        case 'admin_delete_account': case 'admin_user_accounts': case 'admin_create_user':
        case 'admin_accounts': case 'admin_invite': case 'admin_set_role': {
            if (!is_master()) jsonError('Απαιτείται διαχειριστής', 403);
            switch ($authAction) {
                case 'admin_users':
                    jsonResponse(['success' => true, 'users' => users_all()]);
                case 'admin_accounts':
                    jsonResponse(['success' => true, 'accounts' => accounts_all()]);
                case 'admin_create_user': {
                    $r = auth_signup(trim($_POST['email'] ?? ''), (string)($_POST['password'] ?? ''), trim($_POST['business_name'] ?? ''));
                    if ($r['success']) user_update((int)$r['id'], ['status' => 'active']);   // admin-created = active
                    jsonResponse($r);
                }
                case 'admin_invite': {
                    $me = current_user();
                    jsonResponse(auth_invite(
                        trim($_POST['email'] ?? ''),
                        trim($_POST['role'] ?? 'editor'),
                        trim($_POST['name'] ?? $_POST['business_name'] ?? ''),
                        (int)($me['id'] ?? 0)
                    ));
                }
                case 'admin_set_role': {
                    $uid = (int)($_POST['user_id'] ?? 0);
                    $role = in_array($_POST['role'] ?? '', ['master','editor','business'], true) ? $_POST['role'] : 'business';
                    $me = current_user();
                    if ($uid === (int)($me['id'] ?? 0)) jsonError('Δεν μπορείτε να αλλάξετε τον δικό σας ρόλο');
                    user_update($uid, ['role' => $role]);
                    jsonResponse(['success' => true]);
                }
                case 'admin_approve': {
                    $uid = (int)($_POST['user_id'] ?? 0);
                    user_update($uid, ['status' => 'active']);
                    $tu = user_by_id($uid);
                    if ($tu) auth_email_account_approved($tu['email'], $tu['business_name']);
                    jsonResponse(['success' => true]);
                }
                case 'admin_set_status': {
                    $uid = (int)($_POST['user_id'] ?? 0);
                    $newSt = in_array($_POST['status'] ?? '', ['active','pending','disabled'], true) ? $_POST['status'] : 'pending';
                    $prev = user_by_id($uid);
                    user_update($uid, ['status' => $newSt]);
                    if ($newSt === 'active' && $prev && $prev['status'] !== 'active') auth_email_account_approved($prev['email'], $prev['business_name']);
                    jsonResponse(['success' => true]);
                }
                case 'admin_reset_pw': {
                    $uid = (int)($_POST['user_id'] ?? 0);
                    $token = bin2hex(random_bytes(24));
                    user_update($uid, ['reset_token' => $token, 'reset_expires' => time() + 86400]);
                    jsonResponse(['success' => true, 'token' => $token, 'reset_link' => auth_reset_link($token)]);
                }
                case 'admin_user_accounts':
                    jsonResponse(['success' => true, 'accounts' => array_map(fn($a) => ['id'=>$a['id'],'vat'=>$a['vat'],'label'=>$a['label'],'username'=>$a['username']], accounts_for_user((int)($_GET['user_id'] ?? $_POST['user_id'] ?? 0)))]);
                case 'admin_add_account':
                    account_add((int)($_POST['user_id'] ?? 0), trim($_POST['vat'] ?? ''), trim($_POST['label'] ?? ''), trim($_POST['username'] ?? ''), trim($_POST['subkey'] ?? ''));
                    jsonResponse(['success' => true]);
                case 'admin_update_account':
                    account_update((int)($_POST['account_id'] ?? 0), ['vat'=>trim($_POST['vat'] ?? ''),'label'=>trim($_POST['label'] ?? ''),'username'=>trim($_POST['username'] ?? ''),'subkey'=>trim($_POST['subkey'] ?? '')]);
                    jsonResponse(['success' => true]);
                case 'admin_delete_account':
                    jsonResponse(['success' => account_delete((int)($_POST['account_id'] ?? 0))]);
            }
        }
        default:
            jsonError('Άγνωστη ενέργεια auth: ' . $authAction);
    }
}

// ---- SERVICE (SCHEDULER) AUTH — loopback only (TODO 90) --------------------
// The background runner (scheduler.php) replays queued issues over loopback HTTP.
// It presents SCHED_TOKEN + the owning user id; we establish that user's session
// and resolve the requested AADE account, then fall through to the normal issue
// dispatch below. Strictly limited to loopback callers.
$schedTok = (string)($_POST['sched_token'] ?? $_GET['sched_token'] ?? '');
if ($schedTok !== '' && defined('SCHED_TOKEN') && SCHED_TOKEN !== '' && hash_equals((string)SCHED_TOKEN, $schedTok)) {
    $remote     = $_SERVER['REMOTE_ADDR'] ?? '';
    $isLoopback = in_array($remote, ['127.0.0.1', '::1', ''], true);
    $sUid       = (int)($_POST['sched_uid'] ?? $_GET['sched_uid'] ?? 0);
    if ($isLoopback && $sUid > 0) {
        $su = user_by_id($sUid);
        if ($su && $su['status'] !== 'disabled') {
            $_SESSION['uid'] = $sUid;
            $GLOBALS['__issueSource'] = 'scheduled';
            if (!defined('COMPANY_VAT')) auth_resolve_account();   // resolves ?account=
        }
    }
}

// ---- LOGIN GATE: everything past here needs an authenticated user ----------
$__user = current_user();
if (!$__user) jsonError('Απαιτείται σύνδεση', 401);

// ===========================================================================
// LOCAL ENDPOINTS THAT NEED ONLY A LOGIN (no AADE session): issuance
// notifications + scheduled-jobs management. These run BEFORE the AADE gate so
// a master admin WITHOUT a linked AADE account can still use them.
// Scope: master admins see every account ('' scope); a business sees its own.
// ===========================================================================
$__isStaff    = user_is_staff($__user);      // master|editor → all companies
$__acctScope  = $__isStaff ? '' : (defined('COMPANY_VAT') ? COMPANY_VAT : '__none__');

// --- Notifications (TODO 91) ---
if (!empty($_GET['notif_count'] ?? $_POST['notif_count'] ?? '')) {
    jsonResponse(['success' => true, 'unread' => notifications_unread_count($__acctScope)]);
}
if (!empty($_GET['notifications'] ?? $_POST['notifications'] ?? '')) {
    $unreadOnly = !empty($_GET['unread'] ?? $_POST['unread'] ?? '');
    $limit = min(500, max(1, (int)($_GET['limit'] ?? $_POST['limit'] ?? 200)));
    jsonResponse([
        'success' => true,
        'scope'   => $__isStaff ? 'all' : $__acctScope,
        'unread'  => notifications_unread_count($__acctScope),
        'items'   => notifications_list($__acctScope, $unreadOnly, $limit),
    ]);
}
if (!empty($_GET['notif_read'] ?? $_POST['notif_read'] ?? '')) {
    notification_mark_read((int)($_GET['id'] ?? $_POST['id'] ?? 0), $__acctScope);
    jsonResponse(['success' => true, 'unread' => notifications_unread_count($__acctScope)]);
}
if (!empty($_GET['notif_read_all'] ?? $_POST['notif_read_all'] ?? '')) {
    notifications_mark_all_read($__acctScope);
    jsonResponse(['success' => true, 'unread' => 0]);
}

// --- Scheduled jobs (TODO 90) ---
if (!empty($_GET['sched_list'] ?? $_POST['sched_list'] ?? '')) {
    jsonResponse(['success' => true, 'jobs' => sched_list($__acctScope)]);
}
if (!empty($_GET['sched_cancel'] ?? $_POST['sched_cancel'] ?? '')) {
    $ok = sched_cancel((int)($_GET['id'] ?? $_POST['id'] ?? 0), $__isStaff ? '' : $__acctScope);
    jsonResponse(['success' => $ok]);
}
if (!empty($_GET['sched_add'] ?? $_POST['sched_add'] ?? '')) {
    if (!defined('SCHED_TOKEN') || SCHED_TOKEN === '') {
        jsonError('Ο χρονοπρογραμματισμός δεν είναι ενεργοποιημένος (ορίστε SCHED_TOKEN στο config.php).', 409);
    }
    if (!defined('COMPANY_VAT')) {
        jsonError('Επιλέξτε λογαριασμό επιχείρησης πριν τον προγραμματισμό.', 409);
    }
    $payloadRaw = (string)($_POST['sched_payload'] ?? $_GET['sched_payload'] ?? '');
    $payload = json_decode($payloadRaw, true);
    if (!is_array($payload) || empty($payload)) jsonError('Άκυρο ή κενό περιεχόμενο (sched_payload)');
    $runAt = trim((string)($_POST['run_at'] ?? $_GET['run_at'] ?? ''));
    // Accept 'YYYY-MM-DD HH:MM' or ISO 'YYYY-MM-DDTHH:MM'; normalise to 'Y-m-d H:i:s'.
    $runAt = str_replace('T', ' ', $runAt);
    $ts = strtotime($runAt);
    if ($ts === false) jsonError('Άκυρη ημερομηνία/ώρα (run_at)');
    $runAtNorm = date('Y-m-d H:i:s', $ts);
    $rec = trim((string)($_POST['recurrence'] ?? $_GET['recurrence'] ?? 'none'));
    // The runner must issue for real — force live=1 into the replayed params.
    $payload['live'] = 1;
    $id = sched_add(COMPANY_VAT, (int)$__user['id'], [
        'title'      => (string)($_POST['title'] ?? $_GET['title'] ?? ''),
        'kind'       => (string)($_POST['kind'] ?? $_GET['kind'] ?? 'invoice'),
        'payload'    => $payload,
        'run_at'     => $runAtNorm,
        'recurrence' => $rec,
    ]);
    jsonResponse(['success' => true, 'id' => $id, 'run_at' => $runAtNorm, 'recurrence' => $rec]);
}

// A logged-in business user with no linked AADE account yet can't hit AADE.
if (!defined('COMPANY_VAT')) {
    jsonError('Δεν έχει συνδεθεί λογαριασμός AADE στον χρήστη σας (εκκρεμεί ρύθμιση από τον διαχειριστή).', 409);
}

$mark                = trim($_GET['mark']                  ?? $_POST['mark']                  ?? '');
$afm                 = trim($_GET['afm']                   ?? $_POST['afm']                   ?? '');
$amount              = (float)($_GET['amount']             ?? $_POST['amount']                ?? 0);
$type                = trim($_GET['type']                  ?? $_POST['type']                  ?? '58');
$payment             = (int)($_GET['payment']              ?? $_POST['payment']               ?? 3);
$descr               = trim($_GET['description']           ?? $_POST['description']           ?? 'ΥΠ001');
$name                = trim($_GET['name']                  ?? $_POST['name']                  ?? '');
$address             = trim($_GET['address']               ?? $_POST['address']               ?? '');
$city                = trim($_GET['city']                  ?? $_POST['city']                  ?? '');
$zip                 = trim($_GET['zip']                   ?? $_POST['zip']                   ?? '');
$country             = trim($_GET['country']               ?? $_POST['country']               ?? 'GR');
$branch              = trim($_GET['branch']                ?? $_POST['branch']                ?? '0');
$withholdingCategory = (int)($_GET['withholding_category'] ?? $_POST['withholding_category']  ?? 0);
$withholdingAmount   = (float)($_GET['withholding_amount'] ?? $_POST['withholding_amount']    ?? 0);
$live                = !empty(($_GET['live']               ?? $_POST['live']                  ?? ''));

$listCustomers       = !empty(($_GET['list_customers']     ?? $_POST['list_customers']        ?? ''));
$allCustomers        = !empty(($_GET['all_customers']      ?? $_POST['all_customers']         ?? ''));
$customerCodeFilter  = trim($_GET['customer_code']         ?? $_POST['customer_code']         ?? '');
$customerNameFilter  = trim($_GET['customer_name']         ?? $_POST['customer_name']         ?? '');
$customersPageSize   = (int)($_GET['customers_page_size']  ?? $_POST['customers_page_size']   ?? 1000);
$customersMaxPages   = (int)($_GET['customers_max_pages']  ?? $_POST['customers_max_pages']   ?? 20);

$createPersonalCust  = !empty(($_GET['create_personal_customer'] ?? $_POST['create_personal_customer'] ?? ''));
$custName            = trim($_GET['cust_name']             ?? $_POST['cust_name']             ?? '');
$custAddress         = trim($_GET['cust_address']          ?? $_POST['cust_address']          ?? '');
$custCity            = trim($_GET['cust_city']             ?? $_POST['cust_city']             ?? '');
$custZip             = trim($_GET['cust_zip']              ?? $_POST['cust_zip']              ?? '');
$custDoy             = trim($_GET['cust_doy']              ?? $_POST['cust_doy']              ?? 'ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ');
$custCountry         = trim($_GET['cust_country']          ?? $_POST['cust_country']          ?? 'GR');
$custJobDescription  = trim($_GET['cust_job_description']  ?? $_POST['cust_job_description']  ?? 'ΙΔΙΩΤΗΣ');
$custEmail           = trim($_GET['cust_email']            ?? $_POST['cust_email']            ?? '');
$custPhone1          = trim($_GET['cust_phone1']           ?? $_POST['cust_phone1']           ?? '');
$custPhone2          = trim($_GET['cust_phone2']           ?? $_POST['cust_phone2']           ?? '');
$custLanguage        = trim($_GET['cust_language']         ?? $_POST['cust_language']         ?? 'el-GR');
$custIsB2G           = !empty(($_GET['cust_is_b2g']        ?? $_POST['cust_is_b2g']           ?? ''));
$custCode            = trim($_GET['cust_code']             ?? $_POST['cust_code']             ?? '');
$custVat             = trim($_GET['cust_vat']              ?? $_POST['cust_vat']              ?? '');
$custOldVat          = trim($_GET['cust_old_vat']          ?? $_POST['cust_old_vat']          ?? '');

$previewFlag         = !empty(($_GET['preview']            ?? $_POST['preview']               ?? ''));
$reuseTempId         = trim($_GET['temp_id']               ?? $_POST['temp_id']               ?? '');
$searchInvoicesFlag  = !empty(($_GET['search_invoices']    ?? $_POST['search_invoices']       ?? ''));
$issueDateFrom       = trim($_GET['issue_date_from']       ?? $_POST['issue_date_from']       ?? '');
$issueDateTo         = trim($_GET['issue_date_to']         ?? $_POST['issue_date_to']         ?? '');
$searchInvoiceType   = trim($_GET['search_invoice_type']   ?? $_POST['search_invoice_type']   ?? $_GET['invoice_type'] ?? $_POST['invoice_type'] ?? $_GET['type'] ?? $_POST['type'] ?? '');
$seriesFilter        = trim($_GET['series']                ?? $_POST['series']                ?? '');
$buyerVatFilter      = trim($_GET['buyer_vat']             ?? $_POST['buyer_vat']             ?? '');
$includeCancelled    = !empty(($_GET['include_cancelled']  ?? $_POST['include_cancelled']     ?? ''));
$invoiceStatusFilter = trim($_GET['invoice_status']        ?? $_POST['invoice_status']        ?? '');
$searchCounterpart   = !empty(($_GET['search_counterpart'] ?? $_POST['search_counterpart']    ?? ''));
$searchB2G           = !empty(($_GET['search_b2g']         ?? $_POST['search_b2g']            ?? ''));

if ($invoiceStatusFilter === '') {
    $invoiceStatusFilter = $includeCancelled ? '1' : '0';
}

$searchTempFlag      = !empty(($_GET['search_temp']        ?? $_POST['search_temp']           ?? ''));
$saveDateFrom        = trim($_GET['save_date_from']        ?? $_POST['save_date_from']        ?? '');
$saveDateTo          = trim($_GET['save_date_to']          ?? $_POST['save_date_to']          ?? '');
$tempInvoiceIdFilter = trim($_GET['temp_id']               ?? $_POST['temp_id']               ?? '');

$deleteTempId        = trim($_GET['delete_temp_id']        ?? $_POST['delete_temp_id']        ?? '');
$sellerVat           = trim($_GET['seller_vat']            ?? $_POST['seller_vat']            ?? '');
$issueSeries         = trim($_GET['issue_series']          ?? $_POST['issue_series']          ?? 'A');
$issueLang           = (($_GET['issue_lang'] ?? $_POST['issue_lang'] ?? 'el') === 'en') ? 'en' : 'el';
$deleteCustomerCode  = trim($_GET['delete_customer_code']  ?? $_POST['delete_customer_code']  ?? '');
$deleteCustomerVat   = trim($_GET['delete_customer_vat']   ?? $_POST['delete_customer_vat']   ?? '');

$updateCustomerFlag  = !empty(($_GET['update_customer']    ?? $_POST['update_customer']       ?? ''));
$updateCustomerVat   = trim($_GET['update_customer_vat']   ?? $_POST['update_customer_vat']   ?? '');
$updateCustomerCode  = trim($_GET['update_customer_code']  ?? $_POST['update_customer_code']  ?? '');
$updateName          = trim($_GET['update_name']           ?? $_POST['update_name']           ?? '');
$updateAddress       = trim($_GET['update_address']        ?? $_POST['update_address']        ?? '');
$updateCity          = trim($_GET['update_city']           ?? $_POST['update_city']           ?? '');
$updateZip           = trim($_GET['update_zip']            ?? $_POST['update_zip']            ?? '');
$updateDoy           = trim($_GET['update_doy']            ?? $_POST['update_doy']            ?? '');
$updateEmail         = trim($_GET['update_email']          ?? $_POST['update_email']          ?? '');
$updatePhone1        = trim($_GET['update_phone1']         ?? $_POST['update_phone1']         ?? '');
$updatePhone2        = trim($_GET['update_phone2']         ?? $_POST['update_phone2']         ?? '');
$updateJobDesc       = trim($_GET['update_job_description'] ?? $_POST['update_job_description'] ?? '');

$listSeriesFlag      = !empty(($_GET['list_series']               ?? $_POST['list_series']               ?? ''));
$deleteSeriesId      = trim($_GET['delete_series_id']             ?? $_POST['delete_series_id']          ?? '');
$newSeriesFlag       = !empty(($_GET['new_series']                ?? $_POST['new_series']                ?? ''));
$updateSeriesId      = trim($_GET['update_series_id']             ?? $_POST['update_series_id']          ?? '');
$seriesInvoiceType   = trim($_GET['series_invoice_type']          ?? $_POST['series_invoice_type']       ?? '');
$seriesCode          = trim($_GET['series_code']                  ?? $_POST['series_code']               ?? '');
$seriesStartAa       = trim($_GET['series_start_aa']              ?? $_POST['series_start_aa']           ?? '1');
$seriesDescription   = trim($_GET['series_description']           ?? $_POST['series_description']        ?? '');
$seriesIsTransFail   = !empty(($_GET['series_trans_failure']      ?? $_POST['series_trans_failure']      ?? ''));

$newDeductionFlag    = !empty(($_GET['new_deduction']             ?? $_POST['new_deduction']             ?? ''));
$updateDeductionCode = trim($_GET['update_deduction_code']        ?? $_POST['update_deduction_code']     ?? '');
$deductionDesc       = trim($_GET['deduction_description']        ?? $_POST['deduction_description']     ?? '');
$deductionAmtType    = trim($_GET['deduction_amount_type']        ?? $_POST['deduction_amount_type']     ?? '');
$deductionAmt        = trim($_GET['deduction_amount']             ?? $_POST['deduction_amount']          ?? '');
$deductionDecPaid    = trim($_GET['deduction_decrease_total_paid'] ?? $_POST['deduction_decrease_total_paid'] ?? '');

$listDeductionsFlag  = !empty(($_GET['list_deductions']           ?? $_POST['list_deductions']           ?? ''));
$deleteDeductionCode = trim($_GET['delete_deduction_code']        ?? $_POST['delete_deduction_code']     ?? '');

$listProductsFlag    = !empty(($_GET['list_products']             ?? $_POST['list_products']             ?? ''));
$deleteProductCode   = trim($_GET['delete_product_code']          ?? $_POST['delete_product_code']       ?? '');

$listCategoriesFlag  = !empty(($_GET['list_product_categories']   ?? $_POST['list_product_categories']   ?? ''));
$deleteCategoryId    = trim($_GET['delete_product_category_id']   ?? $_POST['delete_product_category_id'] ?? '');

$newProductFlag      = !empty(($_GET['new_product']               ?? $_POST['new_product']               ?? ''));
$updateProductCode   = trim($_GET['update_product_code']         ?? $_POST['update_product_code']       ?? '');
$productType         = trim($_GET['product_type']                ?? $_POST['product_type']              ?? '');
$productCode         = trim($_GET['product_code']               ?? $_POST['product_code']              ?? '');
$productDescription  = trim($_GET['product_description']         ?? $_POST['product_description']       ?? '');
$productCategory     = trim($_GET['product_category']            ?? $_POST['product_category']          ?? '');
$taricCode          = trim($_GET['taric_code']                  ?? $_POST['taric_code']                ?? '');
$unitPrice          = trim($_GET['unit_price']                  ?? $_POST['unit_price']                ?? '0');
$vatCategory        = trim($_GET['vat_category']                ?? $_POST['vat_category']              ?? '1');
$unit               = trim($_GET['unit']                        ?? $_POST['unit']                      ?? '');
$specialType        = trim($_GET['special_type']                ?? $_POST['special_type']              ?? '');
$feesWithVAT        = trim($_GET['fees_with_vat']               ?? $_POST['fees_with_vat']             ?? '');
$otherTaxesWithVAT  = trim($_GET['other_taxes_with_vat']        ?? $_POST['other_taxes_with_vat']      ?? '');

$newCategoryFlag     = !empty(($_GET['new_product_category']     ?? $_POST['new_product_category']     ?? ''));
$updateCategoryId    = trim($_GET['update_category_id']         ?? $_POST['update_category_id']       ?? '');
$categoryName        = trim($_GET['category_name']              ?? $_POST['category_name']            ?? '');

$companyProfileFlag  = !empty(($_GET['company_profile']           ?? $_POST['company_profile']           ?? ''));
$companyFromTaxis    = !empty(($_GET['company_from_taxis']        ?? $_POST['company_from_taxis']        ?? ''));

// New params: statistics, ledger, local payments, accounts
$statisticsFlag      = !empty(($_GET['statistics']               ?? $_POST['statistics']               ?? ''));
$statsPeriod         = trim($_GET['period']                      ?? $_POST['period']                   ?? 'month');
$ledgerFlag          = !empty(($_GET['ledger']                   ?? $_POST['ledger']                   ?? ''));
$listAccountsFlag    = !empty(($_GET['accounts']                 ?? $_POST['accounts']                 ?? ''));
$listPaymentsFlag    = !empty(($_GET['list_payments']            ?? $_POST['list_payments']            ?? ''));
$addPaymentFlag      = !empty(($_GET['add_payment']              ?? $_POST['add_payment']              ?? ''));
$deletePaymentId     = trim($_GET['delete_payment_id']           ?? $_POST['delete_payment_id']        ?? '');
$customerMetaGet     = !empty(($_GET['customer_meta']            ?? $_POST['customer_meta']            ?? ''));
$customerMetaSet     = !empty(($_GET['set_customer_meta']        ?? $_POST['set_customer_meta']        ?? ''));
$custDelivGet        = !empty(($_GET['cust_deliv']               ?? $_POST['cust_deliv']               ?? ''));
$custDelivSet        = !empty(($_GET['save_cust_deliv']          ?? $_POST['save_cust_deliv']          ?? ''));

// ----------------------------------------------------------------------------
// LOCAL-ONLY actions (no e-timologio login needed → fast)
// ----------------------------------------------------------------------------
if ($listAccountsFlag) {
    // Staff (accountant/admin) switch among ALL companies; a business user only
    // among the companies it owns.
    $src = user_is_staff($__user) ? accounts_all() : accounts_for_user((int)$__user['id']);
    $out = [];
    foreach ($src as $a) {
        $out[] = ['label' => $a['label'] ?: $a['vat'], 'vat' => (string)$a['vat']];
    }
    jsonResponse(['success' => true, 'active' => COMPANY_VAT, 'active_staff' => user_is_staff($__user), 'accounts' => $out]);
}

// Instant cache read (no AADE login) — UI renders from this immediately
$cachedKind = trim($_GET['cached'] ?? $_POST['cached'] ?? '');
if ($cachedKind !== '') {
    $c = cache_get(COMPANY_VAT, $cachedKind);
    if ($c) {
        jsonResponse(['success' => true, 'cached' => true, 'kind' => $cachedKind,
            'synced_at' => $c['synced_at'], 'count' => count($c['rows']), 'rows' => $c['rows']]);
    }
    jsonResponse(['success' => true, 'cached' => false, 'kind' => $cachedKind, 'count' => 0, 'rows' => []]);
}

if ($addPaymentFlag) {
    $id = payment_add(COMPANY_VAT, [
        'customer_vat'  => trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm),
        'customer_code' => trim($_GET['customer_code'] ?? $_POST['customer_code'] ?? ''),
        'customer_name' => trim($_GET['customer_name'] ?? $_POST['customer_name'] ?? $name),
        'amount'        => (float)($_GET['pay_amount'] ?? $_POST['pay_amount'] ?? $amount),
        'method'        => (int)($_GET['pay_method'] ?? $_POST['pay_method'] ?? $payment),
        'pay_date'      => trim($_GET['pay_date'] ?? $_POST['pay_date'] ?? date('Y-m-d')),
        'mark'          => $mark,
        'notes'         => trim($_GET['pay_notes'] ?? $_POST['pay_notes'] ?? ''),
    ]);
    jsonResponse(['success' => true, 'payment_id' => $id]);
}

if ($deletePaymentId !== '') {
    $ok = payment_delete(COMPANY_VAT, (int)$deletePaymentId);
    jsonResponse(['success' => $ok, 'deleted' => $ok ? (int)$deletePaymentId : null]);
}

// --- Bank statement (extrait) import → local payments -----------------------
// STEP 1: parse an uploaded file into normalised transactions for the UI to
// review. The bank deposit amount is NOT tied to any balance — each row is a
// standalone candidate payment (partial / over-payment allowed).
if (!empty($_GET['bank_preview'] ?? $_POST['bank_preview'] ?? '')) {
    $b64  = (string)($_POST['file_b64'] ?? $_GET['file_b64'] ?? '');
    $raw  = $b64 !== '' ? (base64_decode($b64, true) ?: '') : '';
    if ($raw === '') jsonError('Λείπει το αρχείο (file_b64)');
    $fn   = trim($_POST['filename'] ?? $_GET['filename'] ?? '');
    $bank = trim($_POST['bank'] ?? $_GET['bank'] ?? '');
    $res  = bank_parse($raw, $fn, $bank);
    // Attach the account's known customers so the UI can auto-suggest matches.
    $custCache = cache_get(COMPANY_VAT, 'customers');
    $customers = [];
    foreach (($custCache['rows'] ?? []) as $c) {
        $customers[] = [
            'vat'  => (string)($c['vat'] ?? $c['afm'] ?? $c['vatNumber'] ?? ''),
            'name' => (string)($c['name'] ?? $c['fullName'] ?? $c['customer_name'] ?? ''),
            'code' => (string)($c['code'] ?? $c['customer_code'] ?? ''),
        ];
    }
    $res['success']   = true;
    $res['customers'] = $customers;
    jsonResponse($res);
}

// STEP 2: register the reviewed rows as local payments. `items` is a JSON array
// of {customer_vat, customer_name, customer_code, amount, pay_date, method,
// mark, notes}. We do NOT reconcile against invoices — amounts are stored as-is.
if (!empty($_GET['bank_import'] ?? $_POST['bank_import'] ?? '')) {
    $itemsRaw = $_POST['items'] ?? $_GET['items'] ?? '';
    $items = is_array($itemsRaw) ? $itemsRaw : json_decode((string)$itemsRaw, true);
    if (!is_array($items) || !$items) jsonError('Λείπουν εγγραφές (items)');
    if (count($items) > 500) jsonError('Πάρα πολλές εγγραφές (μέγιστο 500)');
    $results = []; $ok = 0; $failed = 0;
    foreach ($items as $it) {
        try {
            $id = payment_add(COMPANY_VAT, [
                'customer_vat'  => trim((string)($it['customer_vat']  ?? '')),
                'customer_code' => trim((string)($it['customer_code'] ?? '')),
                'customer_name' => trim((string)($it['customer_name'] ?? '')),
                'amount'        => (float)($it['amount'] ?? 0),
                'method'        => (int)($it['method'] ?? 1), // 1 = Επαγγ. Λογ. Πληρωμών (τράπεζα)
                'pay_date'      => trim((string)($it['pay_date'] ?? date('Y-m-d'))),
                'mark'          => trim((string)($it['mark'] ?? '')),
                'notes'         => trim((string)($it['notes'] ?? '')),
            ]);
            $results[] = ['ok' => true, 'payment_id' => $id];
            $ok++;
        } catch (\Throwable $e) {
            $results[] = ['ok' => false, 'error' => $e->getMessage()];
            $failed++;
        }
    }
    jsonResponse(['success' => true, 'total' => count($items), 'ok' => $ok, 'failed' => $failed, 'results' => $results]);
}

if ($listPaymentsFlag) {
    $rows = payments_list(
        COMPANY_VAT,
        trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm),
        toDbDate(trim($_GET['issue_date_from'] ?? $_POST['issue_date_from'] ?? '')),
        toDbDate(trim($_GET['issue_date_to'] ?? $_POST['issue_date_to'] ?? ''))
    );
    jsonResponse(['success' => true, 'count' => count($rows), 'payments' => $rows]);
}

if ($customerMetaSet) {
    $cv = trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm);
    customer_meta_set(COMPANY_VAT, $cv, [
        'customer_name'   => trim($_GET['customer_name'] ?? $_POST['customer_name'] ?? ''),
        'opening_balance' => (float)($_GET['opening_balance'] ?? $_POST['opening_balance'] ?? 0),
        'notes'           => trim($_GET['cust_notes'] ?? $_POST['cust_notes'] ?? ''),
    ]);
    jsonResponse(['success' => true, 'meta' => customer_meta_get(COMPANY_VAT, $cv)]);
}

if ($customerMetaGet) {
    $cv = trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm);
    jsonResponse(['success' => true, 'meta' => customer_meta_get(COMPANY_VAT, $cv)]);
}

if ($custDelivGet) {
    $cv = trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm);
    jsonResponse(['success' => true, 'deliv' => customer_deliv_get(COMPANY_VAT, $cv)]);
}

if ($custDelivSet) {
    $cv = trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm);
    if ($cv === '') jsonError('Λείπει ο ΑΦΜ πελάτη');
    customer_deliv_set(COMPANY_VAT, $cv, [
        'branch'  => trim($_GET['deliv_branch'] ?? $_POST['deliv_branch'] ?? '0'),
        'street'  => trim($_GET['deliv_street'] ?? $_POST['deliv_street'] ?? ''),
        'number'  => trim($_GET['deliv_number'] ?? $_POST['deliv_number'] ?? ''),
        'city'    => trim($_GET['deliv_city']   ?? $_POST['deliv_city']   ?? ''),
        'zip'     => trim($_GET['deliv_zip']    ?? $_POST['deliv_zip']    ?? ''),
    ]);
    jsonResponse(['success' => true, 'deliv' => customer_deliv_get(COMPANY_VAT, $cv)]);
}

// cls_options is static per (invoice type, self) — serve from cache WITHOUT an
// AADE login when available. This makes the «Νέα κατηγορία με προτεινόμενο
// χαρακτηρισμό» flow (which asks for every invoice type) near-instant.
if (!empty($_GET['cls_options'] ?? $_POST['cls_options'] ?? '')) {
    $selfEarly = !empty($_GET['self'] ?? $_POST['self'] ?? '');
    $clsKey = 'clsopt:' . $type . ':' . ($selfEarly ? '1' : '0');
    $cHit = cache_get(COMPANY_VAT, $clsKey);
    if ($cHit && !empty($cHit['rows'])) jsonResponse($cHit['rows']);
}

$ch = login();

// Serve e-timologio's own client-side PDF scripts through the bridge so the UI can
// render the exact AADE "Προεπισκόπηση" PDF. Whitelisted static assets only.
$jsAsset = trim($_GET['etimologio_js'] ?? '');
if ($jsAsset !== '') {
    $whitelist = [
        'font'         => '/js/print2pdf/font.js',
        'invoice2pdf'  => '/js/print2pdf/invoice2pdf.js',
        'dispatch2pdf' => '/js/print2pdf/dispatchNote2pdf.js',
    ];
    if (isset($whitelist[$jsAsset])) {
        $js = curlGet($ch, BASE_URL . $whitelist[$jsAsset]);
        curl_close($ch);
        header('Content-Type: application/javascript; charset=utf-8');
        header('Cache-Control: public, max-age=86400');
        echo $js;
        exit;
    }
    curl_close($ch);
    jsonError('Unknown asset');
}

if ($statisticsFlag) {
    $result = getStatistics($ch, $statsPeriod);
    curl_close($ch);
    jsonResponse($result);
}

// Preview PDF of an EXISTING draft by its tempInvoiceId — used by the Πρόχειρα list so
// the user can pull up the real AADE preview of a saved draft WITHOUT creating a new one.
// PrintPreviewInvoice2PdfNew renders straight from the persisted draft when given only
// its tempInvoiceId (the server already holds the full model).
// `preview_temp` = the ENCRYPTED tempInvoiceId token (from the draft row's edit link). For
// convenience a raw 36-char GUID is also accepted and resolved to its enc token. UNIVERSAL:
// works for ANY draft, including ones created directly in e-timologio.
$previewTempId = trim($_GET['preview_temp'] ?? $_POST['preview_temp'] ?? '');
if ($previewTempId !== '') {
    $encId = $previewTempId;
    if (preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-/i', $previewTempId)) {   // a raw GUID → find its enc token
        $lst = searchTempInvoices($ch);
        foreach (($lst['temp_invoices'] ?? []) as $ti) {
            if (($ti['temp_id'] ?? '') === $previewTempId) { $encId = $ti['enc_id'] ?? ''; break; }
        }
    }
    $result = previewTempInvoice($ch, $encId);
    $result['temp_id'] = $previewTempId;
    curl_close($ch);
    jsonResponse($result);
}

// Background sync — fetch fresh, compare snapshot hash, update cache, report change
$syncKind = trim($_GET['sync'] ?? $_POST['sync'] ?? '');
if ($syncKind !== '') {
    $prev = cache_get(COMPANY_VAT, $syncKind);
    $rows = [];
    if ($syncKind === 'customers') {
        $r = listCustomers($ch, '', '', '', true, 1000, 20); $rows = $r['customers'] ?? [];
    } elseif ($syncKind === 'products') {
        $r = listProducts($ch); $rows = $r['products'] ?? [];
    } elseif ($syncKind === 'invoices') {
        $r = searchInvoices($ch, $issueDateFrom, $issueDateTo, '', '', '', '', '0'); $rows = $r['invoices'] ?? [];
    } elseif ($syncKind === 'series') {
        $r = listSeries($ch); $rows = $r['series'] ?? [];
    } elseif ($syncKind === 'deductions') {
        $r = listDeductions($ch); $rows = $r['deductions'] ?? [];
    } elseif ($syncKind === 'categories') {
        $r = listCategoryClassifications($ch); $rows = $r['categories'] ?? [];
    } elseif ($syncKind === 'drafts') {
        $r = searchTempInvoices($ch, $saveDateFrom, $saveDateTo, '', '', ''); $rows = $r['temp_invoices'] ?? [];
    } elseif ($syncKind === 'invtypes') {
        // invoice types with code/name split out (same shape the UI expects)
        $rows = getClassificationInvoiceTypes($ch);
        foreach ($rows as &$t) {
            if (preg_match('/^\s*([\d.]+)\s*-\s*(.+)$/u', $t['label'], $m)) { $t['code'] = $m[1]; $t['name'] = trim($m[2]); }
            else { $t['code'] = ''; $t['name'] = $t['label']; }
        }
        unset($t);
    } else {
        curl_close($ch); jsonError('Unknown sync kind: ' . $syncKind);
    }
    $newHash  = md5(json_encode($rows, JSON_UNESCAPED_UNICODE));
    $changed  = !$prev || $prev['hash'] !== $newHash;
    if ($changed) cache_set(COMPANY_VAT, $syncKind, $rows);
    $meta = cache_get(COMPANY_VAT, $syncKind);
    curl_close($ch);
    jsonResponse(['success' => true, 'kind' => $syncKind, 'changed' => $changed,
        'count' => count($rows), 'prev_count' => $prev ? count($prev['rows']) : 0,
        'synced_at' => $meta['synced_at'] ?? '', 'rows' => $rows]);
}

if ($ledgerFlag) {
    $cv = trim($_GET['buyer_vat'] ?? $_POST['buyer_vat'] ?? $afm);
    if ($cv === '') { curl_close($ch); jsonError('Missing buyer_vat for ledger'); }
    $result = buildLedger($ch, $cv, $issueDateFrom, $issueDateTo);
    curl_close($ch);
    jsonResponse($result);
}

// Credit note / cancellation by original MARK
$creditNoteFlag = !empty(($_GET['credit_note'] ?? $_POST['credit_note'] ?? ''));
$cancelMark     = trim($_GET['cancel_mark'] ?? $_POST['cancel_mark'] ?? $_GET['credit_for_mark'] ?? $_POST['credit_for_mark'] ?? '');
$creditReason   = trim($_GET['reason'] ?? $_POST['reason'] ?? '');
if ($creditNoteFlag || $cancelMark !== '') {
    if ($cancelMark === '') { curl_close($ch); jsonError('Λείπει το cancel_mark (ΜΑΡΚ αρχικού παραστατικού)'); }
    $result = createCreditNote($ch, $cancelMark, $live, $creditReason, $descr, $amount, $previewFlag, $issueLang, $reuseTempId);
    curl_close($ch);
    if ($live && !$previewFlag) notifyIssue($result, ['doc_type' => (string)($result['type'] ?? '50'), 'doc_label' => 'Πιστωτικό / Ακύρωση', 'buyer_vat' => $afm, 'buyer_name' => $name]);
    jsonResponse($result);
}

// Classifications (χαρακτηρισμοί) for a product within an invoice type
if (!empty($_GET['classifications'] ?? $_POST['classifications'] ?? '')) {
    $prod = trim($_GET['product'] ?? $_POST['product'] ?? $descr);
    $result = getInvoiceClassifications($ch, $prod, $type);
    curl_close($ch);
    jsonResponse($result);
}

// Pure Taxisnet name lookup by VAT (no customer creation) — used by admin onboarding
// and anywhere we just need the registered company/customer name for an ΑΦΜ.
if (!empty($_GET['taxis_name'] ?? $_POST['taxis_name'] ?? '')) {
    $vat = preg_replace('/\D/', '', $_GET['vat'] ?? $_POST['vat'] ?? '');
    if (!preg_match('/^\d{9}$/', $vat)) { curl_close($ch); jsonError('Μη έγκυρο ΑΦΜ (9 ψηφία)'); }
    $info = getFromTaxisnet($ch, $vat);
    curl_close($ch);
    if (!$info || $info['name'] === '') jsonError('Δεν βρέθηκε επωνυμία για το ΑΦΜ ' . $vat, 404);
    jsonResponse(['success' => true, 'vat' => $vat] + $info);
}

// Invoice taxes / withholdings / fees category lists (Νέος Φόρος)
if (!empty($_GET['tax_categories'] ?? $_POST['tax_categories'] ?? '')) {
    $result = getTaxCategories($ch);
    curl_close($ch);
    jsonResponse($result);
}

// Invoice-type catalogue (numeric value + dotted code + full label) for the UI.
if (!empty($_GET['invoice_types'] ?? $_POST['invoice_types'] ?? '')) {
    $types = getClassificationInvoiceTypes($ch);
    foreach ($types as &$t) {
        // labels look like "2.1 - Τιμολόγιο Παροχής Υπηρεσιών"
        if (preg_match('/^\s*([\d.]+)\s*-\s*(.+)$/u', $t['label'], $m)) {
            $t['code'] = $m[1];
            $t['name'] = trim($m[2]);
        } else { $t['code'] = ''; $t['name'] = $t['label']; }
    }
    unset($t);
    curl_close($ch);
    jsonResponse(['success' => true, 'invoice_types' => $types]);
}

// Allowed classification categories + codes for an invoice type (dropdown source)
if (!empty($_GET['cls_options'] ?? $_POST['cls_options'] ?? '')) {
    $selfP  = !empty($_GET['self'] ?? $_POST['self'] ?? '');
    $result = getClassificationOptions($ch, $type, $selfP);
    curl_close($ch);
    // Cache the static result so future requests skip the AADE round-trip.
    if (!empty($result['success'])) cache_set(COMPANY_VAT, 'clsopt:' . $type . ':' . ($selfP ? '1' : '0'), $result);
    jsonResponse($result);
}

// Category-level classifications — list categories + their χαρακτηρισμοί + type list
if (!empty($_GET['category_cls'] ?? $_POST['category_cls'] ?? '')) {
    $result = listCategoryClassifications($ch);
    $result['invoice_types'] = getClassificationInvoiceTypes($ch);
    curl_close($ch);
    jsonResponse($result);
}

// Save category-level classifications (create or update a product category)
if (!empty($_GET['save_category_cls'] ?? $_POST['save_category_cls'] ?? '')) {
    $catId   = trim($_GET['category_id'] ?? $_POST['category_id'] ?? '');
    $catName = trim($_GET['category_name'] ?? $_POST['category_name'] ?? '');
    $clsJson = trim($_GET['cls'] ?? $_POST['cls'] ?? '');
    $clsArr  = json_decode($clsJson, true);
    if (!is_array($clsArr)) $clsArr = [];
    $result = saveCategoryClassifications($ch, $catId, $catName, $clsArr);
    curl_close($ch);
    jsonResponse($result);
}

// ---- MASS / BULK ISSUANCE (μαζική έκδοση) ---------------------------------
// `?bulk_issue=1` with `items=<JSON array>`; each item is one document:
//   {afm,name,address,city,zip,country,branch, type, series, payment, issue_lang,
//    notes, lines:[{code,qty,price[,disc,discType,rate,cat]}], taxes:[...]}
// Modes: default = DRAFT (savetempinvoice, nothing submitted); `live=1` = real issue
// (each gets a MARK). Returns a per-item result array so a partial batch is transparent.
if (!empty($_GET['bulk_issue'] ?? $_POST['bulk_issue'] ?? '')) {
    $itemsJson = trim($_POST['items'] ?? $_GET['items'] ?? '');
    $items = json_decode($itemsJson, true);
    if (!is_array($items) || empty($items)) { curl_close($ch); jsonError('Άκυρη ή κενή λίστα (items)'); }
    if (count($items) > 200) { curl_close($ch); jsonError('Πολλά παραστατικά σε μία παρτίδα (μέγιστο 200)'); }
    $bulkLive = !empty($_GET['live'] ?? $_POST['live'] ?? '');
    $results = [];
    $okCount = 0;
    foreach (array_values($items) as $idx => $it) {
        if (!is_array($it)) { $results[] = ['index' => $idx, 'success' => false, 'error' => 'Άκυρη γραμμή']; continue; }
        $bAfm    = trim((string)($it['afm'] ?? ''));
        $bType   = trim((string)($it['type'] ?? '58'));
        $bSeries = trim((string)($it['series'] ?? ''));
        $bPay    = (int)($it['payment'] ?? 3);
        $bName   = trim((string)($it['name'] ?? ''));
        $bLines  = is_array($it['lines'] ?? null) ? $it['lines'] : [];
        $bTaxes  = is_array($it['taxes'] ?? null) ? $it['taxes'] : [];
        $bLang   = (($it['issue_lang'] ?? 'el') === 'en') ? 'en' : 'el';
        $bNotes  = trim((string)($it['notes'] ?? ''));
        if (empty($bLines)) { $results[] = ['index' => $idx, 'afm' => $bAfm, 'success' => false, 'error' => 'Καμία γραμμή είδους']; continue; }
        if ($bSeries === '') { $results[] = ['index' => $idx, 'afm' => $bAfm, 'success' => false, 'error' => 'Λείπει η σειρά']; continue; }
        // Auto find/create the customer (GR ΑΦΜ) so the counterpart resolves.
        if ($bAfm !== '' && preg_match('/^\d{9}$/', $bAfm)) {
            $cust = findOrCreateCustomer($ch, $bAfm);
            if (!$cust['success']) { $results[] = ['index' => $idx, 'afm' => $bAfm, 'success' => false, 'error' => $cust['error'] ?? 'Αποτυχία πελάτη']; continue; }
        }
        $r = createInvoice(
            $ch, 0, $bType, $bPay, ($bNotes !== '' ? $bNotes : 'ΥΠ001'), '',
            $bAfm, $bName, trim((string)($it['address'] ?? '')), trim((string)($it['city'] ?? '')),
            trim((string)($it['zip'] ?? '')), trim((string)($it['country'] ?? 'GR')), trim((string)($it['branch'] ?? '0')),
            0, 0.0, $bulkLive, '', $bNotes, -1.0, 0, [], $bLines, $bSeries, $bTaxes, false, $bLang
        );
        $row = [
            'index'        => $idx,
            'afm'          => $bAfm,
            'name'         => $bName,
            'type'         => $bType,
            'success'      => (bool)($r['success'] ?? false),
            'amount_total' => $r['amount_total'] ?? null,
        ];
        if ($r['success'] ?? false) {
            $okCount++;
            if ($bulkLive) {
                $row['mark'] = $r['mark'] ?? ''; $row['aa'] = $r['aa'] ?? '';
                notifyIssue($r, ['doc_type' => $bType, 'series' => $bSeries, 'buyer_vat' => $bAfm, 'buyer_name' => $bName, 'source' => 'bulk']);
            }
            else { $row['temp_id'] = $r['temp_id'] ?? ''; }
        } else {
            $row['error'] = $r['error'] ?? 'Άγνωστο σφάλμα';
        }
        $results[] = $row;
    }
    curl_close($ch);
    jsonResponse([
        'success' => true,
        'live'    => $bulkLive,
        'total'   => count($results),
        'ok'      => $okCount,
        'failed'  => count($results) - $okCount,
        'results' => $results,
    ]);
}

// Delivery / return note (δελτίο αποστολής / επιστροφής)
if (!empty($_GET['delivery_note'] ?? $_POST['delivery_note'] ?? '')) {
    $delivery = [
        'movePurpose'    => trim($_GET['move_purpose'] ?? $_POST['move_purpose'] ?? '1'),
        'vehicleNumber'  => trim($_GET['vehicle'] ?? $_POST['vehicle'] ?? ''),
        'dispatchDate'   => trim($_GET['dispatch_date'] ?? $_POST['dispatch_date'] ?? ''),
        'dispatchTime'   => trim($_GET['dispatch_time'] ?? $_POST['dispatch_time'] ?? ''),
        'reverse'        => !empty($_GET['reverse'] ?? $_POST['reverse'] ?? ''),
        'load_street'    => trim($_GET['load_street'] ?? $_POST['load_street'] ?? ''),
        'load_number'    => trim($_GET['load_number'] ?? $_POST['load_number'] ?? ''),
        'load_zip'       => trim($_GET['load_zip'] ?? $_POST['load_zip'] ?? ''),
        'load_city'      => trim($_GET['load_city'] ?? $_POST['load_city'] ?? ''),
        'deliv_street'   => trim($_GET['deliv_street'] ?? $_POST['deliv_street'] ?? ''),
        'deliv_number'   => trim($_GET['deliv_number'] ?? $_POST['deliv_number'] ?? ''),
        'deliv_zip'      => trim($_GET['deliv_zip'] ?? $_POST['deliv_zip'] ?? ''),
        'deliv_city'     => trim($_GET['deliv_city'] ?? $_POST['deliv_city'] ?? ''),
        'load_branch'    => trim($_GET['load_branch'] ?? $_POST['load_branch'] ?? '0'),
        'deliv_branch'   => trim($_GET['deliv_branch'] ?? $_POST['deliv_branch'] ?? '0'),
    ];
    // Delivery-note type: 503=9.3 (default), 504=9.1 correlated, 505=9.2
    $dnType = trim($_GET['dn_type'] ?? $_POST['dn_type'] ?? '503');
    $dnSeries = trim($_GET['dn_series'] ?? $_POST['dn_series'] ?? '');

    // The δελτίο UI collects the customer only by ΑΦΜ/name and the loading/delivery
    // places — it does NOT carry the customer's registered seat address. AADE, though,
    // requires a full counterpart address (street/city/Τ.Κ.) on delivery notes. When
    // it's missing, fall back to the delivery place (the goods' destination), which the
    // user already supplies and which we validate below.
    if ($address === '' && ($delivery['deliv_street'] ?? '') !== '') $address = $delivery['deliv_street'];
    if ($city === ''    && ($delivery['deliv_city']   ?? '') !== '') $city    = $delivery['deliv_city'];
    if ($zip === ''     && ($delivery['deliv_zip']    ?? '') !== '') $zip     = $delivery['deliv_zip'];

    // Mandatory fields for δελτίο διακίνησης, per AADE's own newinvoice validation
    // (captured live from the e-timologio form). Missing any of these makes
    // PrintPreview/issue fail with a generic «Αδυναμία προεπισκόπησης» — so we
    // check them up front and return the specific, actionable message instead.
    $dnMissing = [];
    if ($dnSeries === '') {
        // 'A' is NOT a valid fallback: every delivery type needs its OWN registered
        // series (e.g. a 503 series). An unregistered series → generic reject.
        $dnMissing[] = 'Σειρά παραστατικού (δημιουργήστε μία σειρά για δελτίο αποστολής στις Ρυθμίσεις → Σειρές)';
    }
    if ($afm === '' || !preg_match('/^\d{9}$/', $afm)) $dnMissing[] = 'ΑΦΜ πελάτη (υποχρεωτικό στα δελτία διακίνησης)';
    if ($address === '') $dnMissing[] = 'Διεύθυνση πελάτη';
    if ($city === '')    $dnMissing[] = 'Πόλη πελάτη';
    if ($zip === '')     $dnMissing[] = 'Τ.Κ. πελάτη';
    if (($delivery['load_zip'] ?? '') === '')    $dnMissing[] = 'Τ.Κ. τόπου φόρτωσης';
    if (($delivery['deliv_number'] ?? '') === '') $dnMissing[] = 'Αριθμός τόπου παράδοσης';
    if (($delivery['deliv_zip'] ?? '') === '')    $dnMissing[] = 'Τ.Κ. τόπου παράδοσης';
    if (!empty($dnMissing)) {
        curl_close($ch);
        jsonResponse([
            'success' => false,
            'error'   => 'Απαιτούνται τα ακόλουθα για το δελτίο διακίνησης: ' . implode(' · ', $dnMissing),
            'missing' => $dnMissing,
        ]);
    }
    if ($afm !== '' && preg_match('/^\d{9}$/', $afm)) {
        $cust = findOrCreateCustomer($ch, $afm);
        if (!$cust['success']) { curl_close($ch); jsonResponse($cust); }
        // Remember the delivery branch/address for this customer for next time.
        customer_deliv_set(COMPANY_VAT, $afm, [
            'branch' => $delivery['deliv_branch'],
            'street' => $delivery['deliv_street'], 'number' => $delivery['deliv_number'],
            'city'   => $delivery['deliv_city'],   'zip'    => $delivery['deliv_zip'],
        ]);
    }
    // Optional multi-line delivery note — same `lines` JSON as invoices.
    $dnLines = [];
    $dnLinesJson = trim($_GET['lines'] ?? $_POST['lines'] ?? '');
    if ($dnLinesJson !== '') {
        $dnLines = json_decode($dnLinesJson, true);
        if (!is_array($dnLines)) $dnLines = [];
    }
    $result = createInvoice(
        $ch, $amount, $dnType, $payment, $descr, '',
        $afm, $name, $address, $city, $zip, $country, $branch,
        0, 0.0, $live, '', trim($_GET['notes'] ?? $_POST['notes'] ?? ''), -1.0, 0, $delivery, $dnLines, $dnSeries, [], $previewFlag, $issueLang, [], $reuseTempId
    );
    curl_close($ch);
    jsonResponse($result);
}

// Multi-line invoice — `lines` is a JSON array of {code, qty, price[, rate, cat]}
$linesJson = trim($_GET['lines'] ?? $_POST['lines'] ?? '');
if ($linesJson !== '') {
    $linesArr = json_decode($linesJson, true);
    if (!is_array($linesArr) || empty($linesArr)) { curl_close($ch); jsonError('Άκυρες γραμμές (lines)'); }
    if ($afm !== '' && preg_match('/^\d{9}$/', $afm)) {
        $cust = findOrCreateCustomer($ch, $afm);
        if (!$cust['success']) { curl_close($ch); jsonResponse($cust); }
    }
    $taxesArr = json_decode(trim($_GET['taxes'] ?? $_POST['taxes'] ?? ''), true);
    if (!is_array($taxesArr)) $taxesArr = [];
    $result = createInvoice(
        $ch, 0, $type, $payment, $descr, '',
        $afm, $name, $address, $city, $zip, $country, $branch,
        $withholdingCategory, $withholdingAmount, $live, '',
        trim($_GET['notes'] ?? $_POST['notes'] ?? ''), -1.0, 0, [], $linesArr, $issueSeries, $taxesArr, $previewFlag, $issueLang, [], $reuseTempId
    );
    curl_close($ch);
    if ($live && !$previewFlag) notifyIssue($result, ['doc_type' => $type, 'series' => $issueSeries, 'buyer_vat' => $afm, 'buyer_name' => $name]);
    jsonResponse($result);
}

// PDF retrieval by MARK — takes priority over all other parameters
if ($mark !== '') {
    getInvoicePdf($ch, $mark);
}

// Bulk / per-customer PDF download as ZIP
if (!empty($_GET['invoices_zip'] ?? $_POST['invoices_zip'] ?? '')) {
    $marksParam = trim($_GET['marks'] ?? $_POST['marks'] ?? '');
    $marks = [];
    if ($marksParam !== '') {
        $marks = array_filter(array_map('trim', explode(',', $marksParam)));
        $zipName = 'invoices.zip';
    } else {
        $bv = $buyerVatFilter !== '' ? $buyerVatFilter : $afm;
        $r  = searchInvoices($ch, $issueDateFrom, $issueDateTo, $searchInvoiceType, '', $seriesFilter, $bv, '0');
        foreach (($r['invoices'] ?? []) as $iv) {
            if (!empty($iv['mark'])) $marks[] = $iv['mark'];
        }
        $zipName = $bv !== '' ? ('invoices-' . preg_replace('/\D/', '', $bv) . '.zip') : 'invoices.zip';
    }
    if (empty($marks)) { curl_close($ch); jsonError('Δεν βρέθηκαν παραστατικά για ZIP'); }
    streamInvoicesZip($ch, $marks, $zipName);
}

if ($deleteCustomerCode !== '' || $deleteCustomerVat !== '') {
    $result = deleteCustomerBySelector($ch, $deleteCustomerVat, $deleteCustomerCode);
    curl_close($ch);
    jsonResponse($result);
}

if ($deleteTempId !== '') {
    $result = deleteTempInvoiceById($ch, $deleteTempId, $sellerVat);
    curl_close($ch);
    jsonResponse($result);
}

if ($deleteSeriesId !== '') {
    $result = deleteSeriesById($ch, $deleteSeriesId);
    curl_close($ch);
    jsonResponse($result);
}

if ($deleteDeductionCode !== '') {
    $result = deleteDeductionByCode($ch, $deleteDeductionCode);
    curl_close($ch);
    jsonResponse($result);
}

if ($deleteProductCode !== '') {
    $result = deleteProductByCode($ch, $deleteProductCode);
    curl_close($ch);
    jsonResponse($result);
}

if ($deleteCategoryId !== '') {
    $result = deleteProductCategoryById($ch, $deleteCategoryId);
    curl_close($ch);
    jsonResponse($result);
}

if ($newSeriesFlag) {
    $result = createSeries(
        $ch,
        $seriesInvoiceType,
        $seriesCode,
        $seriesStartAa,
        $seriesDescription,
        $seriesIsTransFail
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($updateSeriesId !== '') {
    $result = updateSeries(
        $ch,
        $updateSeriesId,
        $seriesInvoiceType,
        $seriesCode,
        $seriesStartAa,
        $seriesDescription
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($newDeductionFlag) {
    $result = createDeduction(
        $ch,
        $deductionDesc,
        $deductionAmtType,
        $deductionAmt,
        $deductionDecPaid
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($updateDeductionCode !== '') {
    $result = updateDeduction(
        $ch,
        $updateDeductionCode,
        $deductionDesc,
        $deductionAmtType,
        $deductionAmt,
        $deductionDecPaid
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($createPersonalCust) {
    $result = createPersonalCustomer(
        $ch,
        $custName,
        $custAddress,
        $custCity,
        $custZip,
        $custDoy,
        $custCountry,
        $custJobDescription,
        $custEmail,
        $custPhone1,
        $custPhone2,
        $custLanguage,
        $custIsB2G,
        $custCode,
        $custVat,
        $custOldVat
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($updateCustomerFlag) {
    $result = updateCustomer(
        $ch,
        $updateCustomerVat,
        $updateCustomerCode,
        $updatePhone1,
        $updatePhone2,
        $updateEmail,
        $updateJobDesc,
        $updateAddress,
        $updateCity,
        $updateZip,
        $updateDoy,
        $updateName
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($listCustomers || $allCustomers) {
    $result = listCustomers(
        $ch,
        $afm,
        $customerCodeFilter,
        $customerNameFilter,
        $allCustomers,
        $customersPageSize,
        $customersMaxPages
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($searchInvoicesFlag) {
    $result = searchInvoices(
        $ch,
        $issueDateFrom,
        $issueDateTo,
        $searchInvoiceType,
        $mark,
        $seriesFilter,
        $buyerVatFilter,
        $invoiceStatusFilter,
        $searchCounterpart,
        $searchB2G
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($searchTempFlag) {
    // NB: use a dedicated temp_type filter (NOT $type, which defaults to '58' for
    // invoice creation and would wrongly filter out every draft).
    $result = searchTempInvoices(
        $ch,
        $saveDateFrom,
        $saveDateTo,
        trim($_GET['temp_type'] ?? $_POST['temp_type'] ?? ''),
        $buyerVatFilter,
        $tempInvoiceIdFilter
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($listSeriesFlag) {
    $result = listSeries($ch);
    curl_close($ch);
    jsonResponse($result);
}

if ($listDeductionsFlag) {
    $result = listDeductions($ch);
    curl_close($ch);
    jsonResponse($result);
}

if ($listProductsFlag) {
    $result = listProducts($ch);
    curl_close($ch);
    jsonResponse($result);
}

if ($listCategoriesFlag) {
    $result = listProductCategories($ch);
    curl_close($ch);
    jsonResponse($result);
}

if ($newProductFlag) {
    $result = createProduct(
        $ch, $productType, $productCode, $productDescription,
        $productCategory, $taricCode, $unitPrice, $vatCategory,
        $unit, $specialType, $feesWithVAT, $otherTaxesWithVAT
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($updateProductCode !== '') {
    $result = updateProduct(
        $ch, $updateProductCode, $productType, $productDescription,
        $productCategory, $taricCode, $unitPrice, $vatCategory,
        $unit, $specialType, $feesWithVAT, $otherTaxesWithVAT
    );
    curl_close($ch);
    jsonResponse($result);
}

if ($newCategoryFlag) {
    $result = createProductCategory($ch, $categoryName);
    curl_close($ch);
    jsonResponse($result);
}

if ($updateCategoryId !== '') {
    $result = updateProductCategory($ch, $updateCategoryId, $categoryName);
    curl_close($ch);
    jsonResponse($result);
}

if ($companyProfileFlag) {
    $result = getCompanyProfile($ch);
    curl_close($ch);
    jsonResponse($result);
}

if ($companyFromTaxis) {
    $result = getCompanyFromTaxis($ch);
    curl_close($ch);
    jsonResponse($result);
}

// Validate AFM — 9 digits required for GR clients only
if ($afm !== '' && $country === 'GR' && !preg_match('/^\d{9}$/', $afm)) {
    jsonError('Invalid AFM - must be 9 digits for Greek clients');
}

if ($amount > 0) {
    // Invoice flow — find/create customer for GR clients only
    if ($afm !== '' && preg_match('/^\d{9}$/', $afm)) {
        $customer = findOrCreateCustomer($ch, $afm);
        if (!$customer['success']) {
            curl_close($ch);
            jsonResponse($customer);
        }
    }
    $result = createInvoice(
        $ch, $amount, $type, $payment, $descr, '',
        $afm, $name, $address, $city, $zip, $country, $branch,
        $withholdingCategory, $withholdingAmount, $live, '', '', -1.0, 0, [], [], $issueSeries
    );
    curl_close($ch);
    if ($live) notifyIssue($result, ['doc_type' => $type, 'series' => $issueSeries, 'buyer_vat' => $afm, 'buyer_name' => $name]);
    jsonResponse($result);
} else {
    // Customer lookup flow
    if ($afm === '') jsonError('Missing AFM parameter');
    $result = findOrCreateCustomer($ch, $afm);
}

curl_close($ch);
jsonResponse($result);
