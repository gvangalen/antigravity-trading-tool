from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


ToolName = Literal[
    "read_profile",
    "read_user_preferences",
    "read_active_asset",
    "read_indicator_configuration",
    "read_asset_scores",
    "read_market_snapshot",
    "read_macro_snapshot",
    "read_technical_snapshot",
    "read_active_setup",
    "read_linked_strategy",
    "read_linked_bot",
    "read_bot_status",
    "read_portfolio",
    "read_latest_report",
    "read_review_history",
]

ToolStatus = Literal["requested", "executing", "completed", "failed"]
FreshnessStatus = Literal["fresh", "stale", "unknown", "not_applicable"]

FINN_V2_TOOL_ORDER: List[ToolName] = [
    "read_profile",
    "read_user_preferences",
    "read_active_asset",
    "read_indicator_configuration",
    "read_asset_scores",
    "read_market_snapshot",
    "read_macro_snapshot",
    "read_technical_snapshot",
    "read_active_setup",
    "read_linked_strategy",
    "read_linked_bot",
    "read_bot_status",
    "read_portfolio",
    "read_latest_report",
    "read_review_history",
]

FINN_V2_EXTERNAL_ERROR_CODES: List[str] = [
    "tool_unknown",
    "tool_feature_disabled",
    "tool_readonly_violation",
    "tool_run_not_owned",
    "tool_run_invalid_state",
    "asset_not_resolved",
    "setup_not_resolved",
    "setup_ambiguous",
    "strategy_not_resolved",
    "strategy_ambiguous",
    "bot_not_resolved",
    "bot_ambiguous",
    "entity_not_found",
    "report_not_found",
    "review_history_unavailable",
    "source_unavailable",
    "tool_timeout",
    "tool_internal_error",
    "result_redacted",
]

FINN_V2_INTERNAL_ERROR_CODES: List[str] = ["ownership_mismatch_detected"]

TOOL_FRESHNESS_MAX_AGE_SECONDS: Dict[str, Optional[int]] = {
    "read_profile": None,
    "read_user_preferences": None,
    "read_active_asset": None,
    "read_indicator_configuration": None,
    "read_asset_scores": 21600,
    "read_market_snapshot": 900,
    "read_macro_snapshot": 21600,
    "read_technical_snapshot": 21600,
    "read_active_setup": None,
    "read_linked_strategy": None,
    "read_linked_bot": None,
    "read_bot_status": 300,
    "read_portfolio": 900,
    "read_latest_report": 43200,
    "read_review_history": None,
}


@dataclass
class ToolDefinition:
    name: ToolName
    description: str
    readonly: bool = True
    depends_on: List[ToolName] = field(default_factory=list)


@dataclass
class ResolvedEntity:
    entity_type: str
    value: Any
    resolution_source: str


@dataclass
class ToolExecutionResult:
    tool_name: ToolName
    status: ToolStatus
    success: bool
    result: Optional[Dict[str, Any]] = None
    result_summary: Optional[Dict[str, Any]] = None
    selector: Dict[str, Any] = field(default_factory=dict)
    error_codes: List[str] = field(default_factory=list)
    resolution_source: Optional[str] = None
    freshness_status: Optional[FreshnessStatus] = None

