"""PDF καρτέλας πελάτη — κίνηση χρέωσης/πίστωσης με τρέχον υπόλοιπο.

Το web το φτιάχνει με jsPDF· εδώ το ζωγραφίζουμε με ``QPdfWriter`` + ``QPainter``,
τα ίδια εργαλεία που ήδη αποδίδουν την προεπισκόπηση εκτύπωσης. Έτσι δεν μπαίνει
νέα εξάρτηση και τα ελληνικά δουλεύουν με τη γραμματοσειρά του συστήματος.

Η καρτέλα **δεν** είναι τα PDF των παραστατικών: είναι η συγκεντρωτική κίνηση,
δηλαδή αυτό που ζητά ο λογιστής όταν λέει «στείλε μου την καρτέλα του πελάτη».
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPdfWriter

#: Πλάτος κάθε στήλης ως ποσοστό του διαθέσιμου πλάτους.
_COLUMNS: list[tuple[str, float, Qt.AlignmentFlag]] = [
    ("Ημ/νία", 0.12, Qt.AlignmentFlag.AlignLeft),
    ("Παραστατικό / Κίνηση", 0.46, Qt.AlignmentFlag.AlignLeft),
    ("Χρέωση", 0.14, Qt.AlignmentFlag.AlignRight),
    ("Πίστωση", 0.14, Qt.AlignmentFlag.AlignRight),
    ("Υπόλοιπο", 0.14, Qt.AlignmentFlag.AlignRight),
]


def _money(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return text


def build_ledger_pdf(
    path: Path,
    *,
    customer: dict[str, Any],
    entries: list[dict[str, Any]],
    period: tuple[str, str] = ("", ""),
) -> Path:
    """Γράφει την καρτέλα στο ``path``.

    ``entries`` είναι ήδη ταξινομημένες κινήσεις: κάθε μία με ``date``, ``label``,
    ``debit`` και ``credit``. Το υπόλοιπο υπολογίζεται εδώ, ώστε να συμφωνεί
    πάντα με τη σειρά που τυπώνεται.
    """
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"Καρτέλα {customer.get('name') or customer.get('vat') or ''}")

    painter = QPainter(writer)
    try:
        _draw(painter, writer, customer, entries, period)
    finally:
        painter.end()
    return path


def _draw(painter, writer, customer, entries, period) -> None:
    dpi = writer.resolution()
    width = writer.width()
    height = writer.height()
    line_h = int(dpi * 0.22)

    base = QFont(painter.font())
    base.setPointSizeF(9.0)
    head = QFont(base)
    head.setBold(True)
    big = QFont(base)
    big.setPointSizeF(15.0)
    big.setBold(True)

    y = 0

    def new_page() -> int:
        writer.newPage()
        return 0

    # --- επικεφαλίδα -------------------------------------------------------
    painter.setFont(big)
    painter.drawText(QRectF(0, y, width, line_h * 2), Qt.AlignmentFlag.AlignLeft, "ΚΑΡΤΕΛΑ ΠΕΛΑΤΗ")
    painter.setFont(base)
    date_from, date_to = period
    right = f"Περίοδος: {date_from} — {date_to}" if date_from else ""
    painter.drawText(
        QRectF(0, y, width, line_h * 2),
        Qt.AlignmentFlag.AlignRight,
        f"{right}\nΈκδοση: {date.today().strftime('%d/%m/%Y')}".strip(),
    )
    y += int(line_h * 2.4)

    painter.setFont(head)
    painter.drawText(QRectF(0, y, width, line_h), Qt.AlignmentFlag.AlignLeft,
                     str(customer.get("name") or ""))
    y += line_h
    painter.setFont(base)
    details = " · ".join(
        p for p in (
            f"ΑΦΜ {customer.get('vat')}" if customer.get("vat") else "",
            str(customer.get("address") or ""),
            str(customer.get("city") or ""),
        ) if p
    )
    painter.drawText(QRectF(0, y, width, line_h), Qt.AlignmentFlag.AlignLeft, details)
    y += int(line_h * 1.6)

    # --- πίνακας -----------------------------------------------------------
    def draw_header(top: int) -> int:
        painter.setFont(head)
        x = 0.0
        for title, share, align in _COLUMNS:
            col_w = width * share
            painter.drawText(QRectF(x, top, col_w - 6, line_h), align | Qt.AlignmentFlag.AlignVCenter, title)
            x += col_w
        painter.drawLine(0, top + line_h, width, top + line_h)
        painter.setFont(base)
        return top + int(line_h * 1.3)

    y = draw_header(y)

    balance = 0.0
    debit_total = credit_total = 0.0
    for entry in entries:
        debit = float(entry.get("debit") or 0)
        credit = float(entry.get("credit") or 0)
        balance += debit - credit
        debit_total += debit
        credit_total += credit
        cells = (
            str(entry.get("date") or ""),
            str(entry.get("label") or ""),
            _money(debit) if debit else "",
            _money(credit) if credit else "",
            _money(balance),
        )
        if y + line_h > height - line_h * 3:
            y = draw_header(new_page())
        x = 0.0
        for (_, share, align), text in zip(_COLUMNS, cells):
            col_w = width * share
            painter.drawText(
                QRectF(x, y, col_w - 6, line_h),
                align | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            x += col_w
        y += line_h

    # --- σύνολα ------------------------------------------------------------
    painter.drawLine(0, y + 4, width, y + 4)
    y += int(line_h * 0.5)
    painter.setFont(head)
    totals = ("", "Σύνολα", _money(debit_total), _money(credit_total), _money(balance))
    x = 0.0
    for (_, share, align), text in zip(_COLUMNS, totals):
        col_w = width * share
        painter.drawText(QRectF(x, y, col_w - 6, line_h), align | Qt.AlignmentFlag.AlignVCenter, text)
        x += col_w
    y += int(line_h * 1.8)

    painter.setFont(base)
    painter.drawText(
        QRectF(0, y, width, line_h),
        Qt.AlignmentFlag.AlignRight,
        f"Υπόλοιπο: {_money(balance)} €",
    )


def entries_from(invoices: list[dict[str, Any]], payments: list[dict[str, Any]],
                 *, type_label=str, method_label=str) -> list[dict[str, Any]]:
    """Ενοποιεί παραστατικά και πληρωμές σε μία σειρά κινήσεων κατά ημερομηνία."""
    from .pages.base import parse_money

    def key(text: str) -> tuple[int, int, int]:
        parts = str(text or "").split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return (int(parts[2]), int(parts[1]), int(parts[0]))
        return (0, 0, 0)

    rows: list[dict[str, Any]] = []
    for inv in invoices:
        rows.append({
            "date": str(inv.get("issue_date") or ""),
            "label": " · ".join(p for p in (
                type_label(str(inv.get("type") or "")),
                f"Σειρά {inv.get('series')} Αρ. {inv.get('aa')}" if inv.get("series") else "",
                f"ΜΑΡΚ {inv.get('mark')}" if inv.get("mark") else "",
            ) if p),
            "debit": parse_money(inv.get("total")),
            "credit": 0.0,
        })
    for pay in payments:
        rows.append({
            "date": str(pay.get("pay_date") or ""),
            "label": " · ".join(p for p in (
                "Πληρωμή",
                method_label(str(pay.get("method") or "")),
                str(pay.get("notes") or ""),
            ) if p),
            "debit": 0.0,
            "credit": parse_money(pay.get("amount")),
        })
    rows.sort(key=lambda r: key(r["date"]))
    return rows
