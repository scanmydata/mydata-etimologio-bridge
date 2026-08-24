"""Προσθήκη / επεξεργασία πελάτη — χειροκίνητα ή από Excel."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..models import Client
from ..normalize import norm_afm, valid_afm, valid_subscription_key
from ..vies import ViesClient
from . import excel_help
from .icons import icon
from .theme import CURRENT

#: Το ΑΦΜ έχει ακριβώς 9 ψηφία — μόλις συμπληρωθούν, ρωτάμε μόνοι μας το VIES.
AFM_DIGITS = 9


class _Lookup(QObject):
    """Η κλήση στο VIES παίρνει ~1 δευτ. — δεν παγώνουμε το παράθυρο."""

    done = Signal(str, str)  # vat, name ('' αν δεν βρέθηκε)

    def __init__(self, vat: str) -> None:
        super().__init__()
        self._vat = vat

    def run(self) -> None:
        name = ""
        try:
            with ViesClient() as vies:
                name = vies.lookup(self._vat) or ""
        except Exception:  # το VIES πέφτει· δεν είναι λόγος να σκάσει ο διάλογος
            name = ""
        self.done.emit(self._vat, name)


def current_month() -> tuple[str, str]:
    """Πρώτη ημέρα του τρέχοντος μήνα → σήμερα, σε μορφή ΑΑΔΕ (dd/MM/yyyy)."""
    today = date.today()
    return today.replace(day=1).strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")


class _CredentialProbe(QObject):
    """Δοκιμή διαπιστευτηρίων myDATA, εκτός του νήματος του UI.

    ΓΙΑΤΙ ΥΠΑΡΧΕΙ: το «Api myData» και το «Subscription key e-timologio» είναι
    δύο διαφορετικά κλειδιά με ίδια μορφή (32 hex). Ο έλεγχος μορφής τα δέχεται
    και τα δύο, οπότε ένας πελάτης καταχωρούνταν «σωστά» και το λάθος φαινόταν
    ώρες αργότερα, μέσα σε μαζική λήψη, ως ένα 403 δίπλα σε δεκάδες επιτυχίες.
    Εδώ ρωτάμε την ΑΑΔΕ επιτόπου.
    """

    done = Signal(bool, str)  # ok, μήνυμα

    def __init__(self, user: str, key: str, vat: str, settings) -> None:
        super().__init__()
        self._user, self._key, self._vat = user, key, vat
        self._settings = settings

    def run(self) -> None:
        from ..mydata.client import MydataClient
        from ..mydata.errors import AuthError, MissingKeyError, MydataError

        date_from, date_to = current_month()
        try:
            with MydataClient(self._user, self._key, self._settings) as api:
                rows = api.check_credentials(
                    date_from=date_from, date_to=date_to, entity_vat=self._vat
                )
        except MissingKeyError:
            self.done.emit(False, "Λείπει ο χρήστης ή το κλειδί API.")
            return
        except AuthError:
            self.done.emit(
                False,
                "Η ΑΑΔΕ απέρριψε τα διαπιστευτήρια (403). Ελέγξτε ότι το κλειδί "
                "είναι το «Api myData» και ότι ο χρήστης αντιστοιχεί σε αυτό.",
            )
            return
        except MydataError as exc:
            self.done.emit(False, f"{exc.message_el} — δοκιμάστε ξανά.")
            return
        except Exception as exc:  # noqa: BLE001 — μια δοκιμή δεν ρίχνει τον διάλογο
            self.done.emit(False, f"Η δοκιμή δεν ολοκληρώθηκε: {exc}")
            return
        # ⚠️ Μηδέν γραμμές ΔΕΝ είναι αποτυχία: ο πελάτης μπορεί να μην έχει έξοδα
        # τον τρέχοντα μήνα. Το HTTP 200 είναι η απόδειξη.
        extra = f" · {rows} εγγραφές" if rows else " · χωρίς έξοδα αυτόν τον μήνα"
        self.done.emit(True, f"Τα διαπιστευτήρια δουλεύουν ({date_from}–{date_to}){extra}.")


class ClientDialog(QDialog):
    """ΑΦΜ -> (VIES) επωνυμία -> credentials, ή μαζική εισαγωγή από Excel."""

    import_requested = Signal(str)  # διαδρομή αρχείου Excel

    def __init__(
        self, conn: sqlite3.Connection, existing: Client | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._existing = existing
        self._thread: QThread | None = None
        self._lookup: _Lookup | None = None
        self._looked_up = ""
        self._probe_thread: QThread | None = None
        self._probe: _CredentialProbe | None = None
        self.client: Client | None = None
        self.excel_path: str | None = None

        self.setWindowTitle("Επεξεργασία πελάτη" if existing else "Νέος πελάτης")
        self.setMinimumWidth(500)
        self._build()
        if existing:
            self._load(existing)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        header = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon("add_client", CURRENT.ok, 26).pixmap(QSize(26, 26)))
        header.addWidget(mark)
        title = QLabel("Επεξεργασία πελάτη" if self._existing else "Νέος πελάτης")
        title.setObjectName("h1")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        intro = QLabel(
            "Γράψτε το ΑΦΜ — μόλις συμπληρωθούν τα 9 ψηφία, η επωνυμία έρχεται "
            "αυτόματα από το μητρώο ΦΠΑ της ΕΕ (VIES)."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)

        vat_row = QHBoxLayout()
        self.vat = QLineEdit()
        self.vat.setPlaceholderText("9 ψηφία")
        self.vat.setMaxLength(AFM_DIGITS)
        # Μόνο ψηφία: ένα ΑΦΜ με γράμματα δεν υπάρχει, και ο validator το λέει
        # τη στιγμή της πληκτρολόγησης αντί για μήνυμα λάθους μετά.
        self.vat.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,9}"), self.vat)
        )
        self.vat.textChanged.connect(self._on_vat_changed)
        vat_row.addWidget(self.vat)
        self.btn_lookup = QPushButton("Αναζήτηση")
        self.btn_lookup.setToolTip("Αναζήτηση επωνυμίας στο VIES")
        self.btn_lookup.clicked.connect(self._lookup_vies)
        vat_row.addWidget(self.btn_lookup)
        form.addRow("ΑΦΜ:", vat_row)

        self.label = QLineEdit()
        self.label.setPlaceholderText("Συμπληρώνεται αυτόματα ή γράψτε την")
        form.addRow("Επωνυμία:", self.label)

        self.user = QLineEdit()
        self.user.setPlaceholderText("Όνομα χρήστη myData")
        self.user.setToolTip(
            "Από το Excel «Κωδικοί Υπόχρεων», στήλη «Όνομα χρήστη myData»"
        )
        form.addRow("Χρήστης API:", self.user)

        self.key = QLineEdit()
        self.key.setPlaceholderText("32 δεκαεξαδικοί χαρακτήρες")
        self.key.setToolTip(
            "Το «Api myData» — ΟΧΙ το «Subscription key e-timologio».\n"
            "Εκδίδεται από το taxisnet: Ηλεκτρονικά Βιβλία ΑΑΔΕ →\n"
            "Εγγραφή στο myDATA REST API."
        )
        self.key.textChanged.connect(self._validate)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key)
        # Ο έλεγχος μορφής δέχεται και το ΛΑΘΟΣ κλειδί (το «Subscription key
        # e-timologio» είναι κι αυτό 32 hex). Μόνο η ΑΑΔΕ ξέρει.
        self.btn_test = QPushButton("Δοκιμή")
        self.btn_test.setToolTip(
            "Ρωτά την ΑΑΔΕ με τα στοιχεία που έγραψες (σύνολα εξόδων του "
            "τρέχοντος μήνα). Δεν κατεβάζει και δεν αποθηκεύει τίποτα."
        )
        self.btn_test.clicked.connect(self._test_credentials)
        key_row.addWidget(self.btn_test)
        form.addRow("Κλειδί API:", key_row)
        root.addLayout(form)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        # --- μαζική εισαγωγή, μέσα στον ίδιο διάλογο
        if self._existing is None:
            line = QFrame()
            line.setObjectName("line")
            root.addWidget(line)

            bulk = QHBoxLayout()
            note = QLabel("Έχετε πολλούς πελάτες;")
            note.setObjectName("muted")
            bulk.addWidget(note)
            self.btn_excel = QPushButton("  Εισαγωγή από Excel…")
            self.btn_excel.setIcon(icon("excel", CURRENT.muted))
            self.btn_excel.setToolTip(
                "Μαζική εισαγωγή από «Κωδικοί Υπόχρεων» ή «Κωδικοί Υπηρεσιών "
                "μέσω Internet»"
            )
            self.btn_excel.clicked.connect(self._pick_excel)
            bulk.addWidget(self.btn_excel)

            # Το «από πού βγάζω αυτό το Excel;» είναι η πρώτη απορία και δεν
            # απαντιέται από μόνο του — οι διαδρομές ζουν δίπλα στο κουμπί.
            self.btn_excel_help = QPushButton()
            self.btn_excel_help.setIcon(icon("info", CURRENT.accent))
            self.btn_excel_help.setFixedSize(30, 30)
            self.btn_excel_help.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_excel_help.setToolTip(
                "Πώς εξάγω τους κωδικούς σε Excel από Hyper/Extra ή TaxSystem"
            )
            self.btn_excel_help.clicked.connect(lambda: excel_help.show(self))
            bulk.addWidget(self.btn_excel_help)
            bulk.addStretch()
            root.addLayout(bulk)

        buttons = QDialogButtonBox()
        self.btn_ok = buttons.addButton("Αποθήκευση", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Άκυρο", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._validate()

    def _load(self, client: Client) -> None:
        self.vat.setText(client.vat)
        self.vat.setEnabled(False)  # το ΑΦΜ είναι το κλειδί — δεν αλλάζει
        self.btn_lookup.setEnabled(False)
        self.label.setText(client.label)
        self.user.setText(client.mydata_user)
        self.key.setText(client.mydata_key)
        if not client.mydata_key:
            self.key.setFocus()

    # ------------------------------------------------------------ Excel
    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Επιλέξτε αρχείο Excel", "", "Excel (*.xlsx)"
        )
        if path:
            self.excel_path = path
            self.accept()

    # ------------------------------------------------------------ VIES
    def _on_vat_changed(self, text: str) -> None:
        self._validate()
        # Μόνο όταν έχουν πληκτρολογηθεί ΑΚΡΙΒΩΣ 9 ψηφία. Αλλιώς το norm_afm
        # συμπληρώνει το 8ψήφιο με μηδενικό μπροστά και θα ξεκινούσε πρόωρη
        # (λάθος) αναζήτηση· όσο εκείνη τρέχει, ο έλεγχος «ένα thread τη φορά»
        # μπλοκάρει τη σωστή αναζήτηση στο 9ο ψηφίο — και ο χρήστης αναγκαζόταν
        # να πατήσει το κουμπί. Το πεδίο δέχεται μόνο ψηφία (validator), οπότε
        # το μήκος του κειμένου είναι ασφαλής ένδειξη.
        if len(text.strip()) != AFM_DIGITS:
            return
        vat = norm_afm(text)
        if not vat or self.label.text().strip():
            return
        # 1) Αν το ξέρουμε ήδη (προμηθευτής ή πελάτης στη βάση), το φέρνουμε
        #    ακαριαία — χωρίς δίκτυο, ακόμη κι αν το VIES είναι κάτω.
        known = self._known_name(vat)
        if known:
            self._looked_up = vat
            self.label.setText(known)
            self._say(f"Βρέθηκε στο μητρώο: {known}", CURRENT.ok)
            self._validate()
            return
        # 2) Αλλιώς ρωτάμε αυτόματα το VIES.
        if vat != self._looked_up:
            self._lookup_vies()

    def _known_name(self, vat: str) -> str:
        """Επωνυμία από το τοπικό μητρώο (προμηθευτές/πελάτες), αν υπάρχει."""
        row = self._conn.execute(
            "SELECT name FROM suppliers WHERE vat = ?", (vat,)
        ).fetchone()
        return (row["name"].strip() if row and row["name"] else "")

    def _lookup_vies(self) -> None:
        vat = norm_afm(self.vat.text())
        if not vat:
            self._say(f"Το ΑΦΜ πρέπει να έχει {AFM_DIGITS} ψηφία.", CURRENT.bad)
            return
        if self._thread is not None:
            return
        self._looked_up = vat
        self.btn_lookup.setEnabled(False)
        self._say("Αναζήτηση στο VIES…", CURRENT.muted)

        self._thread = QThread(self)
        self._lookup = _Lookup(vat)
        self._lookup.moveToThread(self._thread)
        self._thread.started.connect(self._lookup.run)
        self._lookup.done.connect(self._on_lookup_done)
        self._thread.start()

    def _on_lookup_done(self, vat: str, name: str) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._lookup = None
        self.btn_lookup.setEnabled(self.vat.isEnabled())

        if name:
            self.label.setText(name)
            self._say(f"Βρέθηκε: {name}", CURRENT.ok)
            self.user.setFocus()
        else:
            self._say(
                "Το VIES δεν επέστρεψε επωνυμία για αυτό το ΑΦΜ. "
                "Γράψτε την χειροκίνητα.",
                CURRENT.warn,
            )
        self._validate()

    # -------------------------------------------------------- επικύρωση
    def _say(self, text: str, color: str) -> None:
        self.hint.setText(text)
        self.hint.setStyleSheet(f"color:{color};")

    # ------------------------------------------------- δοκιμή διαπιστευτηρίων
    def _test_credentials(self) -> None:
        user = self.user.text().strip()
        key = self.key.text().strip()
        vat = norm_afm(self.vat.text())
        if not user or not key:
            self._say("Συμπλήρωσε χρήστη ΚΑΙ κλειδί API για να γίνει η δοκιμή.", CURRENT.warn)
            return
        if self._probe_thread is not None:
            return
        from ..config import load_settings

        self.btn_test.setEnabled(False)
        self.btn_test.setText("Δοκιμή…")
        self._say("Ερώτηση στην ΑΑΔΕ…", CURRENT.muted)

        self._probe_thread = QThread(self)
        self._probe = _CredentialProbe(user, key, vat, load_settings())
        self._probe.moveToThread(self._probe_thread)
        self._probe_thread.started.connect(self._probe.run)
        self._probe.done.connect(self._on_test_done)
        self._probe_thread.start()

    def _on_test_done(self, ok: bool, message: str) -> None:
        thread = self._probe_thread
        self._probe_thread = None
        self._probe = None
        if thread is not None:
            thread.quit()
            thread.wait(3000)
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Δοκιμή")
        self._say(("✓ " if ok else "✗ ") + message, CURRENT.ok if ok else CURRENT.bad)

    def _validate(self) -> None:
        vat = norm_afm(self.vat.text())
        key = self.key.text().strip()
        if hasattr(self, "btn_ok"):
            self.btn_ok.setEnabled(bool(vat))
        typed = self.vat.text().strip()

        if typed and not vat:
            self._say(f"Το ΑΦΜ πρέπει να έχει {AFM_DIGITS} ψηφία.", CURRENT.muted)
        elif vat and not valid_afm(vat):
            self._say("Το ΑΦΜ δεν περνά τον έλεγχο ορθότητας — ελέγξτε το.", CURRENT.warn)
        elif key and not valid_subscription_key(key):
            self._say(
                "Το κλειδί δεν μοιάζει με «Api myData» (32 δεκαεξαδικοί χαρακτήρες).",
                CURRENT.warn,
            )
        elif vat and not key:
            self._say(
                "Χωρίς κλειδί API ο πελάτης αποθηκεύεται αλλά δεν μπορεί να "
                "κατεβάσει παραστατικά.",
                CURRENT.muted,
            )
        elif vat and key:
            self._say("Έτοιμο.", CURRENT.ok)
        else:
            self._say("", CURRENT.muted)

    def _accept(self) -> None:
        vat = norm_afm(self.vat.text())
        if not vat:
            self._say(f"Το ΑΦΜ πρέπει να έχει {AFM_DIGITS} ψηφία.", CURRENT.bad)
            return

        key = self.key.text().strip()
        if key and not valid_subscription_key(key):
            answer = QMessageBox.question(
                self, "Ύποπτο κλειδί",
                "Το κλειδί δεν μοιάζει με «Api myData» (32 δεκαεξαδικοί "
                "χαρακτήρες).\n\nΠροσοχή: το «Subscription key e-timologio» "
                "είναι άλλο προϊόν και δεν δουλεύει εδώ.\n\nΑποθήκευση έτσι;",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if self._existing is None:
            row = self._conn.execute(
                "SELECT label FROM clients WHERE vat=?", (vat,)
            ).fetchone()
            if row is not None:
                answer = QMessageBox.question(
                    self, "Υπάρχει ήδη",
                    f"Ο πελάτης {vat} υπάρχει ήδη ({row['label'] or '—'}).\n\n"
                    "Να ενημερωθούν τα στοιχεία του;",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

        self.client = Client(
            vat=vat,
            label=self.label.text().strip(),
            mydata_user=self.user.text().strip(),
            mydata_key=key,
            source_file=self._existing.source_file if self._existing else "χειροκίνητα",
        )
        self.accept()

    def closeEvent(self, event) -> None:
        for thread in (self._thread, self._probe_thread):
            if thread is not None:
                thread.quit()
                thread.wait(3000)
        super().closeEvent(event)
