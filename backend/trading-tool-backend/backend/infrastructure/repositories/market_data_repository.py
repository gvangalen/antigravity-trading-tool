from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, desc, delete, func
from typing import List, Optional, Sequence
import datetime

from backend.infrastructure.models import (
    MarketData, MarketDataIndicator, Indicator, MarketIndicatorRule,
    MarketData7D, MarketForwardReturn
)

class MarketDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================
    # GLOBAAL: Market Data (BTC prijs etc)
    # =========================================================
    async def get_latest_market_data(self, symbol: str) -> Optional[MarketData]:
        stmt = (
            select(MarketData)
            .where(MarketData.symbol == symbol)
            .order_by(desc(MarketData.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_snapshot(self, symbol: str = 'BTC') -> Optional[MarketData]:
        return await self.get_latest_market_data(symbol.upper())

    async def get_recent_market_data(self, min_timestamp) -> Sequence[MarketData]:
        stmt = (
            select(MarketData)
            .where(MarketData.timestamp >= min_timestamp)
            .order_by(desc(MarketData.timestamp))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # =========================================================
    # GLOBAL: Config (Indicators & Rules)
    # =========================================================
    async def get_global_indicators(self, category: str = 'market') -> Sequence[Indicator]:
        stmt = (
            select(Indicator)
            .where(Indicator.category == category)
            .order_by(Indicator.display_name.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_indicator_rules(self, name: str, user_id: int) -> Sequence[MarketIndicatorRule]:
        # User-specific eerst
        stmt = (
            select(MarketIndicatorRule)
            .where(MarketIndicatorRule.indicator == name)
            .where(MarketIndicatorRule.user_id == user_id)
            .order_by(MarketIndicatorRule.range_min.asc())
        )
        result = await self.session.execute(stmt)
        rules = result.scalars().all()

        if not rules:
            # Fallback op globals (user_id is None in db)
            stmt = (
                select(MarketIndicatorRule)
                .where(MarketIndicatorRule.indicator == name)
                .where(MarketIndicatorRule.user_id == None)
                .order_by(MarketIndicatorRule.range_min.asc())
            )
            result = await self.session.execute(stmt)
            rules = result.scalars().all()

        return rules

    # =========================================================
    # USER: Market Indicators
    # =========================================================
    async def check_indicator_exists(self, name: str, user_id: int, symbol: str) -> bool:
        stmt = (
            select(MarketDataIndicator.id)
            .where(MarketDataIndicator.name == name)
            .where(MarketDataIndicator.user_id == user_id)
            .where(MarketDataIndicator.symbol == symbol)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def add_market_data_indicator(self, indicator: MarketDataIndicator) -> MarketDataIndicator:
        self.session.add(indicator)
        await self.session.flush()
        return indicator

    async def get_user_market_indicators(self, user_id: int, symbol: str, limit: int = 200) -> Sequence[MarketDataIndicator]:
        stmt = (
            select(MarketDataIndicator)
            .where(MarketDataIndicator.user_id == user_id)
            .where(MarketDataIndicator.symbol == symbol)
            .order_by(desc(MarketDataIndicator.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_user_market_indicator(self, name: str, user_id: int, symbol: str) -> bool:
        stmt = (
            delete(MarketDataIndicator)
            .where(MarketDataIndicator.name == name)
            .where(MarketDataIndicator.user_id == user_id)
            .where(MarketDataIndicator.symbol == symbol)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_active_day_indicators(self, user_id: int, symbol: str) -> Sequence[MarketDataIndicator]:
        # DISTINCT ON equivalent by combining order_by and Python dict (or advanced SQL)
        # SQLAlchemy and asyncpg don't natively abstract PostgreSQL DISTINCT ON nicely without raw strings.
        # We can use order_by + manual distinct in memory because it's only active indicators per user.
        stmt = (
            select(MarketDataIndicator)
            .where(MarketDataIndicator.user_id == user_id)
            .where(MarketDataIndicator.symbol == symbol)
            .order_by(desc(MarketDataIndicator.timestamp))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        # In-memory DISTINCT ON (name)
        seen = set()
        active = []
        for row in rows:
            if row.name not in seen:
                seen.add(row.name)
                active.append(row)
        
        # Sorteer alfabetisch op naam zoals originele query (ORDER BY name, timestamp DESC)
        active.sort(key=lambda x: x.name)
        return active

    async def get_period_indicators(
        self,
        user_id: int,
        symbol: str,
        days: int,
    ) -> Sequence[MarketDataIndicator]:
        date_query = (
            select(func.date(MarketDataIndicator.timestamp).label("period_date"))
            .where(
                and_(
                    MarketDataIndicator.user_id == user_id,
                    MarketDataIndicator.symbol == symbol,
                )
            )
            .group_by(func.date(MarketDataIndicator.timestamp))
            .order_by(desc(func.date(MarketDataIndicator.timestamp)))
            .limit(days)
        )
        date_result = await self.session.execute(date_query)
        dates = [row[0] for row in date_result.fetchall()]

        if not dates:
            return []

        stmt = (
            select(MarketDataIndicator)
            .where(
                and_(
                    MarketDataIndicator.user_id == user_id,
                    MarketDataIndicator.symbol == symbol,
                    func.date(MarketDataIndicator.timestamp).in_(dates),
                )
            )
            .order_by(desc(MarketDataIndicator.timestamp), MarketDataIndicator.name.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # =========================================================
    # GLOBAAL: 7D Data
    # =========================================================
    async def get_market_data_7d(self, symbol: str = 'BTC') -> Sequence[MarketData7D]:
        stmt = (
            select(MarketData7D)
            .where(MarketData7D.symbol == symbol)
            .order_by(desc(MarketData7D.date))
            .limit(200)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_7d_record(self, symbol: str, date: datetime.date) -> Optional[MarketData7D]:
        stmt = (
            select(MarketData7D)
            .where(MarketData7D.symbol == symbol)
            .where(MarketData7D.date == date)
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def add_market_data_7d(self, record: MarketData7D):
        self.session.add(record)
        # Callers handle commit

    # =========================================================
    # GLOBAAL: Forward Returns
    # =========================================================
    async def get_forward_returns(self, symbol: str = 'BTC') -> Sequence[MarketForwardReturn]:
        stmt = (
            select(MarketForwardReturn)
            .where(MarketForwardReturn.symbol == symbol)
            .order_by(MarketForwardReturn.period, desc(MarketForwardReturn.start_date))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_forward_returns_by_period(self, symbol: str, period: str) -> Sequence[MarketForwardReturn]:
        stmt = (
            select(MarketForwardReturn)
            .where(MarketForwardReturn.symbol == symbol)
            .where(MarketForwardReturn.period == period)
            .order_by(MarketForwardReturn.start_date.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
