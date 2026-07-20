from pydantic import BaseModel
from typing import List, Optional, Dict, Any
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
    full_ai_requests: int = 0
    reuse_hits: int = 0
    reuse_savings: float = 0.0

class UserUsageStat(BaseModel):
    user_id: Optional[int]
    email: str
    plan: str
    requests_today: int
    requests_limit: int
    usage_month_eur: float
    usage_today_eur: float
    interactive_usage_month_eur: float = 0.0
    background_usage_month_eur: float = 0.0
    blocked_requests_month: int = 0
    blocked_estimated_cost_month_eur: float = 0.0
    revenue_month_eur: float
    profit_month_eur: float
    last_ai_activity_at: Optional[str] = None

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
    reuse_hit_rate: float = 0.0
    avg_latency_ms: float
    avg_cost_per_full_request: float
    qa_cost_month_eur: float = 0.0
    background_cost_month_eur: float = 0.0
    live_user_cost_month_eur: float = 0.0
    staging_cost_month_eur: float = 0.0
    blocked_requests_month: int = 0
    blocked_estimated_cost_month_eur: float = 0.0
    reuse_hits: int = 0
    reuse_savings_month_eur: float = 0.0
    rejection_breakdown: Optional[Dict[str, int]] = {}

class AiSourceStat(BaseModel):
    source: str
    total_requests: int
    total_cost: float
    blocked_requests: int = 0
    blocked_estimated_cost: float = 0.0
    unique_users: int
    percentage: float

class AiEntryPointStat(BaseModel):
    entry_point: str
    source: str
    total_requests: int
    total_cost: float
    avg_cost: float
    full_ai_requests: int = 0
    reuse_hits: int = 0
    reuse_savings: float = 0.0
    blocked_requests: int = 0
    blocked_estimated_cost: float = 0.0

class AiAnomaly(BaseModel):
    type: str
    severity: str
    message: str
    details: Optional[Dict[str, Any]] = None

class AdminAiStatsResponse(BaseModel):
    overview: PlatformAiOverview
    top_users: List[UserUsageStat]
    feature_breakdown: List[FeatureStat]
    source_breakdown: List[AiSourceStat]
    top_entry_points: List[AiEntryPointStat]
    mode_distribution: List[AiModeStat]
    latency_stats: List[ModeLatency]
    user_distribution: List[UserDistribution]
    heavy_user_impact_pct: float
    anomalies: Optional[List[AiAnomaly]] = []

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
    usage_month_eur: float = 0.0
    usage_today_eur: float = 0.0
    interactive_usage_month_eur: float = 0.0
    background_usage_month_eur: float = 0.0
    blocked_requests_month: int = 0
    blocked_estimated_cost_month_eur: float = 0.0
    subscription_status: str
    last_login_at: Optional[str] = None
    last_ai_activity_at: Optional[str] = None
    created_at: Optional[str] = None

class AdminUserUpdate(BaseModel):
    ai_plan: Optional[str] = None
    ai_requests_limit_day: Optional[int] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    subscription_status: Optional[str] = None

# =========================================================
# 📝 SYSTEM LOGS SCHEMAS
# =========================================================
class AdminSystemLog(BaseModel):
    id: int
    level: str
    message: str
    source: str
    endpoint: Optional[str] = None
    user_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AdminLogAnalysisResponse(BaseModel):
    root_cause: str
    what_is_broken: str
    suggested_fix: str
    severity: str # 'low', 'medium', 'high', 'critical'
    category: str # 'AUTH', 'API', 'DATABASE', 'AI', 'EXTERNAL'
    action_type: str # 'retry', 'validation_fix', 'schema_fix', 'rate_limit_fix', 'missing_data', 'unknown'
    affected_system: str
    explanation: str
