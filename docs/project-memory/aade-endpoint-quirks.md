---
name: aade-endpoint-quirks
description: Ζωντανά επαληθευμένες ιδιοτροπίες των endpoints της ΑΑΔΕ (ΑΦΜ 802576637)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 95dd0925-6c2b-4966-9e94-92c66513165e
  modified: 2026-08-12T09:02:20.648Z
---

Επαληθεύτηκαν με ζωντανό τεστ στις 2026-08-12 (ΑΦΜ 802576637, 22/23 έλεγχοι OK).

- **`?afm=<9ψήφιο>` δεν επιστρέφει στοιχεία πελάτη.** Απαντά μόνο
  `{"success":true,"status":"found","code":"4","vat":"..."}`. Καταχωρεί/επιβεβαιώνει
  τον πελάτη — αυτό είναι το νόημά του — αλλά επωνυμία/διεύθυνση/πόλη/ΤΚ πρέπει να
  ζητηθούν σε **δεύτερο βήμα** με `list_customers&cust_vat=<ΑΦΜ>`. Το web το αγνοεί
  (κρατά ό,τι υπάρχει στη φόρμα), οπότε εκεί τα πεδία μένουν κενά.

- **`?preview_temp=<enc_id|guid>` αποτυγχάνει.** Η ΑΑΔΕ απαντά «Τimologio - Αδυναμία
  προεπισκόπησης παραστατικού» και για τα δύο είδη token. Δοκιμάστηκαν χωρίς επιτυχία:
  κανονικοποίηση του `counterpart` (το μοντέλο δίνει `country: 0` αντί για `"GR"`) και
  προσθήκη `tempInvoiceId` στο payload του `PrintPreviewInvoice2PdfNew`. Ισχύει και για
  το web (ίδιο endpoint). **Η διαδρομή που δουλεύει** είναι `?preview=1&temp_id=<guid>`
  με πλήρεις γραμμές — επιστρέφει ~130KB PDF. Για να λυθεί χρειάζεται capture ενός
  πραγματικού request του browser, όπως έγινε για τα άλλα quirks του `etimologio.php`.

- **`tax_categories`** γυρίζει `withheld:18, fees:22, other:28, digital:4, deductions:0`.
  Το `deductions` είναι το μόνο δικό μας — άδειο όσο δεν έχουν οριστεί κρατήσεις.

- Η **φορητή PHP** χρειάζεται τρία env vars για να τρέξει ο service εκτός πακέτου:
  `TIMOLOGIO_ETIM_PHP`, `TIMOLOGIO_ETIM_PHP_INI`, `TIMOLOGIO_ETIM_CACERT`
  (δες [[local-php-testing]] για το γιατί χρειάζεται CA bundle).

Σχετικά: [[etimologio-architecture]], [[etimologio-native-ui]].
