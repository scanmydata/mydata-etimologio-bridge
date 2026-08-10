---
name: etimologio-web-ui
description: "Web UI (app.php) conventions — theme variables, toggles matching the desktop, bulk print/ZIP, and the assistant's intent router"
metadata:
  type: project
---

Conventions for the **browser** half of e-Τιμολόγιο Pro (`app.php`), which also
serves thin clients. See [[etimologio-native-ui]] for the desktop equivalents.

**Theming.** Everything goes through CSS variables on `:root` /
`:root[data-theme="light"]`. Never hardcode a colour on an element that carries
themed text — that was the cause of every light-mode contrast bug: `--menu-bg`
(sidebar), `--header-bg` (top bar) and `--on-accent` (text on accent fills) exist
precisely because those three were fixed values. `--menu-bg` mirrors the desktop
palette's `menu_bg` (`#0a111e` / `#e9eff7`), so the sidebar goes light in light
mode exactly like the desktop side menu.

**Toggles** match the desktop `ToggleSwitch` spec: 40×22 track, 16px knob, 18px
travel, track `--line`→`--accent2`, knob `--muted`→`--on-accent`, state carried
by a `.on` class (not by a `[data-theme]` selector), labels **stable** («Φωτεινό
θέμα», «Βοηθητικά μηνύματα») — the knob shows the state, the label says what it
controls.

**Bulk print / ZIP.** `?bulk_pdf` with `mode=zip` streams an archive;
`mode=json` returns base64 PDFs and the browser merges them with pdf-lib for a
native print preview (falls back to one tab per file). ZIPs come from
`zipwriter.php` — **zlib only, never `ZipArchive`**, which is missing from the
portable PHP and slim images (the old `invoices_zip` was silently broken there).

**Assistant** (`cbHandle`): rule-based on purpose — NLP.js/Transformers.js were
evaluated and rejected (megabytes + CDN/model fetch, incompatible with offline
and self-hosted installs). `cbNorm()` strips accents/case so each keyword is
listed once. ⚠️ Check **explicit navigation before** the issuance intent:
«πήγαινε στα παραστατικά» contains `παραστατ` and otherwise starts an invoice
flow. Always keep the «άκυρο» escape — a stuck `CB_CTX` swallows every later
command.

**Verifying in the in-app browser:** screenshots do not work (the pane does not
composite), and for the same reason **CSS transitions never advance**, so
`getComputedStyle` returns start values and looks like a bug. Inject
`*{transition:none!important}` before measuring colours. See
[[local-php-testing]].
