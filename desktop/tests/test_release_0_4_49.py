"""0.4.49 — the automatic paths are strictly headless: a fetch never opens a
visible window. The auto-render pass still includes Epsilon DocViewer rows
(headless first) but does NOT retry them through the visible stealth pass;
stealth runs only inside the user-chosen visible download (headed_fallback=True)
in download_viewer_only. The manual popup path stays intact."""

from __future__ import annotations

import inspect

from timologio.download.headless import MIN_TEXT  # noqa: E402
from timologio.download.provider import is_auto_renderable  # noqa: E402
from timologio.sync import _auto_render_pass  # noqa: E402
from timologio.sync import _is_epsilon_docviewer  # noqa: E402
from timologio.sync import download_viewer_only  # noqa: E402

EPS = "https://epsilondigital14.epsilonnet.gr/DocViewer/14e0101f-23ad-47f2-35c2-08ddef1e840a"
ESKAP = "https://eskap.gr/invoice/abc123"


def test_epsilon_rows_are_recognized():
    assert _is_epsilon_docviewer("epsilondigital14.epsilonnet.gr", EPS)
    assert not _is_epsilon_docviewer("eskap.gr", ESKAP)


def test_auto_pass_covers_epsilon_strictly_headless():
    src = inspect.getsource(_auto_render_pass)
    assert "_is_epsilon_docviewer(row[" in src
    assert "is_auto_renderable(row[" in src
    assert "StealthRenderer" not in src  # nothing visible inside a normal fetch


def test_stealth_only_for_the_visible_user_pass():
    src = inspect.getsource(download_viewer_only)
    gate = src[src.index("Πέρασμα 1.5"):]
    assert "stealth_cls=StealthRenderer" in gate
    head = gate[:gate.index("stealth_cls=StealthRenderer")]
    assert "if headed_fallback and remaining" in head


def test_auto_renderable_predicate_untouched_for_eskap():
    assert is_auto_renderable(ESKAP)
    assert not is_auto_renderable(EPS)
    assert MIN_TEXT
