from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TechnicalDataResponse(BaseModel):
    indicator: str
    waarde: float = 0.0
    score: float = 0.0
    advies: str
    uitleg: str
    timestamp: datetime

    class Config:
        orm_mode = True

class TechnicalIndicatorConfig(BaseModel):
    name: str
    display_name: str

class TechnicalIndicatorRuleResponse(BaseModel):
    id: int
    indicator: str
    range_min: Optional[float]
    range_max: Optional[float]
    score: Optional[float]
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]

    class Config:
        orm_mode = True

class TechnicalIndicatorHistoryResponse(BaseModel):
    value: float
    timestamp: datetime

    class Config:
        orm_mode = True


class TechnicalIndicatorPreferenceItem(BaseModel):
    indicator: str
    priority: int = 100


class TechnicalIndicatorPreferenceResponse(BaseModel):
    scope: str
    symbol: Optional[str] = None
    asset_class: Optional[str] = None
    indicators: List[TechnicalIndicatorPreferenceItem]


class TechnicalIndicatorPreferenceUpdate(BaseModel):
    symbol: Optional[str] = None
    asset_class: Optional[str] = None
    indicators: List[TechnicalIndicatorPreferenceItem]
