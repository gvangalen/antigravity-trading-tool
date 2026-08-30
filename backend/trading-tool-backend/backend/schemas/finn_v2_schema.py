from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr


InteractionMode = Literal[
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

RunStatus = Literal[
    "created",
    "queued",
    "collecting",
    "planned",
    "reasoning",
    "verifying",
    "clarification_required",
    "unavailable",
    "downgraded",
    "rejected",
    "blocked",
    "completed",
    "failed",
    "canceled",
]

RunVisibility = Literal["shadow", "visible"]
RunTransport = Literal["chat", "stream"]

PolicyClass = Literal[
    "read",
    "advice",
    "proposal",
    "paper_action",
    "live_action",
    "high_risk_action",
    "unsupported_action",
]

VerifierStatus = Literal[
    "not_run",
    "passed",
    "failed",
    "downgraded",
]

ResponseSource = Literal[
    "foundation_placeholder",
    "v1_adapter",
    "v2_runtime",
]


class AgentRunRequest(BaseModel):
    message: constr(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    # The web composer owns a stable, user-scoped session identifier.  It is
    # distinct from the persisted V2 conversation id and is resolved server-side.
    session_id: Optional[constr(min_length=1, max_length=128)] = None
    workspace_hints: Dict[str, Any] = Field(default_factory=dict)
    client_context: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[constr(min_length=8, max_length=128)] = None
    transport: RunTransport = "chat"

    class Config:
        extra = "forbid"


class AgentRunContext(BaseModel):
    run_id: str
    request_id: str
    trace_id: str
    user_id: int
    conversation_id: str
    idempotency_key: str
    transport: RunTransport
    visibility: RunVisibility
    feature_mode: str
    message: str
    workspace_hints: Dict[str, Any] = Field(default_factory=dict)
    client_context: Dict[str, Any] = Field(default_factory=dict)
    request_path: str
    client_ip_hash: Optional[str] = None
    user_agent_hash: Optional[str] = None
    created_at: datetime


class EvidenceItem(BaseModel):
    entity_type: str
    entity_id: str
    source: str
    as_of: Optional[datetime] = None
    freshness: Optional[str] = None
    confidence: Optional[str] = None
    owned_by_user: Optional[bool] = None


class PolicyDecision(BaseModel):
    allowed: bool = True
    policy_class: PolicyClass = "read"
    reasons: List[str] = Field(default_factory=list)
    confirmation_required: bool = False
    execute_allowed: bool = False


class VerifiedResponse(BaseModel):
    mode: InteractionMode = "UNAVAILABLE"
    content: str = ""
    response_source: ResponseSource = "foundation_placeholder"
    verifier_status: VerifierStatus = "not_run"
    evidence: List[EvidenceItem] = Field(default_factory=list)
    uncertainty: List[str] = Field(default_factory=list)
    proposal_id: Optional[str] = None
    confirmation_required: bool = False
    # Shared terminal projection for polling and SSE.
    next_step: Optional[Dict[str, Any]] = None
    reasoning_provenance: Dict[str, Any] = Field(default_factory=dict)


class AgentRunStatusEnvelope(BaseModel):
    run_id: str
    conversation_id: str
    status: RunStatus
    mode: Optional[InteractionMode] = None
    visibility: RunVisibility
    response: Optional[VerifiedResponse] = None
    policy: Optional[PolicyDecision] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
    # Terminal runs expose a safe projection of their persisted V2 chain.
    # It deliberately contains references and statuses, not evidence payloads.
    runtime_trace: Dict[str, Any] = Field(default_factory=dict)


class AgentRunCancelResponse(BaseModel):
    ok: bool = True
    run: AgentRunStatusEnvelope
