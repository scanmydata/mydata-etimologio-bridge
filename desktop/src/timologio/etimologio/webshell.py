"""e-Τιμολόγιο Pro στον υπολογιστή: **η ίδια** web εφαρμογή, μέσα σε παράθυρο.

Γιατί άλλαξε η αρχιτεκτονική
----------------------------
Οι σελίδες ήταν ξαναγραμμένες σε Qt, μία προς μία, με στόχο να μοιάζουν με το
``app.php``. Κάθε γύρος δοκιμών έβρισκε νέα απόκλιση — επιλογείς που δεν
επέλεγαν, στήλες κομμένες, οδηγός που δεν επέστρεφε, σελίδες που έλειπαν —
επειδή η ομοιότητα συντηρούνταν **με το χέρι**. Δύο υλοποιήσεις του ίδιου UI
αποκλίνουν πάντα· το ερώτημα είναι μόνο πόσο γρήγορα.

Εδώ το UI είναι ένα: η εφαρμογή σηκώνει τον δικό της PHP server (όπως πάντα) και
δείχνει το ``app.php`` του μέσα σε ``QWebEngineView``. Ό,τι αλλάζει στο web
εμφανίζεται αυτούσιο και στον υπολογιστή, χωρίς μεταφορά.

Τι ΔΕΝ αλλάζει: τα δεδομένα μένουν τοπικά και κρυπτογραφημένα, ο server ακούει
μόνο σε loopback, και τίποτα δεν ταξιδεύει στο internet πέρα από τις κλήσεις
προς την ΑΑΔΕ που έκανε ήδη το backend.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .service import EtimologioService

log = logging.getLogger(__name__)


class _Signals(QObject):
    ok = Signal(object)
    err = Signal(str)


class _Job(QRunnable):
    """Ένα σύγχρονο κομμάτι δουλειάς εκτός του νήματος του UI."""

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 — φτάνει στο UI ως μήνυμα
            self._emit(self.signals.err, str(exc))
        else:
            self._emit(self.signals.ok, result)

    @staticmethod
    def _emit(signal, payload) -> None:
        try:
            signal.emit(payload)
        except RuntimeError:
            log.debug("Το αποτέλεσμα αγνοήθηκε: ο παραλήπτης έχει καταστραφεί")


#: Οι εργασίες που τρέχουν, κρατημένες ζωντανές επίτηδες: το ``QThreadPool``
#: κατέχει το runnable μόνο στη C++ πλευρά και το ``_Signals`` θα μπορούσε να
#: συλλεχθεί πριν προλάβει να εκπέμψει.
_INFLIGHT: set[_Job] = set()


def _run(fn, on_ok, on_err) -> None:
    job = _Job(fn)
    _INFLIGHT.add(job)
    job.signals.ok.connect(on_ok)
    job.signals.err.connect(on_err)
    job.signals.ok.connect(lambda *_: _INFLIGHT.discard(job))
    job.signals.err.connect(lambda *_: _INFLIGHT.discard(job))
    QThreadPool.globalInstance().start(job)


def _free_name(path: Path) -> Path:
    """«αρχείο.pdf» → «αρχείο (2).pdf» όταν υπάρχει ήδη.

    Ο ρυθμισμένος φάκελος σημαίνει «μη με ρωτάς» — δεν σημαίνει «σβήσε ό,τι
    κατέβασα πριν από πέντε λεπτά».
    """
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(2, 999):
        candidate = path.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
    return path


def webengine_available() -> bool:
    """Υπάρχει το QtWebEngine σε αυτή την εγκατάσταση;"""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception:  # noqa: BLE001 — λείπει ή δεν φορτώνει
        return False
    return True


class _Host(QObject):
    """Ό,τι μπορεί να ζητήσει η **σελίδα** από την εφαρμογή.

    Οι Ρυθμίσεις του e-Τιμολόγιο ζουν μέσα στο ``app.php``, αλλά «εκκίνηση στο
    tray» και «έλεγχος για ενημερώσεις» δεν είναι ρυθμίσεις του λογαριασμού:
    τις ξέρει μόνο το Qt. Χωρίς γέφυρα θα έπρεπε να ζουν σε άλλη οθόνη — και ο
    χρήστης να τις ψάχνει σε δύο σημεία.

    Τα ονόματα των slots είναι αυτά που καλεί η σελίδα (``window.etimHost``),
    οπότε γράφονται σε camelCase όπως κάθε JavaScript API.
    """

    start_minimized_changed = Signal(bool)
    update_check_requested = Signal()
    restore_requested = Signal()

    @Slot(bool)
    def setStartMinimized(self, value: bool) -> None:  # noqa: N802 — JS API
        self.start_minimized_changed.emit(bool(value))

    @Slot()
    def checkUpdates(self) -> None:  # noqa: N802 — JS API
        self.update_check_requested.emit()

    @Slot()
    def restoreBackup(self) -> None:  # noqa: N802 — JS API
        self.restore_requested.emit()


class EtimologioWebShell(QWidget):
    """Το κέλυφος: ξεκινά το backend και δείχνει το ``app.php`` του."""

    #: Η σελίδα ζήτησε αλλαγή στο «εκκίνηση στο tray».
    start_minimized_changed = Signal(bool)
    #: Η σελίδα ζήτησε έλεγχο για ενημερώσεις.
    update_check_requested = Signal()

    def __init__(self, data_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Ο φάκελος που επέλεξε ο χρήστης στην εγκατάσταση — εκεί μέσα πέφτουν
        # και οι λήψεις, δίπλα στα παραστατικά της «Λήψης Παραστατικών».
        self._data_root = Path(data_dir)
        self._service = EtimologioService(data_dir)
        self._started = False
        self._base = ""
        self._pending_section = ""
        # `None` = «δεν το έχει πει κανείς ακόμη»: η σελίδα κρατά ό,τι είχε.
        self._theme_light: bool | None = None
        self._tips_on: bool | None = None
        #: «Εκκίνηση στο tray» + έκδοση — τα δείχνει το panel «Εφαρμογή
        #: υπολογιστή» των Ρυθμίσεων. `None` = δεν το έχει πει κανείς ακόμη.
        self._start_minimized: bool | None = None
        self._app_version = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ΜΟΝΙΜΗ μπάρα σε λειτουργία server, όχι μόνο στην οθόνη σφάλματος.
        # Η παγίδα που τη γέννησε: ο server ΑΠΑΝΤΑ κανονικά και δείχνει φόρμα
        # σύνδεσης· καμία αποτυχία, άρα καμία οθόνη σφάλματος, άρα καμία έξοδος.
        # Ο λογιστής κάθεται μπροστά σε login που δεν δέχεται τον τοπικό του
        # λογαριασμό (σωστά — είναι άλλη βάση), με τα δεδομένα του να ζουν
        # άθικτα στον δίσκο δύο εκατοστά πιο κάτω, και χωρίς τρόπο να γυρίσει.
        self._thin_bar = QWidget()
        bar = QHBoxLayout(self._thin_bar)
        bar.setContentsMargins(10, 6, 10, 6)
        self._thin_label = QLabel("")
        self._thin_label.setWordWrap(True)
        bar.addWidget(self._thin_label, 1)
        back = QPushButton("💻 Τοπικά δεδομένα")
        back.setToolTip("Επιστροφή στα δεδομένα αυτού του υπολογιστή. "
                        "Ό,τι έχει ανέβει στον server μένει εκεί.")
        back.clicked.connect(self._back_to_local)
        bar.addWidget(back, 0)
        self._thin_bar.hide()
        root.addWidget(self._thin_bar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._status = QLabel("Εκκίνηση e-Τιμολόγιο Pro…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        holder = QWidget()
        holder_box = QVBoxLayout(holder)
        holder_box.addStretch(1)
        holder_box.addWidget(self._status)
        self._retry = QPushButton("Δοκίμασε ξανά")
        self._retry.clicked.connect(self._restart)
        self._retry.hide()
        holder_box.addWidget(self._retry, 0, Qt.AlignmentFlag.AlignHCenter)
        holder_box.addStretch(1)
        self._stack.addWidget(holder)

        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        # ⚠️ Χωρίς χειριστή λήψης, το QtWebEngine **ακυρώνει σιωπηλά** κάθε
        # κατέβασμα: ο χρήστης πατούσε «PDF καρτέλας» ή «ZIP» και δεν συνέβαινε
        # τίποτα. Ρωτάμε πού να μπει το αρχείο και μετά το ανοίγουμε.
        self._view.page().profile().downloadRequested.connect(self._download)
        # Το μικρόφωνο του βοηθού: χωρίς ρητή παραχώρηση, το `getUserMedia`
        # απορρίπτεται σιωπηλά μέσα στο QtWebEngine και η φωνητική εντολή
        # «δεν κάνει τίποτα». Η σελίδα είναι η δική μας, σε loopback.
        self._view.page().featurePermissionRequested.connect(self._permission)
        # Το ενσωματωμένο UI είναι η εφαρμογή μας πάνω σε loopback — δεν υπάρχει
        # λόγος να δείχνει μενού δεξιού κλικ του browser («Reload», «View source»).
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        #: Έχει εμφανιστεί ποτέ η εφαρμογή; Ξεχωρίζει την πραγματική αποτυχία
        #: εκκίνησης από μια πλοήγηση που ακύρωσε μια λήψη.
        self._loaded_ok = False
        self._view.loadFinished.connect(self._load_finished)
        self._install_host_bridge()
        self._stack.addWidget(self._view)

    # --- η γέφυρα σελίδας ↔ εφαρμογής ---------------------------------------
    def _install_host_bridge(self) -> None:
        """Δίνει στη σελίδα ένα ``window.etimHost`` για ό,τι ξέρει μόνο το Qt.

        Το ``qwebchannel.js`` ζει ως **πόρος μέσα στο ίδιο το QtWebEngine**, δεν
        το σερβίρει ο PHP και δεν μπαίνει στο repo: δεν υπάρχει τίποτα να
        ξεχαστεί στο πακετάρισμα. Μπαίνει στο ``DocumentCreation`` ώστε το
        ``etimHost`` να υπάρχει πριν τρέξει ο κώδικας της σελίδας.

        Αν λείψει, η σελίδα απλώς δεν βλέπει γέφυρα και το panel «Εφαρμογή
        υπολογιστή» το λέει — δεν ρίχνει τίποτα.
        """
        from PySide6.QtCore import QFile, QIODevice
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineScript

        self._host = _Host(self)
        self._host.start_minimized_changed.connect(self.start_minimized_changed)
        self._host.update_check_requested.connect(self.update_check_requested)
        self._host.restore_requested.connect(self.restore_backup)

        self._channel = QWebChannel(self)
        self._channel.registerObject("etimHost", self._host)
        self._view.page().setWebChannel(self._channel)

        source = QFile(":/qtwebchannel/qwebchannel.js")
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            log.warning("Λείπει το qwebchannel.js — οι ρυθμίσεις υπολογιστή δεν θα φαίνονται")
            return
        code = bytes(source.readAll()).decode("utf-8")
        source.close()
        script = QWebEngineScript()
        script.setName("etim-host")
        script.setSourceCode(
            code
            + "\nnew QWebChannel(qt.webChannelTransport,function(c){"
            "window.etimHost=c.objects.etimHost;});\n"
        )
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self._view.page().scripts().insert(script)

    # --- κύκλος ζωής --------------------------------------------------------
    def start(self) -> None:
        """Ξεκινά το backend μία φορά και φορτώνει το UI."""
        if self._started:
            return
        self._started = True
        self._sync_thin_bar()
        self._set_status("Εκκίνηση e-Τιμολόγιο Pro…")
        _run(self._service.start_local, self._on_ready, self._on_error)

    def _sync_thin_bar(self) -> None:
        """Δείχνει τη μπάρα όσο η εφαρμογή δουλεύει πάνω στον server."""
        thin = self._service.mode() == "thin"
        if thin:
            self._thin_label.setText(
                "Λειτουργία server: βλέπεις τα δεδομένα του "
                f"{self._service.server_url()} και μπαίνεις με τα στοιχεία ΤΟΥ SERVER. "
                "Τα τοπικά δεδομένα είναι ασφαλή σε αυτόν τον υπολογιστή."
            )
        self._thin_bar.setVisible(thin)

    def _restart(self) -> None:
        self._started = False
        self._retry.hide()
        self.start()

    def shutdown(self) -> None:
        # Πρώτα η σελίδα: ένα ζωντανό QWebEngineView που δείχνει σε server που
        # μόλις σκοτώθηκε κρατά ανοιχτές συνδέσεις και καθυστερεί το κλείσιμο.
        try:
            self._view.stop()
            self._view.setUrl(QUrl("about:blank"))
        except RuntimeError:
            pass
        self._service.stop()

    # --- φόρτωση ------------------------------------------------------------
    def _on_ready(self, url: str) -> None:
        self._base = str(url).rstrip("/")
        self._view.load(QUrl(self._app_url(self._pending_section)))
        self._pending_section = ""

    def _app_url(self, section: str = "") -> str:
        """Η διεύθυνση του UI, με το κλειδί αυτόματης σύνδεσης.

        Το κλειδί ταξιδεύει σε loopback και το δέχεται μόνο ο δικός μας server
        (``auth_desktop_autologin``): ο χρήστης έχει ήδη ανοίξει την εφαρμογή
        του και ο κωδικός που θα ζητούσαμε είναι αυτός που παρήγαγε η ίδια.
        """
        token = quote(self._service.desktop_token(), safe="")
        address = f"{self._base}/app.php?desktop_token={token}"
        return f"{address}#{section}" if section else address

    def _load_finished(self, ok: bool) -> None:
        if ok:
            self._loaded_ok = True
            self._stack.setCurrentWidget(self._view)
            self._apply_prefs()
            return
        # Μια λήψη ΑΚΥΡΩΝΕΙ την τρέχουσα πλοήγηση: το QtWebEngine αναφέρει
        # «η σελίδα δεν φόρτωσε» ενώ το PDF κατεβαίνει και ανοίγει κανονικά.
        # Αν η εφαρμογή έχει ήδη εμφανιστεί, δεν τη σβήνουμε για να δείξουμε
        # μήνυμα σφάλματος που δεν αντιστοιχεί σε τίποτα.
        if self._loaded_ok:
            log.debug("Η αποτυχία πλοήγησης αγνοήθηκε — η εφαρμογή είναι ήδη φορτωμένη")
            return
        self._set_status(
            "Η εφαρμογή δεν φορτώθηκε.\n\nΤο τοπικό backend ξεκίνησε, αλλά η "
            "σελίδα δεν ήρθε. Δες το αρχείο καταγραφής για λεπτομέρειες."
        )
        self._retry.show()

    def _on_error(self, message: str) -> None:
        thin = self._service.mode() == "thin"
        where = (f"Ο server ({self._service.server_url()}) δεν απαντά."
                 if thin else "Το τοπικό backend δεν ξεκίνησε.")
        self._set_status(f"{where}\n\n{message}")
        self._retry.show()
        self._go_local.setVisible(thin)

    def _back_to_local(self) -> None:
        """Πίσω στα δεδομένα αυτού του υπολογιστή, χωρίς να χρειάζεται server.

        Το ίδιο κάνει και το «Αποσύνδεση» των Ρυθμίσεων — αλλά εκείνο ζει μέσα
        στη σελίδα, που εδώ ακριβώς δεν φορτώνει.
        """
        self._service.set_mode("offline")
        self._go_local.hide()
        self._thin_bar.hide()
        self._restart()

    def _set_status(self, text: str) -> None:
        self._status.setText(text)
        self._stack.setCurrentIndex(0)

    # --- δικαιώματα σελίδας -------------------------------------------------
    def _permission(self, origin, feature) -> None:
        from PySide6.QtWebEngineCore import QWebEnginePage

        allowed = {
            QWebEnginePage.Feature.MediaAudioCapture,
        }
        page = self._view.page()
        policy = (
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            if feature in allowed
            else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )
        page.setFeaturePermission(origin, feature, policy)

    # --- λήψεις -------------------------------------------------------------
    def _download(self, item) -> None:
        """Αποθηκεύει το αρχείο στον φάκελο λήψεων και το ανοίγει.

        ΔΕΝ ρωτά. Ο διάλογος «πού να το βάλω;» έβγαινε σε κάθε PDF, και όποτε ο
        χρήστης τον έκλεινε η λήψη **ακυρωνόταν σιωπηλά**: το κουμπί έμοιαζε
        χαλασμένο. Ο φάκελος αλλάζει από τον Πίνακα ελέγχου.
        """
        from .. import config

        suggested = item.downloadFileName() or "αρχείο"
        folder = config.resolve_download_dir(self._data_root)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Απρόσιτος φάκελος (π.χ. δικτυακός που έπεσε): «Λήψεις» του χρήστη,
            # ώστε το αρχείο να φτάσει κάπου αντί να χαθεί.
            folder = Path.home() / "Downloads"
            folder.mkdir(parents=True, exist_ok=True)
        # Ίδιο παραστατικό = ίδιο αρχείο. Χωρίς αυτό, το δεύτερο κατέβασμα
        # άφηνε «ΠΑΡΑΣΤΑΤΙΚΟ (1).pdf» δίπλα σε ένα πανομοιότυπο «ΠΑΡΑΣΤΑΤΙΚΟ.pdf»
        # και ο φάκελος γέμιζε αντίγραφα του ίδιου εγγράφου.
        path = folder / suggested
        try:
            if path.exists():
                path.unlink()
        except OSError:
            # Κλειδωμένο (π.χ. ανοιχτό στον αναγνώστη PDF): καλύτερα ένα
            # δεύτερο όνομα παρά χαμένη λήψη.
            path = _free_name(path)
        item.setDownloadDirectory(str(path.parent))
        item.setDownloadFileName(path.name)
        item.isFinishedChanged.connect(lambda: self._download_done(item, path))
        item.accept()
        log.info("Λήψη → %s", path)

    def _download_done(self, item, path: Path) -> None:
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

        if item.state() != QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            return
        from .pages import ui

        ui.open_file(path, self)

    # --- πλοήγηση από το πλαϊνό μενού --------------------------------------
    #: Κλειδί μενού → `data-view` του web. Ό,τι δεν υπάρχει εδώ ανοίγει την
    #: αρχική οθόνη της εφαρμογής.
    _VIEWS = {
        "issue": "issue", "bulk": "bulk", "customers": "customers",
        "card": "card", "companies": "admin", "products": "products",
        "series": "series", "drafts": "drafts", "credit": "cancel",
        "payments": "bankimp", "stats": "stats", "schedule": "schedule",
        "settings": "settings", "admin": "admin",
        # Η «Παραστατικά» έχει πλέον δική της ενότητα στο web (όλα τα
        # παραστατικά του έτους, με μαζική εκτύπωση/ZIP)· έδειχνε στην Καρτέλα.
        "documents": "documents",
        "home": "issue",
    }

    #: Ό,τι δεν είναι σελίδα αλλά κουμπί της σελίδας. Το μενού της εφαρμογής
    #: υπολογιστή τα καλούσε ως «ενότητες» και άνοιγαν λάθος οθόνη — π.χ. οι
    #: «Ειδοποιήσεις» πήγαιναν στην Έκδοση.
    _ACTIONS = {
        "notifications": "toggleNotifPanel();",
        "tour": "startTour();",
        "manual": "downloadManual();",
        "assistant": "cbTogglePanel();",
    }

    def open_section(self, key: str, *, remember: bool = True) -> None:
        """Ανοίγει μια ενότητα του web UI (το πλαϊνό μενού το καλεί)."""
        action = self._ACTIONS.get(key)
        if action:
            self._js(action)
            return
        view = self._VIEWS.get(key, "")
        if not self._base:
            self._pending_section = view
            return
        if not view:
            return
        # Η αλλαγή γίνεται μέσα στη σελίδα, χωρίς επαναφόρτωση: το `showView`
        # είναι η ίδια συνάρτηση που καλεί το μενού του web.
        self._js(f"showView({view!r});")

    def _js(self, code: str) -> None:
        """Τρέχει κώδικα στη σελίδα, αγνοώντας ό,τι δεν υπάρχει ακόμη."""
        try:
            self._view.page().runJavaScript("try{" + code + "}catch(e){}")
        except RuntimeError:
            pass

    def start_tour(self) -> None:
        self._js("startTour();")

    def open_manual(self) -> None:
        self._js("downloadManual();")

    def toggle_assistant(self) -> None:
        self._js("cbTogglePanel();")

    def toggle_notifications(self) -> None:
        self._js("toggleNotifPanel();")

    # --- ρυθμίσεις που ζουν στο πλαϊνό μενού της εφαρμογής ------------------
    # Το θέμα και τα βοηθητικά μηνύματα έχουν διακόπτη στο μενού του Downloader,
    # αλλά η ενσωματωμένη σελίδα δεν τους άκουγε: άλλαζε το Qt και η σελίδα
    # έμενε σκούρα (ή γεμάτη tooltips). Οι ίδιοι διακόπτες οδηγούν τώρα και τα
    # δύο — η σελίδα κρύβει τη δική της στήλη ρυθμίσεων όταν είναι ενσωματωμένη.
    def set_theme(self, light: bool) -> None:
        self._theme_light = bool(light)
        self._apply_prefs()

    def set_tooltips(self, on: bool) -> None:
        self._tips_on = bool(on)
        self._apply_prefs()

    # --- επαναφορά από αντίγραφο -------------------------------------------
    def restore_backup(self) -> None:
        """Επαναφορά της βάσης του e-Τιμολόγιο από αντίγραφο.

        ΓΙΑΤΙ ΕΔΩ ΚΑΙ ΟΧΙ ΣΤΗΝ PHP: η επαναφορά αντικαθιστά τη βάση πάνω στην
        οποία τρέχει ο ίδιος ο server. Πρέπει πρώτα να σταματήσει — και μόνο
        αυτή η πλευρά ελέγχει τον κύκλο ζωής του. Το «Αντίγραφο τώρα» μένει
        στην PHP: εκεί δεν χρειάζεται να σταματήσει τίποτα.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from . import backup as etim_backup

        folder = etim_backup.backups_dir(self._service.data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        found = etim_backup.list_backups(self._service.data_dir)
        if found:
            newest, when, size = found[0]
            answer = QMessageBox.question(
                self, "Επαναφορά e-Τιμολόγιο",
                f"Επαναφορά από το πιο πρόσφατο αντίγραφο;\n\n"
                f"{newest.name}\n{when:%d/%m/%Y %H:%M} · {size / 1024:.0f} KB\n\n"
                "Η τρέχουσα κατάσταση κρατιέται ως «pre-restore», οπότε η ενέργεια "
                "είναι αναστρέψιμη.\n\n«Άλλο αρχείο…» για δικό σας zip.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Open,
            )
            if answer == QMessageBox.StandardButton.No:
                return
            chosen = newest if answer == QMessageBox.StandardButton.Yes else None
        else:
            chosen = None
        if chosen is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Επιλέξτε αντίγραφο e-Τιμολόγιο", str(folder),
                "Αντίγραφο (*.zip);;Όλα τα αρχεία (*.*)",
            )
            if not path:
                return
            chosen = Path(path)

        # Ο server ΚΡΑΤΑΕΙ τη βάση ανοιχτή: χωρίς αυτό, η SQLite θα έγραφε το
        # παλιό WAL πάνω στη νέα βάση μόλις έκλεινε.
        self.shutdown()
        self._started = False
        try:
            written = etim_backup.restore(chosen, self._service.data_dir)
        except Exception as exc:  # noqa: BLE001 — φτάνει στον χρήστη ως μήνυμα
            QMessageBox.warning(
                self, "Επαναφορά", f"Η επαναφορά δεν έγινε:\n\n{exc}"
            )
            self.start()
            return
        self.start()
        QMessageBox.information(
            self, "Επαναφορά",
            f"Έγινε επαναφορά από:\n{chosen.name}\n\nΑρχεία: {', '.join(written)}",
        )

    def set_desktop_prefs(self, start_minimized: bool, version: str = "") -> None:
        """Η κατάσταση των ρυθμίσεων του προγράμματος, για το panel της σελίδας."""
        self._start_minimized = bool(start_minimized)
        if version:
            self._app_version = str(version)
        self._apply_prefs()

    def _apply_prefs(self) -> None:
        """Στέλνει θέμα + βοηθητικά μηνύματα στη σελίδα.

        Καλείται και μετά από κάθε φόρτωση: μια ρύθμιση που άλλαξε πριν ανοίξει
        η σελίδα δεν έχει πού να πάει, και χωρίς αυτό η πρώτη εμφάνιση ερχόταν
        πάντα με τις προεπιλογές της σελίδας.
        """
        if self._theme_light is not None:
            name = "light" if self._theme_light else "dark"
            self._js(f"applyTheme('{name}');localStorage.setItem('etim_theme','{name}');")
        if self._tips_on is not None:
            flag = "true" if self._tips_on else "false"
            stored = "1" if self._tips_on else "0"
            self._js(f"applyTips({flag});localStorage.setItem('etim_tips','{stored}');")
        if self._start_minimized is not None or self._app_version:
            payload = json.dumps(
                {"tray": self._start_minimized, "version": self._app_version}
            )
            self._js(f"applyDesktopPrefs({payload});")

    # --- συμβατότητα με το κέλυφος του Downloader ---------------------------
    def focus_customer(self, vat: str) -> None:
        """Ανοίγει την καρτέλα ενός ΑΦΜ (το ζητά η «Λήψη Παραστατικών»)."""
        digits = "".join(ch for ch in str(vat) if ch.isdigit())
        if not digits:
            return
        self._view.page().runJavaScript(
            f"try{{openCard({digits!r},'');}}catch(e){{}}"
        )


__all__ = ["EtimologioWebShell", "webengine_available"]
