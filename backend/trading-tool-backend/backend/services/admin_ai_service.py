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
                COALESCE(SUM(cost) FILTER (WHERE status = 'full_ai'), 0) / NULLIF(COUNT(*) FILTER (WHERE status = 'full_ai'), 0) as avg_cost_full,
                COALESCE(SUM(cost) FILTER (WHERE COALESCE(request_source, 'unclassified') = 'qa_user'), 0) as qa_cost_month,
                COALESCE(SUM(cost) FILTER (WHERE COALESCE(request_source, 'unclassified') = 'background_job'), 0) as background_cost_month,
                COALESCE(SUM(cost) FILTER (WHERE COALESCE(request_source, 'unclassified') = 'live_user'), 0) as live_user_cost_month,
                COALESCE(SUM(cost) FILTER (WHERE COALESCE(request_source, 'unclassified') = 'staging_user'), 0) as staging_cost_month,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN 1 ELSE 0 END), 0) as blocked_requests_month,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN COALESCE(estimated_cost_if_full, 0) ELSE 0 END), 0) as blocked_estimated_cost_month
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
        """)
        
        res_logs = await self.db.execute(stmt_logs)
        logs_stats = res_logs.mappings().first()
        total_logs = (logs_stats['total_requests'] or 0) or 1
        
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
                COALESCE(SUM(CASE WHEN l.timestamp >= current_date THEN l.cost ELSE 0 END), 0) as usage_today_eur,
                COALESCE(SUM(CASE WHEN COALESCE(l.request_source, 'unclassified') = 'background_job' THEN l.cost ELSE 0 END), 0) as background_usage_month_eur,
                COALESCE(SUM(CASE WHEN COALESCE(l.request_source, 'unclassified') IN ('live_user', 'staging_user', 'qa_user', 'admin_tool') THEN l.cost ELSE 0 END), 0) as interactive_usage_month_eur,
                COALESCE(SUM(CASE WHEN l.status = 'quota_blocked' THEN 1 ELSE 0 END), 0) as blocked_requests_month,
                COALESCE(SUM(CASE WHEN l.status = 'quota_blocked' THEN COALESCE(l.estimated_cost_if_full, 0) ELSE 0 END), 0) as blocked_estimated_cost_month_eur,
                MAX(l.timestamp) as last_ai_activity_at
            FROM users u
            LEFT JOIN ai_usage_logs l ON l.user_id = u.id AND l.timestamp >= date_trunc('month', current_date)
            WHERE u.is_active = TRUE
            GROUP BY u.id
            ORDER BY (COALESCE(SUM(l.cost), 0) + COALESCE(SUM(CASE WHEN l.status = 'quota_blocked' THEN COALESCE(l.estimated_cost_if_full, 0) ELSE 0 END), 0)) DESC, MAX(l.timestamp) DESC
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
                "interactive_usage_month_eur": float(row['interactive_usage_month_eur'] or 0),
                "background_usage_month_eur": float(row['background_usage_month_eur'] or 0),
                "blocked_requests_month": int(row['blocked_requests_month'] or 0),
                "blocked_estimated_cost_month_eur": float(row['blocked_estimated_cost_month_eur'] or 0),
                "revenue_month_eur": rev,
                "profit_month_eur": rev - u_cost,
                "last_ai_activity_at": row['last_ai_activity_at'].isoformat() if row['last_ai_activity_at'] else None,
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

        stmt_sources = text("""
            SELECT
                COALESCE(request_source, 'unclassified') as source,
                COUNT(*)::int as total_requests,
                COALESCE(SUM(cost), 0) as total_cost,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN 1 ELSE 0 END), 0)::int as blocked_requests,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN COALESCE(estimated_cost_if_full, 0) ELSE 0 END), 0) as blocked_estimated_cost,
                COUNT(DISTINCT user_id)::int as unique_users
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
            GROUP BY COALESCE(request_source, 'unclassified')
            ORDER BY total_cost DESC, blocked_estimated_cost DESC, total_requests DESC
        """)
        res_sources = await self.db.execute(stmt_sources)
        source_breakdown = []
        for row in res_sources.mappings():
            source_breakdown.append({
                "source": row["source"],
                "total_requests": row["total_requests"] or 0,
                "total_cost": float(row["total_cost"] or 0),
                "blocked_requests": row["blocked_requests"] or 0,
                "blocked_estimated_cost": float(row["blocked_estimated_cost"] or 0),
                "unique_users": row["unique_users"] or 0,
                "percentage": (float(row["total_requests"] or 0) / total_logs) * 100,
            })

        stmt_entry_points = text("""
            SELECT
                COALESCE(entry_point, 'unclassified') as entry_point,
                COALESCE(request_source, 'unclassified') as source,
                COUNT(*)::int as total_requests,
                COALESCE(SUM(cost), 0) as total_cost,
                COALESCE(AVG(cost), 0) as avg_cost,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN 1 ELSE 0 END), 0)::int as blocked_requests,
                COALESCE(SUM(CASE WHEN status = 'quota_blocked' THEN COALESCE(estimated_cost_if_full, 0) ELSE 0 END), 0) as blocked_estimated_cost
            FROM ai_usage_logs
            WHERE timestamp >= date_trunc('month', current_date)
            GROUP BY COALESCE(entry_point, 'unclassified'), COALESCE(request_source, 'unclassified')
            ORDER BY total_cost DESC, blocked_estimated_cost DESC, total_requests DESC
            LIMIT 12
        """)
        res_entry_points = await self.db.execute(stmt_entry_points)
        top_entry_points = []
        for row in res_entry_points.mappings():
            top_entry_points.append({
                "entry_point": row["entry_point"],
                "source": row["source"],
                "total_requests": row["total_requests"] or 0,
                "total_cost": float(row["total_cost"] or 0),
                "avg_cost": float(row["avg_cost"] or 0),
                "blocked_requests": row["blocked_requests"] or 0,
                "blocked_estimated_cost": float(row["blocked_estimated_cost"] or 0),
            })

        stmt_distribution = text("""
            WITH user_costs AS (
                SELECT
                    u.id,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= date_trunc('month', current_date)), 0) as usage_month_eur
                FROM users u
                LEFT JOIN ai_usage_logs l ON l.user_id = u.id
                WHERE u.is_active = TRUE
                GROUP BY u.id
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN usage_month_eur < 1 THEN '<1'
                        WHEN usage_month_eur < 5 THEN '1-5'
                        WHEN usage_month_eur < 25 THEN '5-25'
                        ELSE '25+'
                    END AS bucket
                FROM user_costs
            )
            SELECT
                bucket,
                COUNT(*)::int AS count
            FROM bucketed
            GROUP BY bucket
            ORDER BY
                CASE bucket
                    WHEN '<1' THEN 1
                    WHEN '1-5' THEN 2
                    WHEN '5-25' THEN 3
                    ELSE 4
                END
        """)
        res_distribution = await self.db.execute(stmt_distribution)
        user_distribution = [
            {"bucket": row["bucket"], "count": row["count"] or 0}
            for row in res_distribution.mappings()
        ]

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

        # 6. Real-time Anomaly Scanning (Fase 3)
        anomalies = []
        
        # A. Budget violations
        stmt_budget = text("""
            SELECT id, email, ai_plan, ai_requests_used_day, ai_requests_limit_day
            FROM users
            WHERE is_active = TRUE AND ai_requests_used_day >= ai_requests_limit_day AND ai_requests_limit_day > 0
        """)
        res_budget = await self.db.execute(stmt_budget)
        for row in res_budget.mappings():
            anomalies.append({
                "type": "budget_breach",
                "severity": "critical",
                "message": f"Gebruiker {row['email']} heeft de dagelijkse AI limiet overschreden: {row['ai_requests_used_day']}/{row['ai_requests_limit_day']} requests.",
                "details": {
                    "user_id": row["id"],
                    "email": row["email"],
                    "used": row["ai_requests_used_day"],
                    "limit": row["ai_requests_limit_day"]
                }
            })
            
        # B. Parser Recovery Anomalies (Incomplete streams or JSON structure failure recovered by Hardened Parser)
        stmt_parser = text("""
            SELECT l.id, l.user_id, u.email, l.trace_id, l.timestamp, l.response_time_ms
            FROM ai_usage_logs l
            LEFT JOIN users u ON u.id = l.user_id
            WHERE l.parser_recovery_triggered = TRUE AND l.timestamp >= date_trunc('day', current_date)
            ORDER BY l.timestamp DESC
            LIMIT 10
        """)
        res_parser = await self.db.execute(stmt_parser)
        for row in res_parser.mappings():
            anomalies.append({
                "type": "parser_recovery",
                "severity": "warning",
                "message": f"Hardened Parser heeft een incomplete/corrupte JSON stream hersteld voor trace {row['trace_id'][:12]}...",
                "details": {
                    "log_id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "trace_id": row["trace_id"],
                    "response_time_ms": row["response_time_ms"]
                }
            })
            
        # C. Hallucination Risks (Confidence score below 50% or reasoning alerts)
        stmt_hallucination = text("""
            SELECT l.id, l.user_id, u.email, l.trace_id, l.confidence_score, l.timestamp
            FROM ai_usage_logs l
            LEFT JOIN users u ON u.id = l.user_id
            WHERE l.confidence_score IS NOT NULL AND l.confidence_score < 50.0 AND l.timestamp >= date_trunc('day', current_date)
            ORDER BY l.timestamp DESC
            LIMIT 10
        """)
        res_hallucination = await self.db.execute(stmt_hallucination)
        for row in res_hallucination.mappings():
            anomalies.append({
                "type": "hallucination_risk",
                "severity": "high",
                "message": f"Verhoogd risico op AI hallucinatie gedetecteerd (Confidence score: {row['confidence_score']:.1f}%) op trace {row['trace_id'][:12]}...",
                "details": {
                    "log_id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "trace_id": row["trace_id"],
                    "confidence_score": float(row["confidence_score"])
                }
            })
            
        # D. Safety Guardrail Triggers (Deterministic post-processing interventions)
        stmt_safety = text("""
            SELECT l.id, l.user_id, u.email, l.trace_id, l.timestamp
            FROM ai_usage_logs l
            LEFT JOIN users u ON u.id = l.user_id
            WHERE l.safety_guardrail_triggered = TRUE AND l.timestamp >= date_trunc('day', current_date)
            ORDER BY l.timestamp DESC
            LIMIT 10
        """)
        res_safety = await self.db.execute(stmt_safety)
        for row in res_safety.mappings():
            anomalies.append({
                "type": "safety_guardrail_trigger",
                "severity": "warning",
                "message": f"Deterministische Safety Guardrail is getriggerd op trace {row['trace_id'][:12]} om de output te beveiligen.",
                "details": {
                    "log_id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "trace_id": row["trace_id"]
                }
            })

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
                "qa_cost_month_eur": float(logs_stats['qa_cost_month'] or 0),
                "background_cost_month_eur": float(logs_stats['background_cost_month'] or 0),
                "live_user_cost_month_eur": float(logs_stats['live_user_cost_month'] or 0),
                "staging_cost_month_eur": float(logs_stats['staging_cost_month'] or 0),
                "blocked_requests_month": int(logs_stats['blocked_requests_month'] or 0),
                "blocked_estimated_cost_month_eur": float(logs_stats['blocked_estimated_cost_month'] or 0),
                "exact_hits": int(logs_stats['exact_hits'] or 0),
                "semantic_hits": int(logs_stats['semantic_hits'] or 0),
                "rejection_breakdown": rejection_breakdown
            },
            "top_users": heavy_users,
            "feature_breakdown": feature_breakdown,
            "source_breakdown": source_breakdown,
            "top_entry_points": top_entry_points,
            "mode_distribution": mode_distribution,
            "latency_stats": latency_stats,
            "user_distribution": user_distribution,
            "heavy_user_impact_pct": float(heavy_user_impact),
            "anomalies": anomalies
        }
