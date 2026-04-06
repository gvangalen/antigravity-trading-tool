from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, List

class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_insight_by_category(self, user_id: int, category: str) -> Optional[dict]:
        query = text("""
            SELECT avg_score, trend, bias, risk, summary, top_signals, date, created_at
            FROM ai_category_insights
            WHERE category=:category AND user_id=:user_id
            ORDER BY date DESC, created_at DESC
            LIMIT 1
        """)
        result = await self.session.execute(query, {"category": category, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_reflections_by_category(self, user_id: int, category: str) -> List[dict]:
        query = text("""
            SELECT DISTINCT ON (indicator)
                   indicator,
                   raw_score,
                   ai_score,
                   compliance,
                   comment,
                   recommendation,
                   date,
                   timestamp
            FROM ai_reflections
            WHERE category = :category
              AND user_id = :user_id
              AND date = CURRENT_DATE
            ORDER BY indicator, timestamp DESC;
        """)
        result = await self.session.execute(query, {"category": category, "user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]
