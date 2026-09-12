"""Canonical bounded terminal delivery for FINN matrix runners.

Build's public matrices and the protected QA runner share this code.  The
caller supplies only its authenticated request functions; manifest ownership,
fixture binding, and result redaction remain outside this module.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


TERMINAL_STATUSES = {
    "completed", "clarification_required", "failed", "canceled", "unavailable", "downgraded", "rejected", "blocked",
}


@dataclass(frozen=True)
class TerminalObservation:
    terminal: dict[str, Any]
    sse_terminal: dict[str, Any]
    sse_error: Optional[str]
    snapshot_error: Optional[str]
    fallback_poll_error: Optional[str]
    used_sse_terminal: bool


def observe_terminal(
    *,
    remaining_seconds: Callable[[], float],
    read_sse_terminal: Callable[[float], tuple[dict[str, Any], Optional[str]]],
    fetch_persisted_projection: Callable[[float], tuple[dict[str, Any], Optional[str]]],
    initial_projection: dict[str, Any],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    fallback_poll_window_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
) -> TerminalObservation:
    """Deliver one terminal envelope without retaining a stream or poll loop.

    SSE is the primary path.  After terminal SSE delivery, the engine obtains
    one persisted snapshot solely for projection parity and stops polling.
    Polling is used only if SSE could not supply a terminal event.
    """
    terminal = dict(initial_projection)
    sse_terminal: dict[str, Any] = {}
    sse_error: Optional[str] = None
    snapshot_error: Optional[str] = None
    poll_error: Optional[str] = None

    if remaining_seconds() > 0:
        sse_terminal, sse_error = read_sse_terminal(max(0.1, remaining_seconds()))
    else:
        sse_error = "case_timeout"

    if sse_terminal and sse_terminal.get("status") in TERMINAL_STATUSES:
        if remaining_seconds() <= 0:
            return TerminalObservation(
                terminal=sse_terminal,
                sse_terminal=sse_terminal,
                sse_error="case_timeout",
                snapshot_error=None,
                fallback_poll_error=None,
                used_sse_terminal=True,
            )
        snapshot, snapshot_error = fetch_persisted_projection(
            max(0.1, min(5.0, remaining_seconds()))
        )
        if snapshot.get("status") in TERMINAL_STATUSES:
            terminal = snapshot
        else:
            terminal = sse_terminal
        return TerminalObservation(
            terminal=terminal,
            sse_terminal=sse_terminal,
            sse_error=sse_error,
            snapshot_error=snapshot_error,
            fallback_poll_error=None,
            used_sse_terminal=True,
        )

    fallback_deadline = min(monotonic() + fallback_poll_window_seconds, monotonic() + max(0.0, remaining_seconds()))
    while monotonic() < fallback_deadline and remaining_seconds() > 0:
        sleep(poll_interval_seconds)
        snapshot, poll_error = fetch_persisted_projection(
            max(0.1, min(5.0, remaining_seconds()))
        )
        if poll_error:
            continue
        terminal = snapshot
        if terminal.get("status") in TERMINAL_STATUSES:
            break

    return TerminalObservation(
        terminal=terminal,
        sse_terminal=sse_terminal,
        sse_error=sse_error,
        snapshot_error=None,
        fallback_poll_error=poll_error,
        used_sse_terminal=False,
    )
