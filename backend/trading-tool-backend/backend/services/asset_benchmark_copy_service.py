"""Preview and copy owner-scoped benchmark settings across asset classes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite

from sqlalchemy import select, text

from backend.domain.market_indicator_catalog import get_market_indicator_definition
from backend.domain.macro_indicator_catalog import get_macro_indicator_definition, macro_indicator_supports_symbol
from backend.domain.technical_indicator_catalog import get_technical_indicator_definition
from backend.infrastructure.models import TradingMarket, UserIndicatorConfig
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.indicator_config_service import FIXED_BUCKETS, IndicatorConfigService
from backend.services.pair_benchmark_service import (
    PairBenchmarkCopyService, benchmark_weights, save_asset_benchmark_weights,
    save_benchmark_weights,
)
from backend.services.pair_indicator_config_service import PairIndicatorConfigService, effective_pair_configs
from backend.utils.scoring_utils import normalize_indicator_name


DEFINITIONS = {"market": get_market_indicator_definition,
               "macro": get_macro_indicator_definition,
               "technical": get_technical_indicator_definition}


class AssetBenchmarkCopyService:
    def __init__(self, session):
        self.session = session
        self.pairs = PairIndicatorConfigService(session)
        self.pair_copy = PairBenchmarkCopyService(session)
        self.catalog = AssetCatalogService(session)
        self.indicators = IndicatorConfigService(IndicatorConfigRepository(session))

    async def _scope(self, key: str):
        kind, separator, value = str(key or "").partition(":")
        if not separator:
            raise ValueError("invalid_benchmark_scope")
        if kind == "market":
            try:
                market_id = int(value)
            except ValueError as exc:
                raise ValueError("invalid_benchmark_scope") from exc
            if market_id <= 0 or (market := await self.pairs.market(market_id)) is None:
                raise ValueError("benchmark_scope_not_found")
            symbol = str(market.asset_symbol).upper()
            return {"key": f"market:{market_id}", "symbol": symbol, "market_id": market_id,
                    "market": market, "asset_class": "crypto",
                    "label": f"{symbol}/{market.quote_currency}"}
        if kind != "asset" or not value or len(value) > 20 or not value.isalnum():
            raise ValueError("invalid_benchmark_scope")
        symbol = value.upper()
        asset = await self.catalog.get_asset(symbol)
        if (asset.get("provider") == "fallback" or not asset.get("is_active", True)
                or asset.get("asset_class") not in {"crypto", "stock", "etf", "index"}):
            raise ValueError("benchmark_scope_not_found")
        return {"key": f"asset:{symbol}", "symbol": symbol, "market_id": None,
                "market": None, "asset_class": asset["asset_class"], "label": symbol}

    async def sources(self, user_id: int, target_key: str):
        target = await self._scope(target_key)
        result = await self.session.execute(select(UserIndicatorConfig.symbol, UserIndicatorConfig.market_id).where(
            UserIndicatorConfig.user_id == user_id, UserIndicatorConfig.enabled.is_(True),
            UserIndicatorConfig.symbol.is_not(None)))
        selected_rows = result.all()
        keys = {f"market:{market_id}" if market_id is not None else f"asset:{str(symbol).upper()}"
                for symbol, market_id in selected_rows}
        base_symbols = {str(symbol).upper() for symbol, market_id in selected_rows if market_id is None}
        if base_symbols:
            inherited = await self.session.execute(select(TradingMarket).where(
                TradingMarket.asset_symbol.in_(base_symbols),
                TradingMarket.is_active.is_(True), TradingMarket.venue == "BINANCE"))
            for market in inherited.scalars().all():
                pair_rows = await self.pairs.rows(user_id, market)
                if effective_pair_configs(pair_rows):
                    keys.add(f"market:{market.id}")
        weighted = await self.session.execute(text("""
            SELECT market_id FROM user_market_benchmark_weights WHERE user_id=:user_id
        """), {"user_id": user_id})
        keys.update(f"market:{row[0]}" for row in weighted.all())
        rows = []
        for key in sorted(keys):
            if key == target["key"]:
                continue
            try:
                scope = await self._scope(key)
            except ValueError:
                continue
            if scope["market_id"] is not None and target["market_id"] is None and scope["symbol"] == target["symbol"]:
                continue
            rows.append({"key": key, "label": scope["label"], "asset_class": scope["asset_class"]})
        return sorted(rows, key=lambda row: row["label"])

    async def _state(self, user_id: int, scope: dict):
        if scope["market_id"] is not None:
            return await self.pair_copy._state(user_id, scope["market"])
        result = await self.session.execute(select(UserIndicatorConfig).where(
            UserIndicatorConfig.user_id == user_id,
            UserIndicatorConfig.symbol == scope["symbol"],
            UserIndicatorConfig.market_id.is_(None),
            UserIndicatorConfig.enabled.is_(True)))
        selected = {}
        for row in result.scalars().all():
            key = (str(row.category).lower(), normalize_indicator_name(row.indicator))
            selected[key] = {"category": key[0], "indicator": key[1],
                             "weight": (row.config_json or {}).get("weight", row.priority / 100),
                             "score_mode": (row.config_json or {}).get("score_mode", "standard"),
                             "rules": deepcopy((row.config_json or {}).get("rules") or [])}
        weights, _ = await benchmark_weights(self.session, user_id, symbol=scope["symbol"])
        return selected, {key.removesuffix("_score"): value for key, value in (weights or {}).items()}

    async def _unsupported_reason(self, item: dict, source: dict, target: dict):
        category, indicator = item["category"], item["indicator"]
        definition = DEFINITIONS.get(category, lambda _: None)(indicator)
        if not definition or not definition.get("active"):
            return "indicator_unavailable"
        if category == "macro" and not macro_indicator_supports_symbol(indicator, target["symbol"]):
            return "btc_only_source"
        if category == "technical" and target["asset_class"] not in {"crypto", "stock", "etf", "index"}:
            return "technical_provider_unavailable"
        weight, mode = item["weight"], item["score_mode"]
        if type(weight) not in {int, float} or not isfinite(weight) or not 0 <= weight <= 3:
            return "invalid_indicator_weight"
        if mode not in {"standard", "contrarian", "custom"}:
            return "invalid_score_mode"
        if mode == "custom":
            if source["asset_class"] != target["asset_class"]:
                return "custom_rules_need_review"
            rules = item["rules"]
            if len(rules) != 5 or any(
                not isinstance(rule, dict) or rule.get("range_min") != low or
                rule.get("range_max") != high or type(rule.get("score")) not in {int, float} or
                not isfinite(rule["score"]) or not 10 <= rule["score"] <= 100
                for (low, high), rule in zip(FIXED_BUCKETS, rules)
            ):
                return "invalid_custom_rules"
        else:
            templates = await self.indicators.repository.get_system_indicator_rules(category, indicator)
            if not self.indicators._has_complete_rules(templates):
                return "score_rules_unavailable"
        return None

    async def preview(self, user_id: int, source_key: str, target_key: str):
        source = await self._scope(source_key)
        target = await self._scope(target_key)
        if source["key"] == target["key"]:
            raise ValueError("same_benchmark_scope")
        if source["market_id"] is not None and target["market_id"] is None and source["symbol"] == target["symbol"]:
            raise ValueError("source_pair_inherits_target_asset")
        source_items, source_weights = await self._state(user_id, source)
        target_items, target_weights = await self._state(user_id, target)
        included, unsupported = [], []
        for key in sorted(source_items):
            item = source_items[key]
            reason = await self._unsupported_reason(item, source, target)
            if reason:
                unsupported.append({"indicator": f"{item['category']}:{item['indicator']}", "reason": reason})
            else:
                included.append(item)
        state = {"source": source["key"], "target": target["key"],
                 "source_items": [source_items[key] for key in sorted(source_items)],
                 "target_items": [target_items[key] for key in sorted(target_items)],
                 "source_weights": source_weights, "target_weights": target_weights}
        return {"source_key": source["key"], "target_key": target["key"],
                "source_pair": source["label"], "target_pair": target["label"],
                "indicators": included, "unsupported": unsupported,
                "replace": [f"{category}:{indicator}" for category, indicator in sorted(target_items)],
                "source_weights": source_weights, "target_weights": target_weights,
                "revision": sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()}

    async def apply(self, user_id: int, source_key: str, target_key: str, revision: str):
        await self.session.execute(text("SELECT id FROM users WHERE id=:user_id FOR UPDATE"),
                                   {"user_id": user_id})
        preview = await self.preview(user_id, source_key, target_key)
        if preview["revision"] != revision:
            raise ValueError("benchmark_preview_changed")
        if not preview["indicators"]:
            raise ValueError("no_compatible_indicators")
        target = await self._scope(target_key)
        market_id = target["market_id"]
        result = await self.session.execute(select(UserIndicatorConfig).where(
            UserIndicatorConfig.user_id == user_id,
            UserIndicatorConfig.symbol == target["symbol"],
            UserIndicatorConfig.market_id == market_id if market_id is not None else UserIndicatorConfig.market_id.is_(None)))
        rows = {(row.category, normalize_indicator_name(row.indicator)): row for row in result.scalars().all()}
        selected = {(item["category"], item["indicator"]): item for item in preview["indicators"]}
        for key in set(rows) | selected.keys():
            category, indicator = key
            row = rows.get(key)
            if row is None:
                row = UserIndicatorConfig(user_id=user_id, symbol=target["symbol"],
                                          market_id=market_id, asset_class=target["asset_class"],
                                          category=category, indicator=indicator, provenance="product_api")
                self.session.add(row)
            item = selected.get(key)
            row.enabled = item is not None
            if item:
                row.priority = round(float(item["weight"]) * 100)
                row.config_json = {"score_mode": item["score_mode"], "weight": item["weight"],
                                   **({"rules": deepcopy(item["rules"])} if item["rules"] else {})}
            row.updated_at = datetime.utcnow()
        if market_id is not None:
            await save_benchmark_weights(self.session, user_id, market_id,
                                         preview["source_weights"], commit=False, isolated=True)
        else:
            await save_asset_benchmark_weights(self.session, user_id, target["symbol"],
                                               preview["source_weights"], commit=False)
        await self.session.commit()
        return {"ok": True, "target_key": target["key"], "symbol": target["symbol"],
                "market_id": market_id, "copied": len(selected), "skipped": preview["unsupported"]}
