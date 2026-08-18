from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, constr, root_validator, validator

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningNextStep, ReasoningSupportingPoint


FINN_V2_RESPONSE_DRAFT_VERSION = "2026-08-17.block7"
FINN_V2_VERIFIED_RESPONSE_VERSION = "2026-08-17.block7"


class ResponseClaim(BaseModel):
    claim_id: str
    claim_type: Literal["fact", "inference", "evaluation", "recommendation", "uncertainty"]
    text: constr(min_length=1, max_length=600)
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]

    class Config:
        extra = "forbid"


class ResponseDraft(BaseModel):
    draft_id: str
    run_id: str
    user_id: int
    mode: Literal["FACT", "CAPABILITY", "EVALUATION", "PROPOSAL", "ACTION", "CLARIFICATION", "UNAVAILABLE"]
    direct_answer: constr(min_length=1, max_length=1200)
    main_observation: constr(min_length=1, max_length=500)
    supporting_points: List[ReasoningSupportingPoint] = Field(default_factory=list, max_items=4)
    claims: List[ResponseClaim] = Field(default_factory=list)
    uncertainty_summary: Optional[constr(min_length=1, max_length=400)] = None
    uncertainty_codes: List[str] = Field(default_factory=list)
    next_step: Optional[ReasoningNextStep] = None
    follow_up_question: Optional[constr(min_length=1, max_length=300)] = None
    proposal_candidate: Optional[ProposalCandidate] = None
    reasoning_result_id: Optional[str] = None
    evidence_set_hash: str
    draft_version: str = FINN_V2_RESPONSE_DRAFT_VERSION
    created_at: datetime

    @validator("supporting_points")
    def _limit_points(cls, value: List[ReasoningSupportingPoint]) -> List[ReasoningSupportingPoint]:
        if len(value) > 4:
            raise ValueError("too_many_supporting_points")
        return value

    @root_validator
    def _validate_mode_contract(cls, values):
        mode = values.get("mode")
        follow_up_question = values.get("follow_up_question")
        proposal_candidate = values.get("proposal_candidate")
        if proposal_candidate is not None and mode not in {"PROPOSAL", "ACTION"}:
            raise ValueError("proposal_candidate_not_allowed")
        if mode == "CLARIFICATION" and not follow_up_question:
            raise ValueError("clarification_requires_question")
        return values

    class Config:
        extra = "forbid"


class VerifiedResponse(BaseModel):
    verified_response_id: str
    run_id: str
    user_id: int
    mode: Literal["FACT", "CAPABILITY", "EVALUATION", "PROPOSAL", "ACTION", "CLARIFICATION", "UNAVAILABLE"]
    direct_answer: constr(min_length=1, max_length=1200)
    main_observation: constr(min_length=1, max_length=500)
    supporting_points: List[ReasoningSupportingPoint] = Field(default_factory=list, max_items=4)
    claims: List[ResponseClaim] = Field(default_factory=list)
    uncertainty_summary: Optional[constr(min_length=1, max_length=400)] = None
    uncertainty_codes: List[str] = Field(default_factory=list)
    next_step: Optional[ReasoningNextStep] = None
    follow_up_question: Optional[constr(min_length=1, max_length=300)] = None
    proposal_id: Optional[str] = None
    confirmation_required: bool = False
    verifier_status: Literal["passed", "repaired", "downgraded"]
    evidence_set_hash: str
    verifier_result_id: str
    response_version: str = FINN_V2_VERIFIED_RESPONSE_VERSION
    created_at: datetime

    class Config:
        extra = "forbid"
