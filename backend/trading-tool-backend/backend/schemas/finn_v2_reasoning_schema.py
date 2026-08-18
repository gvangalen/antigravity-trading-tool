from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr, root_validator, validator


FINN_V2_REASONING_PROMPT_VERSION = "2026-08-17.block6"
FINN_V2_REASONING_SCHEMA_VERSION = "2026-08-17.block6"
FINN_V2_REASONING_VERSION = "2026-08-17.block6"


class ReasoningClaim(BaseModel):
    claim_id: str
    claim_type: Literal["fact", "inference", "evaluation", "recommendation", "uncertainty"]
    text: constr(min_length=1, max_length=600)
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]

    class Config:
        extra = "forbid"


class ReasoningSupportingPoint(BaseModel):
    title: constr(min_length=1, max_length=120)
    explanation: constr(min_length=1, max_length=500)
    evidence_refs: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ReasoningNextStep(BaseModel):
    title: constr(min_length=1, max_length=120)
    instruction: constr(min_length=1, max_length=400)
    operation_type: Optional[str] = None
    target_entity_type: Optional[str] = None
    target_entity_id: Optional[str] = None
    requires_confirmation: bool = False

    class Config:
        extra = "forbid"


class ProposalCandidate(BaseModel):
    operation_type: Literal[
        "update_indicator_configuration",
        "create_setup",
        "update_setup",
        "update_strategy",
        "save_trade_plan",
        "activate_paper_bot",
        "activate_live_bot",
        "portfolio_rebalance",
        "manual_order",
    ]
    target_type: str
    target_id: Optional[str] = None
    asset: Optional[str] = None
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    impact_summary: str
    risk_summary: str
    confirmation_required: bool

    class Config:
        extra = "forbid"


class ReasoningResult(BaseModel):
    reasoning_result_id: str
    run_id: str
    user_id: int
    mode: Literal["FACT", "CAPABILITY", "EVALUATION", "PROPOSAL", "ACTION", "CLARIFICATION", "UNAVAILABLE"]
    direct_answer: constr(min_length=1, max_length=1200)
    main_observation: constr(min_length=1, max_length=500)
    supporting_points: List[ReasoningSupportingPoint] = Field(default_factory=list, max_items=4)
    claims: List[ReasoningClaim] = Field(default_factory=list)
    uncertainty_summary: Optional[str] = None
    uncertainty_codes: List[str] = Field(default_factory=list)
    next_step: Optional[ReasoningNextStep] = None
    follow_up_question: Optional[constr(min_length=1, max_length=300)] = None
    proposal_candidate: Optional[ProposalCandidate] = None
    evidence_refs_used: List[str] = Field(default_factory=list)
    prompt_version: str = FINN_V2_REASONING_PROMPT_VERSION
    reasoning_version: str = FINN_V2_REASONING_VERSION
    model: str
    created_at: datetime

    @validator("supporting_points")
    def _limit_points(cls, value: List[ReasoningSupportingPoint]) -> List[ReasoningSupportingPoint]:
        if len(value) > 4:
            raise ValueError("too_many_supporting_points")
        return value

    @root_validator
    def _validate_proposal_candidate_mode(cls, values):
        mode = values.get("mode")
        proposal_candidate = values.get("proposal_candidate")
        if proposal_candidate is not None and mode not in {"PROPOSAL", "ACTION"}:
            raise ValueError("proposal_candidate_not_allowed")
        return values

    class Config:
        extra = "forbid"


class PersistedReasoningRecord(BaseModel):
    reasoning_result_id: str
    run_id: str
    user_id: int
    orchestrator_result_id: str
    policy_decision_id: str
    snapshot_id: str
    validation_id: str
    status: Literal["pending", "generating", "ready", "unavailable", "failed"]
    mode: Literal["FACT", "CAPABILITY", "EVALUATION", "PROPOSAL", "ACTION", "CLARIFICATION", "UNAVAILABLE"]
    context_version: str
    evidence_set_hash: str
    input_hash: str
    prompt_version: str
    schema_version: str = FINN_V2_REASONING_SCHEMA_VERSION
    reasoning_version: str = FINN_V2_REASONING_VERSION
    model: Optional[str] = None
    result: Optional[ReasoningResult] = None
    error_codes: List[str] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    retry_count: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        extra = "forbid"
