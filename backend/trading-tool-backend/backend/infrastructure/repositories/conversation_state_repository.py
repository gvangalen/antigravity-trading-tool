from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
from datetime import datetime

class ConversationStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = text("""
            SELECT current_flow, asset, slots
            FROM conversation_state
            WHERE user_id = :user_id
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        row = result.mappings().first()
        if row:
            slots = row["slots"]
            if isinstance(slots, str):
                slots = json.loads(slots)
            return {
                "current_flow": row["current_flow"],
                "asset": row["asset"],
                "slots": slots or {}
            }
        return None

    async def save_state(self, user_id: int, current_flow: Optional[str], asset: Optional[str], slots: Dict[str, Any]):
        # Check if row exists
        check_query = text("SELECT id FROM conversation_state WHERE user_id = :user_id")
        result = await self.session.execute(check_query, {"user_id": user_id})
        exists = result.fetchone() is not None

        slots_json = json.dumps(slots) if isinstance(slots, dict) else "{}"

        if exists:
            update_query = text("""
                UPDATE conversation_state
                SET current_flow = :current_flow,
                    asset = :asset,
                    slots = :slots,
                    updated_at = :now
                WHERE user_id = :user_id
            """)
            await self.session.execute(update_query, {
                "user_id": user_id,
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots_json,
                "now": datetime.utcnow()
            })
        else:
            insert_query = text("""
                INSERT INTO conversation_state (user_id, current_flow, asset, slots, updated_at)
                VALUES (:user_id, :current_flow, :asset, :slots, :now)
            """)
            await self.session.execute(insert_query, {
                "user_id": user_id,
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots_json,
                "now": datetime.utcnow()
            })
        await self.session.commit()

    async def clear_state(self, user_id: int):
        query = text("""
            DELETE FROM conversation_state
            WHERE user_id = :user_id
        """)
        await self.session.execute(query, {"user_id": user_id})
        await self.session.commit()
