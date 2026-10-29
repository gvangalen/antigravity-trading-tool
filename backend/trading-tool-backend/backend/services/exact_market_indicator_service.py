"""Materialize owner-selected indicators from one verified trading pair."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from math import isfinite

from sqlalchemy import or_, select, text

from backend.domain.exact_market_technical import calculate_exact_market_technical
from backend.infrastructure.models import (
    MarketData, MarketDataIndicator, TechnicalDataIndicator, UserIndicatorConfig,
)
from backend.services.trading_market_service import TradingMarket
from backend.services.pair_indicator_config_service import effective_pair_configs
from backend.utils.scoring_utils import normalize_indicator_name, score_exact_market_measurement


class ExactMarketIndicatorService:
    def __init__(self, session):
        self.session = session

    async def _configured_owners(self, market: TradingMarket, owner_ids: set[int] | None = None) -> dict[int, dict[str, set[str]]]:
        # Only owners of a plan for this exact pair are refreshed. Their base
        # asset indicator choices carry over; pair-specific choices override
        # the same name without borrowing another pair's measurements.
        owners_result = await self.session.execute(text("""
            SELECT DISTINCT user_id FROM setups WHERE market_id = :market_id
        """), {"market_id": market.id})
        owner_ids = set(owner_ids or ()) | {int(row[0]) for row in owners_result.fetchall()}
        configured_result = await self.session.execute(select(UserIndicatorConfig.user_id).where(
            UserIndicatorConfig.market_id == market.id,
        ).distinct())
        owner_ids.update(int(row[0]) for row in configured_result.all())
        if not owner_ids:
            return {}
        result = await self.session.execute(select(UserIndicatorConfig).where(
            UserIndicatorConfig.user_id.in_(owner_ids),
            UserIndicatorConfig.symbol == market.asset_symbol,
            or_(UserIndicatorConfig.market_id == market.id,
                UserIndicatorConfig.market_id.is_(None)),
            UserIndicatorConfig.category.in_(("market", "technical")),
        ))
        by_owner: dict[int, dict[str, set[str]]] = {
            owner_id: {"market": set(), "technical": set()} for owner_id in owner_ids
        }
        for config in effective_pair_configs(result.scalars().all()).values():
            by_owner[int(config.user_id)][str(config.category)].add(
                normalize_indicator_name(config.indicator))
        return by_owner

    async def _source_values(self, market: TradingMarket) -> tuple[dict, dict, datetime | None, datetime | None]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        latest = (await self.session.execute(select(MarketData).where(
            MarketData.market_id == market.id,
            MarketData.source_observed_at.is_not(None),
            MarketData.source_observed_at <= now,
        ).order_by(MarketData.source_observed_at.desc(), MarketData.id.desc()).limit(1))).scalars().first()
        if latest is None:
            return {}, {}, None, None
        market_values = {"price": latest.price, "volume": latest.volume,
                         "change_24h": latest.change_24h}
        today = datetime.combine(now.date(), time.min)
        result = await self.session.execute(select(MarketData).where(
            MarketData.market_id == market.id,
            MarketData.source_observed_at >= today - timedelta(days=400),
            MarketData.source_observed_at < today,
            MarketData.price.is_not(None),
        ).order_by(MarketData.source_observed_at, MarketData.id))
        by_day = {}
        for row in result.scalars().all():
            moment = row.source_observed_at
            if moment and all(value is not None for value in (row.high, row.low, row.price)):
                by_day[moment.date()] = {"high": row.high, "low": row.low,
                                         "close": row.price, "observed_at": moment}
        candles = [by_day[day] for day in sorted(by_day)]
        technical_values = calculate_exact_market_technical(candles)
        technical_moment = candles[-1]["observed_at"] if candles else None
        return market_values, technical_values, latest.source_observed_at, technical_moment

    async def _upsert_reading(self, model, *, market: TradingMarket, user_id: int,
                              name: str, value: float, observed_at: datetime,
                              scored: dict) -> None:
        column = model.name if model is MarketDataIndicator else model.indicator
        existing = (await self.session.execute(select(model).where(
            model.user_id == user_id, model.market_id == market.id,
            column == name,
        ).order_by(model.source_observed_at.desc(), model.id.desc()).limit(1))).scalars().first()
        fields = {"value": value, "score": scored.get("score"),
                  "source_observed_at": observed_at, "timestamp": observed_at}
        if model is MarketDataIndicator:
            fields.update({"trend": scored.get("trend"),
                           "interpretation": scored.get("interpretation"),
                           "action": scored.get("action")})
        else:
            fields.update({"advies": scored.get("trend"),
                           "uitleg": scored.get("interpretation")})
        if (existing is not None and existing.source_observed_at is not None
                and existing.source_observed_at.date() == observed_at.date()):
            for key, field_value in fields.items():
                setattr(existing, key, field_value)
            return
        self.session.add(model(
            user_id=user_id, symbol=market.asset_symbol, market_id=market.id,
            **({"name": name} if model is MarketDataIndicator else {"indicator": name}),
            **fields,
        ))

    async def materialize(self, market: TradingMarket, owner_ids: set[int] | None = None) -> dict:
        owners = await self._configured_owners(market, owner_ids)
        if not owners:
            return {"market_id": market.id, "owners": [], "written": 0}
        market_values, technical_values, market_at, technical_at = await self._source_values(market)
        written = 0
        for user_id, categories in owners.items():
            for category, values, observed_at, model in (
                ("market", market_values, market_at, MarketDataIndicator),
                ("technical", technical_values, technical_at, TechnicalDataIndicator),
            ):
                if observed_at is None:
                    continue
                for name in categories[category]:
                    raw = values.get(name)
                    if raw is None:
                        continue
                    value = float(raw)
                    if not isfinite(value):
                        continue
                    scored = await asyncio.to_thread(
                        score_exact_market_measurement, category, name, value,
                        user_id, market.asset_symbol, market.id)
                    await self._upsert_reading(
                        model, market=market, user_id=user_id, name=name,
                        value=value, observed_at=observed_at, scored=scored)
                    written += 1
        if written:
            await self.session.commit()
        return {"market_id": market.id, "owners": sorted(owners), "written": written}
