#!/usr/bin/env node
/**
 * Ελέγχει ότι η JavaScript ΜΕΣΑ στις σελίδες PHP κάνει parse.
 *
 *   node tools/js_check.js app.php [άλλα.php …]
 *
 * ΓΙΑΤΙ ΥΠΑΡΧΕΙ: όλη η εφαρμογή είναι ΕΝΑ inline <script>. Ένας χαρακτήρας που
 * κλείνει νωρίς ένα string —μια ελληνική προστακτική με απόστροφο, «στείλ' το»—
 * ρίχνει ΟΛΟΚΛΗΡΟ το script. Καμία onclick δεν ορίζεται ποτέ, και η σελίδα
 * φορτώνει κανονικά: σωστά χρώματα, σωστά μενού, και τίποτα δεν πατιέται. Ο
 * `php -l` δεν βλέπει τίποτα (η PHP είναι εντάξει), ο server απαντά 200, και
 * ο έλεγχος υγείας λέει «ok». Το μόνο σημάδι είναι η κονσόλα του browser.
 *
 * Ο έλεγχος αντικαθιστά κάθε μπλοκ PHP με το `0`, κρατώντας τις αλλαγές
 * γραμμής, ώστε ο αριθμός γραμμής του σφάλματος να δείχνει στο πραγματικό
 * αρχείο.
 *
 * Η γραμμή που τυπώνεται είναι εκεί που ΠΝΙΓΗΚΕ ο parser, όχι πάντα εκεί που
 * είναι το λάθος: ένα string που κλείνει νωρίς συνεχίζει να μοιάζει έγκυρο για
 * αρκετές γραμμές. Ψάξε λίγο πιο πάνω, για απόστροφο μέσα σε μονά εισαγωγικά.
 *
 * Έξοδος 0 = καθαρό. Έξοδος 1 = υπάρχει σφάλμα (και τυπώνεται πού).
 */
const fs = require('fs');
const vm = require('vm');

const keepLines = (text) => '0' + '\n'.repeat((text.match(/\n/g) || []).length);

let failed = 0;

for (const file of process.argv.slice(2)) {
  // Τα μπλοκ PHP φεύγουν ΠΡΩΤΑ, από ΟΛΟ το αρχείο. Όσο έφευγαν μόνο μέσα στο
  // σώμα του script, ένα `<script src="<?= asset_url(...) ?>">` έσπαγε τον
  // εντοπισμό: το `[^>]*` σταματούσε στο `>` του `?>`, κι έτσι ο ελεγκτής
  // «έβλεπε» σώμα εκεί που δεν υπήρχε και ανέφερε σφάλμα σε καθαρό αρχείο.
  const src = fs.readFileSync(file, 'utf8').replace(/<\?(?:php|=)[\s\S]*?\?>/g, keepLines);
  const re = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  let blocks = 0;

  while ((m = re.exec(src)) !== null) {
    // Εξωτερικά scripts (src=…) δεν έχουν σώμα να ελεγχθεί.
    if (!m[1].trim()) continue;
    blocks++;
    const startLine = src.slice(0, m.index).split('\n').length;
    const code = m[1];
    try {
      new vm.Script(code, { filename: file });
    } catch (err) {
      // Η στήλη/γραμμή του vm μετριέται μέσα στο μπλοκ· τη μεταφράζουμε στο αρχείο.
      const where = (err.stack || '').match(/:(\d+)\n/);
      const line = where ? startLine + Number(where[1]) - 1 : '?';
      console.error(`${file}:${line} — ${err.message}`);
      failed++;
    }
  }

  if (!blocks) console.error(`${file}: κανένα inline <script> — σίγουρα σωστό αρχείο;`);
  else if (!failed) console.log(`${file}: ${blocks} script block(s) κάνουν parse`);
}

process.exit(failed ? 1 : 0);
