from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, constr


class FinnV2ProposalPublicationResult(BaseModel):
    proposal_id: str
    user_id: int
    status: Literal["pending_confirmation"]
    confirmation_token: SecretStr
    expires_at: datetime
    payload_hash: str
    confirmation_required: bool = True


class FinnV2ProposalSummary(BaseModel):
    proposal_id: str
    run_id: str
    user_id: int
    status: str
    operation_type: str
    target: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    evidence_set_hash: str
    requires_step_up_auth: bool
    expires_at: datetime


class FinnV2ExecuteProposalRequest(BaseModel):
    idempotency_key: constr(min_length=8, max_length=128)
    confirmation_token: Optional[SecretStr] = None
    expected_payload_hash: str
    csrf_token: Optional[str] = None


class ExecutionResult(BaseModel):
    execution_id: str
    proposal_id: str
    user_id: int
    operation_type: str
    status: Literal["started", "succeeded", "failed", "blocked", "already_executed"]
    idempotency_key: str
    precondition_hash: str
    postcondition_hash: Optional[str] = None
    error_codes: List[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None

