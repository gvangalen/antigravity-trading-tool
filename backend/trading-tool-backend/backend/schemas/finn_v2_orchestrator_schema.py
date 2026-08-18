from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator

from backend.domain.finn_v2_contract import normalize_interaction_mode
from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER
from backend.schemas.finn_v2_domain_validation_schema import ClarificationCandidate


ANALYSIS_VERSION = "2026-08-17.block4"
PLANNING_VERSION = "2026-08-17.block4"
ORCHESTRATOR_VERSION = "2026-08-17.block4"

SUBJECT_SCOPE_ORDER = [
    "capability",
    "profile",
    "analysis",
    "indicators",
    "setup",
    "strategy",
    "bot",
    "daily_report",
    "reflection",
    "portfolio",
    "unknown",
]
DOMAIN_ORDER = [
    "identity_context",
    "market_context",
    "plan_context",
    "automation_context",
    "portfolio_context",
    "report_context",
    "review_context",
]
CLARIFICATION_PRIORITY = ["asset", "setup", "strategy", "bot"]


class RequestAnalysisResult(BaseModel):
    interaction_mode: Literal[
        "CAPABILITY",
        "READ",
        "EVALUATE",
        "CREATE_PROPOSAL",
        "ACTION_PROPOSAL",
        "CLARIFICATION",
        "CONFIRMATION",
        "EXECUTION",
        "UNAVAILABLE",
    ]
    subject_scopes: List[
        Literal[
            "capability",
            "profile",
            "analysis",
            "indicators",
            "setup",
            "strategy",
            "bot",
            "daily_report",
            "reflection",
            "portfolio",
            "unknown",
        ]
    ] = Field(default_factory=list)
    explicit_asset: Optional[str] = None
    explicit_setup_id: Optional[int] = None
    explicit_strategy_id: Optional[int] = None
    explicit_bot_id: Optional[int] = None
    requires_comparison: bool = False
    requires_gap_analysis: bool = False
    requests_change: bool = False
    requests_execution: bool = False
    confidence: Literal["high", "medium", "low", "none"]
    matched_signals: List[str] = Field(default_factory=list)
    unresolved_signals: List[str] = Field(default_factory=list)
    reasoning_required: bool
    analysis_version: str = ANALYSIS_VERSION

    @validator("subject_scopes", pre=False)
    def _dedupe_scopes(cls, value: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in SUBJECT_SCOPE_ORDER:
            if item in value and item not in seen:
                ordered.append(item)
                seen.add(item)
        return ordered

    @validator("explicit_asset")
    def _normalize_asset(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @validator("interaction_mode", pre=True)
    def _normalize_mode(cls, value: str) -> str:
        return normalize_interaction_mode(value)


class DomainRequirementPlan(BaseModel):
    required_domains: List[
        Literal[
            "identity_context",
            "market_context",
            "plan_context",
            "automation_context",
            "portfolio_context",
            "report_context",
            "review_context",
        ]
    ] = Field(default_factory=list)
    optional_domains: List[str] = Field(default_factory=list)
    requirement_reason: List[str] = Field(default_factory=list)

    @validator("required_domains", "optional_domains", pre=False)
    def _dedupe_domains(cls, value: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in DOMAIN_ORDER:
            if item in value and item not in seen:
                ordered.append(item)
                seen.add(item)
        return ordered


class ToolPlan(BaseModel):
    run_id: str
    interaction_mode: str
    required_domains: List[str] = Field(default_factory=list)
    optional_domains: List[str] = Field(default_factory=list)
    tool_names: List[str] = Field(default_factory=list)
    tool_inputs: Dict[str, Dict[str, object]] = Field(default_factory=dict)
    max_tool_calls: int
    read_only: bool = True
    planning_version: str = PLANNING_VERSION
    planning_reasons: List[str] = Field(default_factory=list)

    @validator("tool_names", pre=False)
    def _ordered_tools(cls, value: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for tool_name in FINN_V2_TOOL_ORDER:
            if tool_name in value and tool_name not in seen:
                ordered.append(tool_name)
                seen.add(tool_name)
        return ordered


class OrchestratorResult(BaseModel):
    orchestrator_result_id: str
    run_id: str
    user_id: int
    analysis: RequestAnalysisResult
    domain_requirements: DomainRequirementPlan
    tool_plan: ToolPlan
    snapshot_id: Optional[str] = None
    validation_id: Optional[str] = None
    outcome: Literal["reasoning_ready", "clarification_required", "unavailable", "failed"]
    selected_clarification: Optional[ClarificationCandidate] = None
    unavailable_codes: List[str] = Field(default_factory=list)
    uncertainty_codes: List[str] = Field(default_factory=list)
    orchestrator_version: str = ORCHESTRATOR_VERSION
    created_at: datetime

    @validator("unavailable_codes", "uncertainty_codes", pre=False)
    def _dedupe_codes(cls, value: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in value:
            if item and item not in seen:
                ordered.append(item)
                seen.add(item)
        return ordered
