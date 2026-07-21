from typing import Literal

from pydantic import BaseModel, Field


class IndicatorContextRequest(BaseModel):
    symbol: str = Field(default="BTC", min_length=1, max_length=20)
    category: Literal["market", "macro", "technical"]
    indicator: str = Field(min_length=1, max_length=120)
    period: Literal["day", "week", "month", "quarter"] = "day"
    timeframe: str = Field(default="1D", min_length=1, max_length=20)
    locale: str = Field(default="nl", min_length=2, max_length=10)


class WorkspaceContextRequest(BaseModel):
    subject_type: Literal["setup", "strategy", "automation", "reflection"]
    subject_id: int | None = Field(default=None, ge=1)
    symbol: str = Field(default="BTC", min_length=1, max_length=20)
    timeframe: str = Field(default="1D", min_length=1, max_length=20)
    period: Literal["day", "week", "month", "quarter"] = "day"
    locale: str = Field(default="nl", min_length=2, max_length=10)
