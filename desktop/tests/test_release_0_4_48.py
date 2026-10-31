"""0.4.48 — Epsilon DocViewer rows are no longer stranded «μόno online» after a
fetch: the auto-render pass takes them (headless first) and retries what stays
empty through the stealth pass (patched real browser). The manual «μόno online»
popup path stays intact."""

from __future__ import annotations

import inspect

from timologio.download.headless import MIN_TEXT  # noqa: E402
from timologio.download.provider import is_auto_renderable  # noqa: E402
from timologio.sync import _auto_render_pass  # noqa: E402
from timologio.sync import _is_epsilon_docviewer  # noqa: E402

EPS = "https://epsilondigital14.epsilonnet.gr/DocViewer/14e0101f-23ad-47f2-35c2-08ddef1e840a"
ESKAP = "https://eskap.gr/invoice/abc123"


def test_epsilon_rows_are_recognized():
    assert _is_epsilon_docviewer("epsilondigital14.epsilonnet.gr", EPS)
    assert not _is_epsilon_docviewer("eskap.gr", ESKAP)


def test_the_auto_pass_includes_epsilon_and_stealth_retry():
    src = inspect.getsource(_auto_render_pass)
    assert "_is_epsilon_docviewer(row[" in src
    assert "stealth_cls=StealthRenderer" in src
    assert "is_auto_renderable(row[" in src  # eskap stays in the same pass


def test_auto_renderable_predicate_untouched_for_eskap():
    assert is_auto_renderable(ESKAP)
    assert not is_auto_renderable(EPS)
