"""Χρονοπρογραμματισμός της αυτόματης λήψης παραστατικών.

ΓΙΑΤΙ ΜΕΣΑ ΣΤΗΝ ΕΦΑΡΜΟΓΗ και όχι με Task Scheduler των Windows: η λήψη θέλει τη
βάση, το κλειδί κρυπτογράφησης, τους πάροχους και — για τα «μόνο online» — έναν
browser. Ένα ξεχωριστό headless στιγμιότυπο θα κλείδωνε την ίδια βάση με το
ανοιχτό παράθυρο (δες `locking.py`) και θα χρειαζόταν δεύτερο σημείο εισόδου στο
πακετάρισμα. Η εφαρμογή έχει ήδη τον τρόπο να μένει ανοιχτή όλη μέρα χωρίς να
ενοχλεί: «εκκίνηση στο tray», που είναι και η προεπιλογή του ρόλου *server*.

Το module είναι **καθαρό** (χωρίς Qt): όλη η λογική «πότε είναι η ώρα;» ελέγχεται
με τεστ, χωρίς ρολόι και χωρίς παράθυρο.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

#: Ελληνικά ονόματα ημερών, Δευτέρα = 0 (όπως το `date.weekday()`).
DAY_NAMES = ("Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ")

#: Πόσο πίσω κοιτά μια προγραμματισμένη λήψη. Το ίδιο διάστημα με το «τρέχον
#: έτος» της οθόνης λήψης: μια αυτόματη λήψη που κατεβάζει λιγότερα από όσα θα
#: κατέβαζε ο χρήστης με το χέρι είναι παγίδα.
DEFAULT_SCOPE = "all"


@dataclass(frozen=True)
class SyncSchedule:
    """Τι, πότε και για ποιους."""

    enabled: bool = False
    #: Ώρα εκκίνησης, «HH:MM».
    at: str = "07:00"
    #: Ημέρες της εβδομάδας (0=Δευτέρα). Κενό σύνολο = κάθε μέρα.
    days: frozenset[int] = field(default_factory=frozenset)
    #: "all" = όλοι οι πελάτες με έγκυρα διαπιστευτήρια · "selected" = μόνο οι
    #: επιλεγμένοι (`vats`).
    scope: str = DEFAULT_SCOPE
    vats: tuple[str, ...] = ()

    # --- ώρα ---------------------------------------------------------------
    def time_of_day(self) -> time:
        """«HH:MM» → ώρα. Ό,τι δεν διαβάζεται πέφτει στις 07:00 αντί να σκάσει."""
        try:
            hour, minute = (int(part) for part in self.at.split(":", 1))
            return time(hour % 24, minute % 60)
        except (ValueError, TypeError):
            return time(7, 0)

    def runs_on(self, day: date) -> bool:
        return not self.days or day.weekday() in self.days

    def scheduled_for(self, day: date) -> datetime | None:
        """Η στιγμή που «χτυπά» μια συγκεκριμένη μέρα (ή ``None``)."""
        if not self.runs_on(day):
            return None
        return datetime.combine(day, self.time_of_day())

    def next_run(self, now: datetime, last_run: datetime | None = None) -> datetime | None:
        """Η επόμενη εκτέλεση — ή ``None`` αν είναι απενεργοποιημένο.

        Κοιτά οκτώ μέρες μπροστά: με επτά, ένα πρόγραμμα «μόνο Δευτέρα» που
        ρωτιέται Δευτέρα μεσημέρι δεν θα έβρισκε ποτέ την επόμενη.
        """
        if not self.enabled:
            return None
        for offset in range(0, 8):
            moment = self.scheduled_for(now.date() + timedelta(days=offset))
            if moment is None or moment <= now:
                continue
            if last_run is not None and moment <= last_run:
                continue
            return moment
        return None

    def is_due(self, now: datetime, last_run: datetime | None = None) -> bool:
        """Έφτασε η ώρα ΚΑΙ δεν έχει ήδη τρέξει γι' αυτό το ραντεβού;

        Ο έλεγχος γίνεται στο *ραντεβού της ημέρας* και όχι σε «πέρασαν 24 ώρες»:
        αλλιώς ένας υπολογιστής που ήταν κλειστός στις 07:00 και άνοιξε στις 11:00
        δεν θα κατέβαζε ποτέ — ή θα κατέβαζε δύο φορές την επόμενη.
        """
        if not self.enabled:
            return False
        moment = self.scheduled_for(now.date())
        if moment is None or now < moment:
            return False
        return last_run is None or last_run < moment

    def targets(self, ready_vats: list[str]) -> list[str]:
        """Ποιοι πελάτες κατεβαίνουν, από όσους ΕΧΟΥΝ έγκυρα διαπιστευτήρια.

        Ένας επιλεγμένος πελάτης που έχασε το κλειδί του δεν μπλοκάρει το
        πρόγραμμα — απλώς δεν συμμετέχει. Επιλογή που άδειασε εντελώς σημαίνει
        «τίποτα», όχι «όλοι»: μια αυτόματη λήψη δεν επιτρέπεται να μεγαλώσει
        μόνη της.
        """
        ready = list(dict.fromkeys(ready_vats))
        if self.scope != "selected":
            return ready
        chosen = set(self.vats)
        return [vat for vat in ready if vat in chosen]

    def describe(self) -> str:
        """Μια γραμμή για την οθόνη ρυθμίσεων."""
        if not self.enabled:
            return "Ανενεργός — η λήψη γίνεται μόνο με το χέρι."
        when = "κάθε μέρα" if not self.days else ", ".join(
            DAY_NAMES[d] for d in sorted(self.days)
        )
        who = (
            "όλοι οι πελάτες με κλειδί API"
            if self.scope != "selected"
            else f"{len(self.vats)} επιλεγμένοι πελάτες"
        )
        return f"{when} στις {self.at} · {who}"


# --- αποθήκευση (QSettings-συμβατό, χωρίς Qt εδώ) ---------------------------
_PREFIX = "sync_schedule/"


def to_dict(schedule: SyncSchedule) -> dict[str, str]:
    """Σε απλά strings — ό,τι δέχεται το QSettings σε κάθε πλατφόρμα.

    ⚠️ Το QSettings των Windows γυρίζει τα πάντα ως κείμενο· ένα `bool` που
    γράφτηκε ως `True` διαβαζόταν ως η **συμβολοσειρά** "true" και το
    `if value:` ήταν πάντα αληθές. Γράφουμε ρητά "1"/"0" και τα διαβάζουμε ως
    τέτοια.
    """
    return {
        _PREFIX + "enabled": "1" if schedule.enabled else "0",
        _PREFIX + "at": schedule.at,
        _PREFIX + "days": ",".join(str(d) for d in sorted(schedule.days)),
        _PREFIX + "scope": schedule.scope,
        _PREFIX + "vats": ",".join(schedule.vats),
    }


def from_dict(values: dict[str, str]) -> SyncSchedule:
    def get(name: str, default: str = "") -> str:
        return str(values.get(_PREFIX + name, default) or "")

    days = frozenset(
        int(part) for part in get("days").split(",") if part.strip().isdigit()
    )
    vats = tuple(part for part in get("vats").split(",") if part.strip())
    scope = get("scope", DEFAULT_SCOPE) or DEFAULT_SCOPE
    return SyncSchedule(
        enabled=get("enabled") == "1",
        at=get("at", "07:00") or "07:00",
        days=frozenset(d for d in days if 0 <= d <= 6),
        scope="selected" if scope == "selected" else "all",
        vats=vats,
    )
