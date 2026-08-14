"""Ο βοηθός μιλάει — ελληνικά, με τη φωνή του συστήματος.

Στο web ο βοηθός απαντούσε φωναχτά (`speechSynthesis` με `el-GR`). Η εφαρμογή
υπολογιστή μόνο **άκουγε**: είχε αναγνώριση φωνής (Vosk) και καμία εκφώνηση,
οπότε δικαιολογημένα «δεν μιλάει πια».

Εδώ χρησιμοποιείται το ``QtTextToSpeech`` του Qt (SAPI/WinRT στα Windows) —
τίποτα να εγκατασταθεί, τίποτα να πακεταριστεί.

**Η ελληνική φωνή είναι του λειτουργικού, όχι δική μας.** Ο browser κουβαλά
δικές του φωνές· τα Windows όχι — αν δεν έχει εγκατασταθεί ελληνική φωνή, οι
διαθέσιμες είναι μόνο αγγλικές. Σε αυτή την περίπτωση **δεν μιλάμε**: ελληνικό
κείμενο με αγγλική φωνή βγαίνει ακατάληπτο και μοιάζει με σφάλμα. Λέμε καθαρά τι
λείπει και πού μπαίνει.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

#: Πού προστίθεται ελληνική φωνή στα Windows (ρυθμίσεις ομιλίας).
WINDOWS_SPEECH_SETTINGS = "ms-settings:speech"

#: Τι να πει το UI όταν λείπει η ελληνική φωνή.
MISSING_VOICE_HINT = (
    "Δεν υπάρχει ελληνική φωνή στα Windows, οπότε ο βοηθός απαντά μόνο γραπτά. "
    "Πρόσθεσέ την από: Ρυθμίσεις → Ώρα και γλώσσα → Ομιλία → Προσθήκη φωνών → "
    "Ελληνικά."
)


def _is_greek(locale: Any) -> bool:
    name = ""
    try:
        name = str(locale.name())
    except Exception:  # noqa: BLE001 — άγνωστος τύπος locale
        name = str(locale)
    return name.lower().startswith("el")


class Speaker:
    """Εκφωνεί ελληνικά, ή εξηγεί γιατί δεν μπορεί.

    Δεν είναι QObject: ζει μέσα στο panel του βοηθού και δεν εκπέμπει σήματα.
    Κάθε αποτυχία καταλήγει σε «σιωπή + αιτία», ποτέ σε εξαίρεση — μια φωνή που
    δεν παίζει δεν πρέπει να ρίχνει την έκδοση παραστατικού.
    """

    def __init__(self) -> None:
        self._tts: Any = None
        self.problem = ""
        self.voice_name = ""
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
        except Exception as exc:  # noqa: BLE001 — λείπει το module του Qt
            self.problem = f"Η εκφώνηση δεν είναι διαθέσιμη σε αυτή την έκδοση του Qt ({exc})."
            return
        try:
            self._tts = QTextToSpeech()
        except Exception as exc:  # noqa: BLE001 — καμία μηχανή ομιλίας
            self.problem = f"Δεν βρέθηκε μηχανή ομιλίας ({exc})."
            self._tts = None
            return
        self._select_greek()

    # --- επιλογή φωνής ------------------------------------------------------
    def _select_greek(self) -> None:
        tts = self._tts
        if tts is None:
            return
        greek = next((loc for loc in tts.availableLocales() if _is_greek(loc)), None)
        if greek is None:
            self.problem = MISSING_VOICE_HINT
            return
        tts.setLocale(greek)
        voices = tts.availableVoices()
        if voices:
            tts.setVoice(voices[0])
            self.voice_name = voices[0].name()
        self.problem = ""

    @property
    def available(self) -> bool:
        """Μπορεί να μιλήσει **ελληνικά** — όχι απλώς να μιλήσει."""
        return self._tts is not None and not self.problem

    # --- εκφώνηση -----------------------------------------------------------
    def say(self, text: str) -> bool:
        """Λέει το κείμενο. Επιστρέφει αν όντως ακούστηκε."""
        if not self.available:
            return False
        clean = " ".join(str(text or "").split())
        # Τα σύμβολα του UI («✅», «➕») διαβάζονται ένα προς ένα και ακούγονται
        # σαν θόρυβος ανάμεσα στις λέξεις.
        clean = "".join(ch for ch in clean if ch.isalnum() or ch in " .,;:!?%€-/")
        if not clean:
            return False
        try:
            self._tts.stop()
            self._tts.say(clean)
            return True
        except Exception as exc:  # noqa: BLE001 — η μηχανή μπορεί να χαθεί
            log.warning("Η εκφώνηση απέτυχε: %s", exc)
            self.problem = f"Η εκφώνηση απέτυχε ({exc})."
            return False

    def stop(self) -> None:
        if self._tts is not None:
            try:
                self._tts.stop()
            except Exception:  # noqa: BLE001
                pass


__all__ = ["Speaker", "MISSING_VOICE_HINT", "WINDOWS_SPEECH_SETTINGS"]
