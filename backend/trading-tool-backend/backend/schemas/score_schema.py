from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime

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
    timestamp: Optional[datetime] = None
    score: Optional[float] = None
    is_active: bool
    breakdown: Dict[str, Any]
    status: Optional[str] = None

class CategoryScoreResponse(BaseModel):
    score: Optional[float] = None
    interpretation: str
    top_contributors: List[str]
    source_status: Optional[str] = None

class SetupScoreResponse(BaseModel):
    score: Optional[float] = None
    interpretation: str
    top_contributors: List[str]
    active_setups: List[ActiveSetupResponse]
    source_status: Optional[str] = None

class DailyCombinedScoreResponse(BaseModel):
    macro: CategoryScoreResponse
    technical: CategoryScoreResponse
    market: CategoryScoreResponse
    setup: SetupScoreResponse
    report_date: Optional[date] = None
    benchmark_score: Optional[float] = None
    benchmark_weights: Optional[Dict[str, float]] = None
    calculated_at: Optional[datetime] = None
    indicator_evidence: Dict[str, Any] = Field(default_factory=dict)

class MasterScoreResponse(BaseModel):
    master_score: Optional[float] = None
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
