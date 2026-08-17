"""Πεδίο αναζήτησης με λίστα που ανοίγει — το widget που λείπει από το native.

Στο web κάθε πεδίο πελάτη ή είδους ανοίγει έναν πίνακα προτάσεων **στο κλικ**,
όχι μόνο όταν αρχίσεις να γράφεις, και η πρώτη γραμμή είναι πάντα «➕ Νέο…».
Το native είχε ένα ``QComboBox`` με completer: για να δεις κάτι έπρεπε να ξέρεις
τι να πληκτρολογήσεις, και δεν υπήρχε τρόπος να φτιάξεις πελάτη χωρίς να φύγεις
από τη σελίδα.

Το ``SearchPicker`` είναι ένα ``QLineEdit`` με δικό του popup, ώστε:

* το κλικ στο πεδίο δείχνει αμέσως τη λίστα (φιλτραρισμένη αν υπάρχει κείμενο),
* η επιλογή γίνεται με ένα κλικ — το popup είναι ``Qt.Popup``, οπότε δεν
  υπάρχει η κούρσα blur/click που στο web λύνεται με ``onmousedown``,
* ↑/↓/Enter/Esc δουλεύουν χωρίς ποντίκι.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: Πόσες προτάσεις δείχνουμε. Το web κόβει στις 30 για πελάτες και 50 για είδη·
#: πάνω από αυτό η λίστα γίνεται άχρηστη ούτως ή άλλως — φιλτράρεις.
MAX_ROWS = 50

#: Ο ρόλος στον οποίο κρύβουμε το row dict της κάθε γραμμής.
_ROW = int(Qt.ItemDataRole.UserRole)
#: Σημαία για τη γραμμή «➕ Νέο…» ώστε να μην μπερδεύεται με πραγματικό row.
_CREATE = int(Qt.ItemDataRole.UserRole) + 1


class SearchPicker(QWidget):
    """Πεδίο κειμένου + popup λίστα με προτάσεις.

    ``rows`` δίνονται με το :meth:`set_rows`. Ο καλών ορίζει πώς διαβάζεται μια
    γραμμή:

    ``label(row)``   το κείμενο που μπαίνει στο πεδίο όταν επιλεγεί
    ``detail(row)``  δευτερεύον κείμενο στη λίστα (προαιρετικό)
    ``haystack(row)``το κείμενο πάνω στο οποίο γίνεται το φιλτράρισμα
    """

    #: Ο χρήστης διάλεξε γραμμή (το ίδιο dict που δόθηκε στο ``set_rows``).
    picked = Signal(object)
    #: Ο χρήστης ζήτησε «➕ Νέο…»· φέρνει ό,τι έχει πληκτρολογήσει.
    create_requested = Signal(str)
    #: Το κείμενο άλλαξε (για ό,τι θέλει ο καλών, π.χ. αναζήτηση ΑΦΜ).
    text_edited = Signal(str)

    def __init__(
        self,
        *,
        placeholder: str = "",
        create_label: str = "",
        label: Callable[[dict[str, Any]], str] | None = None,
        detail: Callable[[dict[str, Any]], str] | None = None,
        haystack: Callable[[dict[str, Any]], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._loading = False
        self._create_label = create_label
        self._label = label or (lambda row: str(row.get("name") or ""))
        self._detail = detail or (lambda _row: "")
        self._haystack = haystack or (
            lambda row: " ".join(str(v) for v in row.values() if isinstance(v, str))
        )

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setClearButtonEnabled(True)
        self._edit.textEdited.connect(self._on_typed)
        self._edit.installEventFilter(self)
        box.addWidget(self._edit)

        #: Όσο τρέχει μια επιλογή, το popup ΔΕΝ ξαναχτίζεται. Δες `_chose`.
        self._choosing = False

        self._popup = QListWidget(self)
        self._popup.setWindowFlags(Qt.WindowType.Popup)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setFrameShape(QFrame.Shape.StyledPanel)
        self._popup.setUniformItemSizes(False)
        # ⚠️ `itemPressed`, ΟΧΙ `itemClicked` — η επιλογή κρίνεται στο **πάτημα**.
        #
        # Με το `itemClicked` (πάτημα + άφημα στο ίδιο στοιχείο) η επιλογή δεν
        # γινόταν ΠΟΤΕ με το ποντίκι: το πάτημα έκλεινε το popup (είναι
        # `Qt.Popup`), η εστίαση γύριζε στο πεδίο, το `FocusIn` ξανάχτιζε τη
        # λίστα με `clear()` — και όταν έφτανε το άφημα, το `QListWidgetItem`
        # του κλικ **είχε ήδη διαγραφεί**:
        #     RuntimeError: Internal C++ object (QListWidgetItem) already deleted
        # Η εξαίρεση πνιγόταν μέσα στο signal dispatch του Qt, οπότε προς τα έξω
        # φαινόταν σαν «το dropdown κολλάει και δεν διαλέγει τίποτα».
        # Το web λύνει το ίδιο πρόβλημα με `onmousedown` — αυτό είναι το ίδιο.
        self._popup.itemPressed.connect(self._chose)
        self._popup.hide()

    # --- API ---------------------------------------------------------------
    def line_edit(self) -> QLineEdit:
        return self._edit

    def text(self) -> str:
        return self._edit.text().strip()

    def setText(self, text: str) -> None:  # noqa: N802 — mirrors QLineEdit
        self._edit.setText(text)

    def clear(self) -> None:
        self._edit.clear()
        self.hide_popup()

    def set_rows(self, rows: Sequence[dict[str, Any]]) -> None:
        self._rows = [r for r in rows if isinstance(r, dict)]
        if self._rows:
            self._loading = False
        if self.popup_visible():
            self.show_popup()          # τα δεδομένα ήρθαν ενώ ήταν ανοιχτή

    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def set_loading(self, loading: bool) -> None:
        """Δηλώνει ότι τα δεδομένα είναι καθ' οδόν.

        Το πελατολόγιο έρχεται από την ΑΑΔΕ σε ~4 δευτερόλεπτα. Χωρίς αυτή την
        ένδειξη, όποιος άνοιγε τη λίστα σε εκείνο το διάστημα έβλεπε μόνο το
        «➕ Νέο…» και συμπέραινε — εύλογα — ότι το dropdown δεν έχει τίποτα.
        """
        self._loading = bool(loading)
        if self.popup_visible():
            self.show_popup()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self._edit.setEnabled(enabled)

    # --- popup -------------------------------------------------------------
    def show_popup(self) -> None:
        # Όσο διαλέγει ο χρήστης, μην ξαναχτίζεις τη λίστα: το `clear()` σβήνει
        # το ίδιο το στοιχείο που μόλις πατήθηκε.
        if self._choosing:
            return
        term = self._edit.text().strip().lower()
        matches = self._rows
        if term:
            matches = [r for r in self._rows if term in self._haystack(r).lower()]
        matches = matches[:MAX_ROWS]

        self._popup.clear()
        if self._create_label:
            item = QListWidgetItem(self._create_label)
            item.setData(_CREATE, True)
            self._popup.addItem(item)
        if self._loading and not self._rows:
            waiting = QListWidgetItem("⏳  Φόρτωση από την ΑΑΔΕ…")
            waiting.setFlags(Qt.ItemFlag.NoItemFlags)
            self._popup.addItem(waiting)
        for row in matches:
            detail = self._detail(row)
            text = f"{self._label(row)}   ·   {detail}" if detail else self._label(row)
            item = QListWidgetItem(text)
            item.setData(_ROW, row)
            self._popup.addItem(item)

        if self._popup.count() == 0:
            self.hide_popup()
            return

        self._popup.setCurrentRow(0)
        width = max(self._edit.width(), 320)
        rows_shown = min(self._popup.count(), 9)
        height = self._popup.sizeHintForRow(0) * rows_shown + 8
        self._popup.resize(width, height)
        self._popup.move(self._edit.mapToGlobal(self._edit.rect().bottomLeft()))
        self._popup.show()

    def hide_popup(self) -> None:
        self._popup.hide()

    def popup_visible(self) -> bool:
        return self._popup.isVisible()

    # --- events ------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is not self._edit:
            return super().eventFilter(watched, event)

        kind = event.type()
        # Το κλικ ΚΑΙ το focus ανοίγουν τη λίστα — αυτό είναι όλο το νόημα: ο
        # χρήστης δεν χρειάζεται να μαντέψει τι να πληκτρολογήσει για να δει τι
        # υπάρχει.
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
            self.show_popup()
        elif kind == QEvent.Type.KeyPress:
            if self._handle_key(event):
                return True
        return super().eventFilter(watched, event)

    def _handle_key(self, event) -> bool:
        key = event.key()
        if key == Qt.Key.Key_Escape and self.popup_visible():
            self.hide_popup()
            return True
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            if not self.popup_visible():
                self.show_popup()
                return True
            step = 1 if key == Qt.Key.Key_Down else -1
            row = (self._popup.currentRow() + step) % max(self._popup.count(), 1)
            self._popup.setCurrentRow(row)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.popup_visible():
            item = self._popup.currentItem()
            if item is not None:
                self._chose(item)
                return True
        return False

    def _on_typed(self, text: str) -> None:
        self.show_popup()
        self.text_edited.emit(text)

    def _chose(self, item: QListWidgetItem) -> None:
        # Τα δεδομένα διαβάζονται ΠΡΩΤΑ και μόνο μετά κλείνει το popup: το
        # κλείσιμο μπορεί να πυροδοτήσει `FocusIn` → `show_popup()` → `clear()`,
        # που θα κατέστρεφε το `item` κάτω από τα πόδια μας.
        self._choosing = True
        try:
            create = bool(item.data(_CREATE))
            row = item.data(_ROW)
        except RuntimeError:
            # Το στοιχείο πρόλαβε να διαγραφεί — δεν υπάρχει τίποτα να επιλεγεί.
            self._choosing = False
            return
        try:
            self.hide_popup()
            if create:
                self.create_requested.emit(self._edit.text().strip())
                return
            if isinstance(row, dict):
                self._edit.setText(self._label(row))
                self.picked.emit(row)
        finally:
            self._choosing = False


def customer_picker(*, placeholder: str = "Αναζήτηση με επωνυμία ή ΑΦΜ…") -> SearchPicker:
    """Ο επιλογέας πελάτη, με τα ίδια πεδία που δείχνει και το web."""
    return SearchPicker(
        placeholder=placeholder,
        create_label="➕  Νέος πελάτης…",
        label=lambda row: str(row.get("name") or row.get("customer_name") or ""),
        detail=lambda row: " · ".join(
            p for p in (str(row.get("vat") or row.get("afm") or ""), str(row.get("city") or "")) if p
        ),
        haystack=lambda row: " ".join(
            str(row.get(k) or "") for k in ("vat", "afm", "name", "customer_name", "code", "city")
        ),
    )


def customer_vat_picker(*, placeholder: str = "ΑΦΜ…") -> SearchPicker:
    """Ο ίδιος επιλογέας πελάτη, αλλά στο πεδίο μένει το **ΑΦΜ**.

    Χρειάζεται στη Μαζική, όπου η στήλη είναι το ΑΦΜ: με τον κανονικό επιλογέα
    θα έγραφε την επωνυμία στη στήλη του ΑΦΜ.
    """
    return SearchPicker(
        placeholder=placeholder,
        create_label="➕  Νέος πελάτης…",
        label=lambda row: str(row.get("vat") or row.get("afm") or ""),
        detail=lambda row: str(row.get("name") or row.get("customer_name") or ""),
        haystack=lambda row: " ".join(
            str(row.get(k) or "") for k in ("vat", "afm", "name", "customer_name", "code", "city")
        ),
    )


def product_picker(*, placeholder: str = "Είδος ή κωδικός…") -> SearchPicker:
    """Ο επιλογέας είδους. Στο πεδίο μπαίνει ο ΚΩΔΙΚΟΣ — αυτό στέλνεται στην
    ΑΑΔΕ — ενώ η περιγραφή φαίνεται δίπλα του στη λίστα."""
    return SearchPicker(
        placeholder=placeholder,
        create_label="➕  Νέο είδος…",
        label=lambda row: str(row.get("code") or row.get("product_code") or ""),
        detail=lambda row: str(row.get("description") or row.get("product_description") or ""),
        haystack=lambda row: " ".join(
            str(row.get(k) or "")
            for k in ("code", "product_code", "description", "product_description", "category")
        ),
    )
