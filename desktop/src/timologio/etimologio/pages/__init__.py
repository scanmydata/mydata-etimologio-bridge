"""Native Qt pages for e-Τιμολόγιο Pro, each a thin view over ``EtimologioClient``.

The pages hold no business logic: they render what the PHP bridge returns and
POST back the same parameters the web UI uses. Backend calls run off the UI
thread through an injected ``run`` callable so the pages stay testable with a
synchronous fake.
"""

from .base import EtimPage, ListPage, parse_money
from .card import CustomerCard
from .catalog import ProductsPage, SeriesPage
from .credit import CreditNotePage
from .customers import CustomersPage
from .drafts import DraftsPage
from .issue import IssuePage

__all__ = [
    "EtimPage",
    "ListPage",
    "parse_money",
    "CustomersPage",
    "CustomerCard",
    "IssuePage",
    "ProductsPage",
    "SeriesPage",
    "DraftsPage",
    "CreditNotePage",
]
