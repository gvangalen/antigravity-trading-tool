from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, Date
from datetime import datetime, timedelta
from typing import List, Optional

from backend.infrastructure.models import TechnicalDataIndicator, TechnicalIndicatorRule, Indicator

class TechnicalDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_for_user(self, user_id: int, limit: int = 50) -> List[TechnicalDataIndicator]:
        result = await self.session.execute(
            select(TechnicalDataIndicator)
            .where(TechnicalDataIndicator.user_id == user_id)
            .order_by(TechnicalDataIndicator.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_indicator_config(self, name: str) -> Optional[Indicator]:
        result = await self.session.execute(
            select(Indicator)
            .where(
                and_(
                    func.lower(Indicator.name) == func.lower(name),
                    Indicator.category == 'technical',
                    Indicator.active == True
                )
            )
        )
        return result.scalars().first()

    async def check_duplicate(self, name: str, user_id: int) -> bool:
        result = await self.session.execute(
            select(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(name),
                    TechnicalDataIndicator.user_id == user_id
                )
            )
            .limit(1)
        )
        return result.scalars().first() is not None

    async def add_indicator(
        self,
        name: str,
        value: float,
        score: float,
        advies: str,
        uitleg: str,
        user_id: int
    ) -> TechnicalDataIndicator:
        new_ind = TechnicalDataIndicator(
            indicator=name,
            value=value,
            score=score,
            advies=advies,
            uitleg=uitleg,
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        self.session.add(new_ind)
        # Flush to get the ID back immediately
        await self.session.flush()
        return new_ind

    async def get_day_data(self, user_id: int) -> List[TechnicalDataIndicator]:
        """
        Haalt de meest recente record op per indicator voor deze gebruiker.
        Dit is de 'Cockpit' view: we willen altijd iets zien, ook als de task van vandaag faalde.
        """
        return await self.get_latest_data_fallback(user_id)

    async def get_latest_data_fallback(self, user_id: int) -> List[TechnicalDataIndicator]:
        """
        Helper die per indicator simpelweg het allerlaatste record pakt.
        Voorkomt 'Geen verbinding' errors op het dashboard.
        """
        stmt = (
            select(TechnicalDataIndicator)
            .distinct(TechnicalDataIndicator.indicator)
            .where(TechnicalDataIndicator.user_id == user_id)
            .order_by(TechnicalDataIndicator.indicator, TechnicalDataIndicator.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_week_data(self, user_id: int) -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 1)

    async def _get_data_by_weeks(self, user_id: int, limit: int) -> List[TechnicalDataIndicator]:
        """
        Helper om data over X weken op te halen. 
        Eerst de meest recente week-startdatums bepalen en dan de data pff.
        """
        # 1. Get distinct weeks
        week_trunc = func.date_trunc('week', TechnicalDataIndicator.timestamp)
        weeks_result = await self.session.execute(
            select(func.cast(week_trunc, Date))
            .where(TechnicalDataIndicator.user_id == user_id)
            .distinct()
            .order_by(func.cast(week_trunc, Date).desc())
            .limit(limit)
        )
        weeks = [r[0] for r in weeks_result.all()]

        if not weeks:
            return []

        # 2. Fetch data for those weeks
        result = await self.session.execute(
            select(TechnicalDataIndicator)
            .where(
                and_(
                    TechnicalDataIndicator.user_id == user_id,
                    func.cast(func.date_trunc('week', TechnicalDataIndicator.timestamp), Date).in_(weeks)
                )
            )
            .order_by(TechnicalDataIndicator.timestamp.desc())
        )
        return list(result.scalars().all())

    async def get_month_data(self, user_id: int) -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 4)

    async def get_quarter_data(self, user_id: int) -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 12)

    async def delete_indicator(self, indicator: str, user_id: int) -> int:
        result = await self.session.execute(
            delete(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(indicator),
                    TechnicalDataIndicator.user_id == user_id
                )
            )
        )
        return result.rowcount

    async def get_all_indicators(self) -> List[dict]:
        result = await self.session.execute(
            select(Indicator.name, Indicator.display_name)
            .where(
                and_(
                    Indicator.active == True,
                    Indicator.category == 'technical'
                )
            )
            .order_by(Indicator.name)
        )
        return [{"name": row.name, "display_name": row.display_name} for row in result.all()]

    async def get_rules_for_indicator(self, indicator_name: str, user_id: int) -> List[TechnicalIndicatorRule]:
        # 1. User rules
        user_rules_result = await self.session.execute(
            select(TechnicalIndicatorRule)
            .where(
                and_(
                    func.lower(TechnicalIndicatorRule.indicator) == func.lower(indicator_name),
                    TechnicalIndicatorRule.user_id == user_id
                )
            )
            .order_by(TechnicalIndicatorRule.range_min.asc())
        )
        rows = list(user_rules_result.scalars().all())

        if not rows:
            # 2. Fallback to template (user_id IS NULL)
            template_rules_result = await self.session.execute(
                select(TechnicalIndicatorRule)
                .where(
                    and_(
                        func.lower(TechnicalIndicatorRule.indicator) == func.lower(indicator_name),
                        TechnicalIndicatorRule.user_id.is_(None)
                    )
                )
                .order_by(TechnicalIndicatorRule.range_min.asc())
            )
            rows = list(template_rules_result.scalars().all())

        return rows

    async def get_indicator_history(self, indicator_name: str, user_id: int, limit: int = 30) -> List[TechnicalDataIndicator]:
        """
        Haalt de laatste 'limit' datapunten op voor een specifieke indicator.
        Handig voor sparklines (trend-visualisatie).
        """
        result = await self.session.execute(
            select(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(indicator_name),
                    TechnicalDataIndicator.user_id == user_id
                )
            )
            .order_by(TechnicalDataIndicator.timestamp.desc())
            .limit(limit)
        )
        # We halen de nieuwste eerst op, en draaien ze om in de lijst voor chronologische volgorde (L -> R)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows
