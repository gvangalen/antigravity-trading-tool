"""Per-run lifecycle budget shared by the asynchronous FINN runtime.

The worker owns one absolute visible-run deadline.  Provider-facing phases use
this context to avoid starting a request that cannot leave time for a durable
terminal projection.  The value is task-local, so concurrent Celery tasks
cannot borrow each other's budget.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from time import monotonic


_deadline: ContextVar[float | None] = ContextVar("finn_v2_lifecycle_deadline", default=None)


def set_lifecycle_deadline(deadline: float) -> Token[float | None]:
    return _deadline.set(deadline)


def reset_lifecycle_deadline(token: Token[float | None]) -> None:
    _deadline.reset(token)


def remaining_lifecycle_seconds(*, reserve_seconds: float = 0.0) -> float | None:
    """Return remaining task-local time after an optional terminal reserve.

    ``None`` means the caller is outside an owned visible lifecycle, which is
    intentional for unit services and non-visible maintenance work.
    """
    deadline = _deadline.get()
    if deadline is None:
        return None
    return max(0.0, deadline - monotonic() - max(0.0, reserve_seconds))
