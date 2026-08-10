"""Native Ρυθμίσεις: password, optional 2FA (QR enrolment), notification prefs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from . import ui
from .base import EtimPage


def qr_pixmap(data: str, size: int = 190) -> QPixmap | None:
    """Render an ``otpauth://`` URI as a QR code, if a QR library is available.

    Returns ``None`` when none is installed — the page then shows the secret as
    text, which every authenticator app also accepts.
    """
    try:
        import qrcode  # type: ignore
    except Exception:  # noqa: BLE001 — optional dependency
        return None
    try:
        matrix = qrcode.QRCode(border=2)
        matrix.add_data(data)
        matrix.make(fit=True)
        module_count = len(matrix.get_matrix())
        scale = max(1, size // max(1, module_count))
        image = QImage(module_count * scale, module_count * scale, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        for y, line in enumerate(matrix.get_matrix()):
            for x, on in enumerate(line):
                if not on:
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        image.setPixelColor(x * scale + dx, y * scale + dy, Qt.GlobalColor.black)
        return QPixmap.fromImage(image)
    except Exception:  # noqa: BLE001
        return None


class SettingsPage(EtimPage):
    go_back = Signal()
    #: Asked the shell to switch backend mode: (mode, server_url).
    mode_change_requested = Signal(str, str)

    def __init__(self, get_client, run, parent=None) -> None:
        super().__init__(get_client, run, parent)
        self._totp_secret = ""
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(12)
        box.addLayout(ui.page_header("Ρυθμίσεις", self.go_back.emit))

        # --- password ------------------------------------------------------
        pw_card, pw = ui.card()
        pw.addWidget(ui.title("Κωδικός πρόσβασης"))
        form = QFormLayout()
        self._current = QLineEdit()
        self._current.setEchoMode(QLineEdit.EchoMode.Password)
        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Τρέχων", self._current)
        form.addRow("Νέος", self._new)
        pw.addLayout(form)
        pw_row = QHBoxLayout()
        pw_row.addStretch(1)
        pw_row.addWidget(ui.button("Αλλαγή κωδικού", self._change_password, kind="primary", icon_name="key"))
        pw.addLayout(pw_row)
        box.addWidget(pw_card)

        # --- 2FA -----------------------------------------------------------
        totp_card, totp = ui.card()
        totp.addWidget(ui.title("Έλεγχος ταυτότητας δύο παραγόντων (2FA)"))
        totp.addWidget(ui.muted(
            "Προαιρετικό. Σάρωσε τον κωδικό QR με οποιαδήποτε εφαρμογή authenticator "
            "και επιβεβαίωσε με τον 6ψήφιο κωδικό."
        ))
        self._qr = QLabel()
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setMinimumHeight(10)
        totp.addWidget(self._qr)
        self._secret_label = ui.muted("")
        self._secret_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._secret_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        totp.addWidget(self._secret_label)
        totp_row = QHBoxLayout()
        self._totp_code = QLineEdit()
        self._totp_code.setPlaceholderText("6ψήφιος κωδικός")
        self._totp_code.setFixedWidth(150)
        totp_row.addWidget(self._totp_code)
        totp_row.addStretch(1)
        totp_row.addWidget(ui.button("Έναρξη ρύθμισης", self._setup_totp, icon_name="lock"))
        totp_row.addWidget(ui.button("Ενεργοποίηση", self._enable_totp, kind="primary", icon_name="check"))
        totp_row.addWidget(ui.button("Απενεργοποίηση", self._disable_totp, kind="danger", icon_name="cancel"))
        totp.addLayout(totp_row)
        box.addWidget(totp_card)

        # --- notification prefs --------------------------------------------
        prefs_card, prefs = ui.card()
        prefs.addWidget(ui.title("Ειδοποιήσεις με email"))
        prefs.addWidget(ui.muted(
            "Άφησε * για όλες. Αλλιώς δώσε ΑΦΜ εταιρειών ή τύπους παραστατικών "
            "χωρισμένα με κόμμα (π.χ. 2.1,11.2)."
        ))
        pform = QFormLayout()
        self._email_enabled = QCheckBox("Λήψη email")
        self._companies = QLineEdit("*")
        self._types = QLineEdit("*")
        pform.addRow("", self._email_enabled)
        pform.addRow("Εταιρείες", self._companies)
        pform.addRow("Κινήσεις", self._types)
        prefs.addLayout(pform)
        prefs_row = QHBoxLayout()
        prefs_row.addStretch(1)
        prefs_row.addWidget(ui.button("Αποθήκευση προτιμήσεων", self._save_prefs, kind="primary", icon_name="check"))
        prefs.addLayout(prefs_row)
        box.addWidget(prefs_card)

        # --- backend mode (offline ↔ thin client) --------------------------
        server_card, server = ui.card()
        server.addWidget(ui.title("Σύνδεση σε server"))
        server.addWidget(ui.muted(
            "Τοπικά (offline): τα δεδομένα μένουν σε αυτόν τον υπολογιστή. "
            "Σε server: δουλεύεις πάνω στα κοινά δεδομένα του γραφείου, μαζί με "
            "τους πελάτες που χρησιμοποιούν το e-Τιμολόγιο από browser."
        ))
        sform = QFormLayout()
        self._server_url = QLineEdit()
        self._server_url.setPlaceholderText("https://timologio.example.gr")
        sform.addRow("Διεύθυνση server", self._server_url)
        server.addLayout(sform)
        self._mode_label = ui.muted("")
        server.addWidget(self._mode_label)
        srow = QHBoxLayout()
        srow.addStretch(1)
        srow.addWidget(ui.button("Τοπικά (offline)", lambda: self._set_mode("offline"), icon_name="lock"))
        srow.addWidget(ui.button("Σύνδεση σε server", lambda: self._set_mode("thin"),
                                 kind="primary", icon_name="network"))
        server.addLayout(srow)
        box.addWidget(server_card)

        box.addStretch(1)
        self._status = ui.muted("")
        box.addWidget(self._status)

    # --- lifecycle ---------------------------------------------------------
    def refresh(self) -> None:
        client = self.client()
        if client is None:
            return
        self._run(client.notif_prefs, self._fill_prefs, lambda _m: None)

    def _fill_prefs(self, data: dict[str, Any]) -> None:
        prefs = data.get("prefs", data)
        self._email_enabled.setChecked(bool(prefs.get("email_enabled", True)))
        companies = prefs.get("companies", "*")
        types = prefs.get("types", "*")
        self._companies.setText(",".join(companies) if isinstance(companies, list) else str(companies))
        self._types.setText(",".join(types) if isinstance(types, list) else str(types))

    # --- actions -----------------------------------------------------------
    def _change_password(self) -> None:
        client = self.client()
        if client is None:
            return
        current, new = self._current.text(), self._new.text()
        if len(new) < 8:
            self._status.setText("Ο νέος κωδικός θέλει τουλάχιστον 8 χαρακτήρες.")
            return
        self._run(
            lambda: client.change_password(current, new),
            self._after_password,
            self._failed,
        )

    def _after_password(self, result: dict) -> None:
        if result.get("success"):
            self._current.clear()
            self._new.clear()
            self._status.setText("Ο κωδικός άλλαξε.")
        else:
            self._failed(result.get("error", "Η αλλαγή απέτυχε."))

    def _setup_totp(self) -> None:
        client = self.client()
        if client is None:
            return
        self._status.setText("Δημιουργία μυστικού…")
        self._run(client.totp_setup, self._show_totp, self._failed)

    def _show_totp(self, result: dict) -> None:
        if not result.get("success", True) and result.get("error"):
            self._failed(result["error"])
            return
        self._totp_secret = str(result.get("secret", ""))
        # The backend calls it `otpauth`; accept `uri` too so a future rename
        # doesn't silently drop the QR.
        uri = str(result.get("otpauth") or result.get("uri") or "")
        pixmap = qr_pixmap(uri) if uri else None
        if pixmap is not None:
            self._qr.setPixmap(pixmap)
        else:
            self._qr.setText("(χωρίς QR — καταχώρισε το μυστικό χειροκίνητα)")
        self._secret_label.setText(f"Μυστικό: {self._totp_secret}")
        self._status.setText("Σάρωσε το QR και δώσε τον 6ψήφιο κωδικό για ενεργοποίηση.")

    def _enable_totp(self) -> None:
        client = self.client()
        if client is None:
            return
        self._run(
            lambda: client.totp_enable(self._totp_code.text().strip()),
            self._after_totp,
            self._failed,
        )

    def _disable_totp(self) -> None:
        client = self.client()
        if client is None:
            return
        if QMessageBox.question(
            self, "Απενεργοποίηση 2FA", "Να απενεργοποιηθεί το 2FA στον λογαριασμό σου;"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: client.totp_disable(self._totp_code.text().strip()),
            self._after_totp,
            self._failed,
        )

    def _after_totp(self, result: dict) -> None:
        if result.get("success"):
            self._totp_code.clear()
            self._qr.clear()
            self._secret_label.clear()
            self._status.setText("Οι ρυθμίσεις 2FA ενημερώθηκαν.")
        else:
            self._failed(result.get("error", "Αποτυχία."))

    def _save_prefs(self) -> None:
        client = self.client()
        if client is None:
            return
        self._run(
            lambda: client.set_notif_prefs(
                companies=self._companies.text().strip() or "*",
                types=self._types.text().strip() or "*",
                email_enabled=self._email_enabled.isChecked(),
            ),
            lambda r: self._status.setText(
                "Οι προτιμήσεις αποθηκεύτηκαν." if r.get("success") else r.get("error", "Αποτυχία.")
            ),
            self._failed,
        )

    # --- backend mode ------------------------------------------------------
    def show_mode(self, mode: str, server_url: str) -> None:
        """Called by the shell so the card reflects the live configuration."""
        self._mode_label.setText(
            "Τώρα: τοπικό backend (offline)" if mode == "offline"
            else f"Τώρα: σύνδεση σε server — {server_url or '(χωρίς διεύθυνση)'}"
        )
        if server_url:
            self._server_url.setText(server_url)

    def _set_mode(self, mode: str) -> None:
        url = self._server_url.text().strip()
        if mode == "thin" and not url:
            self._status.setText("Δώσε τη διεύθυνση του server.")
            self._server_url.setFocus()
            return
        if QMessageBox.question(
            self, "Αλλαγή σύνδεσης",
            "Η εφαρμογή θα επανασυνδεθεί"
            + (" στον server και θα χρειαστεί να συνδεθείς ξανά." if mode == "thin"
               else " στα τοπικά δεδομένα αυτού του υπολογιστή."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.mode_change_requested.emit(mode, url)

    def _failed(self, msg: str) -> None:
        self._status.setText(f"Σφάλμα: {msg}")
