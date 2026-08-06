from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, Date
from datetime import datetime, timedelta
from typing import List, Optional

from backend.infrastructure.models import TechnicalDataIndicator, TechnicalIndicatorRule, Indicator, UserIndicatorConfig

class TechnicalDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _eq_or_null(column, value):
        return column.is_(None) if value is None else column == value

    async def get_user_configs(
        self,
        user_id: int,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None

        if normalized_symbol:
            symbol_stmt = select(UserIndicatorConfig).where(
                and_(
                    UserIndicatorConfig.user_id == user_id,
                    UserIndicatorConfig.category == category,
                    UserIndicatorConfig.enabled == True,
                    UserIndicatorConfig.symbol == normalized_symbol,
                )
            ).order_by(UserIndicatorConfig.priority.asc(), UserIndicatorConfig.id.asc())
            symbol_result = await self.session.execute(symbol_stmt)
            symbol_rows = list(symbol_result.scalars().all())
            if symbol_rows:
                return symbol_rows

        if normalized_asset_class:
            class_stmt = select(UserIndicatorConfig).where(
                and_(
                    UserIndicatorConfig.user_id == user_id,
                    UserIndicatorConfig.category == category,
                    UserIndicatorConfig.enabled == True,
                    UserIndicatorConfig.symbol.is_(None),
                    UserIndicatorConfig.asset_class == normalized_asset_class,
                )
            ).order_by(UserIndicatorConfig.priority.asc(), UserIndicatorConfig.id.asc())
            class_result = await self.session.execute(class_stmt)
            class_rows = list(class_result.scalars().all())
            if class_rows:
                return class_rows

        default_stmt = select(UserIndicatorConfig).where(
            and_(
                UserIndicatorConfig.user_id == user_id,
                UserIndicatorConfig.category == category,
                UserIndicatorConfig.enabled == True,
                UserIndicatorConfig.symbol.is_(None),
                UserIndicatorConfig.asset_class.is_(None),
            )
        ).order_by(UserIndicatorConfig.priority.asc(), UserIndicatorConfig.id.asc())
        default_result = await self.session.execute(default_stmt)
        return list(default_result.scalars().all())

    async def ensure_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        priority: int = 100,
    ):
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        stmt = select(UserIndicatorConfig).where(
            and_(
                UserIndicatorConfig.user_id == user_id,
                UserIndicatorConfig.indicator == indicator,
                UserIndicatorConfig.category == category,
                self._eq_or_null(UserIndicatorConfig.symbol, normalized_symbol),
                self._eq_or_null(UserIndicatorConfig.asset_class, normalized_asset_class),
            )
        )
        res = await self.session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            if existing.enabled is not True:
                existing.enabled = True
            existing.priority = priority
            await self.session.flush()
            return existing

        new_conf = UserIndicatorConfig(
            user_id=user_id,
            indicator=indicator,
            category=category,
            symbol=normalized_symbol,
            asset_class=normalized_asset_class,
            priority=priority,
            enabled=True,
        )
        self.session.add(new_conf)
        await self.session.flush()
        return new_conf

    async def remove_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ):
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        stmt = delete(UserIndicatorConfig).where(
            and_(
                UserIndicatorConfig.user_id == user_id,
                UserIndicatorConfig.indicator == indicator,
                UserIndicatorConfig.category == category,
                self._eq_or_null(UserIndicatorConfig.symbol, normalized_symbol),
                self._eq_or_null(UserIndicatorConfig.asset_class, normalized_asset_class),
            )
        )
        await self.session.execute(stmt)

    async def list_scope_configs(
        self,
        user_id: int,
        *,
        category: str = "technical",
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        stmt = select(UserIndicatorConfig).where(
            and_(
                UserIndicatorConfig.user_id == user_id,
                UserIndicatorConfig.category == category,
                self._eq_or_null(UserIndicatorConfig.symbol, normalized_symbol),
                self._eq_or_null(UserIndicatorConfig.asset_class, normalized_asset_class),
            )
        ).order_by(UserIndicatorConfig.priority.asc(), UserIndicatorConfig.id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace_scope_configs(
        self,
        user_id: int,
        indicators: List[tuple[str, int]],
        *,
        category: str = "technical",
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None

        delete_stmt = delete(UserIndicatorConfig).where(
            and_(
                UserIndicatorConfig.user_id == user_id,
                UserIndicatorConfig.category == category,
                self._eq_or_null(UserIndicatorConfig.symbol, normalized_symbol),
                self._eq_or_null(UserIndicatorConfig.asset_class, normalized_asset_class),
            )
        )
        await self.session.execute(delete_stmt)

        created: List[UserIndicatorConfig] = []
        for indicator, priority in indicators:
            created.append(
                await self.ensure_user_config(
                    user_id,
                    indicator,
                    category=category,
                    symbol=normalized_symbol,
                    asset_class=normalized_asset_class,
                    priority=priority,
                )
            )
        return created

    async def get_latest_for_user(self, user_id: int, symbol: Optional[str] = None, limit: int = 50) -> List[TechnicalDataIndicator]:
        stmt = select(TechnicalDataIndicator).where(TechnicalDataIndicator.user_id == user_id)
        if symbol:
            stmt = stmt.where(TechnicalDataIndicator.symbol == symbol)
        
        result = await self.session.execute(
            stmt.order_by(TechnicalDataIndicator.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_indicator_config(self, name: str, category: str = 'technical') -> Optional[Indicator]:
        result = await self.session.execute(
            select(Indicator)
            .where(
                and_(
                    func.lower(Indicator.name) == func.lower(name),
                    Indicator.category == category,
                    Indicator.active == True
                )
            )
        )
        return result.scalars().first()

    async def check_duplicate(self, name: str, user_id: int, symbol: str = "BTC") -> bool:
        stmt = (
            select(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(name),
                    TechnicalDataIndicator.user_id == user_id
                )
            )
        )
        if symbol:
            stmt = stmt.where(TechnicalDataIndicator.symbol == symbol)
        
        result = await self.session.execute(stmt.limit(1))
        return result.scalars().first() is not None

    async def add_indicator(
        self,
        name: str,
        value: float,
        score: float,
        advies: str,
        uitleg: str,
        user_id: int,
        symbol: str = "BTC"
    ) -> TechnicalDataIndicator:
        new_ind = TechnicalDataIndicator(
            indicator=name,
            value=value,
            score=score,
            advies=advies,
            uitleg=uitleg,
            user_id=user_id,
            symbol=symbol,
            timestamp=datetime.utcnow()
        )
        self.session.add(new_ind)
        # Flush to get the ID back immediately
        await self.session.flush()
        return new_ind

    async def get_day_data(self, user_id: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        """
        Haalt de meest recente record op per indicator voor deze gebruiker.
        Dit is de 'Cockpit' view: we willen altijd iets zien, ook als de task van vandaag faalde.
        """
        return await self.get_latest_data_fallback(user_id, symbol)

    async def get_latest_data_fallback(self, user_id: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        """
        Helper die per indicator simpelweg het allerlaatste record pakt.
        Voorkomt 'Geen verbinding' errors op het dashboard.
        """
        stmt = (
            select(TechnicalDataIndicator)
            .distinct(TechnicalDataIndicator.indicator)
            .where(and_(
                TechnicalDataIndicator.user_id == user_id,
                TechnicalDataIndicator.symbol == symbol
            ))
            .order_by(TechnicalDataIndicator.indicator, TechnicalDataIndicator.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_week_data(self, user_id: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 1, symbol)

    async def _get_data_by_weeks(self, user_id: int, limit: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        """
        Helper om data over X weken op te halen. 
        Eerst de meest recente week-startdatums bepalen en dan de data pff.
        """
        # 1. Get distinct weeks
        week_trunc = func.date_trunc('week', TechnicalDataIndicator.timestamp)
        weeks_result = await self.session.execute(
            select(func.cast(week_trunc, Date))
            .where(and_(
                TechnicalDataIndicator.user_id == user_id,
                TechnicalDataIndicator.symbol == symbol
            ))
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
                    TechnicalDataIndicator.symbol == symbol,
                    func.cast(func.date_trunc('week', TechnicalDataIndicator.timestamp), Date).in_(weeks)
                )
            )
            .order_by(TechnicalDataIndicator.timestamp.desc())
        )
        return list(result.scalars().all())

    async def get_month_data(self, user_id: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 4, symbol)

    async def get_quarter_data(self, user_id: int, symbol: str = "BTC") -> List[TechnicalDataIndicator]:
        return await self._get_data_by_weeks(user_id, 12, symbol)

    async def delete_indicator(self, indicator: str, user_id: int, symbol: Optional[str] = None) -> int:
        stmt = (
            delete(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(indicator),
                    TechnicalDataIndicator.user_id == user_id
                )
            )
        )
        if symbol:
            stmt = stmt.where(TechnicalDataIndicator.symbol == symbol)
        
        result = await self.session.execute(stmt)
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

    async def get_indicator_history(self, indicator_name: str, user_id: int, symbol: str = "BTC", limit: int = 30) -> List[TechnicalDataIndicator]:
        """
        Haalt de laatste 'limit' datapunten op voor een specifieke indicator.
        Handig voor sparklines (trend-visualisatie).
        """
        result = await self.session.execute(
            select(TechnicalDataIndicator)
            .where(
                and_(
                    func.lower(TechnicalDataIndicator.indicator) == func.lower(indicator_name),
                    TechnicalDataIndicator.user_id == user_id,
                    TechnicalDataIndicator.symbol == symbol
                )
            )
            .order_by(TechnicalDataIndicator.timestamp.desc())
            .limit(limit)
        )
        # We halen de nieuwste eerst op, en draaien ze om in de lijst voor chronologische volgorde (L -> R)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows
