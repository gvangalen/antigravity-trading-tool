"""Explicit user attestation for one fully closed imported exchange position."""

from uuid import UUID

from pydantic import BaseModel, StrictInt, conlist


class ExchangeTradeReviewCreate(BaseModel):
    fill_ids: conlist(StrictInt, min_items=2, max_items=500)
    closure_confirmed: bool
    same_account_confirmed: bool = False
    idempotency_key: UUID
