This release fixes the long-standing problem with the **Epsilon Net** provider (links like `epsilondigitalN.epsilonnet.gr/DocViewer/...` and `.../fd/...`): their documents sit behind a Cloudflare Turnstile check and a Blazor viewer app, so no plain HTTP request can ever fetch the official PDF. Earlier releases left those invoices as "view online only" and asked you to click through a browser yourself. Now the application does it for you, end to end.

What changed

1. **Stealth rendering engine (new).** When a provider hides behind Cloudflare, Timologio launches a real, patched Chrome (undetected-chromedriver, MIT) that passes the Turnstile checkbox with human-like mouse movement, waits for the viewer app to render, clicks the provider's own "Save as PDF" button, and captures the downloaded file. No external service, no paid API, everything runs on your machine.

2. **The automatic render pass now covers Epsilon rows.** Previously only the ADEMOE-style viewers were auto-rendered; Epsilon DocViewer rows stayed manual. Now the automatic pass tries the hidden headless renderer first and, for rows it cannot render, retries them with the stealth engine in the same run. So after "fetch" plus "download pending", Epsilon invoices come home as real PDFs without you doing anything.

3. **Direct file links (`/fd/...`) are saved properly.** Some Epsilon tenants serve the file straight from the link instead of a viewer page. The browser (Edge or Chrome) now saves it with a download destination set — in headless mode as well as in the stealth pass — instead of losing it in the built-in PDF viewer, and a dead browser window is re-opened and retried automatically.

4. **Headless mode uses Edge first.** The headless renderer already preferred Microsoft Edge over Chrome; the whole pass was re-audited for Edge coverage. Launch flags (no sync, no component updates, no background networking) keep the first start fast on a fresh profile.

5. **Faster browser startup.** The stealth engine's first render wait was trimmed from 14s to 9s (the Turnstile checkbox appears in ~3-5s) and waits are polled, not fixed sleeps, so healthy pages return in seconds instead of budget time.

Manual actions also fixed

- Double-clicking an "online only" invoice in the viewer opens the assisted-download popup and routes the row through the same automatic chain — the invoice is downloaded on the spot, no browser clicking required.
- "Download all outstanding" now includes the Epsilon retry pass: every occurrence that can render (headless or stealth) is downloaded; the ones that genuinely cannot are marked "view online only" and never block the rest.

Everything else (import, coverage, reports, assistant, voice, backups) is unchanged from 0.4.47. The full test suite ships green: 1,145 tests pass.
