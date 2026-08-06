from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, Date, text
from datetime import datetime, timedelta
from typing import Any, List, Optional

from backend.infrastructure.models import TechnicalDataIndicator, TechnicalIndicatorRule, Indicator, UserIndicatorConfig

class TechnicalDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._user_config_columns_cache: Optional[set[str]] = None

    @staticmethod
    def _eq_or_null(column, value):
        return column.is_(None) if value is None else column == value

    async def _get_user_config_columns(self) -> set[str]:
        if self._user_config_columns_cache is not None:
            return self._user_config_columns_cache

        try:
            result = await self.session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'user_indicator_configs'
                    """
                )
            )
            columns = {str(column_name) for column_name in result.scalars().all()}
        except Exception:
            columns = set()

        if not columns:
            columns = {
                "id",
                "user_id",
                "indicator",
                "category",
                "priority",
                "enabled",
                "created_at",
            }

        self._user_config_columns_cache = columns
        return columns

    async def _supports_asset_scopes(self) -> bool:
        columns = await self._get_user_config_columns()
        return "symbol" in columns and "asset_class" in columns

    @staticmethod
    def _normalize_scope(symbol: Optional[str], asset_class: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        return normalized_symbol, normalized_asset_class

    @staticmethod
    def _row_to_user_config(row: Any, fallback_category: str) -> SimpleNamespace:
        mapping = dict(row._mapping if hasattr(row, "_mapping") else row)
        return SimpleNamespace(
            id=mapping.get("id"),
            user_id=mapping.get("user_id"),
            indicator=mapping.get("indicator"),
            category=mapping.get("category") or fallback_category,
            symbol=mapping.get("symbol"),
            asset_class=mapping.get("asset_class"),
            priority=mapping.get("priority", 100),
            enabled=mapping.get("enabled", True),
            created_at=mapping.get("created_at"),
        )

    async def _fetch_scope_configs(
        self,
        user_id: int,
        *,
        category: str,
        symbol: Optional[str],
        asset_class: Optional[str],
        enabled_only: bool,
    ) -> List[SimpleNamespace]:
        columns = await self._get_user_config_columns()
        supports_asset_scopes = await self._supports_asset_scopes()

        select_fields = [
            "id",
            "user_id",
            "indicator",
            "priority",
            "enabled",
            "created_at",
        ]
        if "category" in columns:
            select_fields.append("category")
        if "symbol" in columns:
            select_fields.append("symbol")
        if "asset_class" in columns:
            select_fields.append("asset_class")

        conditions = ["user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}

        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category

        if enabled_only and "enabled" in columns:
            conditions.append("enabled = TRUE")

        if supports_asset_scopes:
            if symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol

            if asset_class is None:
                conditions.append("asset_class IS NULL")
            else:
                conditions.append("asset_class = :asset_class")
                params["asset_class"] = asset_class

        query = text(
            f"""
            SELECT {", ".join(select_fields)}
            FROM user_indicator_configs
            WHERE {" AND ".join(conditions)}
            ORDER BY priority ASC, id ASC
            """
        )
        result = await self.session.execute(query, params)
        return [self._row_to_user_config(row, category) for row in result.fetchall()]

    async def get_user_configs(
        self,
        user_id: int,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)

        if not await self._supports_asset_scopes():
            return await self._fetch_scope_configs(
                user_id,
                category=category,
                symbol=None,
                asset_class=None,
                enabled_only=True,
            )

        if normalized_symbol:
            symbol_rows = await self._fetch_scope_configs(
                user_id,
                category=category,
                symbol=normalized_symbol,
                asset_class=normalized_asset_class,
                enabled_only=True,
            )
            if symbol_rows:
                return symbol_rows

        if normalized_asset_class:
            class_rows = await self._fetch_scope_configs(
                user_id,
                category=category,
                symbol=None,
                asset_class=normalized_asset_class,
                enabled_only=True,
            )
            if class_rows:
                return class_rows

        return await self._fetch_scope_configs(
            user_id,
            category=category,
            symbol=None,
            asset_class=None,
            enabled_only=True,
        )

    async def ensure_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        priority: int = 100,
    ):
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)
        columns = await self._get_user_config_columns()
        supports_asset_scopes = await self._supports_asset_scopes()

        conditions = [
            "user_id = :user_id",
            "indicator = :indicator",
        ]
        params: dict[str, Any] = {
            "user_id": user_id,
            "indicator": indicator,
        }
        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category
        if supports_asset_scopes:
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol

            if normalized_asset_class is None:
                conditions.append("asset_class IS NULL")
            else:
                conditions.append("asset_class = :asset_class")
                params["asset_class"] = normalized_asset_class

        existing_query = text(
            f"""
            SELECT id, user_id, indicator, priority, enabled, created_at
            {", category" if "category" in columns else ""}
            {", symbol" if "symbol" in columns else ""}
            {", asset_class" if "asset_class" in columns else ""}
            FROM user_indicator_configs
            WHERE {" AND ".join(conditions)}
            ORDER BY id ASC
            LIMIT 1
            """
        )
        existing_result = await self.session.execute(existing_query, params)
        existing = existing_result.first()
        if existing:
            update_sets = ["priority = :priority"]
            update_params = dict(params)
            update_params["priority"] = priority
            if "enabled" in columns:
                update_sets.append("enabled = TRUE")

            await self.session.execute(
                text(
                    f"""
                    UPDATE user_indicator_configs
                    SET {", ".join(update_sets)}
                    WHERE id = :config_id
                    """
                ),
                {
                    **update_params,
                    "config_id": existing._mapping["id"],
                },
            )
            await self.session.flush()
            return SimpleNamespace(
                **dict(existing._mapping),
                category=(existing._mapping.get("category") or category),
                symbol=existing._mapping.get("symbol", normalized_symbol if supports_asset_scopes else None),
                asset_class=existing._mapping.get("asset_class", normalized_asset_class if supports_asset_scopes else None),
                priority=priority,
                enabled=True,
            )

        insert_columns = ["user_id", "indicator", "priority"]
        insert_values = [":user_id", ":indicator", ":priority"]
        insert_params: dict[str, Any] = {
            "user_id": user_id,
            "indicator": indicator,
            "priority": priority,
        }
        if "category" in columns:
            insert_columns.append("category")
            insert_values.append(":category")
            insert_params["category"] = category
        if "enabled" in columns:
            insert_columns.append("enabled")
            insert_values.append("TRUE")
        if "symbol" in columns:
            insert_columns.append("symbol")
            insert_values.append(":symbol")
            insert_params["symbol"] = normalized_symbol
        if "asset_class" in columns:
            insert_columns.append("asset_class")
            insert_values.append(":asset_class")
            insert_params["asset_class"] = normalized_asset_class

        await self.session.execute(
            text(
                f"""
                INSERT INTO user_indicator_configs ({", ".join(insert_columns)})
                VALUES ({", ".join(insert_values)})
                """
            ),
            insert_params,
        )
        await self.session.flush()
        return SimpleNamespace(
            id=None,
            user_id=user_id,
            indicator=indicator,
            category=category,
            symbol=normalized_symbol if supports_asset_scopes else None,
            asset_class=normalized_asset_class if supports_asset_scopes else None,
            priority=priority,
            enabled=True,
            created_at=None,
        )

    async def remove_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ):
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)
        columns = await self._get_user_config_columns()
        supports_asset_scopes = await self._supports_asset_scopes()

        conditions = [
            "user_id = :user_id",
            "indicator = :indicator",
        ]
        params: dict[str, Any] = {
            "user_id": user_id,
            "indicator": indicator,
        }
        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category
        if supports_asset_scopes:
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol
            if normalized_asset_class is None:
                conditions.append("asset_class IS NULL")
            else:
                conditions.append("asset_class = :asset_class")
                params["asset_class"] = normalized_asset_class

        await self.session.execute(
            text(
                f"""
                DELETE FROM user_indicator_configs
                WHERE {" AND ".join(conditions)}
                """
            ),
            params,
        )

    async def list_scope_configs(
        self,
        user_id: int,
        *,
        category: str = "technical",
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)
        if not await self._supports_asset_scopes():
            normalized_symbol = None
            normalized_asset_class = None
        return await self._fetch_scope_configs(
            user_id,
            category=category,
            symbol=normalized_symbol,
            asset_class=normalized_asset_class,
            enabled_only=False,
        )

    async def replace_scope_configs(
        self,
        user_id: int,
        indicators: List[tuple[str, int]],
        *,
        category: str = "technical",
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)
        if not await self._supports_asset_scopes():
            normalized_symbol = None
            normalized_asset_class = None

        columns = await self._get_user_config_columns()
        conditions = ["user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}
        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category
        if await self._supports_asset_scopes():
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol
            if normalized_asset_class is None:
                conditions.append("asset_class IS NULL")
            else:
                conditions.append("asset_class = :asset_class")
                params["asset_class"] = normalized_asset_class

        await self.session.execute(
            text(
                f"""
                DELETE FROM user_indicator_configs
                WHERE {" AND ".join(conditions)}
                """
            ),
            params,
        )

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
