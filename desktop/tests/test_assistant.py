"""Φάση Ε — ο ψηφιακός βοηθός.

Ο δρομολογητής προθέσεων δοκιμάζεται χωρίς Qt και χωρίς δίκτυο· η διαδρομή
«εντολή → φόρμα → πρόχειρο» με fake client. Ο κανόνας που κλειδώνεται εδώ και
δεν επιτρέπεται να σπάσει: **ο βοηθός δεν εκδίδει ποτέ οριστικά**.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QWidget  # noqa: E402

from timologio.etimologio.assistant import (  # noqa: E402
    Assistant,
    DraftSpec,
    find_product,
    normalize,
    parse_issue,
)
from timologio.etimologio.client import EtimologioClient  # noqa: E402
from timologio.etimologio.pages import IssuePage  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


def sync_run(fn, on_ok, on_err) -> None:
    try:
        on_ok(fn())
    except Exception as exc:  # noqa: BLE001
        on_err(str(exc))


CUSTOMERS = [
    {"vat": "094039270", "name": "ΞΕΝΤΕ ΑΕ", "city": "Αθήνα", "address": "Οδός 1"},
    {"vat": "802012659", "name": "MEGATECH ΙΚΕ", "city": "Πάτρα", "address": "Οδός 2"},
]
PRODUCTS = [
    {"code": "ΥΠ001", "product_code": "ΥΠ001", "description": "Συντήρηση εξοπλισμού",
     "unit_price": "150", "vat_category": "1"},
    {"code": "ΑΓ001", "product_code": "ΑΓ001", "description": "Ανταλλακτικό αντλίας",
     "unit_price": "40", "vat_category": "1"},
]


def bot(customers=CUSTOMERS, products=PRODUCTS) -> Assistant:
    return Assistant(lambda: customers, lambda: products)


class DraftClient(EtimologioClient):
    """Καταγράφει τι φεύγει προς το backend, χωρίς δίκτυο."""

    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:0")
        self.calls: list[tuple[dict, dict | None, str]] = []
        self.reply: dict[str, Any] = {"success": True, "temp_id": "TMP-1",
                                      "amount_total": "124,00"}

    def _call(self, params=None, data=None, method="GET"):  # type: ignore[override]
        self.calls.append((dict(params or {}), dict(data) if data else None, method))
        return self.reply

    def sync(self, kind: str):
        """Οι σελίδες φορτώνουν με ``cached`` → ``sync`` (μόνο το δεύτερο
        γράφει το snapshot)."""
        from timologio.etimologio.pages.base import rows_of

        source = {"customers": self.customers, "series": self.series,
                  "products": self.products}.get(kind)
        rows = rows_of(source()) if source else []
        return {"success": True, "kind": kind, "rows": rows, "count": len(rows)}

    def customers(self, **_):
        return {"success": True, "customers": CUSTOMERS}

    def products(self):
        return {"success": True, "products": PRODUCTS}

    def product_categories(self):
        return {"success": True, "categories": [{"name": "ΥΠΗΡΕΣΙΕΣ"}]}

    def series(self):
        return {"success": True, "series": [
            {"invoice_type": "2.1 - Τιμολόγιο Παροχής Υπηρεσιών", "series_code": "ΤΠΥ"},
        ]}

    def tax_categories(self):
        return {
            "success": True,
            "withheld": [{"code": "2", "label": "Αμοιβές Ελ. Επαγγελματιών 20%"}],
            "fees": [], "other": [], "digital": [], "deductions": [],
        }


# --- ο δρομολογητής -----------------------------------------------------------
def test_normalises_accents_and_final_sigma() -> None:
    """«ΚΑΡΤΈΛΑ», «καρτέλα» και «καρτελα» είναι το ίδιο πράγμα."""
    assert normalize("ΚΑΡΤΈΛΑ") == normalize("καρτέλα") == "καρτελα"
    assert normalize("Πρόχειρος") == "προχειροσ"


def test_navigation_wins_over_the_issue_verb() -> None:
    """«πήγαινε στα παραστατικά» περιέχει «παραστατ» — δεν είναι εντολή έκδοσης."""
    assert bot().handle("πήγαινε στα παραστατικά").navigate == "documents"
    assert bot().handle("άνοιξε τα πρόχειρα").navigate == "drafts"
    assert bot().handle("πάμε στις σειρές").navigate == "series"
    assert bot().handle("πελάτες").navigate == "customers"
    assert bot().handle("έκδοση").navigate == "issue"


def test_application_commands_reach_the_shell() -> None:
    """Ο διευρυμένος χειρισμός: ό,τι δεν είναι σελίδα βγαίνει ως `command`."""
    assert bot().handle("άνοιξε το εγχειρίδιο").command == "manual"
    assert bot().handle("κράτα αντίγραφο ασφαλείας").command == "backup"
    assert bot().handle("ξενάγηση").command == "tour"
    assert bot().handle("αποσύνδεση").command == "logout"
    assert bot().handle("ανανέωσε").command == "refresh"
    assert bot().handle("πήγαινε στην αρχική").command == "home"
    assert bot().handle("σώπα").command == "speak:off"
    assert bot().handle("μίλα μου").command == "speak:on"


def test_backup_is_not_read_as_the_back_button() -> None:
    """«backup» περιέχει «back» — η σειρά στο COMMANDS το κρατά αντίγραφο."""
    assert bot().handle("backup").command == "backup"
    assert bot().handle("πίσω").command == "back"


def test_vat_targeted_commands_keep_the_number() -> None:
    """«καρτέλα του Χ» δεν είναι «άνοιξε τους πελάτες»: ο αριθμός είναι η εντολή."""
    assert bot().handle("άνοιξε την καρτέλα του 094039270").command == "card:094039270"
    assert bot().handle("άλλαξε εταιρεία 094019245").command == "company:094019245"
    # Χωρίς ΑΦΜ μένει πλοήγηση — οι Εταιρείες είναι πια δική τους ενότητα.
    assert bot().handle("πήγαινε στις εταιρείες").navigate == "companies"


def test_counts_are_answered_from_memory() -> None:
    """Πελάτες και είδη είναι ήδη φορτωμένα — καμία κλήση στο backend."""
    reply = bot().handle("πόσους πελάτες έχω")
    assert str(len(CUSTOMERS)) in reply.say and reply.fetch == ""
    reply = bot().handle("πόσα είδη έχω")
    assert str(len(PRODUCTS)) in reply.say and reply.fetch == ""
    # Η ερώτηση για παραστατικά συνεχίζει να πηγαίνει στα στατιστικά.
    assert bot().handle("πόσα τιμολόγια φέτος").fetch == "stats:year"


def test_parses_a_full_issue_command() -> None:
    spec = parse_issue(
        "έκδοση τιμολογίου στον 094039270 καθαρή αξία 100 με παρακράτηση 20% "
        "είδος συντήρηση εξοπλισμού"
    )
    assert spec.vat == "094039270"
    assert spec.price == 100.0
    assert spec.withholding_pct == 20.0
    assert spec.item == "συντήρηση εξοπλισμού"
    assert parse_issue("τιμολόγιο 3 τεμ").qty == 3.0


def test_resolves_customer_and_product_then_asks_to_confirm() -> None:
    assistant = bot()
    reply = assistant.handle("έκδοση τιμολογίου στον 094039270 ποσό 100 είδος συντήρηση")
    assert "ΞΕΝΤΕ ΑΕ" in reply.say and "ΥΠ001" in reply.say
    assert reply.draft is None                       # τίποτα δεν ετοιμάζεται χωρίς «ναι»
    assert assistant.pending == "confirm"

    done = assistant.handle("ναι")
    assert done.draft is not None
    assert (done.draft.vat, done.draft.code, done.draft.price) == ("094039270", "ΥΠ001", 100.0)
    assert assistant.pending == ""


def test_asks_who_an_unknown_customer_is() -> None:
    assistant = bot()
    reply = assistant.handle("έκδοση τιμολογίου στην ΑΓΝΩΣΤΟΣ ΕΠΕ ποσό 50")
    assert "επαγγελματίας ή ιδιώτης" in reply.say
    assert [choice[1] for choice in reply.choices] == ["επαγγελματίας", "ιδιώτης"]

    assert "ΑΦΜ" in assistant.handle("επαγγελματίας").say
    assert assistant.pending == "afm"
    assert "9ψήφιο" in assistant.handle("δεν ξέρω").say
    assert assistant.pending == "afm"                # δεν χάνεται η ροή
    assistant.handle("802576637")
    assert assistant.pending == "confirm"


def test_an_individual_gets_a_customer_form_not_a_draft() -> None:
    assistant = bot()
    assistant.handle("απόδειξη στον ΚΩΣΤΑΣ ΠΑΠΑΣ ποσό 20")
    reply = assistant.handle("ιδιώτης")
    assert reply.dialog == "customer"
    assert reply.prefill["personal"] is True
    assert reply.draft is None


def test_a_half_finished_flow_can_always_be_abandoned() -> None:
    """Χωρίς αυτό, κάθε επόμενη εντολή καταναλωνόταν ως απάντηση σε παλιά ερώτηση."""
    assistant = bot()
    assistant.handle("έκδοση τιμολογίου στην ΑΓΝΩΣΤΟΣ ΕΠΕ")
    assert assistant.pending == "who"
    assert "ακύρωσα" in assistant.handle("άκυρο").say
    assert assistant.pending == ""
    assert assistant.handle("πήγαινε στα πρόχειρα").navigate == "drafts"


def test_offers_to_create_an_unknown_product() -> None:
    reply = bot().handle("έκδοση τιμολογίου στον 094039270 ποσό 80 είδος ελαιοχρωματισμός")
    assert reply.dialog == "product"
    assert reply.prefill["description"] == "ελαιοχρωματισμός"


def test_product_match_stays_silent_on_unrelated_words() -> None:
    """Λάθος κωδικός σημαίνει λάθος χαρακτηρισμό στην ΑΑΔΕ — καλύτερα κανένας."""
    assert find_product(PRODUCTS, "συντήρηση εξοπλισμού") == "ΥΠ001"
    assert find_product(PRODUCTS, "αντλίας") == "ΑΓ001"      # μέρος της περιγραφής
    assert find_product(PRODUCTS, "ελαιοχρωματισμός") == ""
    assert find_product(PRODUCTS, "εργασία") == ""


def test_stats_and_notifications_go_through_the_host() -> None:
    assistant = bot()
    assert assistant.handle("πόσα τιμολόγια φέτος").fetch == "stats:year"
    assert assistant.handle("τζίρος μήνα").fetch == "stats:month"
    said = assistant.report("stats:year", {"total_count": 12, "total_value": "3.400,00"}).say
    assert "12" in said and "3.400,00" in said
    unread = assistant.report("notifications", 5)
    assert "5 αδιάβαστες" in unread.say
    # Η απάντηση μπορεί να αργήσει: αν πλοηγούσε μόνη της, θα πετούσε τον χρήστη
    # έξω από τη σελίδα που συμπληρώνει εκείνη τη στιγμή (ζωντανό εύρημα).
    assert unread.navigate == ""
    assert unread.choices[0][1] == "πήγαινε στις ειδοποιήσεις"


def test_help_mentions_that_nothing_is_issued() -> None:
    say = bot().handle("βοήθεια").say
    assert "ΠΡΟΧΕΙΡΟ" in say and "Οριστική Έκδοση" in say


def test_the_router_has_no_notion_of_a_live_issue() -> None:
    """Ο αμετάβλητος κανόνας, κλειδωμένος στον κώδικα και όχι μόνο στα λόγια."""
    import inspect

    from timologio.etimologio import assistant as module

    source = inspect.getsource(module)
    assert "live" not in source
    assert set(module.Reply.__dataclass_fields__) == {
        "say", "navigate", "fetch", "dialog", "prefill", "draft", "choices",
    }


# --- η διαδρομή προς το πρόχειρο ---------------------------------------------
def test_prepare_draft_never_issues_and_applies_the_withholding(app) -> None:
    client = DraftClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    page._type.setCurrentIndex(page._type.findData("20"))        # 2.1 — υπηρεσίες
    client.calls.clear()

    said: list[str] = []
    page.assistant_said.connect(said.append)
    page.prepare_draft(
        DraftSpec(vat="094039270", name="ΞΕΝΤΕ ΑΕ", code="ΥΠ001", qty=1, price=100.0,
                  withholding_pct=20.0)
    )

    posts = [call for call in client.calls if call[2] == "POST"]
    assert len(posts) == 1
    data = posts[0][1] or {}
    assert "live" not in data and "preview" not in data          # ούτε ΜΑΡΚ ούτε PDF
    assert data["afm"] == "094039270"
    assert json.loads(data["lines"])[0]["code"] == "ΥΠ001"
    # Το ποσό της παρακράτησης βγαίνει από το ποσοστό της ετικέτας: 20% × 100.
    assert json.loads(data["taxes"]) == [
        {"type": 1, "category": "2", "amount": 20.0, "notes": ""}
    ]
    assert any("πρόχειρο ετοιμάστηκε" in message for message in said)


def test_prepare_draft_keeps_the_price_from_the_command(app) -> None:
    """Ο κατάλογος λέει 150· ο χρήστης είπε 100 — υπερισχύει αυτός.

    Εδώ ο τύπος ΔΕΝ ορίζεται από το τεστ: ο βοηθός πρέπει να διαλέξει έναν που
    έχει σειρά, αλλιώς το πρόχειρο θα έφευγε με τη σειρά «A» που δεν υπάρχει.
    """
    client = DraftClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    client.calls.clear()
    page.prepare_draft(DraftSpec(vat="094039270", code="ΥΠ001", qty=2, price=100.0))

    data = [c for c in client.calls if c[2] == "POST"][0][1]
    lines = json.loads(data["lines"])
    assert lines[0]["price"] == 100.0 and lines[0]["qty"] == 2.0
    assert data["issue_series"] == "ΤΠΥ" and data["type"] == "20"


def test_missing_withholding_category_still_saves_the_draft(app) -> None:
    """Καλύτερα πρόχειρο με προειδοποίηση παρά τίποτα."""
    client = DraftClient()
    page = IssuePage(lambda: client, sync_run)
    page.refresh()
    client.calls.clear()
    said: list[str] = []
    page.assistant_said.connect(said.append)
    page.prepare_draft(DraftSpec(vat="094039270", code="ΥΠ001", price=100.0,
                                 withholding_pct=7.5))

    posts = [call for call in client.calls if call[2] == "POST"]
    assert len(posts) == 1
    assert "taxes" not in (posts[0][1] or {})
    assert any("7,5%" in m or "7.5%" in m for m in said)


# --- φωνή ---------------------------------------------------------------------
def test_voice_says_exactly_what_is_missing(tmp_path) -> None:
    """Το κουμπί του μικροφώνου δεν μένει βουβό όταν λείπει πακέτο ή μοντέλο."""
    from timologio.etimologio import voice

    reason = voice.missing(tmp_path)
    assert reason and ("vosk" in reason or "μοντέλο" in reason)
    assert voice.model_path(tmp_path) is None

    # Φάκελος με το σωστό όνομα αλλά χωρίς μοντέλο μέσα δεν μετράει: αλλιώς το
    # σφάλμα θα ερχόταν αργότερα, μέσα από το Vosk.
    (tmp_path / voice.MODEL_DIRNAME).mkdir()
    assert voice.model_path(tmp_path) is None
    (tmp_path / voice.MODEL_DIRNAME / "conf").mkdir()
    assert voice.model_path(tmp_path) == tmp_path / voice.MODEL_DIRNAME


# --- το panel -----------------------------------------------------------------
def _buttons(layout) -> list[QPushButton]:
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QPushButton)
    ]


def test_panel_routes_navigation_and_confirms_before_a_draft(app, tmp_path) -> None:
    from timologio.etimologio.pages.assistant_panel import AssistantPanel

    host = QWidget()
    host.resize(900, 700)
    panel = AssistantPanel(
        host, data_dir=tmp_path,
        customers=lambda: CUSTOMERS, products=lambda: PRODUCTS,
    )

    seen: list[str] = []
    panel.navigate.connect(seen.append)
    panel.ask("πήγαινε στα πρόχειρα")
    assert seen == ["drafts"]

    drafts: list[Any] = []
    panel.prepare_draft.connect(drafts.append)
    panel.ask("έκδοση τιμολογίου στον 094039270 ποσό 100 είδος συντήρηση")
    assert drafts == []                              # πρώτα ζητά επιβεβαίωση
    labels = [b.text() for b in _buttons(panel._choices)]
    assert labels and labels[0].startswith("✔")

    panel.ask("ναι")
    assert len(drafts) == 1 and drafts[0].vat == "094039270"
    assert _buttons(panel._choices) == []            # τα κουμπιά καθαρίζουν


def test_panel_is_an_opaque_themed_card(app, tmp_path) -> None:
    """Ο κανόνας του θέματος είναι `QFrame#card`: σκέτο QWidget έμενε άφοντο και
    η σελίδα από κάτω φαινόταν μέσα από το panel."""
    from timologio.etimologio.pages.assistant_panel import AssistantPanel
    from timologio.gui import theme

    panel = AssistantPanel(QWidget(), data_dir=tmp_path, customers=list, products=list)
    assert isinstance(panel, QFrame)
    assert panel.objectName() == "card"
    assert "QFrame#card" in theme.build(theme.DARK)


def test_panel_stays_inside_the_window(app, tmp_path) -> None:
    """Το panel ακολουθεί το παράθυρο· αλλιώς κρεμόταν έξω από την οθόνη."""
    from timologio.etimologio.pages.assistant_panel import AssistantPanel

    host = QWidget()
    host.resize(1000, 800)
    panel = AssistantPanel(host, data_dir=tmp_path, customers=list, products=list)
    panel.reposition()
    assert host.rect().contains(panel.geometry())

    host.resize(700, 600)
    panel.reposition()
    assert host.rect().contains(panel.geometry())
