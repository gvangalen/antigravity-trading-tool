from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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


class InformationScope(str, Enum):
    """Canonical fact scope carried from a tool result into persisted evidence."""

    CAPABILITY = "capability"
    PROFILE = "profile"
    PREFERENCES = "preferences"
    ACTIVE_ASSET = "active_asset"
    INDICATOR_CONFIGURATION = "indicator_configuration"
    MARKET_SNAPSHOT = "market_snapshot"
    WATCHLIST = "watchlist"
    ACTIVE_SETUP = "active_setup"
    LINKED_STRATEGY = "linked_strategy"
    LINKED_BOT = "linked_bot"
    BOT_STATUS = "bot_status"


INFORMATION_SCOPE_ORDER: Tuple[str, ...] = tuple(scope.value for scope in InformationScope)
INFORMATION_SCOPE_ALIASES: Mapping[str, str] = {
    "capability": InformationScope.CAPABILITY.value,
    "asset": InformationScope.ACTIVE_ASSET.value,
    "active_asset": InformationScope.ACTIVE_ASSET.value,
    "indicators": InformationScope.INDICATOR_CONFIGURATION.value,
    "indicator_configuration": InformationScope.INDICATOR_CONFIGURATION.value,
    "setup": InformationScope.ACTIVE_SETUP.value,
    "active_setup": InformationScope.ACTIVE_SETUP.value,
    "strategy": InformationScope.LINKED_STRATEGY.value,
    "linked_strategy": InformationScope.LINKED_STRATEGY.value,
    "bot": InformationScope.LINKED_BOT.value,
    "linked_bot": InformationScope.LINKED_BOT.value,
    "analysis": InformationScope.MARKET_SNAPSHOT.value,
    "user_preferences": InformationScope.PREFERENCES.value,
    "trading_preferences": InformationScope.PREFERENCES.value,
    "assistant_preferences": InformationScope.PREFERENCES.value,
}

# This is the only tool-to-scope mapping for newly created FINN V2 artifacts.
TOOL_OUTPUT_SCOPES: Mapping[str, InformationScope] = {
    "read_profile": InformationScope.PROFILE,
    "read_user_preferences": InformationScope.PREFERENCES,
    "read_active_asset": InformationScope.ACTIVE_ASSET,
    "read_indicator_configuration": InformationScope.INDICATOR_CONFIGURATION,
    "read_asset_scores": InformationScope.MARKET_SNAPSHOT,
    "read_market_snapshot": InformationScope.MARKET_SNAPSHOT,
    "read_macro_snapshot": InformationScope.MARKET_SNAPSHOT,
    "read_technical_snapshot": InformationScope.MARKET_SNAPSHOT,
    "read_active_setup": InformationScope.ACTIVE_SETUP,
    "read_linked_strategy": InformationScope.LINKED_STRATEGY,
    "read_linked_bot": InformationScope.LINKED_BOT,
    "read_bot_status": InformationScope.BOT_STATUS,
    "read_watchlist": InformationScope.WATCHLIST,
    "read_portfolio": InformationScope.PROFILE,
    "read_latest_report": InformationScope.MARKET_SNAPSHOT,
    "read_review_history": InformationScope.PROFILE,
}
PRIMARY_TOOL_BY_INFORMATION_SCOPE: Mapping[InformationScope, str] = {
    InformationScope.PROFILE: "read_profile",
    InformationScope.PREFERENCES: "read_user_preferences",
    InformationScope.ACTIVE_ASSET: "read_active_asset",
    InformationScope.INDICATOR_CONFIGURATION: "read_indicator_configuration",
    InformationScope.MARKET_SNAPSHOT: "read_market_snapshot",
    InformationScope.WATCHLIST: "read_watchlist",
    InformationScope.ACTIVE_SETUP: "read_active_setup",
    InformationScope.LINKED_STRATEGY: "read_linked_strategy",
    InformationScope.LINKED_BOT: "read_linked_bot",
    InformationScope.BOT_STATUS: "read_bot_status",
}


class FinnV2InformationScopeContractError(ValueError):
    code = "finn_v2_information_scope_contract_invalid"

    def __init__(self, scope: Optional[object]):
        self.scope = scope
        super().__init__(f"{self.code}:{scope}")


def normalize_information_scope(scope: Optional[object]) -> str:
    if isinstance(scope, InformationScope):
        return scope.value
    normalized = str(scope or "").strip().lower()
    canonical = INFORMATION_SCOPE_ALIASES.get(normalized, normalized)
    if canonical not in INFORMATION_SCOPE_ORDER:
        raise FinnV2InformationScopeContractError(scope)
    return canonical


def normalize_information_scopes(scopes: list[object]) -> list[str]:
    normalized = {normalize_information_scope(scope) for scope in scopes}
    return [scope for scope in INFORMATION_SCOPE_ORDER if scope in normalized]


def information_scope_for_tool(tool_name: str) -> InformationScope:
    try:
        return TOOL_OUTPUT_SCOPES[tool_name]
    except KeyError as exc:
        raise FinnV2InformationScopeContractError(tool_name) from exc


def canonical_evidence_scope(scope: Optional[object], *, tool_name: str) -> str:
    """Return the one persisted scope a tool is allowed to prove.

    Alias spellings are accepted at legacy boundaries, but cannot silently
    turn one tool result into evidence for another contract scope.
    """
    expected = information_scope_for_tool(tool_name).value
    if scope is None:
        return expected
    # Tool envelopes reject mismatches at ingestion. Context reconstruction
    # additionally has to tolerate pre-scope and test-fixture metadata, so it
    # mechanically projects those records back through the immutable tool map.
    normalize_information_scope(scope)
    return expected


def primary_tool_for_information_scope(scope: object) -> str:
    canonical = InformationScope(normalize_information_scope(scope))
    try:
        return PRIMARY_TOOL_BY_INFORMATION_SCOPE[canonical]
    except KeyError as exc:
        raise FinnV2InformationScopeContractError(scope) from exc


class InvalidRunTransitionError(ValueError):
    pass


class FinnV2ModeContractError(ValueError):
    """Raised when a FINN V2 artifact contains a mode outside the contract."""

    code = "finn_v2_mode_contract_invalid"

    def __init__(self, mode: Optional[str]):
        self.mode = mode
        super().__init__(f"{self.code}:{mode}")


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
        raise FinnV2ModeContractError(mode)
    return normalized
