from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TechnicalDataResponse(BaseModel):
    indicator: str
    waarde: float
    score: float
    advies: str
    uitleg: str
    timestamp: datetime

    class Config:
        from_attributes = True

class TechnicalIndicatorConfig(BaseModel):
    name: str
    display_name: str

class TechnicalIndicatorRuleResponse(BaseModel):
    id: int
    indicator: str
    range_min: Optional[float]
    range_max: Optional[float]
    score: float
    trend: str
    interpretation: str
    action: str

    class Config:
        from_attributes = True

class TechnicalIndicatorHistoryResponse(BaseModel):
    value: float
    timestamp: datetime

    class Config:
        from_attributes = True
