"""Shared plumbing for the native e-Τιμολόγιο pages."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QWidget

#: Injected worker: ``run(fn, on_ok, on_err)`` runs ``fn`` off the UI thread and
#: delivers the result on the main thread. The shell passes its ``QThreadPool``
#: helper; tests pass a synchronous stub.
RunFn = Callable[[Callable[[], Any], Callable[[Any], None], Callable[[str], None]], None]

#: Zero-arg accessor for the live client (may be ``None`` before login).
ClientFn = Callable[[], Any]

_MONEY_RE = re.compile(r"[^0-9,.\-]")


def parse_money(value: Any) -> float:
    """Parse a Greek-formatted money string (``1.234,56 €``) to a float.

    Returns ``0.0`` for blanks or garbage — totals must never raise while a
    table is being filled from whatever the AADE HTML scrape produced.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = _MONEY_RE.sub("", str(value or "")).strip()
    if not text:
        return 0.0
    # Greek grouping: dot = thousands, comma = decimals. Drop dots, comma→dot.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def fmt_money(value: float) -> str:
    """Format a float as ``1.234,56`` (Greek grouping) for display."""
    return f"{value:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


class EtimPage(QWidget):
    """Base for a native page: gives access to the client and the worker."""

    def __init__(
        self,
        get_client: ClientFn,
        run: RunFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_client = get_client
        self._run = run

    def client(self) -> Any:
        return self._get_client()
