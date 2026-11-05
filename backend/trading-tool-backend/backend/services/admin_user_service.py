from typing import List, Dict, Any, Optional
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import User
import logging

logger = logging.getLogger(__name__)

class AdminUserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_usage(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Aggregate a user's current-month AI usage without reading conversation content."""
        exists = (await self.db.execute(
            text("SELECT id FROM users WHERE id = :user_id"), {"user_id": user_id}
        )).scalar()
        if exists is None:
            return None

        rows = (await self.db.execute(text("""
            SELECT
                CASE
                    WHEN purpose IN ('finn_trade_review', 'finn_trade_review_question') THEN 'trade_review'
                    WHEN purpose LIKE '%report%' THEN 'reports'
                    WHEN purpose LIKE 'locale_%' THEN 'translation'
                    WHEN purpose LIKE '%strategy%' OR purpose LIKE '%setup%' THEN 'strategy_setup'
                    WHEN purpose LIKE 'finn_%' OR purpose LIKE 'chat_%' OR purpose LIKE 'assistant_%' THEN 'finn_chat'
                    WHEN purpose LIKE 'admin_%' THEN 'admin_tools'
                    ELSE 'other'
                END AS feature,
                CASE
                    WHEN request_source IN ('live_user', 'background_job', 'qa_user', 'staging_user', 'admin_tool')
                    THEN request_source ELSE 'other'
                END AS source,
                timestamp >= current_date AS today,
                COUNT(*)::int AS requests,
                COALESCE(SUM(prompt_tokens), 0)::bigint AS input_tokens,
                COALESCE(SUM(completion_tokens), 0)::bigint AS output_tokens,
                COALESCE(SUM(cost), 0) AS cost_eur
            FROM ai_usage_logs
            WHERE user_id = :user_id
              AND timestamp >= date_trunc('month', current_date)
              AND timestamp < current_date + interval '1 day'
            GROUP BY 1, 2, 3
        """), {"user_id": user_id})).mappings().all()

        def add_bucket(target: Dict[str, Dict[str, Any]], category: str, row: Any) -> None:
            bucket = target.setdefault(category, {
                "category": category, "requests": 0, "input_tokens": 0,
                "output_tokens": 0, "cost_eur": 0.0,
            })
            bucket["requests"] += int(row["requests"] or 0)
            bucket["input_tokens"] += int(row["input_tokens"] or 0)
            bucket["output_tokens"] += int(row["output_tokens"] or 0)
            bucket["cost_eur"] += float(row["cost_eur"] or 0)

        by_feature: Dict[str, Dict[str, Any]] = {}
        by_source: Dict[str, Dict[str, Any]] = {}
        total = {"requests_month": 0, "requests_today": 0,
                 "input_tokens_month": 0, "output_tokens_month": 0,
                 "cost_month_eur": 0.0, "cost_today_eur": 0.0}
        for row in rows:
            add_bucket(by_feature, row["feature"], row)
            add_bucket(by_source, row["source"], row)
            total["requests_month"] += int(row["requests"] or 0)
            total["input_tokens_month"] += int(row["input_tokens"] or 0)
            total["output_tokens_month"] += int(row["output_tokens"] or 0)
            total["cost_month_eur"] += float(row["cost_eur"] or 0)
            if row["today"]:
                total["requests_today"] += int(row["requests"] or 0)
                total["cost_today_eur"] += float(row["cost_eur"] or 0)
        return {
            "user_id": user_id, **total,
            "by_feature": sorted(by_feature.values(), key=lambda item: item["cost_eur"], reverse=True),
            "by_source": sorted(by_source.values(), key=lambda item: item["cost_eur"], reverse=True),
        }

    async def get_users_page(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str = "",
        plan: str = "all",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return a bounded user page with usage aggregated only for those users."""
        filters = ["(:search = '' OR u.email ILIKE :search OR u.first_name ILIKE :search)"]
        if plan != "all":
            filters.append("u.ai_plan = :plan")
        if user_id is not None:
            filters.append("u.id = :user_id")
        where_clause = " AND ".join(filters)
        params = {
            "search": f"%{search.strip()}%" if search.strip() else "",
            "plan": plan,
            "user_id": user_id,
            "offset": offset,
            "limit": limit,
        }
        total = (await self.db.execute(
            text(f"SELECT COUNT(*) FROM users u WHERE {where_clause}"), params
        )).scalar() or 0
        rows = (await self.db.execute(text(f"""
            SELECT
                u.id, u.email, u.first_name, u.last_name, u.role, u.is_active,
                u.ai_plan, u.ai_requests_used_day, u.ai_requests_limit_day,
                u.ai_usage_current, u.subscription_status, u.last_login_at,
                u.created_at,
                COALESCE(usage.usage_month_eur, 0) AS usage_month_eur,
                COALESCE(usage.usage_today_eur, 0) AS usage_today_eur,
                COALESCE(usage.background_usage_month_eur, 0) AS background_usage_month_eur,
                COALESCE(usage.interactive_usage_month_eur, 0) AS interactive_usage_month_eur,
                COALESCE(usage.blocked_requests_month, 0) AS blocked_requests_month,
                COALESCE(usage.blocked_estimated_cost_month_eur, 0) AS blocked_estimated_cost_month_eur,
                usage.last_ai_activity_at
            FROM (
                SELECT * FROM users u
                WHERE {where_clause}
                ORDER BY u.created_at DESC NULLS LAST, u.id DESC
                LIMIT :limit OFFSET :offset
            ) u
            LEFT JOIN LATERAL (
                SELECT
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= date_trunc('month', current_date)), 0) AS usage_month_eur,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= current_date), 0) AS usage_today_eur,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= date_trunc('month', current_date) AND l.request_source = 'background_job'), 0) AS background_usage_month_eur,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= date_trunc('month', current_date) AND l.request_source IN ('live_user', 'staging_user', 'qa_user', 'admin_tool')), 0) AS interactive_usage_month_eur,
                    COUNT(*) FILTER (WHERE l.timestamp >= date_trunc('month', current_date) AND l.status = 'quota_blocked') AS blocked_requests_month,
                    COALESCE(SUM(l.estimated_cost_if_full) FILTER (WHERE l.timestamp >= date_trunc('month', current_date) AND l.status = 'quota_blocked'), 0) AS blocked_estimated_cost_month_eur,
                    MAX(l.timestamp) AS last_ai_activity_at
                FROM ai_usage_logs l
                WHERE l.user_id = u.id
            ) usage ON TRUE
            ORDER BY u.created_at DESC NULLS LAST, u.id DESC
        """), params)).mappings().all()

        items = []
        for row in rows:
            items.append({
                "id": row["id"],
                "email": row["email"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "role": row["role"],
                "is_active": row["is_active"],
                "ai_plan": row["ai_plan"],
                "ai_requests_used_day": row["ai_requests_used_day"] or 0,
                "ai_requests_limit_day": row["ai_requests_limit_day"] or 0,
                "ai_usage_current": float(row["ai_usage_current"] or 0),
                "usage_month_eur": float(row["usage_month_eur"] or 0),
                "usage_today_eur": float(row["usage_today_eur"] or 0),
                "background_usage_month_eur": float(row["background_usage_month_eur"] or 0),
                "interactive_usage_month_eur": float(row["interactive_usage_month_eur"] or 0),
                "blocked_requests_month": int(row["blocked_requests_month"] or 0),
                "blocked_estimated_cost_month_eur": float(row["blocked_estimated_cost_month_eur"] or 0),
                "subscription_status": row["subscription_status"] or "active",
                "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None,
                "last_ai_activity_at": row["last_ai_activity_at"].isoformat() if row["last_ai_activity_at"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            })
        return {"items": items, "total": int(total), "offset": offset, "limit": limit}

    async def get_all_users_overview(self) -> List[Dict[str, Any]]:
        """
        Haalt een lijst op van alle gebruikers met hun AI-statistieken en status.
        """
        try:
            stmt = text("""
                SELECT
                    u.id,
                    u.email,
                    u.first_name,
                    u.last_name,
                    u.role,
                    u.is_active,
                    u.ai_plan,
                    COALESCE(u.ai_requests_used_day, 0) as ai_requests_used_day,
                    COALESCE(u.ai_requests_limit_day, 0) as ai_requests_limit_day,
                    COALESCE(u.ai_usage_current, 0) as ai_usage_current,
                    u.subscription_status,
                    u.last_login_at,
                    u.created_at,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= date_trunc('month', current_date)), 0) as usage_month_eur,
                    COALESCE(SUM(l.cost) FILTER (WHERE l.timestamp >= current_date), 0) as usage_today_eur,
                    COALESCE(SUM(l.cost) FILTER (
                        WHERE l.timestamp >= date_trunc('month', current_date)
                        AND COALESCE(l.request_source, 'unclassified') = 'background_job'
                    ), 0) as background_usage_month_eur,
                    COALESCE(SUM(l.cost) FILTER (
                        WHERE l.timestamp >= date_trunc('month', current_date)
                        AND COALESCE(l.request_source, 'unclassified') IN ('live_user', 'staging_user', 'qa_user', 'admin_tool')
                    ), 0) as interactive_usage_month_eur,
                    COALESCE(SUM(CASE WHEN l.timestamp >= date_trunc('month', current_date) AND l.status = 'quota_blocked' THEN 1 ELSE 0 END), 0) as blocked_requests_month,
                    COALESCE(SUM(CASE WHEN l.timestamp >= date_trunc('month', current_date) AND l.status = 'quota_blocked' THEN COALESCE(l.estimated_cost_if_full, 0) ELSE 0 END), 0) as blocked_estimated_cost_month_eur,
                    MAX(l.timestamp) as last_ai_activity_at
                FROM users u
                LEFT JOIN ai_usage_logs l ON l.user_id = u.id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            """)
            result = await self.db.execute(stmt)
            users = result.mappings().all()

            user_list = []
            for u in users:
                user_list.append({
                    "id": u["id"],
                    "email": u["email"],
                    "first_name": u["first_name"],
                    "last_name": u["last_name"],
                    "role": u["role"],
                    "is_active": u["is_active"],
                    "ai_plan": u["ai_plan"],
                    "ai_requests_used_day": u["ai_requests_used_day"] or 0,
                    "ai_requests_limit_day": u["ai_requests_limit_day"] or 0,
                    "ai_usage_current": float(u["ai_usage_current"] or 0),
                    "usage_month_eur": float(u["usage_month_eur"] or 0),
                    "usage_today_eur": float(u["usage_today_eur"] or 0),
                    "interactive_usage_month_eur": float(u["interactive_usage_month_eur"] or 0),
                    "background_usage_month_eur": float(u["background_usage_month_eur"] or 0),
                    "blocked_requests_month": int(u["blocked_requests_month"] or 0),
                    "blocked_estimated_cost_month_eur": float(u["blocked_estimated_cost_month_eur"] or 0),
                    "subscription_status": u["subscription_status"] or "active",
                    "last_login_at": u["last_login_at"].isoformat() if u["last_login_at"] else None,
                    "last_ai_activity_at": u["last_ai_activity_at"].isoformat() if u["last_ai_activity_at"] else None,
                    "created_at": u["created_at"].isoformat() if u["created_at"] else None
                })
            
            return user_list

        except Exception as e:
            logger.error(f"❌ Error in get_all_users_overview: {e}", exc_info=True)
            raise

    async def update_user_admin(self, user_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update specifieke velden van een gebruiker door een admin.
        Toegestane velden: ai_plan, ai_requests_limit_day, is_active, role, subscription_status.
        """
        try:
            allowed_fields = [
                "ai_plan", 
                "ai_requests_limit_day", 
                "is_active", 
                "role", 
                "subscription_status"
            ]
            
            filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
            
            if not filtered_updates:
                return None

            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(**filtered_updates)
                .returning(User)
            )
            
            result = await self.db.execute(stmt)
            updated_user = result.scalars().first()
            
            if updated_user:
                await self.db.commit()
                return {
                    "id": updated_user.id,
                    "email": updated_user.email,
                    "ai_plan": updated_user.ai_plan,
                    "is_active": updated_user.is_active,
                    "subscription_status": updated_user.subscription_status
                }
            
            return None

        except Exception as e:
            logger.error(f"❌ Error in update_user_admin: {e}", exc_info=True)
            await self.db.rollback()
            raise
