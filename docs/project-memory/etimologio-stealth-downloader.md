---
name: etimologio-stealth-downloader
description: How the downloader passes Cloudflare interactive Turnstile (Epsilon DocViewer) with the free undetected-chromedriver
metadata:
  node_type: memory
  type: reference
---

# Stealth πrδsσma (0.4.47) — Turnstile-gated ε-Τιμolόyιoς pages

Some Epsilon Net tenants (e.g. epsilondigital6.epsilonnet.gr/DocViewer/...) have
NO server-side PDF: `getfile?fileType=2` → 404 and the page runs an
INTERACTIVE Cloudflare Turnstile (checkbox, `render=explicit`) before the Blazor
viewer. Neither headless CDP (0.4.21) nor FlareSolverr (detector miss — the
widget is created late in a Blazor/DOM mutation burst, so it misses the
`is_cloudflare_threat` heuristic) passes it.

Solution: `timologio/download/stealth.py` → `StealthRenderer` over
**undetected-chromedriver** (free, GitHub/MIT; PyPI `undetected-chromedriver`,
now in the `gui` extras + `timologio.spec` hiddenimports):

- UC's patched Chrome (`headless=False`) passes Cloudflare's bot check; the
  widget renders normally as for a human.
- Risk-based widget → no click needed; interactive checkbox (mode `normal`)
  → UC clicks where the user would, via CDP Input.dispatchMouseEvent through
  UC's own raw-CDP session (`driver._session` — UC has no `execute_cdp_cmd`).
- PDF saved with the provider's «Αnρsτá πδf» button (Blazor fetch→blob→
  `<a download>`, captured through UC's `set_download_path`), printToPDF as
  fallback.
- `sync.download_viewer_only` gained a **πrδsσma 1.5** (after the direct
  endpoint and the headless pass, before the visible headed pass): rows that
  remained «µόno online» are retried through `_render_viewer_batch(stealth_cls=StealthRenderer)`.
  Graceful: without the package (`available()` False / init raises
  `HeadlessError`) → the rows fall to the headed pass exactly as before.
- Test: `tests/test_release_0_4_47.py` (module exists, interface parity,
  graceful absence, `stealth_cls` in the pipeline, direct endpoint still first).

- 0.4.48: `_auto_render_pass` (inside every normal fetch) now also takes Epsilon
  DocViewer rows: headless first, then stealth retry of what stayed empty — so
  gated Epsilon docs stop being stranded «μόnos online». The manual popup path
  (own browser / automatic) unchanged. Test `test_release_0_4_48.py`; tests that
  stub renderers must also `monkeypatch` `stealth.available → False` (else UC
  launches real Chrome in the test).
- `/fd/<hex>:<id>` Epsilon links ARE the file: plain navigation makes Chrome
  open its PDF viewer and the tab dies (`NoSuchWindow` / window-crash). Stealth
  fixes it by setting `Browser.setDownloadBehavior` into its temp dir **before**
  navigating (`_ensure_download_dir` inside `_goto`) and polling that dir for
  the saved `*.pdf` (`_capture_download`); `_goto` also retries a dead window
  via `driver.new_window()`. Verified live 2026-10-31: 3 stranded
  `epsilondigital-enetgroup` rows saved 136–137 KB PDFs each, 122 s total.
- `HeadlessRenderer.render_pdf` got the same download-capture trick for `/fd/`
  links (set download dir → navigate → poll for `*.pdf`, ≤30s) before falling
  back to printToPDF: attachment-disposition links save headlessly in Edge/Chrome,
  while links served as an HTML viewer page (e.g. epsilondigital-3rd) capture
  nothing and fall through to render → stealth retry as before. Verified live.
- Stealth first-render wait `_WAIT_FIRST` 14s → 9s (Turnstile checkbox paints
  ~3-5s in; everything else is polled, not slept). Verified live on client
  035929984 (afm): popup-automatic path saved 4/4 stranded vf rows, 160 s.

Related: [AAΔE endpoint quirks](aade-endpoint-quirks.md).
