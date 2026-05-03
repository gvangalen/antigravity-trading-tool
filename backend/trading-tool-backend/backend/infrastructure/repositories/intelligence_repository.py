from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.infrastructure.models import DailyScore

class IntelligenceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_latest_daily_scores(self, user_id: int, symbol: str = "BTC") -> Optional[DailyScore]:
        stmt = select(DailyScore).where(
            DailyScore.user_id == user_id,
            DailyScore.symbol == symbol
        ).order_by(DailyScore.report_date.desc()).limit(1)
        
        result = await self.db.execute(stmt)
        return result.scalars().first()
