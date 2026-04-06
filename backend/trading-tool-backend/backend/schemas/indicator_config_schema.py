from pydantic import BaseModel
from typing import List, Optional, Any

class IndicatorBucketRule(BaseModel):
    range_min: float
    range_max: float
    score: int
    trend: Optional[str] = None
    interpretation: Optional[str] = None
    action: Optional[str] = None

class IndicatorConfigResponse(BaseModel):
    indicator: str
    category: str
    score_mode: str
    weight: float
    rules: List[IndicatorBucketRule]

class IndicatorSettingsUpdate(BaseModel):
    category: str
    indicator: str
    score_mode: Optional[str] = None
    weight: Optional[float] = 1.0

class IndicatorCustomRulesSave(BaseModel):
    category: str
    indicator: str
    weight: Optional[float] = 1.0
    rules: List[dict] # Allow raw dict because frontend sends score, trend, etc.

class IndicatorResetPayload(BaseModel):
    category: str
    indicator: str
