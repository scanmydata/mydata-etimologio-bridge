# Production TODO vs Official timologio Manual

## Priority A (Core gaps)
- [x] Invoice categories full CRUD (manual section 7): create/update/delete with server-side validations and dependency checks.
- [x] Deductions full CRUD (manual section 8): create/update/list/delete with business rules.
- [x] Classifications (χαρακτηρισμοί) logic (manual section 9): per-line income/VAT classifications driven by product+type (`?classifications=1`); all product classifications emitted on issue. Category-level classification editing done: `?cls_options=1&type=` (allowed income categories+E3 codes per invoice type from the myDATA validation doc), `?category_cls=1` (categories with their existing classifications + invoice-type list), `?save_category_cls=1` (create/update a product category with `categoryClassifications`). UI editor in the Είδη view. Verified via create/update/delete of a temp category.
- [x] Delivery / return note (δελτίο αποστολής-επιστροφής, manual section ~12 / types 9.x): `?delivery_note=1` with movePurpose, dispatch, vehicle, loading/delivery address, reverse. Verified via draft. UI revamp: dynamic type + series dropdowns (`dn_series`, series filtered per 9.x code via `DN_CODE` map), customer autocomplete (+new customer), product-line combobox (like issue, shows code+desc+VAT), loading place from company base (`?company_profile=1`, parsed) with localStorage reuse, per-customer delivery branch (0=κεντρικό) + address saved/loaded via `?cust_deliv=1` / `?save_cust_deliv=1` (encrypted `customer_meta.deliv_meta`; also auto-saved on issue). `startShippingBranch`/`completeShippingBranch` wired to load/deliv branch. Verified via draft (type 503, deleted after).
- [x] Delivery-note draft PDF: «Προεπισκόπηση» button generates a client-side jsPDF draft (issuer/recipient, movement info, loading/delivery + branches, lines table, net total, notes, ΠΡΟΧΕΙΡΟ watermark). Verified.
- [x] Local encrypted cache + background sync for instant UI (`?cached=`, `?sync=`).
- [x] Customer ledger PDF export (χρεώσεις-πιστώσεις) via jsPDF with Greek font.
- [x] Invoice PDF download: single, bulk by date, per-customer ZIP (`?invoices_zip=1`).
- [x] Verified: deductions CRUD, withholding tax in invoices, payment methods.
- [x] Full customer edit flow (manual section 11.2): load/edit/save existing customer from ViewCustomer flow.
- [x] Invoice cancellation endpoint (manual section 12.4): implemented as correlated credit note (`?credit_note=1&cancel_mark=MARK`) — 5.1 for invoices, 11.4 for retail (auto-detected). Verified via draft.
- [~] Draft invoice workflow (manual section 12.5): Πρόχειρα view lists temp invoices (`?search_temp=1`) with delete (`?delete_temp_id=&seller_vat=`). Open/edit/reissue-from-draft still TODO — needs replicating e-timologio's `/invoice/NewInvoiceByTmpInvoice?tempInvoiceId=<encrypted token>` prefilled-form flow (no re-postable model; our AADE session is server-side only).
- [x] Series (σειρά) selection on issue: `createInvoice` `$series` param + `issue_series`; UI per-type series dropdown with inline "new series" create. (Was hardcoded to 'A'.)

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

## Notes
- Manual baseline used: `manualTIMOLOGIO.pdf` / `manualTIMOLOGIO.txt`.
- Current implementation already covers invoice search, PDF retrieval by MARK, customer list/create/delete, personal customer create (no AFM), product/category CRUD basics, series/deductions/product/category listing, and selected delete flows.
