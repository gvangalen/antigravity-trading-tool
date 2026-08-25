from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


FINN_V2_VERIFIER_VERSION = "2026-08-17.block7"


class ClaimVerification(BaseModel):
    claim_id: str
    status: Literal["supported", "partially_supported", "unsupported", "contradicted", "unverifiable"]
    evidence_refs_valid: bool
    ownership_valid: bool
    entailment_valid: bool
    reason_codes: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class CoverageVerification(BaseModel):
    required_scopes: List[str] = Field(default_factory=list)
    covered_scopes: List[str] = Field(default_factory=list)
    missing_scopes: List[str] = Field(default_factory=list)
    coverage_ok: bool
    required_response_fields: List[str] = Field(default_factory=list)
    covered_response_fields: List[str] = Field(default_factory=list)
    missing_response_fields: List[str] = Field(default_factory=list)
    response_coverage_ok: bool = True

    class Config:
        extra = "forbid"


class SemanticVerificationResult(BaseModel):
    available: bool
    passes: bool
    relevance_ok: bool = True
    scope_ok: bool = True
    entailment_ok: bool = True
    recommendation_ok: bool = True
    mode_purity_ok: bool = True
    follow_up_ok: bool = True
    reason_codes: List[str] = Field(default_factory=list)
    model: Optional[str] = None

    class Config:
        extra = "forbid"


class VerifierResult(BaseModel):
    verifier_result_id: str
    run_id: str
    user_id: int
    draft_id: str
    passed: bool
    action: Literal["deliver", "repair_once", "downgrade_to_fact", "downgrade_to_clarification", "downgrade_to_unavailable", "reject"]
    claim_results: List[ClaimVerification] = Field(default_factory=list)
    coverage: CoverageVerification
    schema_ok: bool
    ownership_ok: bool
    evidence_ok: bool
    relevance_ok: bool
    mode_purity_ok: bool
    uncertainty_ok: bool
    follow_up_ok: bool
    proposal_ok: bool
    policy_ok: bool
    safety_ok: bool
    reason_codes: List[str] = Field(default_factory=list)
    semantic_verifier_used: bool
    verifier_version: str = FINN_V2_VERIFIER_VERSION
    created_at: datetime

    class Config:
        extra = "forbid"
