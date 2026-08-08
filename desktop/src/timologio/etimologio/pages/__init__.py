"""Native Qt pages for e-Τιμολόγιο Pro, each a thin view over ``EtimologioClient``.

The pages hold no business logic: they render what the PHP bridge returns and
POST back the same parameters the web UI uses. Backend calls run off the UI
thread through an injected ``run`` callable so the pages stay testable with a
synchronous fake.
"""

from .base import EtimPage, parse_money
from .card import CustomerCard
from .customers import CustomersPage

__all__ = ["EtimPage", "parse_money", "CustomersPage", "CustomerCard"]
