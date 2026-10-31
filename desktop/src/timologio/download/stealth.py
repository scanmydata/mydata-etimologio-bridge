"""Λήψη «μόνο online» παραστατικών背后 Cloudflare interactive Turnstile.

Mechanism (measured live, 2026-10-31): the Epsilon tenants that **do not** expose a
server-side PDF (``/filedocument/getfile?fileType=2`` → 404) serve their DocViewer
page with an **embedded interactive Turnstile widget** (``render=explicit``, mode
``normal`` — a checkbox the user must click). The Blazor/.NET app does not render
the document until the challenge is passed. A raw headless Chrome (πέρασμα 1 of
``download_viewer_only``) fails its fingerprint checks and the page stays empty.

This module drives a **real, visible, patched browser** through the open-source
`undetected-chromedriver <https://github.com/ultrafunkamsterdam/undetected-chromedriver>`_
(MIT, pure Python, no paid service): its CDP patcher restores the Chrome runtime
bits Cloudflare checks, which is what makes the challenge's risk score pass — and
when it does not auto-pass, we click the checkbox through the DevTools protocol
exactly where the user would click, then wait again. No CAPTCHA-solving service,
no token farm, no third-party API: same family of open-source solutions as
FlareSolverr (which is what it is built on, undetected-chromedriver).

If the package is not installed, ``available()`` returns False and the caller
skips this pass entirely — the document falls through to the visible headed
pass (where the user clicks) exactly as before.
"""

from __future__ import annotations

import base64
import logging
import random
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .headless import MIN_TEXT, HeadlessCancelled, HeadlessError, _SAVE_PDF_CLICK_JS

log = logging.getLogger(__name__)

#: Richardson-Lucas style: how long to wait for the app to render (seconds) before
#: the Turnstile click attempt, and after it.
_WAIT_FIRST = 14.0
_WAIT_AFTER_CLICK = 25.0


def available() -> bool:
    """True if undetected-chromedriver is importable in this environment."""
    try:
        import undetected_chromedriver  # noqa: F406
        import selenium  # noqa: F401
    except ImportError:
        return False
    return True


class StealthRenderer:
    """A patched real Chrome (via undetected-chromedriver) that waits on pages and
    prints them to PDF through CDP, mirroring ``HeadlessRenderer``'s interface.

    Used as a context manager like ``HeadlessRenderer``::

        with StealthRenderer() as r:
            pdf = r.render_pdf(url)

    The window IS visible on screen (this is the whole point: a visible,
    non-headless browser is what Cloudflare's score needs) — it opens
    unattended, the user does not touch it; if the checkbox cannot be passed,
    the page simply stays empty and the row falls to the next pass.
    """

    def __init__(
        self,
        *,
        browser: Path | None = None,
        profile_dir: str | Path | None = None,
        should_cancel: Callable[[], bool] | None = None,
        launch_timeout: float = 30.0,
    ) -> None:
        # ``browser`` is accepted for interface parity but only Chrome is supported
        # (undetected-chromedriver patches Chrome specifically — never Edge).
        self._should_cancel = should_cancel
        self._chrome_tmp: str | None = None
        # Download destination for /fd/ file links (Chrome saves instead of opening
        # a PDF viewer, which would close the tab and raise NoSuchWindow).
        self._dl_dir: Path = Path(tempfile.mkdtemp(prefix="tl_stealth_dl_"))
        self._dl_seen: set[str] = set()
        self._dl_behavior = False
        try:
            from undetected_chromedriver import Chrome as UCChrome
        except ImportError as exc:  # pragma: no cover
            raise HeadlessError(
                f"undetected-chromedriver not installed: {exc}"
            ) from exc
        kwargs: dict = {
            "headless": False,
            "delay": 0.01,
            "executable": None,
            "keep_drive": False,
        }
        if browser is not None:
            kwargs["executable"] = str(browser)
        if profile_dir is not None:
            kwargs["user_data_dir"] = str(profile_dir)
            self._persistent_profile = True
        else:
            # Our own temp profile so cleanup is deterministic.
            self._chrome_tmp = tempfile.mkdtemp(prefix="tl_stealth_")
            kwargs["user_data_dir"] = self._chrome_tmp
            self._persistent_profile = False
        started = time.time()
        try:
            self._driver = UCChrome(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surface as flow error
            if self._chrome_tmp:
                shutil.rmtree(self._chrome_tmp, ignore_errors=True)
                self._chrome_tmp = None
            raise HeadlessError(f"UC Chrome launch failed: {exc}") from exc
        if time.time() - started > launch_timeout:  # pragma: no cover
            log.warning("UC launch αργό (%.0fs)", time.time() - started)

    # ------------------------------------------------------------- navigate
    def _cdp(self, method: str, params: dict):
        """One CDP command through UC's passthrough (returns result dict)."""
        try:
            return self._driver.execute_cdp_cmd(method, params)
        except Exception as exc:  # noqa: BLE001
            raise HeadlessError(f"CDP {method}: {exc}") from exc

    def _ensure_download_dir(self) -> None:
        """Allow Chrome downloads into our temp dir (once per renderer)."""
        if self._dl_behavior:
            return
        for method in ("Browser.setDownloadBehavior", "Page.setDownloadBehavior"):
            try:
                self._cdp(method, {"behavior": "allow",
                                   "downloadPath": str(self._dl_dir),
                                   "eventsEnabled": True})
                self._dl_behavior = True
                return
            except HeadlessError:
                continue

    def _capture_download(self, timeout: float) -> bytes | None:
        """Poll our download dir for a freshly saved PDF."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for p in self._dl_dir.glob("*.pdf"):
                if p.name in self._dl_seen or Path(str(p) + ".crdownload").exists():
                    continue
                try:
                    data = p.read_bytes()
                except OSError:
                    continue
                if data.startswith(b"%PDF") and len(data) > 1000:
                    self._dl_seen.add(p.name)
                    return data
            if self._should_cancel and self._should_cancel():
                raise HeadlessCancelled()
            time.sleep(0.5)
        return None

    def _text_length(self) -> int:
        try:
            value = self._driver.execute_script(
                "return document.body ? document.body.innerText.length : 0"
            )
            return int(value or 0)
        except Exception:  # noqa: BLE001 — page/navigation hiccups
            return 0

    def _await_render(
        self,
        min_text: int,
        timeout: float,
        *,
        patient: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> int:
        """Wait until the page's visible text stabilizes above ``min_text``."""
        cancel = should_cancel or self._should_cancel
        deadline = time.time() + timeout
        start = time.time()
        last, stable, textlen = -1, 0, 0
        while time.time() < deadline:
            if cancel and cancel():
                raise HeadlessCancelled()
            textlen = self._text_length()
            if textlen == last:
                stable += 1
                if textlen >= min_text and stable >= 3:
                    return textlen
                if (
                    not patient
                    and textlen < min_text
                    and time.time() - start > 12
                    and stable >= 4
                ):
                    return textlen
            else:
                stable, last = 0, textlen
            for _ in range(5):
                if cancel and cancel():
                    raise HeadlessCancelled()
                time.sleep(0.1)
        return textlen

    # ------------------------------------------------------------ turnstile
    def _turnstile_rect(self) -> tuple[int, int, int, int] | None:
        """Pixel box of the embedded widget (``#cf-turnstile``) or None."""
        js = (
            "(() => { var e = document.getElementById('cf-turnstile');"
            "if (!e) return null;"
            "var b = e.getBoundingClientRect();"
            "if (b.width < 50 || b.height < 30) return null;"
            "return [b.x, b.y, b.width, b.height]; })()"
        )
        try:
            box = self._driver.execute_script("return " + js)
        except Exception:  # noqa: BLE001
            return None
        if not box:
            return None
        return tuple(int(round(v)) for v in box)  # type: ignore

    def _turnstile_token(self) -> str:
        js = (
            "(() => { var i = document.querySelector("
            "\"input[name='cf-turnstile-response']\"); return i ? (i.value || '') : ''; })()"
        )
        try:
            return str(self._driver.execute_script("return " + js) or "")
        except Exception:  # noqa: BLE001
            return ""

    def _pass_turnstile(self, timeout: float) -> bool:
        """Click the checkbox through the DevTools mouse protocol, human-style.

        Mouse path first (CF weighs the trajectory into the click), then
        Pressed/Released inside the checkbox box. Up to three attempts; after each
        successful click Cloudflare mints a token into the hidden input and the
        app's own JS callback proceeds.
        """
        deadline = time.time() + timeout
        for attempt in range(3):
            if time.time() > deadline:
                break
            box = self._turnstile_rect()
            if box is None:
                return bool(self._turnstile_token())
            x0, y0, w, h = box
            # The checkbox sits at the left edge of the widget.
            cx = x0 + 24 + random.randint(-3, 3)
            cy = y0 + h // 2 + random.randint(-4, 4)
            px, py = max(0, cx - 320), max(0, cy - 90)
            try:
                for i in range(1, 15):
                    t = i / 14.0
                    nx = int(px + (cx - px) * t + random.uniform(-5, 5))
                    ny = int(py + (cy - py) * t + random.uniform(-4, 4))
                    self._driver.execute_cdp_cmd(
                        "Input.dispatchMouseEvent",
                        {"type": "mouseMoved", "x": nx, "y": ny, "buttonCount": 0},
                    )
                    time.sleep(random.uniform(0.03, 0.12))
                jx, jy = cx + random.randint(-4, 4), cy + random.randint(-3, 3)
                for ev in ("mousePressed", "mouseReleased"):
                    self._driver.execute_cdp_cmd(
                        "Input.dispatchMouseEvent",
                        {"type": ev, "x": jx, "y": jy, "button": "left", "buttonTypes": ["left"],
                         "buttons": [{"button": "left", "buttonTypes": ["left"]}]},
                    )
                log.info("Turnstile checkbox clicked at (%d,%d) attempt %d", jx, jy, attempt + 1)
            except Exception as exc:  # noqa: BLE001
                log.warning("Turnstile click failed: %s", exc)
                return False
            for _ in range(int(_WAIT_AFTER_CLICK)):
                if self._should_cancel and self._should_cancel():
                    raise HeadlessCancelled()
                if self._turnstile_token() or self._text_length() >= MIN_TEXT:
                    return True
                time.sleep(1)
        return bool(self._turnstile_token())

    def _goto(self, url: str) -> bool:
        """Navigate; if UC's startup window died, open a fresh one and retry."""
        self._ensure_download_dir()
        try:
            self._driver.get(url)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Stealth navigate retry via new window: %s", exc)
            try:
                self._driver.new_window()
                self._driver.get(url)
                return True
            except Exception as exc2:  # noqa: BLE001 — caller treats as «μόνο online»
                log.warning("Stealth navigate failed: %s", exc2)
                return False

    # ------------------------------------------------------------- render
    def render_pdf(
        self,
        url: str,
        *,
        min_text: int = MIN_TEXT,
        timeout: float = 45.0,
        patient: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> bytes | None:
        """Load the page, pass the challenge if one is pending, print to PDF.

        Returns the PDF bytes or ``None`` when the page never rendered — callers
        must treat ``None`` as «μόνο online» and fall to the next pass.
        """
        if not self._goto(url):
            return None
        if re.search(r"/fd/[0-9a-fA-F]+(?::\d+)?", url):
            # /fd/ links ARE the file: Chrome downloads it (the viewer tab
            # closes, which is why plain render_pdf used to die here).
            got = self._capture_download(min(15.0, timeout))
            if got:
                return got
        textlen = self._await_render(min_text, _WAIT_FIRST, patient=patient,
                                     should_cancel=should_cancel or self._should_cancel)
        if textlen < min_text:
            token = self._turnstile_token()
            if not token and self._turnstile_rect() is not None:
                if not self._pass_turnstile(timeout=_WAIT_AFTER_CLICK):
                    log.info("Stealth render: κενή/σκάίη σελίδα for %s", url)
                    return None
            textlen = self._await_render(
                min_text, timeout - _WAIT_FIRST, patient=True,
                should_cancel=should_cancel or self._should_cancel,
            )
        if textlen < min_text:
            log.info("Stealth render: κενή after wait (%d χαρ.) for %s", textlen, url)
            return None
        result = self._cdp(
            "Page.printToPDF",
            {
                "printBackground": True,
                "displayHeaderFooter": False,
                "marginTop": 0.3, "marginBottom": 0.3,
                "marginLeft": 0.3, "marginRight": 0.3,
            },
        )
        pdf = base64.b64decode(result.get("data", ""))
        return pdf if pdf.startswith(b"%PDF") else None

    def save_via_button(
        self,
        url: str,
        download_dir: str | Path,
        *,
        min_text: int = MIN_TEXT,
        render_timeout: float = 40.0,
        download_timeout: float = 45.0,
        should_cancel: Callable[[], bool] | None = None,
    ) -> bytes | None:
        """Open the page and click the provider's own «Αποθήкеυσenϛ as PDF» button,
        capturing the file that downloads — same semantics as
        ``HeadlessRenderer.save_via_button``.
        """
        download_dir = Path(download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)
        for method in ("Browser.setDownloadBehavior", "Page.setDownloadBehavior"):
            try:
                self._cdp(method, {"behavior": "allow", "downloadPath": str(download_dir),
                                   "eventsEnabled": True})
                break
            except HeadlessError:
                continue

        before = {p.name for p in download_dir.glob("*")}
        if not self._goto(url):
            return None
        cancel = should_cancel or self._should_cancel
        textlen = self._await_render(min_text, _WAIT_FIRST, patient=False, should_cancel=cancel)
        if textlen < min_text and not self._pass_turnstile(timeout=_WAIT_AFTER_CLICK):
            log.info("save_via_button (stealth): κelη for %s", url)
            return None
        textlen = self._await_render(min_text, render_timeout, patient=True, should_cancel=cancel)
        if textlen < min_text:
            return None
        try:
            clicked = self._driver.execute_script("return " + _SAVE_PDF_CLICK_JS)
        except Exception:  # noqa: BLE001
            clicked = False
        if not clicked:
            log.info("save_via_button (stealth): no PDF button on %s", url)
            return None
        deadline = time.time() + download_timeout
        while time.time() < deadline:
            if cancel and cancel():
                raise HeadlessCancelled()
            for p in download_dir.glob("*.pdf"):
                if p.name in before:
                    continue
                if Path(str(p) + ".crdownload").exists():
                    continue
                try:
                    data = p.read_bytes()
                except OSError:
                    continue
                if data.startswith(b"%PDF") and len(data) > 1000:
                    return data
            time.sleep(0.5)
        log.info("save_via_button (stealth): no download within %ss", download_timeout)
        return None

    # -------------------------------------------------------------- cleanup
    def close(self) -> None:
        try:
            self._driver.quit()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._dl_dir, ignore_errors=True)
        if self._chrome_tmp:
            shutil.rmtree(self._chrome_tmp, ignore_errors=True)
            self._chrome_tmp = None

    def __enter__(self) -> "StealthRenderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
