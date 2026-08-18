from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple


INTERACTION_MODES: Tuple[str, ...] = (
    "FACT",
    "CAPABILITY",
    "EVALUATION",
    "PROPOSAL",
    "ACTION",
    "CLARIFICATION",
    "UNAVAILABLE",
)

RUN_STATUSES: Tuple[str, ...] = (
    "created",
    "collecting",
    "planned",
    "blocked",
    "completed",
    "failed",
    "canceled",
)

RUN_VISIBILITIES: Tuple[str, ...] = ("shadow", "visible")
RUN_TRANSPORTS: Tuple[str, ...] = ("chat", "stream")

POLICY_CLASSES: Tuple[str, ...] = (
    "read",
    "advice",
    "proposal",
    "paper_action",
    "live_action",
    "high_risk_action",
)

VERIFIER_STATUSES: Tuple[str, ...] = (
    "not_run",
    "passed",
    "failed",
    "downgraded",
)

RESPONSE_SOURCES: Tuple[str, ...] = (
    "foundation_placeholder",
    "v1_adapter",
    "v2_runtime",
)

TERMINAL_RUN_STATUSES = {"completed", "blocked", "failed", "canceled"}

ALLOWED_RUN_TRANSITIONS: Mapping[str, Tuple[str, ...]] = {
    "created": ("collecting", "failed", "canceled"),
    "collecting": ("planned", "blocked", "failed", "canceled"),
    "planned": ("completed", "blocked", "failed", "canceled"),
    "blocked": (),
    "completed": (),
    "failed": (),
    "canceled": (),
}

TRACE_EVENT_BY_STATUS: Mapping[str, str] = {
    "created": "run_created",
    "collecting": "run_collecting",
    "planned": "run_planned",
    "blocked": "run_blocked",
    "completed": "run_completed_placeholder",
    "failed": "run_failed",
    "canceled": "run_canceled",
}

SSE_EVENT_BY_STATUS: Mapping[str, str] = {
    "created": "run.created",
    "collecting": "run.collecting",
    "planned": "run.planned",
    "blocked": "run.blocked",
    "completed": "run.completed",
    "failed": "run.failed",
    "canceled": "run.canceled",
}

FOUNDATION_PLACEHOLDER_CONTENT = "FINN Core V2 orchestration shadow run completed."


class InvalidRunTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class RunTransition:
    from_status: str
    to_status: str
    at: datetime
    response_source: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_RUN_STATUSES


def validate_run_transition(current_status: str, next_status: str) -> None:
    allowed = ALLOWED_RUN_TRANSITIONS.get(current_status, ())
    if next_status not in allowed:
        raise InvalidRunTransitionError(f"Invalid FINN V2 run transition: {current_status} -> {next_status}")


def build_placeholder_response() -> Dict[str, Any]:
    return {
        "mode": "UNAVAILABLE",
        "response_source": "foundation_placeholder",
        "content": FOUNDATION_PLACEHOLDER_CONTENT,
        "verifier_status": "not_run",
        "evidence": [],
        "uncertainty": [],
        "proposal_id": None,
        "confirmation_required": False,
    }
