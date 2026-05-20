from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class ActiveSetupResponse(BaseModel):
    id: int
    name: str
    symbol: str
    timeframe: str
    setup_type: Optional[str] = None
    dca_frequency: Optional[str] = None
    dca_day: Optional[Any] = None
    dca_month_day: Optional[Any] = None
    min_macro_score: Optional[float] = None
    max_macro_score: Optional[float] = None
    min_technical_score: Optional[float] = None
    max_technical_score: Optional[float] = None
    min_market_score: Optional[float] = None
    max_market_score: Optional[float] = None
    explanation: str
    timestamp: datetime
    score: float
    is_active: bool
    breakdown: Dict[str, Any]

class CategoryScoreResponse(BaseModel):
    score: float
    interpretation: str
    top_contributors: List[str]

class SetupScoreResponse(BaseModel):
    score: float
    interpretation: str
    top_contributors: List[str]
    active_setups: List[ActiveSetupResponse]

class DailyCombinedScoreResponse(BaseModel):
    macro: CategoryScoreResponse
    technical: CategoryScoreResponse
    market: CategoryScoreResponse
    setup: SetupScoreResponse

class MasterScoreResponse(BaseModel):
    master_score: float
    master_trend: str
    master_bias: str
    master_risk: str
    alignment_score: float
    outlook: str
    weights: Dict[str, float]
    data_warnings: List[str]
    domains: Dict[str, Any]
    summary: str
    date: Optional[str]

class IntelligenceWeightsRequest(BaseModel):
    weights: Dict[str, float]
