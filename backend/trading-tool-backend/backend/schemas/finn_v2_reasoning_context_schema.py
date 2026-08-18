from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr, validator

from backend.domain.finn_v2_contract import normalize_interaction_mode


REASONING_CONTEXT_VERSION = "2026-08-17.block6"


class ReasoningEvidenceItem(BaseModel):
    evidence_id: constr(min_length=2, max_length=8)
    artifact_id: str
    tool_name: str
    domain: str
    entity_type: str
    entity_id: Optional[str] = None
    asset: Optional[str] = None
    source: str
    as_of: Optional[datetime] = None
    freshness: str
    confidence: str
    facts: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class ReasoningDomainStatus(BaseModel):
    domain: str
    status: str
    confidence: str
    issue_codes: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ReasoningPolicyContext(BaseModel):
    policy_class: str
    allowed: bool
    proposal_allowed: bool
    confirmation_required: bool
    step_up_required: bool
    execution_allowed: bool
    operation_type: Optional[str] = None
    warning_codes: List[str] = Field(default_factory=list)
    blocking_codes: List[str] = Field(default_factory=list)
    proposal_input_required: bool = False

    class Config:
        extra = "forbid"


class ReasoningContextPackage(BaseModel):
    run_id: str
    user_id: int
    user_message: str
    locale: str
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
    subject_scopes: List[str] = Field(default_factory=list)
    required_domains: List[str] = Field(default_factory=list)
    orchestrator_result_id: str
    snapshot_id: str
    validation_id: str
    policy_decision_id: str
    evidence_set_hash: str
    context_version: str = REASONING_CONTEXT_VERSION
    evidence: List[ReasoningEvidenceItem] = Field(default_factory=list)
    domain_statuses: List[ReasoningDomainStatus] = Field(default_factory=list)
    policy: ReasoningPolicyContext
    allowed_response_modes: List[str] = Field(default_factory=list)
    allowed_operation_types: List[str] = Field(default_factory=list)
    uncertainty_codes: List[str] = Field(default_factory=list)

    @validator("evidence")
    def _validate_unique_evidence_ids(cls, value: List[ReasoningEvidenceItem]) -> List[ReasoningEvidenceItem]:
        ids = [item.evidence_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_evidence_ids")
        return value

    @validator("interaction_mode", pre=True)
    def _normalize_mode(cls, value: str) -> str:
        return normalize_interaction_mode(value)

    class Config:
        extra = "forbid"
