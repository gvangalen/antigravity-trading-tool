from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List

# Basis response object voor Macro Data
class MacroDataResponse(BaseModel):
    id: Optional[int] = None
    name: str
    value: float
    score: Optional[float]
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]
    timestamp: datetime

    class Config:
        orm_mode = True

# Aggregatie model voor de week/maand/kwartaal weergaves (de oude frontend verwacht specifieke fields)
class MacroAggregateResponse(BaseModel):
    indicator: str
    waarde: float
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]
    score: Optional[float]
    timestamp: datetime

    class Config:
        orm_mode = True

# Voor het toevoegen reponse
class MacroAddResponse(BaseModel):
    message: str
    value: float
    score: Optional[float]
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]

class MacroIndicatorRuleResponse(BaseModel):
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

class MacroIndicatorNamesResponse(BaseModel):
    name: str
    display_name: str
