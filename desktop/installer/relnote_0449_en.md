Timologio Downloader 0.4.49 — browser-mode discipline

The "automatic" download mode now keeps its promise: when you choose the automatic (headless) option — or when the normal "fetch" run renders page-only invoices — the application NEVER opens a visible browser window. What used to pop up on your desktop in those runs is gone; anything a hidden Edge/Chrome cannot finish simply stays "view online only", exactly where you can act on it through the popup.

What changed

1. **Automatic = invisible, always.** The automatic download path and the automatic pass inside every fetch now run strictly in the hidden browser (Edge first, then Chrome). If a provider's page cannot render there, the invoice stays "view online only" — no surprise window, no interruption during a fetch.

2. **The visible browser is yours to command, via the popup.** When an invoice is stuck "view online only", the popup asks how to handle it. Pick the assisted option and the visible browser opens for that run only — with your own browser session kept, so repeated invoices from the same provider open fast. Choosing the automatic option keeps everything hidden.

3. **Direct file links stay fixed.** Links that serve the file itself are captured through the browser's own download, in the hidden browser as well — no lost windows, and retries happen automatically if a window dies.

4. **Faster browser startup.** Render waits are polled instead of fixed sleeps, trimmed first-wait budgets, and the launch flags (no sync, no component updates, no background networking) keep a cold browser start quick on every Windows machine.

Everything else from 0.4.48 is unchanged: import, coverage, reports, sharing, assistant, voice and backups work the same. The full test suite ships green (1,145 tests).
