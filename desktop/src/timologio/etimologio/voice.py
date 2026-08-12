"""Φωνητική είσοδος για τον βοηθό — Vosk, εντελώς εκτός δικτύου.

Γιατί Vosk και όχι το Web Speech API του web: εκείνο στέλνει τον ήχο στους
servers της Google και δουλεύει μόνο μέσα σε Chromium. Η εφαρμογή υπολογιστή
δουλεύει και χωρίς σύνδεση, και τα λόγια του λογιστή («τιμολόγιο στον πελάτη Χ»)
δεν έχουν λόγο να ταξιδεύουν.

**Το μοντέλο δεν πακετάρεται.** Το μοναδικό ελληνικό μοντέλο του Vosk
(``vosk-model-el-gr-0.7``) είναι ~1.1 GB — δεκαπλάσιο από ολόκληρο τον installer.
Μπαίνει με τη θέλησή του χρήστη, μία φορά, και ζει στον φάκελο δεδομένων.
Ό,τι λείπει το λέμε ρητά, αντί ένα κουμπί μικροφώνου να μη κάνει τίποτα.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger(__name__)

#: Ρυθμός δειγματοληψίας που περιμένουν τα μοντέλα του Vosk.
SAMPLE_RATE = 16000

#: Υποφάκελος του φακέλου δεδομένων όπου ψάχνουμε το μοντέλο.
MODEL_DIRNAME = "vosk-model-el"

#: Από πού κατεβαίνει, όταν το ζητήσει ο χρήστης (το λέμε, δεν το κάνουμε μόνοι).
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-el-gr-0.7.zip"


def model_path(data_dir: Path) -> Path | None:
    """Ο φάκελος του μοντέλου: μεταβλητή περιβάλλοντος → δεδομένα → bundle."""
    env = os.environ.get("TIMOLOGIO_VOSK_MODEL", "").strip()
    candidates = [Path(env)] if env else []
    candidates.append(Path(data_dir) / MODEL_DIRNAME)
    base = getattr(sys, "_MEIPASS", "")
    if base:
        candidates.append(Path(base) / MODEL_DIRNAME)
    for candidate in candidates:
        # Ένας φάκελος μοντέλου έχει πάντα `am/` ή `conf/`· ένας άδειος φάκελος
        # με το σωστό όνομα θα έσκαγε αργότερα, μέσα στο Vosk.
        if candidate.is_dir() and any((candidate / part).exists() for part in ("am", "conf")):
            return candidate
    return None


def missing(data_dir: Path) -> str:
    """Τι λείπει για να δουλέψει η φωνή («» όταν όλα είναι στη θέση τους)."""
    try:
        import vosk  # noqa: F401
        import sounddevice  # noqa: F401
    except Exception:  # noqa: BLE001 — λείπει ή δεν φορτώνει το πακέτο
        return (
            "Λείπουν τα πακέτα φωνής. Εγκατάστασή τους:\n"
            "    pip install vosk sounddevice"
        )
    if model_path(data_dir) is None:
        return (
            "Λείπει το ελληνικό μοντέλο αναγνώρισης (~1.1 GB).\n"
            f"Κατέβασέ το από {MODEL_URL}\n"
            f"και αποσυμπίεσέ το ως: {Path(data_dir) / MODEL_DIRNAME}"
        )
    return ""


def available(data_dir: Path) -> bool:
    return not missing(data_dir)


class _Listener(QThread):
    """Διαβάζει το μικρόφωνο και βγάζει τελικές φράσεις.

    Ζει σε δικό του νήμα: το ``sounddevice`` μπλοκάρει στην ανάγνωση, και στο
    νήμα του UI θα πάγωνε ολόκληρο το παράθυρο όσο ακούει.
    """

    heard = Signal(str)
    failed = Signal(str)

    def __init__(self, model_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model_dir = model_dir
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # pragma: no cover — χρειάζεται μικρόφωνο
        try:
            import sounddevice as sd
            import vosk

            vosk.SetLogLevel(-1)
            model = vosk.Model(str(self._model_dir))
            recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Η αναγνώριση δεν ξεκίνησε: {exc}")
            return

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16", channels=1
            ) as stream:
                while not self._stop:
                    data, _overflow = stream.read(4000)
                    if recognizer.AcceptWaveform(bytes(data)):
                        text = json.loads(recognizer.Result()).get("text", "").strip()
                        if text:
                            self.heard.emit(text)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Το μικρόφωνο σταμάτησε: {exc}")


class VoiceInput(QObject):
    """Διακόπτης μικροφώνου: ``toggle()`` και ένα σήμα με ό,τι ακούστηκε."""

    heard = Signal(str)
    failed = Signal(str)
    #: True όσο ακούει — για να χρωματιστεί το κουμπί.
    listening_changed = Signal(bool)

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._data_dir = Path(data_dir)
        self._listener: _Listener | None = None

    @property
    def listening(self) -> bool:
        return self._listener is not None and self._listener.isRunning()

    def missing(self) -> str:
        return missing(self._data_dir)

    def toggle(self) -> None:
        if self.listening:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.listening:
            return
        reason = missing(self._data_dir)
        if reason:
            self.failed.emit(reason)
            return
        model_dir = model_path(self._data_dir)
        if model_dir is None:  # pragma: no cover — καλύπτεται από το missing()
            self.failed.emit("Δεν βρέθηκε το μοντέλο φωνής.")
            return
        listener = _Listener(model_dir, self)
        listener.heard.connect(self.heard)
        listener.failed.connect(self._on_failed)
        listener.finished.connect(lambda: self.listening_changed.emit(False))
        self._listener = listener
        listener.start()
        self.listening_changed.emit(True)

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        if listener is None:
            return
        listener.stop()
        # Χωρίς αναμονή, το νήμα θα καταστρεφόταν μαζί με το γονικό αντικείμενο
        # ενώ ακόμη διαβάζει από το μικρόφωνο.
        listener.wait(3000)
        self.listening_changed.emit(False)

    def _on_failed(self, message: str) -> None:
        self._listener = None
        self.listening_changed.emit(False)
        self.failed.emit(message)
