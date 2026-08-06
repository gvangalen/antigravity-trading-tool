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

    async def _fetch_asset_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        try:
            return await self._fetch_extended_rows(symbols)
        except Exception:
            await self.session.rollback()
            return await self._fetch_legacy_rows(symbols)

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
