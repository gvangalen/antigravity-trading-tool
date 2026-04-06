from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List

class MarketDataIndicatorBase(BaseModel):
    name: str
    value: float

class MarketDataIndicatorCreate(MarketDataIndicatorBase):
    pass

class MarketDataIndicatorResponse(MarketDataIndicatorBase):
    id: int
    score: Optional[float]
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]
    timestamp: datetime

    class Config:
        orm_mode = True

class MarketDataResponse(BaseModel):
    id: int
    symbol: str
    price: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    change_24h: Optional[float]
    volume: Optional[float]
    timestamp: datetime

    class Config:
        orm_mode = True

class MarketIndicatorRuleResponse(BaseModel):
    range_min: Optional[float]
    range_max: Optional[float]
    score: Optional[float]
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]

    class Config:
        orm_mode = True

class MarketData7DResponse(BaseModel):
    id: int
    symbol: str
    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    change: Optional[float]
    volume: Optional[float]
    created_at: datetime
    
    class Config:
        orm_mode = True

class MarketForwardReturnResponse(BaseModel):
    id: int
    symbol: str
    period: str
    start: datetime = Field(alias="start_date")
    end: datetime = Field(alias="end_date")
    change: Optional[float]
    avgDaily: Optional[float] = Field(alias="avg_daily")
    created_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

class ForwardReturnChartResponse(BaseModel):
    year: int
    values: List[Optional[float]]
