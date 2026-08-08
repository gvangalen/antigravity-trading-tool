from typing import List, Optional, Sequence
from sqlalchemy import select, delete, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import MacroData, MacroIndicatorRule, Indicator

class MacroDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_global_indicators(self, category: str = 'macro') -> Sequence[Indicator]:
        stmt = (
            select(Indicator)
            .where(
                and_(
                    Indicator.category == category,
                    Indicator.active == True,
                )
            )
            .order_by(Indicator.display_name.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def check_indicator_exists(self, user_id: int, name: str, symbol: Optional[str] = None) -> bool:
        stmt = (
            select(MacroData)
            .where(
                and_(
                    func.lower(MacroData.name) == func.lower(name),
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def add_macro_data(self, record: MacroData):
        self.session.add(record)

    async def get_indicator_info(self, name: str) -> Optional[Indicator]:
        stmt = select(Indicator).where(
            and_(
                func.lower(Indicator.name) == func.lower(name),
                Indicator.active == True,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # =========================================================
    # QUERIES: LATEST / DAY
    # =========================================================
    async def get_user_macro_data(self, user_id: int, symbol: Optional[str] = None, limit: int = 100) -> List[MacroData]:
        stmt = select(MacroData).where(
            and_(
                MacroData.user_id == user_id,
                MacroData.symbol == symbol,
            )
        )
        result = await self.session.execute(
            stmt.order_by(MacroData.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_day_macro_data(self, user_id: int, symbol: Optional[str] = None) -> List[MacroData]:
        subq = (
            select(
                MacroData.name,
                func.max(MacroData.timestamp).label("max_ts")
            )
            .where(
                and_(
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                )
            )
            .group_by(MacroData.name)
            .subquery()
        )
        
        stmt = (
            select(MacroData)
            .join(subq, and_(MacroData.name == subq.c.name, MacroData.timestamp == subq.c.max_ts))
            .where(
                and_(
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                )
            )
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # =========================================================
    # AGGREGATIES (WEEK / MAAND / KWARTAAL)
    # =========================================================
    async def _get_data_by_days(self, user_id: int, days: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        day_q = (
            select(func.date(MacroData.timestamp).label("d"))
            .where(
                and_(
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                )
            )
            .group_by(func.date(MacroData.timestamp))
            .order_by(desc(func.date(MacroData.timestamp)))
            .limit(days)
        )
        day_res = await self.session.execute(day_q)
        dates = [r[0] for r in day_res.fetchall()]

        if not dates:
            return []

        stmt = (
            select(MacroData)
            .where(
                and_(
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                    func.date(MacroData.timestamp).in_(dates)
                )
            )
            .order_by(desc(MacroData.timestamp))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_macro_week_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 7, symbol=symbol)

    async def get_macro_month_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 30, symbol=symbol)

    async def get_macro_quarter_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 90, symbol=symbol)

    # =========================================================
    # CRUD: DELETE / RULES
    # =========================================================
    async def delete_user_macro_indicator(self, name: str, user_id: int, symbol: Optional[str] = None) -> bool:
        stmt = (
            delete(MacroData)
            .where(
                and_(
                    func.lower(MacroData.name) == func.lower(name),
                    MacroData.user_id == user_id,
                    MacroData.symbol == symbol,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_indicator_rules(self, name: str, user_id: int) -> Sequence[MacroIndicatorRule]:
        stmt = (
            select(MacroIndicatorRule)
            .where(
                and_(
                    func.lower(MacroIndicatorRule.indicator) == func.lower(name),
                    MacroIndicatorRule.user_id == user_id,
                    MacroIndicatorRule.is_active == True
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
