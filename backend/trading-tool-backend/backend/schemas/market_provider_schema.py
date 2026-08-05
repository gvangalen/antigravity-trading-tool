from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AssetRecord(BaseModel):
    symbol: str
    display_name: str
    asset_class: str
    provider: str = "manual"
    primary_provider: str = "manual"
    fallback_provider: Optional[str] = None
    provider_symbol: Optional[str] = None
    exchange: Optional[str] = None
    market_region: str = "global"
    timezone: str = "UTC"
    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None
    entitlement_tier: str = "internal"
    is_delayed: bool = False
    refresh_policy: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PriceSnapshotDTO(BaseModel):
    symbol: str
    provider: str
    provider_symbol: str
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    change_absolute: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[float] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    observed_at: Optional[datetime] = None
    is_delayed: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OHLCVCandleDTO(BaseModel):
    symbol: str
    provider: str
    provider_symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    period_start: datetime
    period_end: Optional[datetime] = None
    is_final: bool = True
    raw_payload: dict[str, Any] = Field(default_factory=dict)
