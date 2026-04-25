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
    rejection_breakdown: Optional[Dict[str, int]] = {}

class AdminAiStatsResponse(BaseModel):
    overview: PlatformAiOverview
    top_users: List[UserUsageStat]
    feature_breakdown: List[FeatureStat]
    mode_distribution: List[AiModeStat]
    latency_stats: List[ModeLatency]
    user_distribution: List[UserDistribution]
    heavy_user_impact_pct: float

# =========================================================
# 👥 USER MANAGEMENT SCHEMAS
# =========================================================
class AdminUserOverview(BaseModel):
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool
    ai_plan: str
    ai_requests_used_day: int
    ai_requests_limit_day: int
    ai_usage_current: float
    subscription_status: str
    last_login_at: Optional[str] = None
    created_at: Optional[str] = None

class AdminUserUpdate(BaseModel):
    ai_plan: Optional[str] = None
    ai_requests_limit_day: Optional[int] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    subscription_status: Optional[str] = None
