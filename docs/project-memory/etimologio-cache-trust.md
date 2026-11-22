---
name: etimologio-cache-trust
description: Μοντέλο «η μνήμη είναι η πηγή» (0.4.51) — cacheTrusted, dirty σημάδια, sync_all, επωνυμία Taxisnet στην έκδοση, τοπικός scheduler
metadata:
  type: project
---

Από την 0.4.51:

- `cacheTrusted(vat, kind)` = μνήμη υπάρχει + όχι dirty + ηλικία < `SYNC_TRUST_SECONDS` (6h) ή `DOCS_TRUST_SECONDS` (30' για `docs`). Το `?cached=` γυρίζει `trusted`, και το `cacheIsFresh` του app.php το εμπιστεύεται.
- Αλλαγή που έγινε απευθείας στην ΑΑΔΕ φαίνεται ΜΟΝΟ μέσω `newdocs` (ωριαίο): σημαδεύει dirty `docs` (+ `customers` αν ο αγοραστής είναι άγνωστος). Για είδη/κατηγορίες/κρατήσεις δεν υπάρχει φτηνός ανιχνευτής — παράθυρο 6h ή `force`.
- `search_invoices` χωρίς φίλτρα απαντά από `docs` πριν το login όταν είναι έμπιστη· το κουμπί «Αναζήτηση» στέλνει `force=1`.
- Το sync ζει στη `runSyncKind()`· `?sync_all=1` (μία σύνδεση, όλα τα `BG_SYNC_KINDS`) καλείται από τον scheduler.php ανά εταιρεία κάθε `BG_SYNC_MINUTES` (60· 0 τοπικά).
- Αποτυχία ΑΑΔΕ σε sync ΔΕΝ γράφεται στη μνήμη (πριν έγραφε άδεια λίστα).
- Ελληνικό ΑΦΜ στην έκδοση: η επωνυμία ΕΠΙΒΑΛΛΕΤΑΙ από `authoritativeCounterpart()` (Taxisnet → καρτέλα)· η διαφορά γυρίζει ως `name_corrected` + `warning`. Σύγκριση με `custNameNorm()`.
- **Τοπικός scheduler:** το `service.py` τρέχει το `scheduler.php` κάθε 60″ όσο η εφαρμογή είναι ανοιχτή (config: `SCHEDULER_LOCAL`, `BG_SYNC_MINUTES=0`). Εργασία που έληξε >12h πριν (`SCHED_STALE_HOURS`) ΔΕΝ εκδίδεται· σημειώνεται failed και η επαναλαμβανόμενη πάει στην επόμενη μελλοντική ώρα.

Σχετικά: [[aade-endpoint-quirks]], [[etimologio-web-ui]].
