from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
from datetime import date, datetime
from decimal import Decimal


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

class ConversationStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = text("""
            SELECT current_flow, asset, slots, updated_at
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
                "slots": slots or {},
                "updated_at": row["updated_at"],
            }
        return None

    async def save_state(self, user_id: int, current_flow: Optional[str], asset: Optional[str], slots: Dict[str, Any]):
        slots_json = json.dumps(slots, default=_json_default) if isinstance(slots, dict) else "{}"

        upsert_query = text("""
            INSERT INTO conversation_state (user_id, current_flow, asset, slots, updated_at)
            VALUES (:user_id, :current_flow, :asset, CAST(:slots AS jsonb), :now)
            ON CONFLICT (user_id) DO UPDATE SET
                current_flow = EXCLUDED.current_flow,
                asset = EXCLUDED.asset,
                slots = EXCLUDED.slots,
                updated_at = EXCLUDED.updated_at
        """)
        await self.session.execute(upsert_query, {
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
