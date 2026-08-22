from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple


INTERACTION_MODES: Tuple[str, ...] = (
    "CAPABILITY",
    "READ",
    "EVALUATE",
    "CREATE_PROPOSAL",
    "ACTION_PROPOSAL",
    "CLARIFICATION",
    "CONFIRMATION",
    "EXECUTION",
    "UNAVAILABLE",
)

RUN_STATUSES: Tuple[str, ...] = (
    "created",
    "queued",
    "collecting",
    "planned",
    "reasoning",
    "verifying",
    "clarification_required",
    "unavailable",
    "downgraded",
    "rejected",
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

TERMINAL_RUN_STATUSES = {
    "clarification_required",
    "unavailable",
    "downgraded",
    "rejected",
    "blocked",
    "completed",
    "failed",
    "canceled",
}
ACTIVE_RUN_STATUSES = tuple(status for status in RUN_STATUSES if status not in TERMINAL_RUN_STATUSES)

ALLOWED_RUN_TRANSITIONS: Mapping[str, Tuple[str, ...]] = {
    "created": ("queued", "failed", "canceled"),
    "queued": ("collecting", "failed", "canceled"),
    "collecting": ("planned", "blocked", "failed", "canceled"),
    "planned": ("reasoning", "clarification_required", "unavailable", "completed", "blocked", "failed", "canceled"),
    "reasoning": ("verifying", "completed", "downgraded", "rejected", "unavailable", "failed", "canceled"),
    "verifying": ("completed", "downgraded", "rejected", "unavailable", "failed", "canceled"),
    "clarification_required": (),
    "unavailable": (),
    "downgraded": (),
    "rejected": (),
    "blocked": (),
    "completed": (),
    "failed": (),
    "canceled": (),
}

TRACE_EVENT_BY_STATUS: Mapping[str, str] = {
    "created": "run_created",
    "queued": "run_queued",
    "collecting": "run_collecting",
    "planned": "run_planned",
    "reasoning": "run_reasoning",
    "verifying": "run_verifying",
    "clarification_required": "run_clarification_required",
    "unavailable": "run_unavailable",
    "downgraded": "run_downgraded",
    "rejected": "run_rejected",
    "blocked": "run_blocked",
    "completed": "run_completed_placeholder",
    "failed": "run_failed",
    "canceled": "run_canceled",
}

SSE_EVENT_BY_STATUS: Mapping[str, str] = {
    "created": "run.created",
    "queued": "run.queued",
    "collecting": "run.collecting",
    "planned": "run.planned",
    "reasoning": "run.reasoning",
    "verifying": "run.verifying",
    "clarification_required": "run.clarification_required",
    "unavailable": "run.unavailable",
    "downgraded": "run.downgraded",
    "rejected": "run.rejected",
    "blocked": "run.blocked",
    "completed": "run.completed",
    "failed": "run.failed",
    "canceled": "run.canceled",
}

FOUNDATION_PLACEHOLDER_CONTENT = "FINN Core V2 orchestration shadow run completed."

LEGACY_INTERACTION_MODE_ALIASES: Mapping[str, str] = {
    "FACT": "READ",
    "EVALUATION": "EVALUATE",
    "PROPOSAL": "CREATE_PROPOSAL",
    "ACTION": "ACTION_PROPOSAL",
}


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


def normalize_interaction_mode(mode: Optional[str]) -> str:
    normalized = str(mode or "").strip().upper()
    normalized = LEGACY_INTERACTION_MODE_ALIASES.get(normalized, normalized)
    if normalized not in INTERACTION_MODES:
        raise ValueError(f"unsupported_interaction_mode:{mode}")
    return normalized
