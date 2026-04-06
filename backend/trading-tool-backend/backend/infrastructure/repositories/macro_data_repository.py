from typing import List, Sequence, Optional, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, text, func

from backend.infrastructure.models import MacroData, MacroIndicatorRule, Indicator

class MacroDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================
    # CONFIG & RULES
    # =========================================================
    async def get_global_indicators(self) -> Sequence[Indicator]:
        stmt = (
            select(Indicator)
            .where(Indicator.category == 'macro')
            .where(Indicator.active == True)
            .order_by(Indicator.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_indicator_info(self, name: str) -> Optional[Indicator]:
        stmt = (
            select(Indicator)
            .where(func.lower(Indicator.name) == name.lower())
            .where(Indicator.category == 'macro')
            .where(Indicator.active == True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_indicator_rules(self, name: str, user_id: int) -> Sequence[MacroIndicatorRule]:
        # User-specific
        stmt = (
            select(MacroIndicatorRule)
            .where(MacroIndicatorRule.indicator == name)
            .where(MacroIndicatorRule.user_id == user_id)
            .order_by(MacroIndicatorRule.range_min.asc())
        )
        result = await self.session.execute(stmt)
        rules = result.scalars().all()

        if not rules:
            # Fallback global
            stmt2 = (
                select(MacroIndicatorRule)
                .where(MacroIndicatorRule.indicator == name)
                .where(MacroIndicatorRule.user_id.is_(None))
                .order_by(MacroIndicatorRule.range_min.asc())
            )
            result2 = await self.session.execute(stmt2)
            rules = result2.scalars().all()

        return rules

    # =========================================================
    # USER: Macro Data CRUD
    # =========================================================
    async def check_indicator_exists(self, name: str, user_id: int) -> bool:
        stmt = (
            select(MacroData.id)
            .where(MacroData.name == name)
            .where(MacroData.user_id == user_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar() is not None

    async def add_macro_data(self, record: MacroData) -> MacroData:
        self.session.add(record)
        await self.session.flush()
        return record

    async def delete_user_macro_indicator(self, name: str, user_id: int) -> bool:
        stmt = (
            delete(MacroData)
            .where(MacroData.name == name)
            .where(MacroData.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    # =========================================================
    # QUERIES: LATEST / DAY
    # =========================================================
    async def get_user_macro_data(self, user_id: int, limit: int = 100) -> Sequence[MacroData]:
        stmt = (
            select(MacroData)
            .where(MacroData.user_id == user_id)
            .order_by(desc(MacroData.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active_day_macro_data(self, user_id: int) -> Sequence[MacroData]:
        # Eerst huidige dag zoeken
        stmt = (
            select(MacroData)
            .where(MacroData.user_id == user_id)
            .where(func.date(MacroData.timestamp) == func.current_date())
            .order_by(desc(MacroData.timestamp))
        )
        result = await self.session.execute(stmt)
        records = result.scalars().all()

        if not records:
            # Zoek de laatste beschikbare timestamp
            recent_stmt = (
                select(MacroData.timestamp)
                .where(MacroData.user_id == user_id)
                .order_by(desc(MacroData.timestamp))
                .limit(1)
            )
            recent_res = await self.session.execute(recent_stmt)
            latest_ts = recent_res.scalar()

            if not latest_ts:
                return []

            latest_date = latest_ts.date()
            stmt2 = (
                select(MacroData)
                .where(MacroData.user_id == user_id)
                .where(func.date(MacroData.timestamp) == latest_date)
                .order_by(desc(MacroData.timestamp))
            )
            res2 = await self.session.execute(stmt2)
            records = res2.scalars().all()

        return records

    # =========================================================
    # AGGREGATIES (WEEK / MAAND / KWARTAAL)
    # =========================================================
    async def get_macro_week_data(self, user_id: int) -> Sequence[MacroData]:
        # Fetch 7 distinct days
        day_q = (
            select(func.date(MacroData.timestamp).label("d"))
            .where(MacroData.user_id == user_id)
            .group_by(func.date(MacroData.timestamp))
            .order_by(desc(func.date(MacroData.timestamp)))
            .limit(7)
        )
        day_res = await self.session.execute(day_q)
        days = [r[0] for r in day_res.all()]

        if not days:
            return []

        stmt = (
            select(MacroData)
            .where(MacroData.user_id == user_id)
            .where(func.date(MacroData.timestamp).in_(days))
            .order_by(desc(MacroData.timestamp))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_macro_aggregated_data(self, user_id: int, limit: int) -> Sequence[MacroData]:
        # Fetch distinct weeks
        week_q = (
            select(func.date_trunc('week', MacroData.timestamp).cast(func.date()).label("w"))
            .where(MacroData.user_id == user_id)
            .group_by(func.date_trunc('week', MacroData.timestamp).cast(func.date()))
            .order_by(desc(func.date_trunc('week', MacroData.timestamp).cast(func.date())))
            .limit(limit)
        )
        week_res = await self.session.execute(week_q)
        weeks = [r[0] for r in week_res.all()]

        if not weeks:
            return []

        stmt = (
            select(MacroData)
            .where(MacroData.user_id == user_id)
            .where(func.date_trunc('week', MacroData.timestamp).cast(func.date()).in_(weeks))
            .order_by(desc(MacroData.timestamp))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
