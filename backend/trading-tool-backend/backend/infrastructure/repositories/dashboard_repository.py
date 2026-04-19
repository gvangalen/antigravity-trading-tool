from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class DashboardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_market_data(self, user_id: int, symbol: str = 'BTC') -> List[dict]:
        query = text("""
            SELECT DISTINCT ON (symbol)
                symbol, price, volume, change_24h, timestamp
            FROM market_data
            WHERE user_id = :user_id AND symbol = :symbol
            ORDER BY symbol, timestamp DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id, "symbol": symbol})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_latest_technical_data(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT LOWER(indicator) AS indicator, value, score, timestamp
            FROM technical_indicators
            WHERE user_id = :user_id
            ORDER BY indicator, timestamp DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_latest_macro_data(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT DISTINCT ON (name)
                name, value, trend, interpretation, action, score, timestamp
            FROM macro_data
            WHERE user_id = :user_id
            ORDER BY name, timestamp DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_user_setups_summary(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT DISTINCT ON (name)
                name, created_at AS timestamp
            FROM setups
            WHERE user_id = :user_id
            ORDER BY name, created_at DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_latest_trading_advice(self, user_id: int, symbol: str) -> Optional[dict]:
        query = text("""
            SELECT symbol, advice, explanation, timestamp
            FROM trading_advice
            WHERE symbol = :symbol AND user_id = :user_id
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id, "symbol": symbol})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_top_setups(self, user_id: int, limit: int = 5) -> List[dict]:
        query = text("""
            SELECT name, score, timeframe, symbol, explanation, timestamp
            FROM strategies
            WHERE user_id = :user_id AND data->>'score' IS NOT NULL
            ORDER BY CAST(data->>'score' AS FLOAT) DESC
            LIMIT :limit
        """)
        result = await self.session.execute(query, {"user_id": user_id, "limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]

    async def check_health(self) -> bool:
        try:
            result = await self.session.execute(text("SELECT 1"))
            return result.scalar() == 1
        except Exception:
            return False
