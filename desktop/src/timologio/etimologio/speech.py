"""Ο βοηθός μιλάει — ελληνικά και αγγλικά, με **δική μας** φωνή.

Γιατί δεν αρκεί η φωνή του λειτουργικού
---------------------------------------
Η πρώτη υλοποίηση ζητούσε ελληνική φωνή από τα Windows (``QtTextToSpeech``) και
το web από τον browser (``speechSynthesis``). Και τα δύο απέτυχαν στο ίδιο
σημείο: **τα Windows δεν έχουν ελληνική φωνή εγκατεστημένη** από προεπιλογή, και
ο browser κληρονομεί τις ίδιες φωνές. Το αποτέλεσμα ήταν είτε σιωπή είτε — χειρότερα —
μια αγγλική φωνή που **συλλάβιζε γράμμα-γράμμα** τους ελληνικούς χαρακτήρες.

Η μόνιμη λύση είναι να κουβαλάμε τη φωνή μαζί μας: **Piper** (νευρωνικό TTS,
άδεια MIT, εκτός δικτύου) με ένα ελληνικό και ένα αγγλικό μοντέλο. Ό,τι ακούει ο
χρήστης δεν εξαρτάται πια από το τι έχει εγκαταστήσει στα Windows.

Η αναπαραγωγή γίνεται με το ``winsound`` της βασικής βιβλιοθήκης — όχι με
QtMultimedia, που δεν πακετάρεται (εξαιρείται ρητά στο spec για μέγεθος).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)

#: Υποφάκελος με τη μηχανή και τα μοντέλα, μέσα στο bundle ή στα δεδομένα.
PIPER_DIRNAME = "piper"

#: Γλώσσα → αρχή του ονόματος του μοντέλου. Ό,τι ταιριάζει πρώτο κερδίζει, ώστε
#: μια αναβάθμιση μοντέλου να μη χρειάζεται αλλαγή κώδικα.
_VOICE_PREFIX = {"el": "el_", "en": "en_"}

#: Ποια φωνή προτιμάμε όταν υπάρχουν πολλές για την ίδια γλώσσα. Η «joy» σε
#: medium είναι πιο αργή και πιο καθαρή στην άρθρωση από τη rapunzelina — σε
#: αριθμούς και ΑΦΜ, που είναι το μισό περιεχόμενο των απαντήσεων, η διαφορά
#: φαίνεται. Ό,τι δεν είναι εδώ κρίνεται αλφαβητικά, όπως πριν.
_VOICE_PREFERRED = {
    "el": ("el_GR-joy-medium", "el_GR-rapunzelina-medium", "el_GR-rapunzelina-low"),
    "en": ("en_US-lessac-medium", "en_US-lessac-low"),
}

WINDOWS_SPEECH_SETTINGS = "ms-settings:speech"

MISSING_VOICE_HINT = (
    "Δεν βρέθηκε η μηχανή φωνής. Ο βοηθός απαντά μόνο γραπτά — "
    "επανεγκατέστησε την εφαρμογή για να μπει ξανά."
)


def _roots(data_dir: Path | None) -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("TIMOLOGIO_PIPER", "").strip()
    if env:
        roots.append(Path(env))
    base = getattr(sys, "_MEIPASS", "")
    if base:
        roots.append(Path(base) / PIPER_DIRNAME)
    if data_dir is not None:
        roots.append(Path(data_dir) / PIPER_DIRNAME)
    return roots


def engine_path(data_dir: Path | None = None) -> Path | None:
    """Το εκτελέσιμο του Piper, αν ταξιδεύει μαζί μας."""
    name = "piper.exe" if os.name == "nt" else "piper"
    for root in _roots(data_dir):
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def voice_path(lang: str, data_dir: Path | None = None) -> Path | None:
    """Το μοντέλο φωνής για μια γλώσσα («el» ή «en»)."""
    code = str(lang or "el")[:2].lower()
    prefix = _VOICE_PREFIX.get(code, "el_")
    preferred = _VOICE_PREFERRED.get(code, ())
    for root in _roots(data_dir):
        folder = root / "voices"
        if not folder.is_dir():
            continue
        # Το .json δίπλα του κρατά τη ρύθμιση· χωρίς αυτό το Piper σκάει.
        found = [m for m in sorted(folder.glob(f"{prefix}*.onnx"))
                 if m.with_suffix(".onnx.json").exists()]
        if not found:
            continue
        for name in preferred:
            for model in found:
                if model.stem == name:
                    return model
        return found[0]
    return None


# --- Αναγνώριση φωνής (whisper.cpp) -----------------------------------------
#
# Το Web Speech API στηρίζεται σε υπηρεσία της Google: μέσα στο QtWebEngine δεν
# υπάρχει, και η κλήση **παγώνει την εφαρμογή** αντί να αποτύχει. Το Vosk έχει
# ελληνικό μοντέλο ~1,1 GB — δεκαπλάσιο του installer. Το whisper.cpp με το
# `base` (~142 MB) είναι πολύγλωσσο, τρέχει σε CPU και χωράει στο πακέτο.

#: Υποφάκελος με τη μηχανή και το μοντέλο αναγνώρισης.
WHISPER_DIRNAME = "whisper"

#: Τα ονόματα που έχει πάρει το εκτελέσιμο κατά καιρούς (`main.exe` πριν το 2024).
_WHISPER_EXE_NAMES = ("whisper-cli.exe", "main.exe", "whisper-cli", "main")


def _whisper_roots(data_dir: Path | None) -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("TIMOLOGIO_WHISPER", "").strip()
    if env:
        roots.append(Path(env))
    base = getattr(sys, "_MEIPASS", "")
    if base:
        roots.append(Path(base) / WHISPER_DIRNAME)
    if data_dir is not None:
        roots.append(Path(data_dir) / WHISPER_DIRNAME)
    return roots


def whisper_engine(data_dir: Path | None = None) -> Path | None:
    """Το εκτελέσιμο του whisper.cpp, αν ταξιδεύει μαζί μας."""
    for root in _whisper_roots(data_dir):
        for name in _WHISPER_EXE_NAMES:
            candidate = root / name
            if candidate.exists():
                return candidate
    return None


def whisper_model(data_dir: Path | None = None) -> Path | None:
    """Το μοντέλο αναγνώρισης (`ggml-*.bin`) — το μεγαλύτερο που βρεθεί."""
    for root in _whisper_roots(data_dir):
        models = sorted(root.glob("ggml-*.bin"), key=lambda p: p.stat().st_size)
        if models:
            return models[-1]
    return None


def stt_missing(data_dir: Path | None = None) -> str:
    """Τι λείπει για φωνητική εντολή («» όταν όλα είναι στη θέση τους)."""
    if whisper_engine(data_dir) is None:
        return "Δεν βρέθηκε η μηχανή αναγνώρισης φωνής."
    if whisper_model(data_dir) is None:
        return "Λείπει το μοντέλο αναγνώρισης φωνής."
    return ""


def missing(data_dir: Path | None = None) -> str:
    """Τι λείπει για να ακουστεί φωνή («» όταν όλα είναι στη θέση τους)."""
    if engine_path(data_dir) is None:
        return MISSING_VOICE_HINT
    if voice_path("el", data_dir) is None and voice_path("en", data_dir) is None:
        return "Λείπουν τα μοντέλα φωνής (ελληνικό/αγγλικό)."
    return ""


class Speaker:
    """Εκφωνεί κείμενο. Κάθε αποτυχία γίνεται σιωπή + αιτία, ποτέ εξαίρεση."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else None
        self._engine = engine_path(self._data_dir)
        self.problem = missing(self._data_dir)
        self._current: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._engine is not None and not self.problem

    def warm_up(self, lang: str = "el") -> None:
        """Φορτώνει το μοντέλο μία φορά, χωρίς να ακουστεί τίποτα.

        Η πρώτη σύνθεση πληρώνει το φόρτωμα του μοντέλου. Επειδή η αναπαραγωγή
        ξεκινά μαζί με τη σύνθεση, αυτό το κόστος **τρώει τις πρώτες λέξεις**:
        ο βοηθός ακούγεται σαν να μπερδεύεται στην αρχή κάθε πρώτης πρότασης.
        Μία άφωνη σύνθεση στην εκκίνηση το εξαφανίζει.
        """
        if not self.available:
            return
        voice = voice_path(lang, self._data_dir)
        if voice is None:
            return

        def _run() -> None:
            try:
                wav = self.synthesize("ένα", voice)
            except Exception:  # noqa: BLE001 — η προθέρμανση δεν αποτυγχάνει «δυνατά»
                return
            if wav is not None:
                try:
                    wav.unlink(missing_ok=True)
                except OSError:
                    pass

        threading.Thread(target=_run, daemon=True).start()

    def say(self, text: str, lang: str = "el") -> bool:
        """Λέει το κείμενο στη γλώσσα που ζητήθηκε. Δεν μπλοκάρει το UI."""
        if not self.available:
            return False
        clean = _speakable(text)
        if not clean:
            return False
        # Κόμμα και παύση πριν την πρόταση: χωρίς αυτό η πρώτη συλλαβή βγαίνει
        # κομμένη και ακούγεται σαν λάθος λέξη, όχι σαν καθυστέρηση.
        clean = ", " + clean
        voice = voice_path(lang, self._data_dir) or voice_path("el", self._data_dir)
        if voice is None:
            self.problem = "Λείπει το μοντέλο φωνής για αυτή τη γλώσσα."
            return False
        # Σε νήμα: η σύνθεση παίρνει κλάσματα δευτερολέπτου, αλλά η αναπαραγωγή
        # διαρκεί όσο η πρόταση — και το UI δεν έχει λόγο να περιμένει.
        threading.Thread(
            target=self._speak_now, args=(clean, voice), daemon=True
        ).start()
        return True

    def _speak_now(self, text: str, voice: Path) -> None:
        try:
            wav = self.synthesize(text, voice)
        except Exception as exc:  # noqa: BLE001 — η φωνή δεν ρίχνει την εφαρμογή
            log.warning("Η σύνθεση φωνής απέτυχε: %s", exc)
            self.problem = f"Η σύνθεση φωνής απέτυχε ({exc})."
            return
        if wav is None:
            return
        try:
            _play(wav)
        finally:
            try:
                wav.unlink(missing_ok=True)
            except OSError:
                pass

    def synthesize(self, text: str, voice: Path) -> Path | None:
        """Γράφει ένα WAV με τη φωνή· επιστρέφει τη διαδρομή του."""
        if self._engine is None:
            return None
        # Το `mkstemp` επιστρέφει ΑΝΟΙΧΤΟ descriptor: αν δεν κλείσει, στα Windows
        # το αρχείο μένει κλειδωμένο και δεν σβήνεται ποτέ μετά την αναπαραγωγή.
        handle, name = tempfile.mkstemp(prefix="etim_tts_", suffix=".wav")
        os.close(handle)
        target = Path(name)
        command = [
            str(self._engine), "--model", str(voice),
            "--output_file", str(target),
        ]
        creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with self._lock:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, creationflags=creation,
            )
            self._current = process
        _out, err = process.communicate(text.encode("utf-8"), timeout=60)
        self._current = None
        if process.returncode != 0 or not target.exists() or target.stat().st_size < 64:
            detail = (err or b"").decode("utf-8", "replace").strip()[:200]
            raise RuntimeError(detail or f"piper exit {process.returncode}")
        return target

    def stop(self) -> None:
        process = self._current
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        _stop_playback()


def _speakable(text: str) -> str:
    """Καθαρό κείμενο για εκφώνηση — χωρίς εικονίδια, που διαβάζονται ένα-ένα.

    ⚠️ Και **πεζά**: τα ελληνικά κεφαλαία γράφονται χωρίς τόνο («ΕΚΔΟΘΗΚΕ»),
    οπότε η μηχανή δεν ξέρει πού πέφτει η έμφαση — προφέρει λάθος τη λέξη ή τη
    συλλαβίζει σαν ακρωνύμιο. Η ίδια λέξη πεζή ακούγεται σωστά.
    """
    clean = " ".join(str(text or "").split())
    return "".join(
        ch for ch in clean
        if ch.isalnum() or ch.isspace() or ch in ".,;:!?%€-/()'"
    ).strip().lower()


def _play(wav: Path) -> None:
    if os.name == "nt":
        import winsound

        winsound.PlaySound(str(wav), winsound.SND_FILENAME)
        return
    subprocess.run(["aplay", "-q", str(wav)], check=False)


def _stop_playback() -> None:
    if os.name != "nt":
        return
    import winsound

    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except RuntimeError:
        pass


__all__ = [
    "Speaker", "missing", "engine_path", "voice_path",
    "whisper_engine", "whisper_model", "stt_missing",
    "MISSING_VOICE_HINT", "WINDOWS_SPEECH_SETTINGS", "PIPER_DIRNAME",
    "WHISPER_DIRNAME",
]
