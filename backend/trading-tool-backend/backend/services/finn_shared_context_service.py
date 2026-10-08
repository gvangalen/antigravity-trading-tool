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
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.finn_v2_tool_adapters.indicator_tool_adapter import IndicatorToolAdapter
from backend.services.setup_market_match_service import SetupMarketMatchService
from backend.services.trader_profile_service import normalize_trader_context, normalize_trader_profile_preferences


class FinnSharedContextService:
    def __init__(self, session):
        self.session = session
        self.setups = SetupRepository(session)
        self.strategies = StrategyRepository(session)
        self.bots = BotRepository(session)
        self.users = UserRepository(session)
        self.matches = SetupMarketMatchService(session)
        self.indicators = IndicatorToolAdapter(session)

    async def benchmark_for_asset(self, user_id: int, symbol: str, *, setups=None) -> dict[str, Any]:
        return await self.matches.for_asset(user_id, symbol, setups=setups)

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
            symbols = [str(symbol).strip().upper()]
        else:
            result = await self.session.execute(text("""
                SELECT symbol FROM watchlists WHERE user_id = :user_id
                UNION SELECT symbol FROM user_indicator_configs
                WHERE user_id = :user_id AND enabled = TRUE AND symbol IS NOT NULL
            """), {"user_id": user_id})
            symbols = sorted({
                *(str(row[0]).strip().upper() for row in result.fetchall() if row[0]),
                *(str(row.get("symbol") or "").strip().upper() for row in owned_setups),
            } - {""})

        assets = []
        for asset in symbols:
            asset_setups = [row for row in owned_setups if str(row.get("symbol") or "").upper() == asset]
            setup_ids = {int(row["id"]) for row in asset_setups if row.get("id") is not None}
            asset_strategies = [row for row in owned_strategies if row.get("setup_id") in setup_ids]
            strategy_ids = {int(row["id"]) for row in asset_strategies if row.get("id") is not None}
            asset_bots = [row for row in owned_bots if row.get("strategy_id") in strategy_ids]
            benchmark = await self.benchmark_for_asset(user_id, asset, setups=owned_setups)
            try:
                indicator_result = await self.indicators.execute(user_id=user_id, asset=asset)
                # The evidence schema is a Pydantic v1 model in the deployed
                # runtime. FastAPI's encoder supports both v1 and v2; calling
                # model_dump here made every successful lookup appear unknown.
                configuration = jsonable_encoder(indicator_result["data"])
                configuration_status = "available"
            except Exception:
                # A failed lookup cannot be interpreted as no configuration.
                configuration = None
                configuration_status = "unknown"
            assets.append({
                "symbol": asset,
                "indicator_configuration": configuration,
                "indicator_lookup_status": configuration_status,
                "benchmark": benchmark,
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
