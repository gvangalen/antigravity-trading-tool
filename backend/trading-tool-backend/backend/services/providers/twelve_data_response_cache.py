from __future__ import annotations

"""Short-lived, process-local response reuse for Twelve Data reads.

The market snapshot and technical indicator services can run in the same
Celery process for one owner-scoped Analysis refresh.  Reusing a successful
provider response prevents that refresh from spending quota repeatedly on the
same symbol while the persisted database rows remain the product authority.
"""

from copy import deepcopy
from time import monotonic
from typing import Any


class TwelveDataResponseCache:
    _ttl_seconds = 45.0
    _entries: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, dict[str, Any]]] = {}

    @classmethod
    def get(cls, endpoint: str, **params: Any) -> dict[str, Any] | None:
        key = (endpoint, tuple(sorted((str(name), str(value)) for name, value in params.items())))
        entry = cls._entries.get(key)
        if entry is None:
            return None
        stored_at, payload = entry
        if monotonic() - stored_at >= cls._ttl_seconds:
            cls._entries.pop(key, None)
            return None
        return deepcopy(payload)

    @classmethod
    def put(cls, endpoint: str, payload: dict[str, Any], **params: Any) -> None:
        key = (endpoint, tuple(sorted((str(name), str(value)) for name, value in params.items())))
        cls._entries[key] = (monotonic(), deepcopy(payload))

    @classmethod
    def clear_for_testing(cls) -> None:
        cls._entries.clear()
