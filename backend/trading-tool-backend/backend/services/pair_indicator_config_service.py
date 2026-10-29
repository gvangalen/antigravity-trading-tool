"""Owner preferences for one verified trading market.

Base-asset preferences remain a fallback for older plans. An explicit pair row,
including a disabled row, always takes precedence over that fallback.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from backend.infrastructure.models import TradingMarket, UserIndicatorConfig
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.services.indicator_config_service import IndicatorConfigService, FIXED_BUCKETS, _clamp_weight
from backend.utils.scoring_utils import normalize_indicator_name


def effective_pair_configs(rows):
    """Return the effective enabled selection by category and indicator."""
    result = {}
    for row in sorted(rows, key=lambda value: value.market_id is not None):
        result[(row.user_id, row.category, normalize_indicator_name(row.indicator))] = row
    return {key: value for key, value in result.items() if value.enabled}


class PairIndicatorConfigService:
    def __init__(self, session):
        self.session = session
        self.base = IndicatorConfigService(IndicatorConfigRepository(session))

    async def market(self, market_id: int):
        return (await self.session.execute(select(TradingMarket).where(
            TradingMarket.id == market_id,
            TradingMarket.is_active.is_(True),
            TradingMarket.venue == "BINANCE",
        ))).scalars().first()

    async def rows(self, user_id: int, market):
        return (await self.session.execute(select(UserIndicatorConfig).where(
            UserIndicatorConfig.user_id == user_id,
            UserIndicatorConfig.symbol == market.asset_symbol,
            (UserIndicatorConfig.market_id == market.id) | UserIndicatorConfig.market_id.is_(None),
        ))).scalars().all()

    async def get(self, user_id: int, market, category: str, indicator: str):
        rows = await self.rows(user_id, market)
        row = effective_pair_configs(rows).get((user_id, category, indicator))
        default = await self.base.get_indicator_config(category, indicator, user_id, market.asset_symbol)
        if row is None:
            return default.dict()
        metadata = row.config_json or {}
        rules = self.base._rules_to_fixed_buckets(metadata.get("rules") or
            await self.base.repository.get_system_indicator_rules(category, indicator))
        return {"category": category, "indicator": indicator,
                "score_mode": metadata.get("score_mode", "standard"),
                "weight": metadata.get("weight", row.priority / 100),
                "rules": [rule.dict() for rule in rules]}

    async def save(self, user_id: int, market, category: str, indicator: str,
                   *, mode: str, score_mode: str, weight: float, rules: list[dict]):
        rows = await self.rows(user_id, market)
        pair_row = next((row for row in rows if row.market_id == market.id
                         and row.category == category
                         and normalize_indicator_name(row.indicator) == indicator), None)
        if mode == "add" and pair_row is not None and pair_row.enabled:
            raise ValueError("indicator_already_configured_for_pair")
        if mode == "edit" and pair_row is None and (user_id, category, indicator) not in effective_pair_configs(rows):
            raise ValueError("indicator_not_configured_for_pair")
        if score_mode in {"standard", "contrarian"}:
            templates = await self.base.repository.get_system_indicator_rules(category, indicator)
            if not self.base._has_complete_rules(templates):
                raise ValueError("indicator_score_rules_unavailable")
            metadata = {"score_mode": score_mode, "weight": _clamp_weight(weight)}
        elif score_mode == "custom":
            if len(rules) != 5:
                raise ValueError("indicator_requires_five_rules")
            normalized = []
            for (low, high), rule in zip(FIXED_BUCKETS, rules):
                try:
                    score = int(rule["score"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("invalid_indicator_score") from exc
                if not 10 <= score <= 100:
                    raise ValueError("invalid_indicator_score")
                normalized.append({"range_min": low, "range_max": high, "score": score,
                                   "trend": rule.get("trend")})
            metadata = {"score_mode": "custom", "weight": _clamp_weight(weight),
                        "rules": normalized}
        else:
            raise ValueError("invalid_score_mode")
        if pair_row is None:
            pair_row = UserIndicatorConfig(user_id=user_id, market_id=market.id,
                                           symbol=market.asset_symbol, category=category,
                                           indicator=indicator, provenance="product_api")
            self.session.add(pair_row)
        pair_row.enabled = True
        pair_row.config_json = metadata
        pair_row.priority = round(metadata["weight"] * 100)
        pair_row.updated_at = datetime.utcnow()
        await self.session.commit()
        return pair_row

    async def disable(self, user_id: int, market, category: str, indicator: str):
        rows = await self.rows(user_id, market)
        pair_row = next((row for row in rows if row.market_id == market.id
                         and row.category == category
                         and normalize_indicator_name(row.indicator) == indicator), None)
        if pair_row is None:
            pair_row = UserIndicatorConfig(user_id=user_id, market_id=market.id,
                                           symbol=market.asset_symbol, category=category,
                                           indicator=indicator, provenance="product_api",
                                           config_json={})
            self.session.add(pair_row)
        pair_row.enabled = False
        pair_row.updated_at = datetime.utcnow()
        await self.session.commit()
