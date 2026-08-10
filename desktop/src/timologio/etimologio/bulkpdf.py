"""Fetch AADE PDFs in bulk, then preview-print or export them as a ZIP.

Mirrors what the Downloader offers for downloaded παραστατικά — same print
preview dialog (``gui.printing.print_pdfs``) and the same "pack the selection
into one ZIP" gesture — except the PDFs here are pulled from e-timologio by
MARK rather than read off disk. They are written to a per-session temp folder
so the preview and the ZIP both work off real files.
"""

from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

log = logging.getLogger(__name__)

#: One temp folder per process, reused so repeated previews don't refetch.
_CACHE_DIR: Path | None = None


def cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(tempfile.mkdtemp(prefix="etimologio_pdf_"))
    return _CACHE_DIR


def _safe(text: str) -> str:
    """Filesystem-safe fragment (keeps Greek letters, drops path characters)."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", str(text or "")).strip()
    return re.sub(r"\s+", " ", cleaned)[:60]


def pdf_filename(row: dict) -> str:
    """``<ημερομηνία> <σειρά>-<ΑΑ> <ΜΑΡΚ>.pdf`` — sorts and reads sensibly."""
    date = _safe(row.get("issue_date", "")).replace("/", "-")
    series = _safe(row.get("series", ""))
    aa = _safe(row.get("aa", ""))
    mark = _safe(row.get("mark", ""))
    stem = " ".join(p for p in (date, f"{series}-{aa}".strip("-"), mark) if p)
    return f"{stem or 'παραστατικό'}.pdf"


def fetch_pdfs(
    client,
    rows: Iterable[dict],
    *,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[Path], list[str]]:
    """Download the PDF of each row (by MARK) into the cache folder.

    Returns ``(paths, errors)``; a row whose PDF cannot be fetched is reported in
    ``errors`` instead of aborting the batch — one bad document should never cost
    the accountant the whole print job.
    """
    rows = list(rows)
    target = cache_dir()
    paths: list[Path] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        mark = str(row.get("mark") or "").strip()
        if not mark:
            errors.append("Γραμμή χωρίς ΜΑΡΚ")
            continue
        path = target / pdf_filename(row)
        try:
            if not path.exists() or path.stat().st_size == 0:
                path.write_bytes(client.invoice_pdf(mark))
            paths.append(path)
        except Exception as exc:  # noqa: BLE001 — reported per row
            log.warning("PDF απέτυχε για ΜΑΡΚ %s: %s", mark, exc)
            errors.append(f"ΜΑΡΚ {mark}: {exc}")
        if progress is not None:
            progress(index, len(rows))
    return paths, errors


def export_zip(paths: Iterable[Path], target: Path) -> int:
    """Pack the PDFs into ``target`` (flat, deduplicated names). Returns count."""
    target.parent.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    added = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists():
                continue
            name = path.name
            if name in used:
                stem, suffix = path.stem, path.suffix
                counter = 2
                while f"{stem} ({counter}){suffix}" in used:
                    counter += 1
                name = f"{stem} ({counter}){suffix}"
            used.add(name)
            zf.write(path, arcname=name)
            added += 1
    return added
