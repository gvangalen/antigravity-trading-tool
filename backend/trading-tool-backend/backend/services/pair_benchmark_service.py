"""Owner-scoped benchmark category weights and atomic exact-market copies."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite

from sqlalchemy import select, text

from backend.domain.finn_dca_plan_contract import normalize_benchmark_weights
from backend.infrastructure.models import UserIndicatorConfig
from backend.services.pair_indicator_config_service import PairIndicatorConfigService, effective_pair_configs
from backend.services.indicator_config_service import FIXED_BUCKETS
from backend.domain.market_indicator_catalog import get_market_indicator_definition
from backend.domain.macro_indicator_catalog import get_macro_indicator_definition
from backend.domain.technical_indicator_catalog import get_technical_indicator_definition
from backend.utils.scoring_utils import normalize_indicator_name


def _categories(weights):
    return {key.removesuffix("_score"): value for key, value in weights.items()}


async def benchmark_weights(session, user_id: int, market_id: int | None = None):
    """Pair row wins; old user preference is a read-only migration fallback."""
    if market_id is not None:
        result = await session.execute(text("""
            SELECT weights FROM user_market_benchmark_weights
            WHERE user_id=:user_id AND market_id=:market_id
        """), {"user_id": user_id, "market_id": market_id})
        row = result.first()
        if row is not None:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            return normalize_benchmark_weights(value), "market"
        return normalize_benchmark_weights(None), "equal_default"
    result = await session.execute(text("SELECT ai_preferences FROM users WHERE id=:user_id"),
                                   {"user_id": user_id})
    row = result.first()
    if row is None:
        return None, "missing_user"
    preferences = row[0] or {}
    if isinstance(preferences, str):
        preferences = json.loads(preferences)
    if not isinstance(preferences, dict):
        return None, "invalid_preferences"
    custom = preferences.get("intelligence_weights")
    return normalize_benchmark_weights(custom), "legacy_user_preferences" if custom else "equal_default"


async def save_benchmark_weights(session, user_id: int, market_id: int, weights: dict,
                                 *, commit: bool = True, isolated: bool = False):
    normalized = normalize_benchmark_weights(weights)
    if normalized is None or set(weights) != {"market", "macro", "technical"}:
        raise ValueError("invalid_benchmark_weights")
    await session.execute(text("SELECT id FROM users WHERE id=:user_id FOR UPDATE"),
                          {"user_id": user_id})
    await session.execute(text("""
        INSERT INTO user_market_benchmark_weights(user_id, market_id, weights, indicators_isolated, updated_at)
        VALUES (:user_id, :market_id, CAST(:weights AS jsonb), :isolated, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, market_id) DO UPDATE
        SET weights=EXCLUDED.weights,
            indicators_isolated=user_market_benchmark_weights.indicators_isolated OR EXCLUDED.indicators_isolated,
            updated_at=EXCLUDED.updated_at
    """), {"user_id": user_id, "market_id": market_id,
           "weights": json.dumps(_categories(normalized), sort_keys=True), "isolated": isolated})
    if commit:
        await session.commit()
    return normalized


class PairBenchmarkCopyService:
    def __init__(self, session):
        self.session = session
        self.configs = PairIndicatorConfigService(session)

    async def _state(self, user_id, market):
        rows = effective_pair_configs(await self.configs.rows(user_id, market))
        selected = {}
        for (_, category, indicator), row in rows.items():
            selected[(category, indicator)] = {
                "category": category, "indicator": indicator,
                "weight": (row.config_json or {}).get("weight", row.priority / 100),
                "score_mode": (row.config_json or {}).get("score_mode", "standard"),
                "rules": deepcopy((row.config_json or {}).get("rules") or []),
            }
        weights, _ = await benchmark_weights(self.session, user_id, market.id)
        return selected, _categories(weights or normalize_benchmark_weights(None))

    async def preview(self, user_id: int, source_id: int, target_id: int):
        if source_id == target_id:
            raise ValueError("same_market")
        source = await self.configs.market(source_id)
        target = await self.configs.market(target_id)
        if source is None or target is None:
            raise ValueError("exact_market_not_verified")
        source_items, source_weights = await self._state(user_id, source)
        target_items, target_weights = await self._state(user_id, target)
        definitions = {"market": get_market_indicator_definition,
                       "macro": get_macro_indicator_definition,
                       "technical": get_technical_indicator_definition}
        unsupported = [f"{category}:{indicator}" for category, indicator in source_items
                       if category not in definitions or
                       not (definition := definitions[category](indicator)) or not definition.get("active")]
        for (category, indicator), item in source_items.items():
            mode = item["score_mode"]
            weight = item["weight"]
            if mode not in {"standard", "contrarian", "custom"} or (
                type(weight) not in {int, float} or not isfinite(weight) or not 0 <= weight <= 3
            ) or (mode == "custom" and (
                len(item["rules"]) != 5 or any(
                    not isinstance(rule, dict) or
                    rule.get("range_min") != low or rule.get("range_max") != high or
                    type(rule.get("score")) not in {int, float} or
                    not isfinite(rule["score"]) or not 10 <= rule["score"] <= 100
                    for (low, high), rule in zip(FIXED_BUCKETS, item["rules"])
                )
            )):
                unsupported.append(f"{category}:{indicator}")
        unsupported = sorted(set(unsupported))
        state = {"source": source_id, "target": target_id,
                 "source_items": [source_items[key] for key in sorted(source_items)],
                 "target_items": [target_items[key] for key in sorted(target_items)],
                 "source_weights": source_weights, "target_weights": target_weights}
        revision = sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()
        return {"source_market_id": source_id, "target_market_id": target_id,
                "source_pair": f"{source.asset_symbol}/{source.quote_currency}",
                "target_pair": f"{target.asset_symbol}/{target.quote_currency}",
                "indicators": [source_items[key] for key in sorted(source_items)],
                "replace": sorted(f"{category}:{indicator}" for category, indicator in target_items),
                "unsupported": unsupported,
                "source_weights": source_weights, "target_weights": target_weights,
                "revision": revision}

    async def apply(self, user_id: int, source_id: int, target_id: int, revision: str):
        # Serialize copies and pair edits through the owner row. A stale preview
        # cannot overwrite an intervening user change to either market.
        await self.session.execute(text("SELECT id FROM users WHERE id=:user_id FOR UPDATE"),
                                   {"user_id": user_id})
        preview = await self.preview(user_id, source_id, target_id)
        if preview["revision"] != revision:
            raise ValueError("benchmark_preview_changed")
        if preview["unsupported"]:
            raise ValueError("unsupported_indicators_for_target")
        target = await self.configs.market(target_id)
        source_items = {(item["category"], item["indicator"]): item for item in preview["indicators"]}
        source_weights = preview["source_weights"]
        target_items = {tuple(value.split(":", 1)) for value in preview["replace"]}
        existing_rows = (await self.session.execute(select(UserIndicatorConfig).where(
            UserIndicatorConfig.user_id == user_id,
            UserIndicatorConfig.market_id == target_id))).scalars().all()
        pair_rows = {(row.category, normalize_indicator_name(row.indicator)): row for row in existing_rows}
        for key in target_items | set(source_items):
            category, indicator = key
            row = pair_rows.get(key)
            if row is None:
                row = UserIndicatorConfig(user_id=user_id, market_id=target_id,
                                          symbol=target.asset_symbol, category=category,
                                          indicator=indicator, provenance="product_api")
                self.session.add(row)
            item = source_items.get(key)
            row.enabled = item is not None
            if item is not None:
                row.config_json = {"score_mode": item["score_mode"], "weight": item["weight"],
                                   **({"rules": deepcopy(item["rules"])} if item["rules"] else {})}
                row.priority = round(float(item["weight"]) * 100)
            row.updated_at = datetime.utcnow()
        await save_benchmark_weights(self.session, user_id, target_id, source_weights,
                                     commit=False, isolated=True)
        await self.session.commit()
        return {"ok": True, "target_market_id": target_id, "copied": len(source_items)}
