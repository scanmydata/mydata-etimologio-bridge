"""e-Τιμολόγιο Pro — native desktop integration.

The heavy backend (AADE session, myDATA model, SQLite/Postgres, PDF, 2FA, mail,
scheduler) stays in PHP under ``backend/etimologio`` and is reached over HTTP.
This package is the thin native side:

* :mod:`.service` — owns the PHP backend: either spawns a local ``php -S`` server
  (offline mode) or points at the shared VPS (thin-client mode).
* :mod:`.client` — a :class:`requests.Session` wrapper over the PHP JSON API.
"""

from .client import EtimologioClient, EtimologioError
from .service import EtimologioService

__all__ = ["EtimologioClient", "EtimologioError", "EtimologioService"]
