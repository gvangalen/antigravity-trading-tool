from json import dumps
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, Date, text
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.infrastructure.models import (
    AssetCatalog,
    TechnicalDataIndicator,
    Indicator,
    TechnicalIndicatorRule,
    UserIndicatorConfig,
)
from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.utils.scoring_utils import normalize_indicator_name


CANONICAL_USER_INDICATOR_CONFIG_COLUMNS = {
    "id",
    "user_id",
    "indicator",
    "category",
    "symbol",
    "asset_class",
    "priority",
    "enabled",
    "config_json",
    "provenance",
    "source_record_id",
    "created_at",
    "updated_at",
}


class TechnicalDataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._user_config_columns_cache: Optional[set[str]] = None
        self._source_registry = FinnV2InformationSourceRegistry()

    @staticmethod
    def _eq_or_null(column, value):
        return column.is_(None) if value is None else column == value

    async def _get_user_config_columns(self) -> set[str]:
        # The deploy schema gate guarantees this exact contract before the
        # backend starts. Runtime probing/fallback made an old schema silently
        # behave as a second source of truth.
        return set(CANONICAL_USER_INDICATOR_CONFIG_COLUMNS)

    async def _supports_asset_scopes(self) -> bool:
        return True

    @staticmethod
    def _normalize_scope(symbol: Optional[str], asset_class: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        return normalized_symbol, normalized_asset_class

    async def _resolve_effective_scope(
        self,
        symbol: Optional[str],
        asset_class: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        normalized_symbol, normalized_asset_class = self._normalize_scope(symbol, asset_class)
        if normalized_asset_class or not normalized_symbol:
            return normalized_symbol, normalized_asset_class
        columns = await self._get_user_config_columns()
        if "asset_class" not in columns:
            return normalized_symbol, normalized_asset_class

        try:
            result = await self.session.execute(
                select(AssetCatalog.asset_class)
                .where(func.upper(AssetCatalog.symbol) == normalized_symbol)
                .limit(1)
            )
            resolved_asset_class = result.scalar()
        except Exception:
            return normalized_symbol, normalized_asset_class

        normalized_resolved = str(resolved_asset_class or "").strip().lower() or None
        return normalized_symbol, normalized_resolved

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
            config_json=mapping.get("config_json") or {},
            provenance=mapping.get("provenance") or "product_api",
            source_record_id=mapping.get("source_record_id"),
            created_at=mapping.get("created_at"),
            updated_at=mapping.get("updated_at"),
        )

    @staticmethod
    def _ordered_existing_columns(columns: set[str], desired: list[str]) -> list[str]:
        return [column for column in desired if column in columns]

    @staticmethod
    def _order_by_clause(columns: set[str]) -> str:
        order_parts: list[str] = []
        if "priority" in columns:
            order_parts.append("priority ASC")
        if "id" in columns:
            order_parts.append("id ASC")
        return f" ORDER BY {', '.join(order_parts)}" if order_parts else ""

    @staticmethod
    def _dedupe_indicator_rows(rows: List[SimpleNamespace]) -> List[SimpleNamespace]:
        deduped: List[SimpleNamespace] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            category = str(getattr(row, "category", "") or "technical").strip().lower() or "technical"
            indicator = normalize_indicator_name(str(getattr(row, "indicator", "") or ""))
            if not indicator:
                continue
            key = (category, indicator)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

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
        has_symbol_scope = "symbol" in columns
        has_asset_class_scope = "asset_class" in columns

        select_fields = self._ordered_existing_columns(columns, [
            "id",
            "user_id",
            "indicator",
            "priority",
            "enabled",
            "created_at",
            "category",
            "symbol",
            "asset_class",
            "config_json",
            "provenance",
            "source_record_id",
            "updated_at",
        ])

        conditions = ["user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}

        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category

        if enabled_only and "enabled" in columns:
            conditions.append("enabled = TRUE")

        if has_symbol_scope:
            if symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol

        # A symbol override is already the most specific asset identity. Requiring
        # a matching class label here can hide a valid row when catalog and legacy
        # clients use equivalent but differently named classes.
        if has_asset_class_scope and symbol is None:
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
            {self._order_by_clause(columns)}
            """
        )
        result = await self.session.execute(query, params)
        if hasattr(result, "fetchall"):
            rows = result.fetchall()
        else:
            rows = result.mappings().all()
        if "category" not in columns:
            # Without an explicit category column we cannot safely infer whether a
            # configured indicator belongs to technical, market, or macro scope.
            return []
        serialized_rows = [self._row_to_user_config(row, category) for row in rows]
        filtered_rows: List[SimpleNamespace] = []
        for row in serialized_rows:
            row_category = str(getattr(row, "category", "") or category).strip().lower()
            if row_category != str(category or "").strip().lower():
                continue
            if has_symbol_scope or has_asset_class_scope:
                row_symbol, row_asset_class = self._normalize_scope(
                    getattr(row, "symbol", None),
                    getattr(row, "asset_class", None),
                )
                if has_symbol_scope and symbol is not None and row_symbol != symbol:
                    continue
                if has_asset_class_scope and symbol is None and asset_class is not None and row_asset_class not in {None, asset_class}:
                    continue
            filtered_rows.append(row)
        return filtered_rows

    async def get_user_configs(
        self,
        user_id: int,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[UserIndicatorConfig]:
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)

        columns = await self._get_user_config_columns()
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        return await self._fetch_scope_configs(
            user_id,
            category=category,
            symbol=normalized_symbol,
            asset_class=normalized_asset_class,
            enabled_only=True,
        )

    async def resolve_effective_scope_configs(
        self,
        user_id: int,
        *,
        category: str = "technical",
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        enabled_only: bool = True,
    ) -> dict[str, Any]:
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)

        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        symbol_rows = self._dedupe_indicator_rows(
            await self._fetch_scope_configs(
                user_id,
                category=category,
                symbol=normalized_symbol,
                asset_class=normalized_asset_class,
                enabled_only=enabled_only,
            )
        )
        return {
            "scope": "symbol" if symbol_rows else "empty",
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "rows": symbol_rows,
            "storage_mode": "canonical_asset_scoped",
        }

    async def get_canonical_indicator_configuration(
        self,
        user_id: int,
        *,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        enabled_only: bool = True,
    ) -> dict[str, Any]:
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        categories = ("technical", "market", "macro")
        category_payloads: dict[str, dict[str, Any]] = {}
        for category in categories:
            category_payloads[category] = await self.resolve_effective_scope_configs(
                user_id,
                category=category,
                symbol=normalized_symbol,
                asset_class=normalized_asset_class,
                enabled_only=enabled_only,
            )

        return {
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "technical": category_payloads["technical"]["rows"],
            "market": category_payloads["market"]["rows"],
            "macro": category_payloads["macro"]["rows"],
            "scope_by_category": {
                category: payload["scope"] for category, payload in category_payloads.items()
            },
            "storage_mode_by_category": {
                category: payload["storage_mode"] for category, payload in category_payloads.items()
            },
        }

    async def get_configured_indicator_names(
        self,
        user_id: int,
        *,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        enabled_only: bool = True,
    ) -> Dict[str, List[str]]:
        configuration = await self.get_canonical_indicator_configuration(
            user_id,
            symbol=symbol,
            asset_class=asset_class,
            enabled_only=enabled_only,
        )
        names: Dict[str, List[str]] = {"market": [], "macro": [], "technical": []}
        for category in names:
            for row in configuration.get(category, []):
                indicator = str(getattr(row, "indicator", "") or "").strip()
                if not indicator:
                    continue
                display_name = indicator.upper() if indicator.lower() == "rsi" else indicator
                if display_name not in names[category]:
                    names[category].append(display_name)
        return names

    async def ensure_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        priority: int = 100,
    ):
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        columns = await self._get_user_config_columns()
        has_symbol_scope = "symbol" in columns
        has_asset_class_scope = "asset_class" in columns

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
        if has_symbol_scope:
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol

        existing_select_fields = self._ordered_existing_columns(columns, [
            "id",
            "user_id",
            "indicator",
            "priority",
            "enabled",
            "created_at",
            "category",
            "symbol",
            "asset_class",
            "config_json",
            "provenance",
            "source_record_id",
            "updated_at",
        ])
        existing_query = text(
            f"""
            SELECT {", ".join(existing_select_fields)}
            FROM user_indicator_configs
            WHERE {" AND ".join(conditions)}
            {self._order_by_clause(columns)}
            LIMIT 1
            """
        )
        existing_result = await self.session.execute(existing_query, params)
        existing = existing_result.first()
        if existing:
            existing_mapping = dict(existing._mapping)
            update_params = dict(params)
            update_sets: list[str] = []
            if "priority" in columns:
                update_sets.append("priority = :priority")
                update_params["priority"] = priority
            if "enabled" in columns:
                update_sets.append("enabled = TRUE")
            if "asset_class" in columns and normalized_asset_class is not None:
                update_sets.append("asset_class = :asset_class")
                update_params["asset_class"] = normalized_asset_class
            if "updated_at" in columns:
                update_sets.append("updated_at = CURRENT_TIMESTAMP")

            if update_sets:
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
            existing_mapping["category"] = existing_mapping.get("category") or category
            existing_mapping["symbol"] = existing_mapping.get(
                "symbol",
                normalized_symbol if has_symbol_scope else None,
            )
            existing_mapping["asset_class"] = existing_mapping.get(
                "asset_class",
                normalized_asset_class if has_asset_class_scope else None,
            )
            existing_mapping["priority"] = (
                priority if "priority" in columns else existing_mapping.get("priority", 100)
            )
            existing_mapping["enabled"] = (
                True if "enabled" in columns else existing_mapping.get("enabled", True)
            )
            existing_mapping["config_json"] = existing_mapping.get("config_json") or {}
            existing_mapping["provenance"] = existing_mapping.get("provenance") or "product_api"
            return SimpleNamespace(
                **existing_mapping,
            )

        insert_columns = ["user_id", "indicator"]
        insert_values = [":user_id", ":indicator"]
        insert_params: dict[str, Any] = {
            "user_id": user_id,
            "indicator": indicator,
        }
        if "priority" in columns:
            insert_columns.append("priority")
            insert_values.append(":priority")
            insert_params["priority"] = priority
        if "category" in columns:
            insert_columns.append("category")
            insert_values.append(":category")
            insert_params["category"] = category
        if "enabled" in columns:
            insert_columns.append("enabled")
            insert_values.append("TRUE")
        if "config_json" in columns:
            insert_columns.append("config_json")
            insert_values.append("CAST(:config_json AS JSONB)")
            insert_params["config_json"] = "{}"
        if "provenance" in columns:
            insert_columns.append("provenance")
            insert_values.append(":provenance")
            insert_params["provenance"] = "product_api"
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
            symbol=normalized_symbol if has_symbol_scope else None,
            asset_class=normalized_asset_class if has_asset_class_scope else None,
            priority=priority if "priority" in columns else 100,
            enabled=True,
            config_json={},
            provenance="product_api",
            source_record_id=None,
            created_at=None,
            updated_at=None,
        )

    async def remove_user_config(
        self,
        user_id: int,
        indicator: str,
        category: str = 'technical',
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ):
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        columns = await self._get_user_config_columns()
        has_symbol_scope = "symbol" in columns
        has_asset_class_scope = "asset_class" in columns

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
        if has_symbol_scope:
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol

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
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        columns = await self._get_user_config_columns()
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
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
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        columns = await self._get_user_config_columns()
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )

        conditions = ["user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}
        if "category" in columns:
            conditions.append("category = :category")
            params["category"] = category
        if "symbol" in columns:
            if normalized_symbol is None:
                conditions.append("symbol IS NULL")
            else:
                conditions.append("symbol = :symbol")
                params["symbol"] = normalized_symbol
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

    async def set_indicator_config_metadata(
        self,
        user_id: int,
        indicator: str,
        category: str,
        *,
        symbol: str,
        asset_class: Optional[str] = None,
        config_json: Optional[dict[str, Any]] = None,
        priority: int = 100,
        provenance: str = "indicator_config_api",
    ) -> SimpleNamespace:
        """Persist user-specific scoring settings beside the canonical selection."""
        normalized_symbol, normalized_asset_class = await self._resolve_effective_scope(symbol, asset_class)
        self._source_registry.get("indicator_configuration").validate_request(
            user_id=user_id,
            symbol=normalized_symbol,
        )
        row = await self.ensure_user_config(
            user_id,
            indicator,
            category,
            symbol=normalized_symbol,
            asset_class=normalized_asset_class,
            priority=priority,
        )
        await self.session.execute(
            text(
                """
                UPDATE user_indicator_configs
                SET config_json = CAST(:config_json AS JSONB),
                    provenance = :provenance,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                  AND symbol = :symbol
                  AND category = :category
                  AND indicator = :indicator
                """
            ),
            {
                "user_id": user_id,
                "symbol": normalized_symbol,
                "category": category,
                "indicator": indicator,
                "config_json": dumps(config_json or {}),
                "provenance": provenance,
            },
        )
        await self.session.flush()
        row.config_json = config_json or {}
        row.provenance = provenance
        return row

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
