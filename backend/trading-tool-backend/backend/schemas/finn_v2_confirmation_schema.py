from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, SecretStr


class FinnV2ConfirmationRequest(BaseModel):
    proposal_id: str
    confirmation_token: SecretStr
    expected_payload_hash: str

    class Config:
        extra = "forbid"


class FinnV2ConfirmationResult(BaseModel):
    confirmation_id: str
    proposal_id: str
    confirmed: bool
    already_confirmed: bool
    step_up_required: bool
    step_up_satisfied: bool
    eligibility_must_be_rechecked: bool
    reasons: List[str] = Field(default_factory=list)
    created_at: datetime
