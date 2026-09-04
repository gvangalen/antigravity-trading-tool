from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Literal, Optional

from pydantic import BaseModel

from backend.schemas.finn_v2_response_schema import VerifiedResponse


class FinnV2DeliveryEnvelope(BaseModel):
    run_id: str
    conversation_id: str
    status: Literal[
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
    response: Optional[VerifiedResponse] = None
    proposal_id: Optional[str] = None
    confirmation_required: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    delivery_source: Literal["finn_v2_verified", "runtime_contract_projection"] = "finn_v2_verified"

    class Config:
        extra = "forbid"


class FinnV2StreamEvent(BaseModel):
    # Keep this union aligned with every terminal status the delivery service
    # can expose. A typed SSE envelope must never turn a valid rejected or
    # unavailable run into a serialization failure.
    event: Literal[
        "run.started", "run.progress", "run.completed", "run.failed",
        "run.unavailable", "run.downgraded", "run.rejected", "run.blocked", "run.canceled",
    ]
    run_id: str
    payload: Dict[str, Any]

    class Config:
        extra = "forbid"


__all__ = [
    "AsyncIterator",
    "FinnV2DeliveryEnvelope",
    "FinnV2StreamEvent",
]
