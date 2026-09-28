"""Σημείο εισόδου για το PyInstaller.

Το bundle δεν έχει console, οπότε ένα σφάλμα κατά την εκκίνηση θα εξαφανιζόταν
σιωπηλά. Εδώ το πιάνουμε και το δείχνουμε σε παράθυρο — αλλιώς ο χρήστης βλέπει
απλώς ένα εικονίδιο που δεν ανοίγει.
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        from timologio.gui.app import main as gui_main

        return gui_main(sys.argv)
    except Exception as exc:
        detail = traceback.format_exc()
        # Υπάρχουν σφάλματα που ΞΕΡΟΥΜΕ τι σημαίνουν (π.χ. η βάση που δεν
        # ανοίγει). Εκεί ο χρήστης πρέπει να δει τι να κάνει, όχι stack trace:
        # το «sqlite3.OperationalError: disk I/O error» δεν βοήθησε ποτέ κανέναν.
        known = type(exc).__name__ == "DatabaseUnavailable"
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            box = QMessageBox(
                QMessageBox.Icon.Critical,
                "Σφάλμα εκκίνησης",
                str(exc) if known else "Η εφαρμογή δεν μπόρεσε να ξεκινήσει.\n\n" + detail[:1500],
            )
            if known:
                box.setDetailedText(detail)
            box.exec()
        except Exception:
            print(detail, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
