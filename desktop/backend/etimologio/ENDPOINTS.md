# e-Timologio — Discovered Endpoints Map

Reverse-engineered from the live e-timologio app (`https://mydata.aade.gr/timologio`)
by inspecting rendered pages + JS bundles (`invoice.js`, `invoiceAjax.js`,
`myDATAInvoicing.js`) while authenticated. **No invoices were issued during discovery.**

All AJAX calls are built as `_g_Application_Url + '/Controller/Action'`, where
`_g_Application_Url = '/timologio'`. Auth is a form POST to `/Account/Login`
(fields: `UserName`, `VatNumber`, `SubscriptionKey`, `ReturnUrl`,
`__RequestVerificationToken`) which sets `.AspNetCore.Identity.Application` +
`.AspNetCore.Session` cookies.

> Note: the above is the **upstream AADE** login. Our app adds its own login layer
> (`auth.php`, PHP session cookie `ETIM_SID`) in front: businesses authenticate to *our*
> app, and the bridge then performs the AADE login using that business's AADE
> credentials (stored encrypted in the DB). See "App auth" below.

## App auth & multi-client (our layer, not AADE)
`auth.php` gates `app.php` and `etimologio.php`. Users + AADE credentials live in the
encrypted SQLite DB (`users`, `aade_accounts`). A master admin (bootstrapped from
`MASTER_ADMIN_EMAIL`/`MASTER_ADMIN_PASSWORD` in config) approves public signups and links
each business's AADE username/subscription-key (encrypted). The active AADE account is
resolved per session from the logged-in user's accounts (by `?account=<vat>`), replacing
the legacy `config.php` `$ACCOUNTS` resolution (which is skipped when `SKIP_ACCOUNT_RESOLUTION`
is defined and auto-migrated to the master on first run).
Actions: `POST ?auth=login|logout|me|signup|forgot|reset|change_password` and master-only
`?auth=admin_users|admin_create_user|admin_approve|admin_set_status|admin_reset_pw|admin_add_account|admin_update_account|admin_delete_account|admin_user_accounts`.
Password reset generates a token (1h; admin tokens 24h); emailed if `SMTP_FROM` set, else
handed over via the admin panel. All non-auth bridge actions return HTTP 401 without a session.

## Navigation map (left menu)

| Menu label | Route |
|---|---|
| Νέος Πελάτης | `/customer/NewCustomer` |
| Προβολή Πελατών | `/customer/ListCustomers` |
| Έκδοση | `/invoice/newinvoice` |
| Διαβίβαση Σύνοψης | `/invoice/newsynopsis` |
| Αναζήτηση/Προβολή | `/invoice/listinvoices` |
| Προσωρινά Αποθηκευμένα | `/tempinvoice/tempinvoices` |
| Επιχείρηση | `/company/company` |
| Κατηγορίες Παραστατικών | `/series/ListSeries` |
| Κατηγορίες (ειδών) | `/product/productCategories` |
| Δημιουργία / Προβολή (ειδών) | `/product/products` |
| Κρατήσεις | `/deduction/ListDeductions` |
| Στατιστικά | `/Dashboard/Dashboard` |

## Endpoint status vs. existing PHP bridge

### Already implemented in `etimologio.php`
`/Account/Login`, `/customer/ListCustomers`, `/customer/SearchCustomers`,
`/customer/NewCustomer`, `/Customer/GetCustomerByTaxis`,
`/Customer/GetProposedCustomersByName`, `/Customer/DeleteCustomer`,
`/Customer/viewcustomer` (update flow), `/invoice/ListInvoices`,
`/invoice/SearchInvoices`, `/Invoice/create`, `/TempInvoice/savetempinvoice`,
`/TempInvoice/DeleteTempInvoice`, `/tempinvoice/SearchTempInvoices`,
`/Invoice/PrintInvoice2PdfNew`, `/Product/GetProduct`, `/product/products`,
`/product/create`, `/Product/Delete`, `/product/productCategories`,
`/product/createCategory`, `/Product/DeleteCategory`, `/series/ListSeries`,
`/series/NewSeries`, `/series/updateseries`, `/Series/DeleteSeries`,
`/deduction/ListDeductions`, `/deduction/NewDeduction`,
`/Deduction/DeleteDeduction`, `/company/company`, `/Company/GetCompanyByTaxis`.

### NEW — discovered, not yet in the bridge
| Endpoint | Method | Purpose | Verified |
|---|---|---|---|
| `/Dashboard/Dashboard` | GET | Statistics dashboard (current month) | ✅ 200, data server-rendered in page |
| `/Dashboard/DashboardByDate?type=month\|preMonth\|year` | GET | Statistics by period; chart data embedded as `labels:[...]` / `data:[...]` | ✅ 200 (real data parsed) |
| `/invoice/newsynopsis` | GET | Διαβίβαση Σύνοψης (summary transmission) page | ⚠️ 500 without params |
| `/Invoice/PrintPreviewInvoice2Pdf` / `...PdfNew` | POST | Render invoice PDF preview BEFORE issuing | not exercised (avoid issuance side) |
| `/Invoice/SearchForDigitalClients` | GET/POST | B2G digital client lookup (JSON) | ✅ 200 JSON (`success:false` w/o valid term) |
| `/Customer/viewcustomer` | GET | Full customer view/edit form | ✅ 200 |
| `/invoice/NewInvoiceByCustomerList` | GET | Start invoice pre-filled from a customer | discovered (link) |
| `/Invoice/B2GBridgePeppol` + `/Invoice/B2GBridgePeppolPost?em=` | POST/GET | B2G / Peppol bridge | discovered (JS) |
| `/Invoice/GetValidationDoc` | GET/POST | Invoice validation document data | discovered (JS) |
| `/customer/getcustomersautocomplete` | GET | Customer autocomplete | ⚠️ 404 with `term=` (param name differs) |
| `/Invoice/TempInvoice` | GET | Load a temp invoice for editing | discovered (JS) |

### Not found (confirmed absent in e-timologio)
- **Payments / receipts** — no payment endpoint exists. e-timologio does NOT track
  customer payments or balances.
- **Customer ledger / καρτέλα πελάτη** — no ledger endpoint. Per-customer history can
  only be reconstructed by filtering `/invoice/SearchInvoices` by `buyer_vat`.

> Implication: a payments + customer-card (καρτέλα) feature must be stored **locally**
> (bridge-side), reconciled against issued invoices fetched from e-timologio.

## Invoice type codes (`_invoiceType` select on `/invoice/newinvoice`)
| Code | Type | | Code | Type |
|---|---|---|---|---|
| 1 | 1.1 Τιμολόγιο Πώλησης | | 51 | 5.2 Πιστωτικό (Μη συσχ.) |
| 2 | 1.2 Πώληση / Ενδοκοινοτικές | | 52 | 6.1 Αυτοπαράδοση |
| 3 | 1.3 Πώληση / Τρίτες Χώρες | | 53 | 6.2 Ιδιοχρησιμοποίηση |
| 4 | 1.4 Πώληση για Λογ. Τρίτων | | 55 | 8.1 Ενοίκια / Έσοδο |
| 20 | 2.1 Παροχή Υπηρεσιών | | 56 | 8.2 Τέλος ανθεκτικότητας |
| 21 | 2.2 Ενδοκοινοτική Παροχή | | 57 | 11.1 ΑΛΠ |
| 22 | 2.3 Παροχή Τρίτων Χωρών | | 58 | 11.2 ΑΠΥ |
| 30 | 3.1 Τίτλος Κτήσης | | 59 | 11.3 Απλοποιημένο Τιμολόγιο |
| 31 | 3.2 Τίτλος Κτήσης (άρνηση) | | 60 | 11.4 Πιστωτικό Λιανικής |
| **50** | **5.1 Πιστωτικό (Συσχετιζόμενο)** | | **61** | **11.4 Πιστωτικό Λιανικής (Συσχ.)** |

> Cancellation = correlated credit note: original invoice (1.x/2.x) → **50**;
> retail (11.x) → **61**; set `CorrelatedInvoice` to the original MARK.

## Move purpose codes (delivery note `movePurpose`)
1 Πώληση · 2 Πώληση για Λογ. Τρίτων · 3 Δειγματισμός · 4 Έκθεση · **5 Επιστροφή** ·
6 Φύλαξη · 7 Επεξεργασία/Συναρμολόγηση · 8 Ενδοδιακίνηση · 9 Αγορά · 10 Εφοδιασμός
πλοίων/αεροσκαφών · 11 Δωρεάν διάθεση · 12 Εγγύηση · 13 Χρησιδανεισμός · 14 Αποθήκευση
σε Τρίτους · 15 Επιστροφή από Φύλαξη · 16 Ανακύκλωση · 17 Καταστροφή · 18 Διακίνηση
Παγίων · 19 Λοιπές · 20 Μεταφορές.

Delivery note payload extras (when `isDeliveryNote=true`, types 9.x):
`invoice.trans=true`, `invoice.DispatchTime`, `invoiceHeader.dispatchDate`,
`invoiceHeader.vehicleNumber`, `invoiceHeader.movePurpose`, and
`invoiceHeader.otherDeliveryNoteHeader = {loadingAddress{street,number,postalCode,city},
deliveryAddress{…}, startShippingBranch, completeShippingBranch}`. For 9.3 reverse:
`invoice.reverseDeliveryNote=true` + `invoiceHeader.reverseDeliveryNotePurpose`.

## Classifications (χαρακτηρισμοί)
`GET /Product/GetProduct?sCompanyVat&productCode&invoiceType&selfPrice` returns `cl[]`
with `cc` (classificationCategory, e.g. `category1_3`), `tc` (classificationType, e.g.
`E3_561_001`), `ct`/`tt` labels, `k` (classificationKind: income=1). Each invoice line
carries these as `classifications[{classificationKind, classificationCategory,
classificationType, amount}]`.

### Category-level classifications (manual §9)
Default classifications can be attached to a product CATEGORY, one per invoice type
(+ optional self-pricing variant). The allowed categories/codes per invoice type come
from the myDATA validation document:
`GET /Product/GetValidationDoc?invType=<numeric type value>&selfPrice=<bool>` →
`IncomeClassificationCategories[]` each with `classificationCategory_9` (e.g.
`category1_3`), `classificationCategory_9_Title`, `classificationCodes_E3_VAT[]` (E3
codes) and parallel `incomeCategoryCodesTiles[]` labels. `invType` is the *numeric*
option value from the `clsInvoiceType` dropdown (1=1.1, 20=2.1, 58=11.2, …), NOT the
`1.1` string.
Existing category classifications are rendered on the ProductCategories page in each row's
`data-classifications` attribute: `[{i,it,sp,k,cc,ct,tc,tt}]` (i=invoiceType value,
it=label, sp=selfPricing, cc=category, tc=E3 code).
Save = `POST /Product/createCategory` (new) or `/Product/updateCategory` (id>0) with a
nested object serialized as `prdCategory[id]`, `prdCategory[name]`,
`prdCategory[categoryClassifications][n][_invoiceType|selfPricing|classificationCategoryCode|classificationTypeCode]`
+ `__RequestVerificationToken`. Success returns a plain body (e.g. `0`); validation
failure returns JSON `{message:"err1~err2"}`.
Bridge params: `?cls_options=1&type=&self=`, `?category_cls=1`, `?save_category_cls=1&category_id=&category_name=&cls=<JSON>`.

## Statistics data shape (Dashboard)
The dashboard page embeds Chart.js datasets directly, e.g.:
```js
labels: ["2.1","11.2"]   // invoice type codes
data:   [7, 1]            // counts
data:   [7628.94, 2628.8] // totals (€)
```
So the bridge can GET `/Dashboard/DashboardByDate?type=...` and regex out
`labels:` + `data:` arrays to expose statistics as clean JSON.
