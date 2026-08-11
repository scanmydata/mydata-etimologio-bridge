---
name: etimologio-packaging
description: "Building the merged 0.3.0 installer — vendored tree sync, bundled PHP runtime, and the packaging traps that only appear after freezing"
metadata:
  type: project
---

Χτίσιμο του ενοποιημένου installer (Downloader + e-Τιμολόγιο Pro) από
`desktop/` στο bridge repo. Δες [[etimologio-downloader-merge]].

**Δύο αντίγραφα του Downloader.** Το upstream είναι το repo
`scanmydata/MyData-Invoice-Downloader` (τοπικά στο `Documents/timologio-downloader`)·
το `desktop/` είναι vendored copy. Όταν βγαίνει νέα upstream έκδοση, φέρε αυτούσια
τα αρχεία που ΔΕΝ έχουμε πειράξει (`updates.py`, `gui/updater.py`, `installer/*`,
`tests/test_features.py`, `config.py`, `docs/manual.pdf`, `memory.md`) και κάνε
merge μόνο τα δύο με αλλαγές εκατέρωθεν: `gui/main_window.py` και `pyproject.toml`.
Μοιράζονται το ίδιο Inno **AppId**, οπότε build από παλιό vendored tree περνά ως
«αναβάθμιση» και υποβαθμίζει τις διορθώσεις self-update.

**Έκδοση σε 3 σημεία** (η .spec διαβάζει το config.py με regex):
`src/timologio/config.py` · `pyproject.toml` · `installer/timologio.iss`.
Το ενοποιημένο συνεχίζει τη σειρά του Downloader (0.2.28 → **0.3.0**), ώστε οι
υπάρχοντες χρήστες να το λάβουν ως ενημέρωση.

**Φορητή PHP.** Το `build.ps1` την κατεβάζει στο `installer/php/` (gitignored),
βρίσκοντας την τρέχουσα 8.3 NTS x64 από το **releases.json** — σταθερό URL 404άρει
μόλις βγει η επόμενη patch. Μετά **κλαδεύει**: κρατά 6 επεκτάσεις (pdo_sqlite,
sqlite3, openssl, mbstring, curl, pdo_pgsql) και πετά ICU/enchant → 88MB γίνονται
24.8MB, installer 78→**54.7MB**. Το βήμα επαληθεύει με `php -m` ότι φορτώνουν,
αλλιώς σκάει το build.

**Παγίδες που εμφανίζονται ΜΟΝΟ μετά το packaging:**
- Το `.spec` πρέπει να βάζει `backend/etimologio/**` και `backend/php/**` στα
  `datas` — το `service.py` τα ψάχνει σε `_MEIPASS/backend/…`.
- Το `qrcode` εισάγεται lazy μέσα σε συνάρτηση → χρειάζεται ρητά στα
  `hiddenimports`, αλλιώς το 2FA QR βγαίνει κενό μόνο στο frozen build.
- WARNING: το `curl.cainfo` το λύνει η PHP ως προς το **cwd**, όχι ως προς το ini
  (σε αντίθεση με το `extension_dir`). Ο server ξεκινά με cwd στο backend, άρα
  σχετική τιμή δίνει **curl error 77** και κάθε κλήση ΑΑΔΕ αποτυγχάνει. Το
  `service.py` περνά `-d curl.cainfo=<absolute>` — δες `resolve_cacert()` και τα
  regression tests στο `tests/test_etimologio.py`.
- Το `_tree()` στο .spec αποκλείει ρητά `config.php`/`.enckey`/`*.sqlite`:
  αλλιώς ο installer θα μοίραζε τα κλειδιά του προγραμματιστή.

**Build:** `powershell -ExecutionPolicy Bypass -File desktop\installer\build.ps1`
(θέλει Inno Setup 6 και `.venv` — εδώ είναι junction προς το venv του downloader).
