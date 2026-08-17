---
name: etimologio-native-ui
description: "How the native e-Τιμολόγιο Qt pages are built — shared ui helpers, ListPage base, the background worker contract, and bulk print/ZIP"
metadata: 
  node_type: memory
  type: project
  originSessionId: 95dd0925-6c2b-4966-9e94-92c66513165e
  modified: 2026-08-14T12:35:21.485Z
---

Conventions for the native e-Τιμολόγιο Pro screens in
`desktop/src/timologio/etimologio/` (see [[etimologio-downloader-merge]]).

**Look & feel = the Downloader's.** Never hardcode colours; the app-wide QSS in
`gui/theme.py` keys off **object names**. `pages/ui.py` wraps them:
`ui.card()`, `ui.page_header()`, `ui.muted()`, `ui.hint()`, `ui.button(kind=
"primary"|"danger")`, `ui.stat_tile()`/`set_tile_value()`, `ui.nav_tile()`,
`ui.table()`. Use these so light/dark both work.

**Page bases** (`pages/base.py`): `EtimPage` (client accessor + injected `run`)
and `ListPage` (back-bar + toolbar + table + refresh/`selected_row()`/status —
subclass, set `columns`/`rows_key`, implement `fetch(client)`).

**Worker contract:** pages never touch threads; they get `run(fn, on_ok,
on_err)`. Tests pass a synchronous stub. ⚠️ `shell._run` **must** keep the
`_Job` in `_INFLIGHT` until it emits `done` — `QThreadPool.start()` owns the
runnable in C++ only, so without that the Python signal object is GC'd
mid-flight and results vanish (a page that randomly never loads). Regression
tests: `test_run_delivers_result_even_after_gc`, `test_run_releases_finished_jobs`.

**Bulk print / ZIP** (`etimologio/bulkpdf.py`): `fetch_pdfs(client, rows)`
downloads each row's PDF by ΜΑΡΚ into a per-process temp dir (errors collected
per row, never aborting the batch), then `gui.printing.print_pdfs(paths)` gives
the *same* preview dialog as the Downloader, and `export_zip(paths, target)`
packs them (flat, de-duplicated names). Wired into **Παραστατικά** (checkbox
multi-select) and **Καρτέλα** (whole customer).

**⚠️ Ο κανόνας του θέματος για κάρτες είναι `QFrame#card`, όχι `#card`.** Ένα
`QWidget` με `setObjectName("card")` δεν παίρνει **κανένα** φόντο — φαίνεται ό,τι
υπάρχει από κάτω. Επηρεάζει κάθε επικάλυψη (π.χ. το panel του βοηθού): κάν' την
`QFrame`. Το ίδιο ισχύει για κάθε νέο όνομα που προστίθεται στο `theme.build()`.

**⚠️ Το `TableColumnFilter` ΑΝΤΙΚΑΘΙΣΤΑ την κεφαλίδα** (`setHorizontalHeader`).
Πρέπει να φτιάχνεται **ΠΡΙΝ** από `persist_header`/`setup_columns`, αλλιώς πετά
ό,τι μόλις επαναφέρθηκε: πλάτη, σειρά στηλών και δείκτη ταξινόμησης. Ο δείκτης
τότε γυρίζει στην προεπιλογή του Qt, που είναι **φθίνουσα στη στήλη 0** — γι'
αυτό οι λίστες άνοιγαν ανάποδα. Το `ui.make_sortable()` τα κάνει με τη σωστή
σειρά και ορίζει ρητά τον δείκτη (αύξουσα, ή `default_column` για «νεότερα
πρώτα»), κρατώντας σε δική του σημαία αν ταξινόμησε ο χρήστης.

**Οι πληρωμές κρατούν ISO ημερομηνία στη βάση** (`payment_date_iso` στο
`localdb.php`) γιατί το `pay_date` συγκρίνεται ως κείμενο σε κάθε φίλτρο. Στο UI
περνούν από `fmt_date`/`ui.date_cell`, που δέχονται και τις δύο μορφές.

**Offscreen renders: τα ελληνικά βγαίνουν κουτάκια.** Το `QT_QPA_PLATFORM=
offscreen` σε αυτό το μηχάνημα δεν βρίσκει γραμματοσειρά με ελληνικά, οπότε κάθε
`widget.grab()` δείχνει tofu. Χρήσιμο για **διάταξη και χρώματα**, άχρηστο για
έλεγχο κειμένου — μη το εκλάβεις ως σφάλμα απόδοσης.

**2FA QR:** `pages/settings.py` renders `otpauth` (note: the backend key is
`otpauth`, not `uri`) via the `qrcode` package — declared in the `gui` extra,
pure-Python, drawn with Qt from `get_matrix()`; falls back to showing the secret
as text if missing.
