from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr, validator

from backend.domain.finn_v2_contract import InformationScope, information_scope_for_tool, normalize_information_scope
from backend.domain.finn_v2_tools import FINN_V2_EXTERNAL_ERROR_CODES, FINN_V2_TOOL_ORDER
from backend.schemas.finn_v2_evidence_schema import ToolDataUnion, parse_tool_payload


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
    "read_watchlist",
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
    result: Optional[ToolDataUnion] = None
    result_summary: Optional[Dict[str, Any]] = None
    resolution_source: Optional[str] = None
    freshness_status: Optional[FreshnessStatus] = None
    error_codes: List[str] = Field(default_factory=list)
    source: str = "internal"
    schema_name: Optional[str] = None
    schema_version: str = "2026-08-17.block3"
    availability: Literal["available", "stale", "ambiguous", "unavailable", "not_collected"] = "available"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    asset: Optional[str] = None
    tool_call_id: Optional[int] = None
    artifact_id: Optional[str] = None
    information_scope: Optional[InformationScope] = None
    operation_id: Optional[str] = None
    operation_contract_version: Optional[str] = None

    @validator("result", pre=True, always=True)
    def _parse_result(cls, value, values):
        return parse_tool_payload(values.get("schema_name"), value)

    @validator("information_scope", pre=True, always=True)
    def _enforce_canonical_output_scope(cls, value, values):
        expected = information_scope_for_tool(str(values.get("tool_name") or ""))
        if value is None:
            return expected
        normalized = normalize_information_scope(value)
        if normalized != expected.value:
            raise ValueError(f"finn_v2_tool_scope_mismatch:{values.get('tool_name')}:{normalized}")
        return expected

    class Config:
        smart_union = True


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
