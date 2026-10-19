"""Η χρήση (φορολογικό έτος) — το «κουτί» μέσα στο οποίο δουλεύει ο λογιστής.

Δύο κανόνες ζουν εδώ, χωρίς τίποτα από Qt ώστε να τους χρησιμοποιούν και το
CLI και τα tests:

1. **Τα στοιχεία κατεβαίνουν για όλη τη χρήση.** Τα σύνολα (έσοδα, έξοδα,
   αχαρακτήριστα, παρακρατήσεις) βγαίνουν σωστά μόνο όταν η βάση έχει ΟΛΑ τα
   παραστατικά της χρήσης — όχι μόνο όσα έπεσαν μέσα στο διάστημα που ζήτησε ο
   χρήστης για PDF. Οπότε η ανακάλυψη στην ΑΑΔΕ καλύπτει από την 1η Ιανουαρίου
   μέχρι σήμερα, και το διάστημα του χρήστη ορίζει μόνο ποια PDF θα κατέβουν.

2. **Η χρήση αλλάζει μόνη της με το έτος**, αλλά ο χρήστης μπορεί να διαλέξει
   άλλη (π.χ. τον Ιανουάριο κλείνει ακόμη την περσινή). Η επιλογή του ισχύει
   μέσα στο ημερολογιακό έτος που την έκανε· με την αλλαγή του χρόνου η
   εφαρμογή περνά στη νέα χρήση.
"""

from __future__ import annotations

from datetime import date, datetime


def _parse_gr(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _gr(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def year_window(year: int, today: date | None = None) -> tuple[date, date]:
    """1/1 έως 31/12 — ή έως σήμερα, για την τρέχουσα χρήση.

    Η ΑΑΔΕ δεν έχει παραστατικά από το μέλλον· ένα αίτημα ως τις 31/12 θα
    σήμαινε ότι το διάστημα «καλύφθηκε» ενώ οι μέρες του δεν έχουν έρθει.
    """
    today = today or date.today()
    start, end = date(year, 1, 1), date(year, 12, 31)
    if end > today:
        end = max(today, start)
    return start, end


def year_bounds_iso(year: int) -> tuple[str, str]:
    """Τα όρια της χρήσης σε ISO, για φίλτρα πάνω στο ``issue_date``."""
    return f"{year:04d}-01-01", f"{year:04d}-12-31"


def discovery_window(
    date_from: str, date_to: str, today: date | None = None
) -> tuple[str, str]:
    """Το διάστημα που ζητείται από την ΑΑΔΕ για να ζητηθούν PDF ``date_from–date_to``.

    Απλώνεται στις ολόκληρες χρήσεις που αγγίζει το διάστημα του χρήστη: από
    την 1/1 του έτους της αρχής ως το τέλος του έτους της λήξης (ή σήμερα).
    Δεν μικραίνει ποτέ το αίτημα του χρήστη. Μη έγκυρες ημερομηνίες
    επιστρέφονται ως έχουν.
    """
    today = today or date.today()
    start, end = _parse_gr(date_from), _parse_gr(date_to)
    if start is None or end is None or start > end:
        return date_from, date_to
    wide_start = date(start.year, 1, 1)
    wide_end = max(year_window(end.year, today)[1], end)
    return _gr(wide_start), _gr(wide_end)


def resolve_year(stored: int | None, chosen_in: int | None,
                 today: date | None = None) -> int:
    """Ποια χρήση ισχύει τώρα.

    ``stored`` είναι η χρήση που διάλεξε ο χρήστης και ``chosen_in`` το
    ημερολογιακό έτος όπου τη διάλεξε. Όταν αλλάξει ο χρόνος, η επιλογή παύει
    να ισχύει και η εφαρμογή περνά μόνη της στη νέα χρήση.
    """
    today = today or date.today()
    if not stored or chosen_in != today.year:
        return today.year
    return int(stored)


def year_choices(years_with_data: list[int], today: date | None = None) -> list[int]:
    """Οι χρήσεις που προσφέρονται: όσες έχουν δεδομένα, συν φέτος και πέρσι.

    Φθίνουσα σειρά — η τρέχουσα πρώτη.
    """
    today = today or date.today()
    years = {today.year, today.year - 1}
    years.update(y for y in years_with_data if 2000 <= y <= today.year)
    return sorted(years, reverse=True)
