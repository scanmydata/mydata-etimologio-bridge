"""Πλαϊνό μενού με λογότυπο, εικονίδια και κείμενο.

Ό,τι δεν είναι η καθημερινή δουλειά ζει εδώ, ώστε η κύρια οθόνη να μένει καθαρή.
Το μενού μαζεύεται σε μια λωρίδα εικονιδίων όταν ο χρήστης θέλει τον χώρο.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QDesktopServices, QPixmap

from ..config import APP_VERSION
from .icons import icon, logo_pixmap
from .theme import CURRENT
from .widgets import ToggleSwitch

# Ελάχιστο και μέγιστο πλάτος του ανοιχτού μενού. Το πραγματικό πλάτος
# υπολογίζεται στο `_fit_width()` από τις ΠΡΑΓΜΑΤΙΚΕΣ διαστάσεις των ετικετών:
# με καρφωμένο 226 και λίγο μεγαλύτερη γραμματοσειρά συστήματος, μισή ντουζίνα
# ετικέτες («Αντίγραφο ασφαλείας», «Αρχείο καταγραφής», …) κόβονταν στη μέση.
WIDE_MIN, WIDE_MAX, NARROW = 226, 320, 58
WIDE = WIDE_MIN


#: Εικονίδιο ανά ενέργεια, όπου το όνομα της ενέργειας δεν είναι και όνομα
#: εικονιδίου. Χωρίς αυτό το `icon()` δεν έβρισκε σχέδιο για το «sync» και
#: γύριζε σιωπηλά άδειο QIcon — γι' αυτό η Λήψη και τα Παραστατικά έμεναν χωρίς
#: εικονίδιο ενώ όλα τα υπόλοιπα είχαν.
_ICONS = {
    "sync": "download",
    "documents": "pdf",
    "logfile": "csv",
    "password": "lock",
    "control": "network",
    "online_pdf": "link",
    # --- e-Τιμολόγιο Pro: τα ονόματα είναι με πρόθεμα ώστε να μη συγκρούονται
    # με τις ενέργειες του Downloader (π.χ. «Πελάτες» υπάρχει και στα δύο).
    "etim_home": "network",
    "etim_issue": "edit",
    "etim_bulk": "import",
    "etim_credit": "cancel",
    "etim_drafts": "restore",
    "etim_documents": "pdf",
    "etim_customers": "clients",
    "etim_card": "csv",
    "etim_companies": "network",
    "etim_products": "folder",
    "etim_series": "filter",
    "etim_payments": "income",
    "etim_stats": "stats",
    "etim_schedule": "schedule",
    "etim_notifications": "bell",
    "etim_settings": "settings",
    "etim_admin": "key",
    # Ίδια εικονίδια με τη ΒΟΗΘΕΙΑ του Downloader — είναι η ίδια ενέργεια.
    "etim_tour": "tour",
    "etim_manual": "manual",
    "etim_assistant": "info",
    "downloader": "download",
}


class MenuButton(QPushButton):
    def __init__(self, name: str, text: str, tip: str = "") -> None:
        super().__init__(text)
        self._name = name
        self._icon = _ICONS.get(name, name)
        self._label = text
        self._tip = tip
        self._active = False
        self.setObjectName("menuButton")
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_text = tip
        if tip:
            self.setToolTip(tip)
        self.restyle()

    def restyle(self) -> None:
        """Ξαναβάφει το εικονίδιο — το SVG είναι μονόχρωμο, οπότε πρέπει να
        ξαναφτιαχτεί όταν αλλάξει θέμα."""
        self.setIcon(icon(self._icon, CURRENT.accent if self._active else CURRENT.muted))

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", active)
        self.restyle()
        # Το Qt δεν ξαναδιαβάζει το stylesheet μόνο του σε αλλαγή property.
        self.style().unpolish(self)
        self.style().polish(self)

    def set_collapsed(self, collapsed: bool) -> None:
        """Μαζεμένο: μόνο εικονίδιο, με το κείμενο να επιβιώνει ως tooltip.

        Χωρίς αυτό η λωρίδα θα ήταν εικονίδια χωρίς όνομα — αναγνωρίσιμα μόνο
        από όποιον ξέρει ήδη το πρόγραμμα.
        """
        self.setText("" if collapsed else self._label)
        full = f"{self._label} — {self._tip}" if self._tip else self._label
        self.help_text = full if collapsed else self._tip
        self.setToolTip(self.help_text)
        self.setProperty("help_text", self.help_text)


#: Ο ιστότοπος του γραφείου — το σήμα κάτω αριστερά οδηγεί εκεί.
BRAND_URL = "https://scanmydata.gr"


def _brand_path(name: str):
    """Το λογότυπο, είτε τρέχουμε από πηγαίο κώδικα είτε από το πακέτο."""
    import sys
    from pathlib import Path

    roots = []
    base = getattr(sys, "_MEIPASS", "")
    if base:
        roots.append(Path(base))
    here = Path(__file__).resolve()
    roots.append(here.parents[3] / "installer")           # <repo>/desktop/installer
    roots.append(here.parents[4] / "assets" / "brand")    # <repo>/assets/brand
    for root in roots:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


class SideMenu(QWidget):
    """Εκπέμπει το όνομα της ενέργειας· δεν ξέρει τι κάνει η καθεμιά."""

    triggered = Signal(str)
    tooltips_toggled = Signal(bool)
    theme_toggled = Signal(bool)  # True = φωτεινό
    collapsed_changed = Signal(bool)
    #: Κλικ στον αριθμό έκδοσης. Είναι η πρώτη πληροφορία που κοιτά όποιος
    #: αναρωτιέται «τρέχω την τελευταία;» — άρα είναι και το φυσικό σημείο για
    #: να ρωτήσει. Ο έλεγχος τον κάνει το παράθυρο, ένας και μοναδικός.
    version_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideMenu")
        self._wide = WIDE_MIN
        self.setFixedWidth(self._wide)
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        self._layout = layout

        layout.addWidget(self._header())
        layout.addSpacing(12)

        self._buttons: dict[str, MenuButton] = {}
        self._sections: list[QLabel] = []

        # Δύο εφαρμογές, δύο μενού. Το καθένα ζει σε δικό του panel και
        # εμφανίζεται ολόκληρο ή καθόλου (`set_mode`): ανακατεμένα, ο χρήστης
        # έβλεπε «Νέος πελάτης» του Downloader ενώ δούλευε στο e-Τιμολόγιο.
        self._dl_panel = self._build_downloader_menu()
        self._etim_panel = self._build_etimologio_menu()
        # Σε χαμηλή οθόνη (ή με ανοιγμένη τη ΒΟΗΘΕΙΑ) το μενού δεν χωρά και το Qt
        # έκοβε τα τελευταία στοιχεία χωρίς κανένα σημάδι. Με κύλιση, ό,τι
        # περισσεύει παραμένει προσβάσιμο.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder_box = QVBoxLayout(holder)
        holder_box.setContentsMargins(0, 0, 0, 0)
        holder_box.setSpacing(0)
        holder_box.addWidget(self._dl_panel)
        holder_box.addWidget(self._etim_panel)
        holder_box.addStretch(1)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        self._etim_panel.hide()
        self._mode = "downloader"

        layout.addStretch()
        self._settings_label = self._separator("ΡΥΘΜΙΣΕΙΣ")
        layout.addWidget(self._settings_label)

        self.chk_light = ToggleSwitch("Φωτεινό θέμα")
        self.chk_light.setToolTip("Εναλλαγή ανάμεσα σε σκούρο και φωτεινό")
        self.chk_light.toggled.connect(self.theme_toggled.emit)
        layout.addWidget(self.chk_light)

        self.chk_tooltips = ToggleSwitch("Βοηθητικά μηνύματα")
        self.chk_tooltips.setChecked(True)
        self.chk_tooltips.setToolTip(
            "Εμφάνιση επεξηγήσεων όταν αφήνετε τον δείκτη πάνω από ένα κουμπί"
        )
        self.chk_tooltips.toggled.connect(self.tooltips_toggled.emit)
        layout.addWidget(self.chk_tooltips)

        layout.addSpacing(8)
        layout.addWidget(self._footer())

        self._fit_width()

    def _fit_width(self) -> None:
        """Πλάτος όσο χρειάζεται η μακρύτερη ετικέτα — και των δύο μενού.

        Με σταθερό πλάτος, όποιος έχει λίγο μεγαλύτερη γραμματοσειρά συστήματος
        έβλεπε κομμένα τα «Αντίγραφο ασφαλείας», «Αρχείο καταγραφής» κ.λπ. Το
        μετράμε αντί να το μαντεύουμε, με όριο ώστε να μη φάει την οθόνη.
        """
        widest = max(
            (b.sizeHint().width() for b in self._buttons.values()),
            default=WIDE_MIN,
        )
        margins = self._layout.contentsMargins()
        needed = widest + margins.left() + margins.right()
        self._wide = max(WIDE_MIN, min(WIDE_MAX, needed))
        if not self._collapsed:
            self.setFixedWidth(self._wide)

    # --------------------------------------------------- τα δύο μενού
    def _panel(self) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        return panel, box

    def _build_downloader_menu(self) -> QWidget:
        """Timologio Downloader — η αρχική εφαρμογή."""
        panel, box = self._panel()

        # Ο «Νέος πελάτης» πάνω από τη λίστα: είναι το πρώτο πράγμα που κάνει
        # κάποιος σε άδεια εγκατάσταση.
        self._add(box, "add_client", "Νέος πελάτης",
                  "Προσθήκη πελάτη — χειροκίνητα ή από Excel")
        box.addSpacing(6)

        self._pages = ("clients", "sync", "documents")
        for name, text, tip in [
            ("clients", "Πελάτες", "Η λίστα των πελατών σας"),
            ("sync", "Λήψη", "Επιλογή πελατών, περιόδου και έναρξη λήψης"),
            ("documents", "Παραστατικά", "Τα παραστατικά του επιλεγμένου πελάτη"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΔΕΔΟΜΕΝΑ"))
        for name, text, tip in [
            ("folder", "Φάκελος αρχείων", "Άνοιγμα του φακέλου με τα PDF"),
            ("csv", "Εξαγωγή",
             "Αναλυτική κατάσταση παραστατικών — θα επιλέξετε μορφή (Excel ή CSV) "
             "και πού θα αποθηκευτεί· επιλέξτε πρώτα πελάτη/πελάτες"),
            ("online_pdf", "Λήψη μόνο-online",
             "Κατεβάζει με headless browser (Edge/Chrome) όσα παραστατικά ο "
             "πάροχος δείχνει μόνο online"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΑΣΦΑΛΕΙΑ"))
        for name, text, tip in [
            ("backup", "Αντίγραφο ασφαλείας",
             "Αντίγραφο ασφαλείας της βάσης αυτή τη στιγμή"),
            ("restore", "Επαναφορά", "Επαναφορά της βάσης από αντίγραφο ασφαλείας"),
            ("password", "Κύριος κωδικός",
             "Προστασία του φακέλου δεδομένων με κωδικό"),
            ("wipe", "Εκκαθάριση",
             "Διαγραφή ληφθέντων παραστατικών και αρχείων — οι πελάτες μένουν"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΣΥΣΤΗΜΑ"))
        self._add(box, "control", "Πίνακας ελέγχου",
                  "Συνδέσεις δικτύου, κατάσταση βάσης και ρυθμίσεις")

        box.addSpacing(10)
        box.addWidget(self._separator("ΒΟΗΘΕΙΑ"))
        for name, text, tip in [
            ("tour", "Ξενάγηση", "Σύντομη περιήγηση στις λειτουργίες της εφαρμογής"),
            ("manual", "Εγχειρίδιο PDF", "Άνοιγμα του πλήρους εγχειριδίου χρήσης"),
            ("logfile", "Αρχείο καταγραφής",
             "Άνοιγμα του αρχείου με το αναλυτικό ιστορικό"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΕΦΑΡΜΟΓΕΣ"))
        self._add(box, "etimologio", "e-Τιμολόγιο Pro",
                  "Έκδοση παραστατικών ΑΑΔΕ — έκδοση, πελάτες, καρτέλες")
        return panel

    def _build_etimologio_menu(self) -> QWidget:
        """e-Τιμολόγιο Pro — ίδια διάταξη ενοτήτων με το web UI."""
        panel, box = self._panel()

        self._add(box, "etim_home", "Αρχική", "Επισκόπηση και συντομεύσεις")
        box.addSpacing(6)

        box.addWidget(self._separator("ΕΚΔΟΣΗ"))
        for name, text, tip in [
            ("etim_issue", "Έκδοση", "Νέο παραστατικό — πρόχειρο, προεπισκόπηση ή έκδοση"),
            ("etim_bulk", "Μαζική έκδοση", "Πολλά παραστατικά σε μία παρτίδα"),
            ("etim_credit", "Ακύρωση/Πιστωτικό", "Συσχετιζόμενο πιστωτικό με βάση το ΜΑΡΚ"),
            ("etim_drafts", "Πρόχειρα", "Αποθηκευμένα προσχέδια χωρίς ΜΑΡΚ"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΑΡΧΕΙΟ"))
        for name, text, tip in [
            ("etim_documents", "Παραστατικά", "Αναζήτηση, μαζική εκτύπωση και εξαγωγή ZIP"),
            ("etim_customers", "Πελάτες", "Πελατολόγιο και καρτέλες"),
            # Δική της εγγραφή, όπως το «📇 Καρτέλα» του web: χωρίς αυτήν ο μόνος
            # δρόμος ήταν διπλό κλικ σε πελάτη, και η σελίδα έμοιαζε να λείπει.
            ("etim_card", "Καρτέλα", "Κίνηση πελάτη: χρεώσεις, πιστώσεις, υπόλοιπο"),
            # Ο κατάλογος των εταιρειών που διαχειρίζεται το γραφείο.
            ("etim_companies", "Εταιρείες", "Προσθήκη, επεξεργασία και εναλλαγή εταιρειών"),
            ("etim_products", "Είδη", "Κατάλογος ειδών και τιμών"),
            ("etim_series", "Σειρές", "Αρίθμηση ανά τύπο παραστατικού"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΟΙΚΟΝΟΜΙΚΑ"))
        for name, text, tip in [
            ("etim_payments", "Πληρωμές", "Ταμείο και εισαγωγή extrait τράπεζας"),
            ("etim_stats", "Στατιστικά", "Τζίρος ανά τύπο παραστατικού"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΑΥΤΟΜΑΤΑ"))
        for name, text, tip in [
            ("etim_schedule", "Προγραμματισμός", "Αυτόματη έκδοση σε μελλοντική ώρα"),
            ("etim_notifications", "Ειδοποιήσεις", "Ροή των εκδόσεων"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΣΥΣΤΗΜΑ"))
        for name, text, tip in [
            ("etim_settings", "Ρυθμίσεις", "Κωδικός, 2FA και ειδοποιήσεις email"),
            ("etim_admin", "Διαχείριση", "Χρήστες, ρόλοι και προσκλήσεις"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        # Η βοήθεια εξαφανιζόταν μόλις έμπαινες στο e-Τιμολόγιο: η ξενάγηση και
        # το εγχειρίδιο υπήρχαν μόνο στο μενού του Downloader.
        box.addWidget(self._separator("ΒΟΗΘΕΙΑ"))
        for name, text, tip in [
            ("etim_assistant", "Βοηθός", "Εντολές με κείμενο ή φωνή (Ctrl+B)"),
            ("etim_tour", "Ξενάγηση", "Γρήγορη περιήγηση στις λειτουργίες"),
            ("etim_manual", "Εγχειρίδιο", "Οδηγίες σε PDF"),
        ]:
            self._add(box, name, text, tip)

        box.addSpacing(10)
        box.addWidget(self._separator("ΕΦΑΡΜΟΓΕΣ"))
        self._add(box, "downloader", "Timologio Downloader",
                  "Επιστροφή στη μαζική λήψη παραστατικών myDATA")
        return panel

    def set_mode(self, mode: str) -> None:
        """Εναλλάσσει ολόκληρο το μενού, το λογότυπο και τον τίτλο."""
        etim = mode == "etimologio"
        self._mode = "etimologio" if etim else "downloader"
        self._etim_panel.setVisible(etim)
        self._dl_panel.setVisible(not etim)
        self.logo.setPixmap(logo_pixmap(38, etimologio=etim))
        self._title.setText("e-Τιμολόγιο" if etim else "myDATA")
        self._subtitle.setText("Pro · ΑΑΔΕ" if etim else "Timologio Downloader")

    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------ UI
    def _header(self) -> QWidget:
        holder = QWidget()
        # Όταν το μενού δεν χωρά σε ύψος, το Qt συμπιέζει ό,τι μπορεί. Η
        # κεφαλίδα συρρικνωνόταν στα 31px ενώ το λογότυπο είναι 38, οπότε του
        # κοβόταν το κάτω μέρος. Το λογότυπο δεν είναι διαπραγματεύσιμο.
        holder.setMinimumHeight(38)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)

        self.logo = QLabel()
        self.logo.setPixmap(logo_pixmap(38))
        self.logo.setFixedSize(38, 38)
        self.logo.setScaledContents(True)
        row.addWidget(self.logo)

        self._title_box = QWidget()
        text = QVBoxLayout(self._title_box)
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        # Κρατιούνται ως πεδία: το `set_mode` τα αλλάζει όταν ο χρήστης περνά
        # στο e-Τιμολόγιο, ώστε να ξέρει πάντα σε ποια εφαρμογή βρίσκεται.
        self._title = QLabel("myDATA")
        self._title.setObjectName("menuTitle")
        self._subtitle = QLabel("Timologio Downloader")
        self._subtitle.setObjectName("menuSubtitle")
        text.addWidget(self._title)
        text.addWidget(self._subtitle)
        row.addWidget(self._title_box)
        row.addStretch()

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("menuToggle")
        self.btn_toggle.setIcon(icon("menu", CURRENT.muted))
        self.btn_toggle.setIconSize(QSize(18, 18))
        self.btn_toggle.setFixedSize(30, 30)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setToolTip("Σύμπτυξη/ανάπτυξη του μενού")
        self.btn_toggle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        row.addWidget(self.btn_toggle)
        return holder

    def _footer(self) -> QWidget:
        """Το σήμα του γραφείου, κάτω αριστερά — και η έκδοση, διακριτικά.

        Το εικονίδιο της εφαρμογής έφυγε από εδώ: κάθεται ήδη στην κορυφή του
        μενού, και δίπλα στο σήμα του γραφείου διαβαζόταν σαν δεύτερο λογότυπο.
        """
        holder = QWidget()
        holder.setMinimumHeight(26)
        row = QHBoxLayout(holder)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(8)

        # Σήμα του γραφείου — το ίδιο που δείχνει και η web εφαρμογή, ώστε οι
        # δύο μισές να μοιάζουν ένα προϊόν. Ανοίγει το scanmydata.gr.
        self.brand = QLabel()
        self.brand.setObjectName("brandMark")
        self.brand.setScaledContents(True)
        # Η αναλογία του αρχείου είναι 360x176 (εικονίδιο + λεκτικός τύπος,
        # χωρίς το σύνθημα). Ένα «λογικό» 110x22 το έλιωνε.
        self.brand.setFixedSize(53, 26)
        self.brand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.brand.setToolTip(f"{BRAND_URL} — άνοιγμα στον browser")
        self.brand.mousePressEvent = self._open_brand_site
        row.addWidget(self.brand)
        self._paint_brand()

        self.version = QLabel(f"έκδοση {APP_VERSION}")
        self.version.setObjectName("menuVersion")
        self.version.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version.setToolTip("Έλεγχος για νεότερη έκδοση")
        self.version.mousePressEvent = self._version_pressed
        row.addWidget(self.version)
        row.addStretch()
        return holder

    def _version_pressed(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.version_clicked.emit()

    def _open_brand_site(self, event) -> None:
        """Το σήμα είναι σύνδεσμος. Ανοίγει στον ΚΑΝΟΝΙΚΟ browser, όχι μέσα
        στην εφαρμογή: είναι ιστότοπος, όχι οθόνη του προγράμματος."""
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(BRAND_URL))

    def _paint_brand(self) -> None:
        """Διαλέγει την εκδοχή του λογοτύπου που ταιριάζει στο θέμα.

        Το φωτεινό λογότυπο πάνω σε σκούρο μενού χάνεται — και αντίστροφα.
        """
        brand = getattr(self, "brand", None)
        if brand is None:
            return
        light_theme = getattr(CURRENT, "name", "dark") == "light"
        name = "scanmydata-light.png" if light_theme else "scanmydata-dark.png"
        path = _brand_path(name)
        if path is None:
            brand.hide()
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            brand.hide()
            return
        brand.setPixmap(pix)
        brand.show()

    def _add(self, layout: QVBoxLayout, name: str, text: str, tip: str) -> None:
        button = MenuButton(name, text, tip)
        button.clicked.connect(lambda _=False, n=name: self.triggered.emit(n))
        layout.addWidget(button)
        self._buttons[name] = button

    def _separator(self, text: str) -> QWidget:
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(6, 4, 0, 2)
        box.setSpacing(3)
        label = QLabel(text)
        label.setObjectName("menuSection")
        box.addWidget(label)
        self._sections.append(label)
        line = QFrame()
        line.setObjectName("line")
        box.addWidget(line)
        return holder

    # ------------------------------------------------------------ σύμπτυξη
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        for button in self._buttons.values():
            button.set_collapsed(collapsed)
        for label in self._sections:
            label.setVisible(not collapsed)
        self._title_box.setVisible(not collapsed)
        self.version.setVisible(not collapsed)
        # Στη λωρίδα δεν χωρούν λογότυπο (38px) και ☰ (30px) μαζί. Φεύγει το
        # λογότυπο: χωρίς το ☰ δεν υπάρχει τρόπος να ξανανοίξει το μενού — και
        # το λογότυπο μένει ούτως ή άλλως στο κάτω μέρος.
        self.logo.setVisible(not collapsed)
        self.chk_light.setText("" if collapsed else "Φωτεινό θέμα")
        self.chk_tooltips.setText("" if collapsed else "Βοηθητικά μηνύματα")
        self._layout.setContentsMargins(*((8, 10, 8, 10) if collapsed
                                          else (10, 10, 10, 10)))

        target = NARROW if collapsed else self._wide
        if not animate:
            self.setFixedWidth(target)
        else:
            # Το πλάτος εκκίνησης διαβάζεται ΠΡΙΝ ξεκλειδώσουμε το maximumWidth:
            # αν το διαβάζαμε μετά, στο άνοιγμα το layout είχε ήδη επεκταθεί στο
            # WIDE, οπότε start == end και η κίνηση δεν φαινόταν — το μενού
            # «πεταγόταν» ανοιχτό ενώ το κλείσιμο κινούνταν ομαλά. Κρατάμε το
            # maximumWidth στο σημείο εκκίνησης ώστε να μην πηδήξει, και μετά το
            # κινούμε: έτσι άνοιγμα και κλείσιμο έχουν ακριβώς το ίδιο εφέ.
            start = self.width()
            self.setMinimumWidth(0)
            self.setMaximumWidth(start)
            anim = QPropertyAnimation(self, b"maximumWidth", self)
            anim.setDuration(160)
            anim.setStartValue(start)
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: self.setFixedWidth(target))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self.collapsed_changed.emit(collapsed)

    # ------------------------------------------------------------------ API
    def restyle(self) -> None:
        """Μετά από αλλαγή θέματος: τα εικονίδια είναι bitmaps σε συγκεκριμένο
        χρώμα και δεν αλλάζουν μόνα τους από το stylesheet."""
        for button in self._buttons.values():
            button.restyle()
        self.btn_toggle.setIcon(icon("menu", CURRENT.muted))
        self.logo.setPixmap(logo_pixmap(38))
        self._paint_brand()
        self.chk_light.update()
        self.chk_tooltips.update()

    #: Κουμπιά του e-Τιμολόγιο που ΔΕΝ είναι σελίδες: ανοίγουν κάτι και
    #: επιστρέφουν, οπότε δεν πρέπει να μένουν «επιλεγμένα».
    _ETIM_ACTIONS = ("etim_tour", "etim_manual", "etim_assistant", "etim_notifications")

    def set_active(self, name: str) -> None:
        """Σημαδεύει πού βρίσκεται ο χρήστης.

        Παλιά κοίταζε μόνο τις σελίδες του Downloader, οπότε μέσα στο
        e-Τιμολόγιο **καμία** γραμμή δεν ήταν φωτισμένη και το μενού δεν έλεγε
        πού είσαι.
        """
        for key, button in self._buttons.items():
            selectable = key in self._pages or (
                key.startswith("etim_") and key not in self._ETIM_ACTIONS
            )
            if selectable:
                button.set_active(key == name)

    def set_enabled_action(self, name: str, enabled: bool) -> None:
        if name in self._buttons:
            self._buttons[name].setEnabled(enabled)

    def button(self, name: str) -> MenuButton | None:
        return self._buttons.get(name)
