import logging
from typing import List, Dict, Any
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import User, AiUsageLog

logger = logging.getLogger(__name__)

PLAN_REVENUE = {
    "free": 0.0,
    "basis": 89.0,
    "pro": 149.0
}

class AdminAiService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_ai_stats_overview(self) -> Dict[str, Any]:
        """
        Aggregeert globale AI statistieken voor de admin met robuuste null-handling.
        """
        # 1. Platform-wide totals (Current month)
        stmt_logs = text("""
            SELECT 
                COUNT(*) as total_requests,
                COALESCE(SUM(cost), 0) as total_cost,
                COALESCE(SUM(estimated_cost_if_full) FILTER (WHERE status = 'cache_exact'), 0) as exact_savings,
                COALESCE(SUM(estimated_cost_if_full) FILTER (WHERE status = 'cache_semantic'), 0) as semantic_savings,
                COALESCE(SUM(CASE WHEN user_id IS NULL THEN cost ELSE 0 END), 0) as platform_overhead,
                COALESCE(SUM(CASE WHEN status = 'cache_exact' THEN 1 ELSE 0 END), 0) as exact_hits,
                COALESCE(SUM(CASE WHEN status = 'cache_semantic' THEN 1 ELSE 0 END), 0) as semantic_hits,
                COALESCE(AVG(response_time_ms), 0) as avg_latency,
                COALESCE(SUM(cost) FILTER (WHERE status = 'full_ai'), 0) / NULLIF(COUNT(*) FILTER (WHERE status = 'full_ai'), 0) as avg_cost_full
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
        """)
        
        res_logs = await self.db.execute(stmt_logs)
        logs_stats = res_logs.mappings().first()
        
        # 2. Revenue totals from active users
        stmt_users = text("SELECT ai_plan, count(*) as count FROM users WHERE is_active = TRUE GROUP BY ai_plan")
        res_users = await self.db.execute(stmt_users)
        user_counts = res_users.mappings().all()
        
        total_revenue = 0.0
        for row in user_counts:
            plan = row['ai_plan']
            total_revenue += PLAN_REVENUE.get(plan, 0.0) * (row['count'] or 0)
            
        # 3. Aggregatie Users
        stmt_heavy_users = text(f"""
            SELECT 
                u.id as user_id, 
                u.email, 
                u.ai_plan as plan, 
                COALESCE(u.ai_requests_used_day, 0) as requests_today, 
                COALESCE(u.ai_requests_limit_day, 0) as requests_limit,
                COALESCE(SUM(l.cost), 0) as usage_month_eur,
                COALESCE(SUM(CASE WHEN l.timestamp >= current_date THEN l.cost ELSE 0 END), 0) as usage_today_eur
            FROM users u
            LEFT JOIN ai_usage_logs l ON l.user_id = u.id AND l.timestamp >= date_trunc('month', current_date)
            WHERE u.is_active = TRUE
            GROUP BY u.id
            ORDER BY usage_month_eur DESC
            LIMIT 10
        """)
        res_heavy = await self.db.execute(stmt_heavy_users)
        heavy_users = []
        top_10_cost = 0.0
        for row in res_heavy.mappings():
            rev = PLAN_REVENUE.get(row['plan'], 0.0)
            u_cost = float(row['usage_month_eur'] or 0)
            top_10_cost += u_cost
            heavy_users.append({
                "user_id": row['user_id'],
                "email": row['email'],
                "plan": row['plan'],
                "requests_today": row['requests_today'] or 0,
                "requests_limit": row['requests_limit'] or 0,
                "usage_month_eur": u_cost,
                "usage_today_eur": float(row['usage_today_eur'] or 0),
                "revenue_month_eur": rev,
                "profit_month_eur": rev - u_cost
            })

        # 4. Feature Breakdown
        stmt_features = text("""
            SELECT 
                purpose, 
                count(*) as total_requests, 
                COALESCE(sum(cost), 0) as total_cost
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
            GROUP BY purpose
            ORDER BY total_cost DESC
        """)
        res_features = await self.db.execute(stmt_features)
        feature_breakdown = []
        for row in res_features.mappings():
            feature_breakdown.append({
                "purpose": row['purpose'],
                "total_requests": row['total_requests'] or 0,
                "total_cost": float(row['total_cost'] or 0),
                "avg_cost": float(row['total_cost'] or 0) / (row['total_requests'] or 1) if row['total_requests'] else 0
            })

        # 5. Mode Distribution
        stmt_modes = text("""
            SELECT 
                status as mode, 
                count(*) as count,
                COALESCE(AVG(response_time_ms), 0) as avg_ms
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
            GROUP BY status
        """)
        res_modes = await self.db.execute(stmt_modes)
        total_logs = (logs_stats['total_requests'] or 0) or 1
        mode_distribution = []
        latency_stats = []
        for row in res_modes.mappings():
            mode_distribution.append({
                "mode": row['mode'],
                "count": row['count'] or 0,
                "percentage": (float(row['count'] or 0) / total_logs) * 100
            })
            latency_stats.append({
                "mode": row['mode'],
                "avg_ms": float(row['avg_ms'] or 0)
            })

        total_cost_month = float(logs_stats['total_cost'] or 0)
        heavy_user_impact = (top_10_cost / (total_cost_month or 1) * 100) if total_cost_month > 0 else 0

        # ... (rest of logic same but with safe floats)
        stmt_rejections = text("""
            SELECT rejected_reason, count(*) as count 
            FROM ai_usage_logs 
            WHERE rejected_reason IS NOT NULL AND timestamp >= date_trunc('month', current_date)
            GROUP BY rejected_reason
        """)
        res_rejections = await self.db.execute(stmt_rejections)
        rejection_breakdown = {r["rejected_reason"]: r["count"] for r in res_rejections.mappings()}

        return {
            "overview": {
                "total_requests_today": sum(u['requests_today'] for u in heavy_users),
                "total_requests_month": logs_stats['total_requests'] or 0,
                "total_cost_month_eur": total_cost_month,
                "total_revenue_month_eur": total_revenue,
                "total_profit_month_eur": total_revenue - total_cost_month,
                "total_savings_month_eur": float((logs_stats['exact_savings'] or 0) + (logs_stats['semantic_savings'] or 0)),
                "platform_overhead_eur": float(logs_stats['platform_overhead'] or 0),
                "cache_hit_rate": ((float(logs_stats['exact_hits'] or 0) + float(logs_stats['semantic_hits'] or 0)) / total_logs) * 100,
                "avg_latency_ms": float(logs_stats['avg_latency'] or 0),
                "avg_cost_per_full_request": float(logs_stats['avg_cost_full'] or 0),
                "exact_hits": int(logs_stats['exact_hits'] or 0),
                "semantic_hits": int(logs_stats['semantic_hits'] or 0),
                "rejection_breakdown": rejection_breakdown
            },
            "top_users": heavy_users,
            "feature_breakdown": feature_breakdown,
            "mode_distribution": mode_distribution,
            "latency_stats": latency_stats,
            "user_distribution": [], # we can add if needed
            "heavy_user_impact_pct": float(heavy_user_impact)
        }
