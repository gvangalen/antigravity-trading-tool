"""Fill only genuinely dated source history required by absolute indicator scores."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import MacroData, MarketData
from backend.schemas.market_provider_schema import AssetRecord
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.market_data_provider_registry import MarketDataProviderRegistry
from backend.utils.macro_interpreter import fetch_absolute_macro_history


ABSOLUTE_MACRO_INDICATORS = frozenset({"dxy", "sp500", "gold_price", "oil_price"})
ABSOLUTE_MARKET_INDICATORS = frozenset({"price", "volume"})
REQUIRED_SOURCE_DAYS = 5


class IndicatorHistoryBootstrap:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def market_coverage(self, symbol: str) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        rows = (await self.session.execute(
            select(MarketData.source_observed_at, MarketData.price, MarketData.volume).where(
                MarketData.symbol == symbol,
                MarketData.source_observed_at >= cutoff,
            )
        )).all()
        return {
            "price": len({stamp.date() for stamp, price, _ in rows if stamp and price is not None}),
            "volume": len({stamp.date() for stamp, _, volume in rows if stamp and volume is not None}),
        }

    async def macro_coverage(self, user_id: int, indicator: str) -> int:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
        rows = (await self.session.execute(
            select(MacroData.source_observed_at).where(
                MacroData.user_id == user_id,
                MacroData.name.ilike(indicator),
                MacroData.source_observed_at >= cutoff,
                MacroData.value.is_not(None),
            )
        )).scalars().all()
        return len({stamp.date() for stamp in rows if stamp})

    async def bootstrap_market(self, symbol: str, indicators: set[str]) -> dict:
        normalized_symbol = str(symbol or "").strip().upper()
        requested = indicators & ABSOLUTE_MARKET_INDICATORS
        if not normalized_symbol or not requested:
            return {"inserted": 0, "status": "not_required"}
        coverage = await self.market_coverage(normalized_symbol)
        if all(coverage[name] >= REQUIRED_SOURCE_DAYS for name in requested):
            return {"inserted": 0, "status": "ready", "coverage": coverage}

        asset = AssetRecord(**await AssetCatalogService(self.session).get_asset(normalized_symbol))
        provider = MarketDataProviderRegistry().resolve_for_asset(asset)
        candles = await provider.fetch_candles(asset, "1d" if asset.asset_class == "crypto" else "1day", limit=40)
        today = datetime.now(timezone.utc).date()
        cutoff_day = today - timedelta(days=30)
        existing = (await self.session.execute(
            select(MarketData.source_observed_at, MarketData.price, MarketData.volume).where(
                MarketData.symbol == normalized_symbol,
                MarketData.source_observed_at >= datetime.combine(cutoff_day, time.min),
            )
        )).all()
        existing_days = {
            stamp.date() for stamp, price, volume in existing
            if stamp and all((price if name == "price" else volume) is not None
                             for name in requested)
        }
        inserted = 0
        for candle in candles:
            day = candle.period_start.date()
            if day in existing_days or not cutoff_day <= day < today or not candle.is_final:
                continue
            price = float(candle.close)
            volume = float(candle.volume) if candle.volume is not None else None
            if (not isfinite(price) or price <= 0
                    or (volume is not None and not isfinite(volume))
                    or ("volume" in requested and volume is None)):
                continue
            observed_at = datetime.combine(day, time(23, 59, 59))
            self.session.add(MarketData(
                symbol=normalized_symbol, price=price, volume=volume,
                open=candle.open, high=candle.high, low=candle.low,
                timestamp=observed_at, source_observed_at=observed_at,
            ))
            existing_days.add(day)
            inserted += 1
        if inserted:
            await self.session.commit()
        coverage = await self.market_coverage(normalized_symbol)
        return {"inserted": inserted, "status": (
            "ready" if all(coverage[name] >= REQUIRED_SOURCE_DAYS for name in requested)
            else "insufficient_history"
        ), "coverage": coverage}

    async def bootstrap_macro(self, user_id: int, indicator: str, symbol: str) -> dict:
        name = str(indicator or "").strip().lower()
        if name not in ABSOLUTE_MACRO_INDICATORS:
            return {"inserted": 0, "status": "not_required"}
        coverage = await self.macro_coverage(user_id, name)
        if coverage >= REQUIRED_SOURCE_DAYS:
            return {"inserted": 0, "status": "ready", "observed_days": coverage}

        readings = await asyncio.to_thread(fetch_absolute_macro_history, name)
        today = datetime.now(timezone.utc).date()
        cutoff_day = today - timedelta(days=90)
        existing = (await self.session.execute(
            select(MacroData.source_observed_at).where(
                MacroData.user_id == user_id,
                MacroData.name.ilike(name),
                MacroData.source_observed_at >= datetime.combine(cutoff_day, time.min),
            )
        )).scalars().all()
        existing_days = {stamp.date() for stamp in existing if stamp}
        inserted = 0
        for observed_at, value in readings:
            day = observed_at.date()
            if day in existing_days or not cutoff_day <= day < today or not isfinite(value):
                continue
            self.session.add(MacroData(
                name=name, user_id=user_id, symbol=str(symbol or "BTC").upper(),
                value=value, score=None, timestamp=observed_at,
                source_observed_at=observed_at,
            ))
            existing_days.add(day)
            inserted += 1
        if inserted:
            await self.session.commit()
        coverage = await self.macro_coverage(user_id, name)
        return {"inserted": inserted, "status": (
            "ready" if coverage >= REQUIRED_SOURCE_DAYS else "insufficient_history"
        ), "observed_days": coverage}
