# Production TODO vs Official timologio Manual

## Priority A (Core gaps)
- [x] Invoice categories full CRUD (manual section 7): create/update/delete with server-side validations and dependency checks.
- [x] Deductions full CRUD (manual section 8): create/update/list/delete with business rules.
- [x] Classifications (χαρακτηρισμοί) logic (manual section 9): per-line income/VAT classifications driven by product+type (`?classifications=1`); all product classifications emitted on issue. Category-level classification editing done: `?cls_options=1&type=` (allowed income categories+E3 codes per invoice type from the myDATA validation doc), `?category_cls=1` (categories with their existing classifications + invoice-type list), `?save_category_cls=1` (create/update a product category with `categoryClassifications`). UI editor in the Είδη view. Verified via create/update/delete of a temp category.
- [x] Delivery / return note (δελτίο αποστολής-επιστροφής, manual section ~12 / types 9.x): `?delivery_note=1` with movePurpose, dispatch, vehicle, loading/delivery address, reverse. Verified via draft. UI revamp: dynamic type + series dropdowns (`dn_series`, series filtered per 9.x code via `DN_CODE` map), customer autocomplete (+new customer), product-line combobox (like issue, shows code+desc+VAT), loading place from company base (`?company_profile=1`, parsed) with localStorage reuse, per-customer delivery branch (0=κεντρικό) + address saved/loaded via `?cust_deliv=1` / `?save_cust_deliv=1` (encrypted `customer_meta.deliv_meta`; also auto-saved on issue). `startShippingBranch`/`completeShippingBranch` wired to load/deliv branch. Verified via draft (type 503, deleted after).
- [x] Delivery-note draft PDF: «Προεπισκόπηση» button generates a client-side jsPDF draft (issuer/recipient, movement info, loading/delivery + branches, lines table, net total, notes, ΠΡΟΧΕΙΡΟ watermark). Verified.
- [x] Real AADE preview PDF (invoices): `?preview=1` saves the draft then POSTs the model to `/Invoice/PrintPreviewInvoice2PdfNew`, which returns the genuine AADE PDF directly (`application/pdf`, not a `data2print` JSON — the client-renderer theory was wrong). Model must match the form exactly: **empty issuer** (server fills identity), `issueDate` in **Y-n-j** (no zero-pad), per-line tax buckets (`withheld/stamp/fees/otherTaxes/deductions=0`), no `invoiceSummary`. Bridge returns `pdf_b64`; `previewInvoice()` opens it. Verified against the live authenticated server (200 `%PDF-1.4`, 97906 bytes).
- [x] Real AADE preview for **delivery notes** and **credit/cancellation notes** too: both go through the same `?preview=1` → `PrintPreviewInvoice2PdfNew` path. `createCreditNote` now takes `$preview`/`$issueLang` and forwards them; the delivery-note handler already forwarded `$previewFlag`. UI: `dnPreviewPdf()` opens the real AADE `pdf_b64` and only falls back to the local jsPDF draft if AADE declines; the credit-note card has a «👁 Προεπισκόπηση» button (`previewCredit()`). Since delivery-note and credit drafts already save via savetempinvoice with these exact field names, the same model is accepted by the preview endpoint. (Invoice path verified byte-for-byte against the live server; DN/credit wired identically with a safe fallback.)
- [x] Local encrypted cache + background sync for instant UI (`?cached=`, `?sync=`).
- [x] Customer ledger PDF export (χρεώσεις-πιστώσεις) via jsPDF with Greek font.
- [x] Invoice PDF download: single, bulk by date, per-customer ZIP (`?invoices_zip=1`).
- [x] Verified: deductions CRUD, withholding tax in invoices, payment methods.
- [x] Full customer edit flow (manual section 11.2): load/edit/save existing customer from ViewCustomer flow.
- [x] Invoice cancellation endpoint (manual section 12.4): implemented as correlated credit note (`?credit_note=1&cancel_mark=MARK`) — 5.1 for invoices, 11.4 for retail (auto-detected). Verified via draft.
- [~] Draft invoice workflow (manual section 12.5): Πρόχειρα view lists temp invoices (`?search_temp=1`) with delete (`?delete_temp_id=&seller_vat=`). Open/edit/reissue-from-draft still TODO — needs replicating e-timologio's `/invoice/NewInvoiceByTmpInvoice?tempInvoiceId=<encrypted token>` prefilled-form flow (no re-postable model; our AADE session is server-side only).
- [x] Series (σειρά) selection on issue: `createInvoice` `$series` param + `issue_series`; UI per-type series dropdown with inline "new series" create. (Was hardcoded to 'A'.)
- [x] Dedicated **Σειρές** management view (app.php): list all registered series, create a series for ANY invoice type (`?new_series=1&series_invoice_type=&series_code=&series_start_aa=&series_description=`), delete (`?delete_series_id=`). Backend `createSeries`/`deleteSeriesById` verified (created+deleted a 503 test series). Every invoice type needs ≥1 registered series to issue/preview.
- [~] Real AADE preview for delivery notes & credit notes: wired through the same `?preview=1` → `PrintPreviewInvoice2PdfNew` path (invoice preview verified end-to-end via the real bridge, %PDF). Fixed real model bugs found by a local CLI test harness: emit `quantity`/`measurementUnit` only for delivery notes or qty≠1 (services forbid them — this had been breaking the invoice preview too), add `toWeigh`, always send `reverseDeliveryNote`(+purpose) for 9.3, resolve the correct credit-note series (ΠΤ) instead of 'A', and use classification `category3` (Διακίνηση, no E3 code) for delivery notes. STILL OPEN: (a) 503 delivery-note preview still returns a generic «Αδυναμία προεπισκόπησης» despite valid goods item + series + category3 + measurementUnit — needs a captured real 503 preview to find the last missing field; (b) credit-note preview reaches business validation but always reports «το πληρωτέο/καθαρή αξία δεν μπορεί να είναι μεγαλύτερη του συσχετιζόμενου» — the correlation of the original invoice's values isn't established for the preview. Both fall back to the local draft/error message in the UI.

## Priority B (Invoice issuance parity)
- [x] Multi-line invoices (manual section 12.2.3): `?lines=[...]` JSON, per-line product/qty/price/VAT/classifications, live net total in UI.
- [x] Per-line discounts: each `lines[]` entry accepts `disc` (percentage by default, or absolute € with `discType:"amount"`); line emits `netValueWithoutDiscount`/`discountAmount`/`netValueWithDiscount`. UI has an «Έκπτωση %» column. Verified via draft (10% and absolute €).
- [x] Multi-line delivery notes: `?delivery_note=1` accepts the same `lines=[...]` JSON; UI Δελτίο view has a line editor. Verified via draft.
- [ ] Misc taxes API parity (manual section 12.2.4): all tax categories and constraints as in UI.
- [ ] Invoice notes/remarks parity (manual section 12.2.5) with full validation.
- [ ] Totals/rounding parity tests (manual section 12.2.6) against UI outputs.
- [ ] Counterpart/related invoice MARK helper flows (manual section 12.2.1 / 12.3).

## Priority C (Reporting & account features)
- [x] Statistics endpoints (manual section 13): expose statistics views as API JSON (`?statistics=1`, parsed from `/Dashboard/DashboardByDate`).
- [x] Multi-tenant accounts: `$ACCOUNTS` in config, per-request `account` selection, per-account cookie jar.
- [x] Local payments + customer ledger (καρτέλα): SQLite store, `?ledger=1` combines issued invoices with local payments into a running balance (e-timologio has no payment/ledger endpoint).
- [x] New self-contained UI (`app.php`): account switcher, statistics, smart customer search, ledger, products, issue.
- [x] Multi-client login (`auth.php`): master admin + business accounts, public signup with admin approval, login/logout, forgot/reset (admin token link + optional SMTP email), change password. Access to `app.php`/`etimologio.php` gated by session. Verified end-to-end.
- [x] AADE credentials moved to the encrypted DB (per business user, managed by master admin); legacy `$ACCOUNTS` auto-migrated to the master on first run. Admin panel + Ρυθμίσεις view in `app.php`.
- [x] UI polish: verbal invoice-type labels (stats/card/PDF), customer autocomplete + «Έκδοση» from customer rows, issue type list limited to types with an active series, inline product picker showing description + VAT per line.
- [x] Ledger PDF redesigned (καρτέλα layout: header band, customer block, Ημ/νία·Παραστατικό·Χρέωση·Πίστωση·Υπόλοιπο with totals) keeping the app's colors/font.
- [ ] Summary book endpoints (manual section 15): export/retrieve summary book data.
- [ ] Company settings update endpoints (manual section 6): persist profile edits (not only read/get from taxis).
- [ ] User/account management related capabilities where technically feasible (manual section 2.2): document unsupported flows that require interactive auth.

## Reliability & Production hardening
- [ ] Add integration tests for HTML parsing on all key pages (customers/invoices/temp/products/series).
- [ ] Add resilient retries + timeout strategy for transient AADE failures.
- [ ] Add structured logging and request correlation IDs.
- [ ] Add API versioning and changelog policy for upstream UI/manual changes.
- [ ] Add secure secret management guidance (environment variables/secret store).
- [ ] Add health-check endpoint and smoke-test script for login/search/pdf lifecycle.

## Changelog / decisions (2026-08)
Done & verified (real bridge, %PDF where relevant):
- [x] Real AADE preview for **credit notes** (5.1/50): root cause was empty `ccr_totalNetValueWithDisc`/`ccr_grossValue` (must be populated) + must NOT send a `paymentMethods` block. Correlated via top-level `CorrelatedInvoice`=MARK + line values mirroring the original.
- [x] Real AADE preview for **delivery notes** (9.3/503): line `vatCategory`=8 (Άνευ ΦΠΑ), empty `paymentType`/`currency`/`ccr_*`, add per-line `movePurposeLine`, `dispatchDate` in Y-n-j, DispatchTime ≥ current Greece time; needs a 503 series + full counterpart address + loading/delivery Τ.Κ.
- [x] **Universal preview from Πρόχειρα** (`?preview_temp=<enc_id>`): fetch the draft model via `/Invoice/TempInvoice?encTempInvoiceId=`, whitelist-reshape → postable model → %PDF. Works for ANY draft (even AADE-created). `searchTempInvoices` now returns `enc_id` per row.
- [x] **Merged Save+Preview** + draft-ID reuse (`temp_id` param → savetempinvoice updates in place; UI keeps `__issueTempId/__dnTempId/__cxTempId`).
- [x] **Μαζική έκδοση** (`?bulk_issue=1`, items JSON, per-item results, draft/live) + UI «Μαζική» view (CSV import).
- [x] **Χαρακτηρισμοί ανά είδος**: trust the product's AADE per-type classification (GetProduct?invoiceType=), remap only the guessed fallback (was corrupting E3_561_007 etc.).
- [x] **Light/Dark theme** (toggle switch bottom-left, localStorage) + tooltips (`data-tip`); flash messages moved top-right.
- [x] **Ακύρωση**: «Αναζήτηση χρεωστικών» works with date-range only (customer optional) + counterpart column.
- [x] **Admin**: businesses list (all AADE accounts) so ΤΟ ΒΑΨΙΜΟ shows; admin framed as manager, not a business.
- [x] **Δελτίο removed from the side menu** — reachable via the Έκδοση wizard (step 1). View kept.
- [x] **Σειρές creation → popup** (`#seriesModal`) opened by «➕ Νέα σειρά», with a green «➕ Εισαγωγή σειράς» button; result/refresh in place.
- [x] **Cache everything from e-timologio** (like πελάτες): sync now also handles `series`/`invtypes`/`categories`/`deductions`; cache-first loaders (`loadInvTypes`, `loadIssueTypes` via `applyIssueSeries()`, `loadCatCls`) read the SQLite snapshot instantly then refresh; `prewarmAll()` warms all snapshots in the background on login. Verified end-to-end (series 5, invtypes 24, categories 3; cached read = 0 AADE logins).

Open (requested, next):
- [x] Έκδοση **guided start screen** (`#issueWizard`): step 1 Τιμολόγιο/Απόδειξη vs Δελτίο (routes to the Δελτίο view); step 2 Επαγγελματίας vs Ιδιώτης → auto-picks the matching registered invoice type (τιμολ / λιανικ) and focuses ΑΦΜ (pro) or Επωνυμία (ιδιώτης). `wizSkip()` bypasses it for Πελάτες→Έκδοση (`issueFor`) and the φωνητικό (`cbDoIssue`). Shows on fresh open; «↺ Αλλαγή επιλογής» re-opens it. Voice map already routes «τραπέζ/μαζικ» too.
- [ ] **Interactive μαζική έκδοση** (customer/product pickers instead of typing ΑΦΜ/codes).
- [ ] **Column filters + row selection** (checkboxes, select-all) + restyle ALL tables to the *timologio-downloader* look; better panels/frames in Έκδοση.
- [ ] **Auto-compute taxes/withholdings** (φόροι-κρατήσεις) on the issue form.
- [x] **Number formatting** on blur for unit-price & total-with-VAT (el-GR thousands `.`, decimals `,`): fields are now text+inputmode=decimal, formatted on blur (price ≤4 decimals, gross 2). `elNum()` parses el-GR OR plain (last separator = decimal) and `elFmt()` renders; every read of `.ln-price`/`.ln-gross` uses `elNum` so the invoice math is unchanged. Verified with parse/format/round-trip unit tests (all pass).
- [ ] **Prefill issue form** correctly from Πελάτες→Έκδοση (`issueFor`).
- [ ] Perf: new-category-with-suggested-classification loads slowly.
- [x] **Bulk payment import from bank extraits** — `bankimport.php` parses CSV (Eurobank, `;`-sep, **CP1253 via iconv** — mbstring here lacks the codepage) and XLSX (Optima/Εθνική, ZipArchive+SimpleXML). Column mapping is by **header-keyword detection** (not fixed indices) so it tolerates layout differences; handles both a single signed `Ποσό` column and separate `Χρέωση/Πίστωση`; parses Greek money `1.234,56` / `(…)` / Excel serial dates; sniffs a 9-digit ΑΦΜ from the description. Endpoints `?bank_preview` (parse + attach customers) and `?bank_import` (register up to 500 payments). UI: **Εισαγωγή τραπέζης** view — upload → analyse → per-row customer auto-match (ΑΦΜ or fuzzy name) with editable picker + include checkboxes/select-all → «Καταχώρηση». **IMPORTANT: deposit amount ≠ customer balance** — each row is a standalone payment stored as-is (partial/over-payments allowed), NO invoice reconciliation. Verified end-to-end via harness (CSV+XLSX, add+delete). Voice: «τραπέζ/extrait» → bankimp.
  - Still open: real per-bank sample files were not on disk this session — detection is generic; when actual Optima/Εθνική exports are available, confirm their exact headers land on the right fields (add explicit presets if needed). MARK-level matching (link a payment to a specific invoice) not implemented — payments attach to the customer only.
- [ ] Future: merge into `github.com/scanmydata/MyData-Invoice-Downloader` — run all locally; web = client-side; single client logs in & issues; admin-accountant notified of new movements (issue/save/payment).

## Notes
- Manual baseline used: `manualTIMOLOGIO.pdf` / `manualTIMOLOGIO.txt`.
- Current implementation already covers invoice search, PDF retrieval by MARK, customer list/create/delete, personal customer create (no AFM), product/category CRUD basics, series/deductions/product/category listing, and selected delete flows.
