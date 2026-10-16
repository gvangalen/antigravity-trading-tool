"""Authenticated user attestation for one closed Bybit derivative episode."""

from typing import Literal
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt, constr


class BybitDerivativeReviewCreate(BaseModel):
    source_id: StrictInt
    category: Literal["linear", "inverse"]
    symbol: constr(regex=r"^[A-Za-z0-9]{1,40}$")
    position_idx: StrictInt
    episode_key: constr(regex=r"^[0-9a-f]{64}$")
    closure_confirmed: StrictBool
    idempotency_key: UUID
    before_at: datetime | None = None
    before_id: StrictInt | None = None
