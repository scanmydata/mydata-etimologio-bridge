"""0.4.47 — πrδsσmα 1.5 «stealth»: patched real browser (undetected-chromedriver,
free/GitHub/MIT) for Cloudflare-gated pages (Epsilon DocViewer interactive
Turnstile) when the server-side PDF does not exist (getfile fileType=2 → 404).
Everything must degrade gracefully when the package is absent."""

from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from timologio.download import stealth  # noqa: E402
from timologio.download.headless import HeadlessError  # noqa: E402
from timologio.download.provider import epsilon_pdf_url  # noqa: E402
from timologio.sync import _render_viewer_batch  # noqa: E402

EPS_URL = (
    "https://epsilondigital6.epsilonnet.gr/DocViewer/"
    "5ede0676-c619-4f16-b398-08de6b5a8532"
)


def test_the_stealth_module_exists_and_probes_without_crashing():
    assert callable(stealth.available)
    # available() must never raise — just False/True per installed packages.
    assert stealth.available() in (True, False)


def test_renderer_interface_mirrors_the_headless_one():
    for name in ("render_pdf", "save_via_button", "close"):
        assert hasattr(stealth.StealthRenderer, name)
    import inspect as _i

    sig = _i.signature(stealth.StealthRenderer.render_pdf)
    for kw in ("min_text", "timeout", "patient", "should_cancel"):
        assert kw in sig.parameters


def test_without_the_package_init_raises_flow_error_not_import_error():
    try:
        import undetected_chromedriver  # noqa: F406

        pytest.skip("package installed — launching a browser in a test is wrong")
    except ImportError:
        with pytest.raises(HeadlessError):
            stealth.StealthRenderer()


def test_the_batch_pipeline_knows_stealth_cls():
    params = inspect.signature(_render_viewer_batch).parameters
    assert "stealth_cls" in params
    assert params["stealth_cls"].default is None


def test_direct_endpoint_stays_the_preferred_path_for_epsilon():
    # The direct getfile endpoint (no browser at all) must keep winning when it
    # exists — stealth is only the fallback for the Turnstile-only tenants.
    direct = epsilon_pdf_url(EPS_URL)
    assert direct is not None
    assert "getfile?fileType=2" in direct
    assert "documentId=5ede0676-c619-4f16-b398-08de6b5a8532" in direct
