from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

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


# =========================================================
# 📊 UNIFIED MOBILE OVERVIEW SCHEMAS (Fase 4 / Optie C)
# =========================================================

class MobileAssetWatchlistSchema(BaseModel):
    symbol: str
    price: Optional[float] = None
    change_24h: Optional[float] = None
    macro_score: float
    technical_score: float
    market_score: float
    setup_score: float

class MobileActiveBotSchema(BaseModel):
    bot_id: int
    name: str
    symbol: str
    is_active: bool
    is_live: bool
    invested_eur: float
    position_value_eur: Optional[float] = None
    profit_pct: Optional[float] = None

class MobileFinnBriefingSchema(BaseModel):
    greeting: str
    summary: str
    suggested_actions: List[str]

class MobilePortfolioOverviewSchema(BaseModel):
    total_balance_eur: float
    total_invested_eur: float
    total_profit_pct: float
    active_bots_count: int

class MobileIntelligenceEventSchema(BaseModel):
    id: int
    type: str
    symbol: Optional[str] = None
    title: str
    description: str
    severity: str
    created_at: datetime

class MobileOverviewResponse(BaseModel):
    user_id: int
    portfolio: MobilePortfolioOverviewSchema
    watchlist: List[MobileAssetWatchlistSchema]
    active_bots: List[MobileActiveBotSchema]
    finn_briefing: MobileFinnBriefingSchema
    intelligence_events: Optional[List[MobileIntelligenceEventSchema]] = None
