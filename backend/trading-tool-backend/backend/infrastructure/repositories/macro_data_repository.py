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
            .where(Indicator.category == category)
            .order_by(Indicator.display_name.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def check_indicator_exists(self, user_id: int, name: str) -> bool:
        stmt = (
            select(MacroData)
            .where(
                and_(
                    func.lower(MacroData.name) == func.lower(name),
                    MacroData.user_id == user_id
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def add_macro_data(self, record: MacroData):
        self.session.add(record)

    async def get_indicator_info(self, name: str) -> Optional[Indicator]:
        stmt = select(Indicator).where(func.lower(Indicator.name) == func.lower(name))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # =========================================================
    # QUERIES: LATEST / DAY
    # =========================================================
    async def get_user_macro_data(self, user_id: int, limit: int = 100) -> List[MacroData]:
        # Macro is GLOBAL POOL voor de user. 
        stmt = select(MacroData).where(MacroData.user_id == user_id)
        result = await self.session.execute(
            stmt.order_by(MacroData.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_day_macro_data(self, user_id: int, symbol: Optional[str] = None) -> List[MacroData]:
        # We pakken de meest recente records per indicator_name voor deze gebruiker
        # We negeren 'symbol' want macro is globaal
        subq = (
            select(
                MacroData.name,
                func.max(MacroData.timestamp).label("max_ts")
            )
            .where(MacroData.user_id == user_id)
            .group_by(MacroData.name)
            .subquery()
        )
        
        stmt = (
            select(MacroData)
            .join(subq, and_(MacroData.name == subq.c.name, MacroData.timestamp == subq.c.max_ts))
            .where(MacroData.user_id == user_id)
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # =========================================================
    # AGGREGATIES (WEEK / MAAND / KWARTAAL)
    # =========================================================
    async def _get_data_by_days(self, user_id: int, days: int) -> Sequence[MacroData]:
        # Zoek de laatste X dagen waarvoor data bestaat (ongeacht symbool)
        day_q = (
            select(func.date(MacroData.timestamp).label("d"))
            .where(MacroData.user_id == user_id)
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
                    func.date(MacroData.timestamp).in_(dates)
                )
            )
            .order_by(desc(MacroData.timestamp))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_macro_week_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 7)

    async def get_macro_month_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 30)

    async def get_macro_quarter_data(self, user_id: int, symbol: Optional[str] = None) -> Sequence[MacroData]:
        return await self._get_data_by_days(user_id, 90)

    # =========================================================
    # CRUD: DELETE / RULES
    # =========================================================
    async def delete_user_macro_indicator(self, name: str, user_id: int, symbol: Optional[str] = None) -> bool:
        stmt = (
            delete(MacroData)
            .where(
                and_(
                    func.lower(MacroData.name) == func.lower(name),
                    MacroData.user_id == user_id
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
