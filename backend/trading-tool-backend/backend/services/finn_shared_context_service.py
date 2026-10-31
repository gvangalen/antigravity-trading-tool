"""One owner-scoped fact snapshot for FINN chat, Today and reports.

This service does not write state or generate prose. The measured benchmark
and setup-match service remains the authority for score freshness and match
ranking; missing measurements never become zeroes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.finn_v2_tool_adapters.indicator_tool_adapter import IndicatorToolAdapter
from backend.services.setup_market_match_service import SetupMarketMatchService
from backend.services.setup_market_match_service import verified_indicator_evidence
from backend.services.pair_indicator_config_service import PairIndicatorConfigService, effective_pair_configs
from backend.utils.scoring_utils import score_source_is_fresh
from backend.services.trader_profile_service import normalize_trader_context, normalize_trader_profile_preferences


class FinnSharedContextService:
    def __init__(self, session):
        self.session = session
        self.setups = SetupRepository(session)
        self.strategies = StrategyRepository(session)
        self.bots = BotRepository(session)
        self.market_data = MarketDataRepository(session)
        self.users = UserRepository(session)
        self.matches = SetupMarketMatchService(session)
        self.indicators = IndicatorToolAdapter(session)

    async def benchmark_for_asset(self, user_id: int, symbol: str, *, setups=None,
                                  market_id: int | None = None) -> dict[str, Any]:
        return await self.matches.for_asset(user_id, symbol, setups=setups, market_id=market_id)

    async def for_user(self, user_id: int, *, symbol: str | None = None) -> dict[str, Any]:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise LookupError("user_not_found")
        preferences = getattr(user, "ai_preferences", {}) or {}
        profile = normalize_trader_profile_preferences(preferences)
        owned_setups = [dict(row) for row in await self.setups.get_all_setups(user_id)]
        owned_strategies = [dict(row) for row in await self.strategies.query_strategies(user_id, {})]
        owned_bots = [dict(row) for row in await self.bots.get_bot_configs(user_id)]

        if symbol:
            scopes = [(str(symbol).strip().upper(), None)]
        else:
            result = await self.session.execute(text("""
                SELECT symbol, NULL::bigint AS market_id FROM watchlists WHERE user_id = :user_id
                UNION SELECT symbol, market_id FROM user_indicator_configs
                WHERE user_id = :user_id AND enabled = TRUE AND symbol IS NOT NULL
            """), {"user_id": user_id})
            scopes = {(str(row[0]).strip().upper(), row[1] if len(row) > 1 else None)
                      for row in result.fetchall() if row[0]}
            scopes.update((str(row.get("symbol") or "").strip().upper(), row.get("market_id"))
                          for row in owned_setups)
            scopes = {(asset, market_id) for asset, market_id in scopes if asset}
            exact_symbols = {asset for asset, market_id in scopes if market_id is not None}
            scopes = sorted(((asset, market_id) for asset, market_id in scopes
                             if market_id is not None or asset not in exact_symbols),
                            key=lambda scope: (scope[0], scope[1] or 0))

        assets = []
        for asset, market_id in scopes:
            asset_setups = [row for row in owned_setups
                            if str(row.get("symbol") or "").upper() == asset
                            and (market_id is None or row.get("market_id") == market_id)]
            setup_ids = {int(row["id"]) for row in asset_setups if row.get("id") is not None}
            asset_strategies = [row for row in owned_strategies if row.get("setup_id") in setup_ids]
            strategy_ids = {int(row["id"]) for row in asset_strategies if row.get("id") is not None}
            asset_bots = [row for row in owned_bots if row.get("strategy_id") in strategy_ids]
            benchmark = await self.benchmark_for_asset(user_id, asset, setups=asset_setups,
                                                       market_id=market_id)
            # Read values from the same score row that passed the freshness and
            # configuration checks. A later reading must not be relabelled as
            # evidence for this report's saved score.
            verified_evidence = verified_indicator_evidence(
                benchmark, self.matches.last_source_row,
            )
            price_row = (await self.market_data.get_latest_exact_market_snapshot(market_id)
                         if market_id is not None else await self.market_data.get_latest_snapshot(asset))
            price_as_of = getattr(price_row, "source_observed_at", None)
            price_fresh = score_source_is_fresh("market", "price", price_as_of, symbol=asset)
            market_snapshot = {
                "source_status": "fresh" if price_fresh else "stale_or_missing",
                "as_of": price_as_of,
                "price": float(price_row.price) if price_fresh and price_row.price is not None else None,
                "change_24h": float(price_row.change_24h) if price_fresh and price_row.change_24h is not None else None,
                "volume": float(price_row.volume) if price_fresh and price_row.volume is not None else None,
            } if price_row is not None else {"source_status": "missing", "as_of": None,
                                              "price": None, "change_24h": None, "volume": None}
            pair_label = None
            try:
                if market_id is None:
                    indicator_result = await self.indicators.execute(user_id=user_id, asset=asset)
                    configuration = jsonable_encoder(indicator_result["data"])
                else:
                    market = await PairIndicatorConfigService(self.session).market(market_id)
                    if market is None or market.asset_symbol != asset:
                        raise LookupError("exact_market_not_verified")
                    pair_label = f"{asset}/{market.quote_currency}"
                    selected = effective_pair_configs(
                        await PairIndicatorConfigService(self.session).rows(user_id, market))
                    configuration = {category: [
                        {"indicator": name, "enabled": True}
                        for (owner, group, name) in selected if owner == user_id and group == category
                    ] for category in ("market", "macro", "technical")}
                configuration_status = "available"
            except Exception:
                # A failed lookup cannot be interpreted as no configuration.
                configuration = None
                configuration_status = "unknown"
            assets.append({
                "symbol": asset,
                "market_id": market_id,
                "pair": pair_label,
                "indicator_configuration": configuration,
                "indicator_lookup_status": configuration_status,
                "benchmark": benchmark,
                "verified_indicator_evidence": verified_evidence,
                "market_snapshot": market_snapshot,
                "setups": asset_setups,
                "strategies": asset_strategies,
                "bots": asset_bots,
            })
        return jsonable_encoder({
            "context_version": "finn_shared_context.v1",
            "owner_user_id": user_id,
            "observed_at": datetime.now(timezone.utc),
            "locale": str(preferences.get("locale") or "nl").lower().split("-", 1)[0],
            "profile": profile,
            "trader_context": normalize_trader_context(preferences.get("trader_context")),
            "assets": assets,
        })
