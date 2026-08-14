---
name: aade-endpoint-quirks
description: Ζωντανά επαληθευμένες ιδιοτροπίες των endpoints της ΑΑΔΕ (ΑΦΜ 802576637)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 95dd0925-6c2b-4966-9e94-92c66513165e
  modified: 2026-08-14T14:02:08.241Z
---

Επαληθεύτηκαν με ζωντανό τεστ στις 2026-08-12 (ΑΦΜ 802576637, 22/23 έλεγχοι OK).

- **`?afm=<9ψήφιο>` δεν επιστρέφει στοιχεία πελάτη.** Απαντά μόνο
  `{"success":true,"status":"found","code":"4","vat":"..."}`. Καταχωρεί/επιβεβαιώνει
  τον πελάτη — αυτό είναι το νόημά του — αλλά επωνυμία/διεύθυνση/πόλη/ΤΚ πρέπει να
  ζητηθούν σε **δεύτερο βήμα** με `list_customers&cust_vat=<ΑΦΜ>`. Το web το αγνοεί
  (κρατά ό,τι υπάρχει στη φόρμα), οπότε εκεί τα πεδία μένουν κενά.

- **`?preview_temp=` ΛΥΘΗΚΕ** (2026-08-12). Αιτία: το `/Invoice/TempInvoice` επιστρέφει
  το ΜΟΝΤΕΛΟ (nulls, `country` ως αριθμητικό enum, `itemId` = 0) ενώ το
  `PrintPreviewInvoice2PdfNew` τροφοδοτείται από τη ΦΟΡΜΑ (στενό σύνολο πεδίων,
  strings, μηδενικά, `itemId` από το 1, `isGiftVoucher`/`stampAmount`/`invoiceNotes`/
  `transmissionFailure`/`tempInvoiceId` παρόντα). Οι `tempCounterpartToForm()` και
  `tempLinesToForm()` κάνουν τη μετάφραση.
  **Η τεχνική που το έλυσε** — χρήσιμη για κάθε επόμενο quirk: προσωρινό dump μέσα στη
  `curlPostInvoice()` (env-gated), εκτέλεση της διαδρομής που ΔΟΥΛΕΥΕΙ και αυτής που
  ΣΚΑΕΙ για το ίδιο πρόχειρο, και flatten-diff των δύο JSON. Δεν χρειάζεται browser.

- **Η αναζήτηση παραστατικών ΑΓΝΟΕΙ το `BuyerVatNumber` για τις ΑΠΥ (11.2).**
  Επαληθεύτηκε 2026-08-14: για ΑΦΜ που έχει αποδείξεις, η
  `SearchInvoices` με φίλτρο αγοραστή γυρίζει **άδεια**, ενώ τα ίδια
  παραστατικά εμφανίζονται κανονικά στην αναζήτηση χωρίς φίλτρο (4 περιπτώσεις,
  δύο εκτελέσεις η καθεμία· τα τιμολόγια 2.1 φιλτράρονται σωστά). Γι' αυτό το
  `buildLedger` ζητά όλο το διάστημα και φιλτράρει σε PHP.

- **Οι σειρές ταιριάζουν με `invoice_type_code`, όχι με την ετικέτα.** Το
  `listSeries` βγάζει τον αριθμητικό κωδικό από το `data-bound-id` και τον
  δίνει δίπλα στο `invoice_type` («2.1 - Τιμολόγιο…»). Ταίριασμα με prefix
  ετικέτας βρήκε **2 από 5** σειρές σε πραγματικό λογαριασμό (2026-08-14):
  οι 5.1, 11.4 και 9.3 δεν υπάρχουν στον πίνακα `INVOICE_TYPES` του desktop.

- **Μόνο το `?sync=<kind>` γράφει την cache** (`cache_set`)· τα `list_*` όχι.
  Άρα το μοτίβο «cached πρώτα» χρειάζεται **sync** ως ζωντανό βήμα, αλλιώς η
  cache μένει για πάντα άδεια. Μετρημένα: `sync=customers` 5,6s ·
  `cached=customers` **0,02s** (ίδιες 27 γραμμές).

- **Ο ενσωματωμένος server της PHP εξυπηρετεί σειριακά.** Παράλληλες κλήσεις
  μπαίνουν σε ουρά: μια ανάγνωση cache 20ms περιμένει πίσω από ένα sync 5s. Ό,τι
  θέλει να φανεί γρήγορα πρέπει να **ζητηθεί πρώτο**, όχι απλώς να είναι γρήγορο.

- **Το `000000000` δεν είναι φιλτράρσιμο ΑΦΜ** — είναι η λιανική. Καρτέλα για
  πελάτη χωρίς ΑΦΜ δεν υπάρχει.

- **`new_deduction` θέλει ΚΑΙ ΤΑ ΤΕΣΣΕΡΑ πεδία**, μαζί με
  `deduction_decrease_total_paid` (ακόμη και «0»). Χωρίς αυτό: «Description, amount
  type, amount, and decrease_total_paid are required».

- **`save_category_cls` διαβάζει `{invoice_type, category, code}`**, όχι
  `{type, cc, tc}`. Κάνει `continue` στις άγνωστες εγγραφές και απαντά
  `success: true` με `count: 0` — η κατηγορία δημιουργείται ΧΩΡΙΣ χαρακτηρισμούς.
  Πάντα να ελέγχεται το `count`, όχι μόνο το `success`.

- **`tax_categories`** γυρίζει `withheld:18, fees:22, other:28, digital:4, deductions:0`.
  Το `deductions` είναι το μόνο δικό μας — άδειο όσο δεν έχουν οριστεί κρατήσεις.

- Η **φορητή PHP** χρειάζεται τρία env vars για να τρέξει ο service εκτός πακέτου:
  `TIMOLOGIO_ETIM_PHP`, `TIMOLOGIO_ETIM_PHP_INI`, `TIMOLOGIO_ETIM_CACERT`
  (δες [[local-php-testing]] για το γιατί χρειάζεται CA bundle).

Σχετικά: [[etimologio-architecture]], [[etimologio-native-ui]].
