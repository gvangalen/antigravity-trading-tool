from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ScoresSchema(BaseModel):
    macro: float
    technical: float
    market: float
    setup: float

class ExplanationSchema(BaseModel):
    macro: str
    technical: str
    setup: str

class TopSetupSchema(BaseModel):
    name: str
    score: float
    timeframe: Optional[str] = None
    symbol: Optional[str] = None
    explanation: Optional[str] = None
    timestamp: Optional[str] = None

class SetupSummarySchema(BaseModel):
    name: str
    timestamp: str

class TradingAdviceSchema(BaseModel):
    symbol: str
    advice: str
    explanation: str
    timestamp: str

class DashboardResponse(BaseModel):
    user_id: int
    market_data: List[Dict[str, Any]]
    technical_data: Dict[str, Dict[str, Any]]
    macro_data: List[Dict[str, Any]]
    setups: List[Dict[str, Any]]
    scores: ScoresSchema
    explanation: ExplanationSchema
