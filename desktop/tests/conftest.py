"""Κοινές ρυθμίσεις για όλα τα tests.

**Οι ρυθμίσεις του χρήστη είναι εκτός ορίων.** Οι σελίδες θυμούνται πλάτη,
σειρά και ταξινόμηση στηλών μέσω ``QSettings``. Χωρίς απομόνωση, δύο πράγματα
συνέβαιναν και τα δύο άσχημα: το test suite διάβαζε την κατάσταση της
πραγματικής εγκατάστασης (μια ταξινόμηση που έκανε ο χρήστης με το ποντίκι
άλλαζε το αποτέλεσμα ενός assert) και έγραφε πάνω της.

Το redirect γίνεται στην εισαγωγή του conftest — πριν φτιαχτεί οποιοδήποτε
``QSettings`` από τα modules που εισάγουν τα tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

try:
    from PySide6.QtCore import QCoreApplication, QSettings
except ImportError:  # pragma: no cover — τα GUI tests κάνουν skip μόνα τους
    QSettings = None


if QSettings is not None:
    _SETTINGS_DIR = Path(tempfile.mkdtemp(prefix="timologio-tests-"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(_SETTINGS_DIR)
    )
    # Ρητά ονόματα: αλλιώς το QSettings() χωρίς παραμέτρους γράφει σε αρχείο με
    # το όνομα του εκτελέσιμου (python.ini) — κοινό για κάθε έργο στο μηχάνημα.
    QCoreApplication.setOrganizationName("scanmydata-tests")
    QCoreApplication.setApplicationName("timologio-tests")


@pytest.fixture(autouse=True)
def _clean_settings():
    """Κάθε test ξεκινά με καθαρές προτιμήσεις στηλών."""
    if QSettings is None:
        yield
        return
    QSettings().clear()
    yield
