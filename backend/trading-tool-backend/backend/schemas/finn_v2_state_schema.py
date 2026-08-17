from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, validator

from backend.schemas.finn_v2_evidence_schema import PAYLOAD_TYPE_TO_SCHEMA_NAME, SCHEMA_VERSION, ToolDataUnion, parse_tool_payload


ASSEMBLY_VERSION = "2026-08-17.block3"


class EvidenceReference(BaseModel):
    artifact_id: str
    tool_call_id: int
    tool_name: str
    content_hash: str
    source: str
    source_as_of: Optional[datetime] = None


class StateNode(BaseModel):
    node_id: str
    entity_type: str
    entity_id: Optional[str] = None
    asset: Optional[str] = None
    payload_type: str
    payload: Optional[ToolDataUnion] = None
    availability: Literal["available", "stale", "ambiguous", "unavailable", "not_collected"]
    freshness: Literal["fresh", "stale", "unknown", "not_applicable"]
    confidence: Literal["high", "medium", "low", "none"]
    evidence: List[EvidenceReference] = Field(default_factory=list)
    issue_codes: List[str] = Field(default_factory=list)

    @validator("payload", pre=True, always=True)
    def _parse_payload(cls, value, values):
        schema_name = PAYLOAD_TYPE_TO_SCHEMA_NAME.get(values.get("payload_type"))
        return parse_tool_payload(schema_name, value)

    class Config:
        smart_union = True


class StateEdge(BaseModel):
    from_node_id: str
    to_node_id: str
    relation: Literal[
        "has_preferences",
        "focuses_on_asset",
        "has_indicator_configuration",
        "has_scores",
        "has_market_snapshot",
        "has_macro_snapshot",
        "has_technical_snapshot",
        "has_setup",
        "has_strategy",
        "has_bot",
        "has_bot_status",
        "has_portfolio",
        "has_latest_report",
        "has_review_history",
    ]
    confidence: Literal["high", "medium", "low"]
    evidence: List[EvidenceReference] = Field(default_factory=list)


class ToolOutcome(BaseModel):
    tool_name: str
    status: Literal["available", "stale", "ambiguous", "unavailable", "not_collected", "failed"]
    artifact_id: Optional[str] = None
    error_codes: List[str] = Field(default_factory=list)


class FinancialStateSnapshot(BaseModel):
    snapshot_id: str
    run_id: str
    user_id: int
    revision: int
    schema_version: str = SCHEMA_VERSION
    assembly_version: str = ASSEMBLY_VERSION
    evidence_set_hash: str
    nodes: List[StateNode] = Field(default_factory=list)
    edges: List[StateEdge] = Field(default_factory=list)
    tool_outcomes: List[ToolOutcome] = Field(default_factory=list)
    assembled_at: datetime
    redacted_at: Optional[datetime] = None
