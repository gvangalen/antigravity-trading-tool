from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

class AiModeStat(BaseModel):
    mode: str
    count: int
    percentage: float

class FeatureStat(BaseModel):
    purpose: str
    total_requests: int
    total_cost: float
    avg_cost: float

class UserUsageStat(BaseModel):
    user_id: Optional[int]
    email: str
    plan: str
    requests_today: int
    requests_limit: int
    usage_month_eur: float
    usage_today_eur: float
    revenue_month_eur: float
    profit_month_eur: float

class UserDistribution(BaseModel):
    bucket: str # '<10', '10-25', '25-100', '>100'
    count: int

class ModeLatency(BaseModel):
    mode: str
    avg_ms: float

class PlatformAiOverview(BaseModel):
    total_requests_today: int
    total_requests_month: int
    total_cost_month_eur: float
    total_revenue_month_eur: float
    total_profit_month_eur: float
    total_savings_month_eur: float
    platform_overhead_eur: float
    cache_hit_rate: float
    avg_latency_ms: float
    avg_cost_per_full_request: float

class AdminAiStatsResponse(BaseModel):
    overview: PlatformAiOverview
    top_users: List[UserUsageStat]
    feature_breakdown: List[FeatureStat]
    mode_distribution: List[AiModeStat]
    latency_stats: List[ModeLatency]
    user_distribution: List[UserDistribution]
    heavy_user_impact_pct: float
