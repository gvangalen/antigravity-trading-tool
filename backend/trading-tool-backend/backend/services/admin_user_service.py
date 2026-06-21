from typing import List, Dict, Any, Optional
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import User
import logging

logger = logging.getLogger(__name__)

class AdminUserService:
    def __init__(self, db: AsyncSession):
        self.db = db

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
