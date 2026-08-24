"""Ο χρονοπρογραμματισμός της αυτόματης λήψης.

Η λογική «πότε είναι η ώρα;» είναι το είδος που σπάει σιωπηλά: ένα λάθος εδώ
είτε δεν κατεβάζει ποτέ, είτε κατεβάζει σε κάθε τικ του ρολογιού. Τίποτα από τα
δύο δεν φαίνεται πριν το δει ο πελάτης.
"""

from __future__ import annotations

from datetime import datetime

from timologio.schedule import SyncSchedule, from_dict, to_dict

MON = datetime(2026, 8, 24, 9, 0)   # Δευτέρα
TUE = datetime(2026, 8, 25, 9, 0)   # Τρίτη


def test_disabled_never_fires() -> None:
    assert SyncSchedule(at="00:00").is_due(MON) is False
    assert SyncSchedule(at="00:00").next_run(MON) is None


def test_fires_after_its_hour_and_only_once_a_day() -> None:
    """Ο έλεγχος γίνεται στο ΡΑΝΤΕΒΟΥ της ημέρας, όχι σε «πέρασαν 24 ώρες»."""
    daily = SyncSchedule(enabled=True, at="07:00")
    assert daily.is_due(MON.replace(hour=6, minute=59)) is False
    assert daily.is_due(MON.replace(hour=7)) is True
    # Έτρεξε ήδη σήμερα στις 07:05 -> δεν ξαναχτυπά μέχρι αύριο.
    assert daily.is_due(MON.replace(hour=23), MON.replace(hour=7, minute=5)) is False
    # Χθεσινή εκτέλεση δεν καλύπτει το σημερινό ραντεβού.
    assert daily.is_due(MON.replace(hour=8), MON.replace(day=23, hour=7)) is True


def test_a_missed_appointment_runs_when_the_machine_comes_back() -> None:
    """Κλειστός υπολογιστής στις 07:00, άνοιγμα στις 11:00: κατεβάζει."""
    daily = SyncSchedule(enabled=True, at="07:00")
    assert daily.is_due(MON.replace(hour=11)) is True


def test_days_filter_and_empty_means_every_day() -> None:
    only_monday = SyncSchedule(enabled=True, at="07:00", days=frozenset({0}))
    assert only_monday.is_due(MON) is True
    assert only_monday.is_due(TUE) is False
    assert SyncSchedule(enabled=True, at="07:00").is_due(TUE) is True


def test_next_run_looks_far_enough_ahead() -> None:
    """Με επτά μέρες, «μόνο Δευτέρα» ρωτημένο Δευτέρα δεν έβρισκε ποτέ επόμενη."""
    only_monday = SyncSchedule(enabled=True, at="07:00", days=frozenset({0}))
    upcoming = only_monday.next_run(MON)   # Δευτέρα 09:00, το ραντεβού πέρασε
    assert upcoming == datetime(2026, 8, 31, 7, 0)


def test_targets_never_include_clients_without_credentials() -> None:
    """Το «έγκυρα διαπιστευτήρια» το κρίνει ο καλών· εμείς δεν το παρακάμπτουμε."""
    picked = SyncSchedule(enabled=True, scope="selected", vats=("1", "2"))
    assert picked.targets(["2", "3"]) == ["2"]
    # Επιλογή που άδειασε σημαίνει «τίποτα», ΟΧΙ «όλοι»: μια αυτόματη λήψη δεν
    # επιτρέπεται να μεγαλώσει μόνη της.
    assert picked.targets(["3"]) == []
    assert SyncSchedule(enabled=True).targets(["3", "4", "3"]) == ["3", "4"]


def test_survives_a_round_trip_through_settings() -> None:
    """Το QSettings γυρίζει τα πάντα ως κείμενο — τα bool γράφονται "1"/"0"."""
    schedule = SyncSchedule(
        enabled=True, at="06:30", days=frozenset({1, 5}), scope="selected",
        vats=("111111111",),
    )
    stored = to_dict(schedule)
    assert stored["sync_schedule/enabled"] == "1"
    assert from_dict(stored) == schedule
    # Άδειο QSettings -> ασφαλείς προεπιλογές, όχι εξαίρεση.
    assert from_dict({}) == SyncSchedule()


def test_a_broken_time_does_not_crash_the_app() -> None:
    assert SyncSchedule(at="όχι ώρα").time_of_day().hour == 7
    assert SyncSchedule(at="25:99").time_of_day().hour == 1


def test_describe_says_what_will_happen() -> None:
    text = SyncSchedule(enabled=True, at="06:30", days=frozenset({0})).describe()
    assert "06:30" in text and "Δευ" in text
    assert "κάθε μέρα" in SyncSchedule(enabled=True).describe()
    assert "Ανενεργός" in SyncSchedule().describe()
