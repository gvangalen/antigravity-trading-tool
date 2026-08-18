from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AssetCatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_assets(self, symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))
        if not normalized:
            return {}

        rows = await self._fetch_asset_rows(normalized)
        return {str(row["symbol"]).upper(): row for row in rows}

    async def search_assets(
        self,
        query: str,
        asset_classes: Sequence[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        normalized_classes = [
            str(asset_class or "").strip().lower()
            for asset_class in (asset_classes or [])
            if str(asset_class or "").strip()
        ]

        return await self._with_legacy_fallback(
            primary=lambda: self._search_extended_rows(normalized_query, normalized_classes, limit),
            fallback=lambda: self._search_legacy_rows(normalized_query, normalized_classes, limit),
        )

    async def _fetch_asset_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        return await self._with_legacy_fallback(
            primary=lambda: self._fetch_extended_rows(symbols),
            fallback=lambda: self._fetch_legacy_rows(symbols),
        )

    async def _with_legacy_fallback(self, *, primary, fallback):
        try:
            return await primary()
        except Exception:
            transaction = self.session.get_transaction()
            if transaction is None:
                return await fallback()
            async with self.session.begin_nested():
                try:
                    return await primary()
                except Exception:
                    pass
            return await fallback()

    async def _fetch_extended_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                SELECT
                    symbol,
                    display_name,
                    asset_class,
                    logo_url,
                    tradingview_symbol,
                    coingecko_id,
                    coincap_id,
                    yahoo_symbol,
                    provider,
                    primary_provider,
                    fallback_provider,
                    provider_symbol,
                    exchange,
                    market_region,
                    timezone,
                    base_currency,
                    quote_currency,
                    entitlement_tier,
                    is_delayed,
                    refresh_policy,
                    is_active,
                    metadata
                FROM asset_catalog
                WHERE symbol = ANY(:symbols)
                """
            ),
            {"symbols": symbols},
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def _fetch_legacy_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                SELECT
                    symbol,
                    display_name,
                    asset_class,
                    logo_url,
                    tradingview_symbol,
                    coingecko_id,
                    coincap_id,
                    yahoo_symbol,
                    provider,
                    is_active,
                    metadata
                FROM asset_catalog
                WHERE symbol = ANY(:symbols)
                """
            ),
            {"symbols": symbols},
        )
        rows = []
        for row in result.fetchall():
            payload = dict(row._mapping)
            payload.setdefault("primary_provider", payload.get("provider"))
            payload.setdefault("fallback_provider", None)
            payload.setdefault("provider_symbol", None)
            payload.setdefault("exchange", None)
            payload.setdefault("market_region", None)
            payload.setdefault("timezone", "UTC")
            payload.setdefault("base_currency", None)
            payload.setdefault("quote_currency", None)
            payload.setdefault("entitlement_tier", "internal")
            payload.setdefault("is_delayed", False)
            payload.setdefault("refresh_policy", None)
            rows.append(payload)
        return rows

    async def _search_extended_rows(
        self,
        query: str,
        asset_classes: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        conditions = [
            "(symbol ILIKE :pattern OR display_name ILIKE :pattern)",
            "COALESCE(is_active, TRUE) = TRUE",
        ]
        params: dict[str, Any] = {
            "pattern": f"%{query}%",
            "prefix": f"{query}%",
            "exact": query.upper(),
            "limit": limit,
        }

        if asset_classes:
            conditions.append("LOWER(COALESCE(asset_class, '')) = ANY(:asset_classes)")
            params["asset_classes"] = asset_classes

        sql = f"""
            SELECT
                symbol,
                display_name,
                asset_class,
                logo_url,
                tradingview_symbol,
                coingecko_id,
                coincap_id,
                yahoo_symbol,
                provider,
                primary_provider,
                fallback_provider,
                provider_symbol,
                exchange,
                market_region,
                timezone,
                base_currency,
                quote_currency,
                entitlement_tier,
                is_delayed,
                refresh_policy,
                is_active,
                metadata
            FROM asset_catalog
            WHERE {" AND ".join(conditions)}
            ORDER BY
                CASE
                    WHEN UPPER(symbol) = :exact THEN 0
                    WHEN symbol ILIKE :prefix THEN 1
                    WHEN display_name ILIKE :prefix THEN 2
                    ELSE 3
                END,
                symbol ASC
            LIMIT :limit
        """
        result = await self.session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def _search_legacy_rows(
        self,
        query: str,
        asset_classes: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        conditions = [
            "(symbol ILIKE :pattern OR display_name ILIKE :pattern)",
            "COALESCE(is_active, TRUE) = TRUE",
        ]
        params: dict[str, Any] = {
            "pattern": f"%{query}%",
            "prefix": f"{query}%",
            "exact": query.upper(),
            "limit": limit,
        }

        if asset_classes:
            conditions.append("LOWER(COALESCE(asset_class, '')) = ANY(:asset_classes)")
            params["asset_classes"] = asset_classes

        sql = f"""
            SELECT
                symbol,
                display_name,
                asset_class,
                logo_url,
                tradingview_symbol,
                coingecko_id,
                coincap_id,
                yahoo_symbol,
                provider,
                is_active,
                metadata
            FROM asset_catalog
            WHERE {" AND ".join(conditions)}
            ORDER BY
                CASE
                    WHEN UPPER(symbol) = :exact THEN 0
                    WHEN symbol ILIKE :prefix THEN 1
                    WHEN display_name ILIKE :prefix THEN 2
                    ELSE 3
                END,
                symbol ASC
            LIMIT :limit
        """
        result = await self.session.execute(text(sql), params)
        rows = []
        for row in result.fetchall():
            payload = dict(row._mapping)
            payload.setdefault("primary_provider", payload.get("provider"))
            payload.setdefault("fallback_provider", None)
            payload.setdefault("provider_symbol", None)
            payload.setdefault("exchange", None)
            payload.setdefault("market_region", None)
            payload.setdefault("timezone", "UTC")
            payload.setdefault("base_currency", None)
            payload.setdefault("quote_currency", None)
            payload.setdefault("entitlement_tier", "internal")
            payload.setdefault("is_delayed", False)
            payload.setdefault("refresh_policy", None)
            rows.append(payload)
        return rows
