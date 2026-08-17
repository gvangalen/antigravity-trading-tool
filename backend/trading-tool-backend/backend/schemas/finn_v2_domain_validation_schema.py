from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas.finn_v2_evidence_schema import SCHEMA_VERSION


VALIDATOR_VERSION = "2026-08-17.block3"


class EvidenceIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    domain: str
    node_id: Optional[str] = None
    artifact_id: Optional[str] = None
    message: str


class ClarificationCandidate(BaseModel):
    code: str
    domain: str
    question: str
    entity_type: Optional[str] = None


class DomainValidationResult(BaseModel):
    domain: Literal[
        "identity_context",
        "market_context",
        "plan_context",
        "automation_context",
        "portfolio_context",
        "report_context",
        "review_context",
    ]
    status: Literal["available", "degraded", "ambiguous", "unavailable", "not_collected", "invalid"]
    confidence: Literal["high", "medium", "low", "none"]
    issues: List[EvidenceIssue] = Field(default_factory=list)
    clarification_candidates: List[ClarificationCandidate] = Field(default_factory=list)
    required_artifacts: List[str] = Field(default_factory=list)
    available_artifacts: List[str] = Field(default_factory=list)


class EvidenceValidationResult(BaseModel):
    validation_id: str
    snapshot_id: str
    run_id: str
    user_id: int
    schema_version: str = SCHEMA_VERSION
    validator_version: str = VALIDATOR_VERSION
    evidence_set_hash: str
    integrity_status: Literal["valid", "degraded", "invalid"]
    domains: List[DomainValidationResult] = Field(default_factory=list)
    issues: List[EvidenceIssue] = Field(default_factory=list)
    validated_at: datetime
    redacted_at: Optional[datetime] = None
