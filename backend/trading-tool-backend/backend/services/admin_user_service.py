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
            # We joinen met ai_usage_logs om de totale kosten per gebruiker te zien (indien gewenst)
            # Maar voor een simpel overzicht pakken we eerst de data uit de User tabel zelf.
            stmt = select(User).order_by(User.created_at.desc())
            result = await self.db.execute(stmt)
            users = result.scalars().all()

            user_list = []
            for u in users:
                user_list.append({
                    "id": u.id,
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "role": u.role,
                    "is_active": u.is_active,
                    "ai_plan": u.ai_plan,
                    "ai_requests_used_day": u.ai_requests_used_day or 0,
                    "ai_requests_limit_day": u.ai_requests_limit_day or 0,
                    "ai_usage_current": float(u.ai_usage_current or 0),
                    "subscription_status": u.subscription_status or "active",
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                    "created_at": u.created_at.isoformat() if u.created_at else None
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
