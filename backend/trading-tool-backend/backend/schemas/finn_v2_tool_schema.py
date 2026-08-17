from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr

from backend.domain.finn_v2_tools import FINN_V2_EXTERNAL_ERROR_CODES, FINN_V2_TOOL_ORDER


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
ToolCallStatus = Literal["requested", "executing", "completed", "failed"]
FreshnessStatus = Literal["fresh", "stale", "unknown", "not_applicable"]


class ToolSelector(BaseModel):
    asset: Optional[constr(strip_whitespace=True, min_length=1, max_length=20)] = None
    setup_id: Optional[int] = None
    strategy_id: Optional[int] = None
    bot_id: Optional[int] = None
    report_type: Optional[constr(strip_whitespace=True, min_length=1, max_length=32)] = None
    report_date: Optional[datetime] = None

    class Config:
        extra = "allow"


class ToolSummary(BaseModel):
    title: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ToolExecutionEnvelope(BaseModel):
    tool_name: ToolName
    status: ToolCallStatus
    success: bool
    selector: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    result_summary: Optional[Dict[str, Any]] = None
    resolution_source: Optional[str] = None
    freshness_status: Optional[FreshnessStatus] = None
    error_codes: List[str] = Field(default_factory=list)


class ToolRegistryEntry(BaseModel):
    name: ToolName
    readonly: bool = True
    description: str
    depends_on: List[ToolName] = Field(default_factory=list)


class ToolRegistryResponse(BaseModel):
    tools: List[ToolRegistryEntry]


def tool_names() -> List[str]:
    return list(FINN_V2_TOOL_ORDER)


def external_error_codes() -> List[str]:
    return list(FINN_V2_EXTERNAL_ERROR_CODES)

