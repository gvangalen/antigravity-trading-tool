from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from backend.infrastructure.models import AiCategoryInsight, Setup, DailySetupScore
from datetime import date
from typing import List, Dict, Any, Optional

class ScoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_active_setups(self, user_id: int) -> List[Dict[str, Any]]:
        today = date.today()
        stmt = text("""
            SELECT DISTINCT ON (s.id)
                   s.id,
                   s.name,
                   COALESCE(s.symbol, 'BTC') AS symbol,
                   COALESCE(s.timeframe, '1D') AS timeframe,
                   COALESCE(s.explanation, '') AS explanation,
                   s.created_at AS timestamp,
                   COALESCE(ds.score, 0) AS score,
                   COALESCE(ds.active, false) AS is_active,
                   COALESCE(ds.breakdown, '{}'::jsonb) AS breakdown
            FROM setups s
            LEFT JOIN daily_setup_scores ds
                ON ds.setup_id = s.id
                AND ds.report_date = :today
            WHERE s.user_id = :user_id
            ORDER BY s.id, ds.report_date DESC
            LIMIT 100
        """)
        
        result = await self.db.execute(stmt, {"today": today, "user_id": user_id})
        
        # Build dictionary from rows
        mapped = []
        for row in result.mappings():
            mapped.append(dict(row))
        return mapped

    async def get_master_score(self, user_id: int) -> Optional[AiCategoryInsight]:
        stmt = select(AiCategoryInsight).where(
            AiCategoryInsight.user_id == user_id,
            AiCategoryInsight.category == 'master'
        ).order_by(AiCategoryInsight.date.desc()).limit(1)
        
        result = await self.db.execute(stmt)
        return result.scalars().first()
