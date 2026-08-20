from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text

from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.schemas.bot_schema import BotConfigUpdateSchema, TradePlanUpsertSchema
from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.services.bot_service import BotService
from backend.services.indicator_config_service import IndicatorConfigService
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService
from backend.services.finn_v2_flag_service import FinnV2FlagService


AdapterFn = Callable[[int, dict], Awaitable[dict]]


class FinnV2ActionAdapterRegistry:
    def __init__(self, session, *, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.indicators = IndicatorConfigService(IndicatorConfigRepository(session))
        self.setups = SetupService(session)
        self.strategies = StrategyService(session)
        self.bots = BotService(session)

    def get(self, operation_type: str) -> Optional[AdapterFn]:
        mapping = {
            "update_indicator_configuration": self._update_indicator_configuration,
            "create_setup": self._create_setup,
            "update_setup": self._update_setup,
            "update_strategy": self._update_strategy,
            "watchlist_add": self._watchlist_add,
            "watchlist_remove": self._watchlist_remove,
            "save_trade_plan": self._save_trade_plan,
            "activate_paper_bot": self._activate_paper_bot,
            "activate_live_bot": self._activate_live_bot,
        }
        return mapping.get(operation_type)

    async def postcondition_hash(self, operation_type: str, *, user_id: int, payload: dict) -> str:
        canonical = json.dumps({"operation_type": operation_type, "payload": payload}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _update_indicator_configuration(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_indicator_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        after = change.get("after") or {}
        if "rules" in after:
            await self.indicators.save_custom_rules(
                category=str(after.get("category") or "technical"),
                indicator=str(after.get("indicator_id") or change.get("indicator_id")),
                user_id=user_id,
                rules=after.get("rules") or [],
                weight=float(after.get("weight") or 1.0),
            )
        else:
            await self.indicators.update_indicator_settings(
                category=str(after.get("category") or "technical"),
                indicator=str(after.get("indicator_id") or change.get("indicator_id")),
                user_id=user_id,
                score_mode=str(after.get("score_mode") or "standard"),
                weight=float(after.get("weight") or 1.0),
            )
        return {"ok": True}

    async def _update_setup(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_setup_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        return await self.setups.update_setup(int(change["setup_id"]), dict(change.get("changed_fields") or {}), user_id)

    async def _create_setup(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_setup_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        raw_payload = dict(change.get("setup_fields") or {})
        setup_payload = SetupCreateSchema.parse_obj(raw_payload)
        return await self.setups.save_setup(setup_payload, raw_payload, user_id)

    async def _update_strategy(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_strategy_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        return await self.strategies.update_strategy(int(change["strategy_id"]), dict(change.get("changed_fields") or {}), user_id)

    async def _watchlist_add(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_watchlist_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        asset = str(change.get("asset") or payload.get("target", {}).get("asset") or "").strip().upper()
        if not asset:
            raise ValueError("asset_required")
        await self.session.execute(
            text(
                """
                INSERT INTO watchlists (user_id, symbol, created_at)
                SELECT :user_id, :symbol, NOW()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM watchlists
                    WHERE user_id = :user_id
                      AND symbol = :symbol
                )
                """
            ),
            {"user_id": user_id, "symbol": asset},
        )
        return {"ok": True, "asset": asset, "operation": "watchlist_add"}

    async def _watchlist_remove(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_watchlist_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        asset = str(change.get("asset") or payload.get("target", {}).get("asset") or "").strip().upper()
        if not asset:
            raise ValueError("asset_required")
        await self.session.execute(
            text("DELETE FROM watchlists WHERE user_id = :user_id AND symbol = :symbol"),
            {"user_id": user_id, "symbol": asset},
        )
        return {"ok": True, "asset": asset, "operation": "watchlist_remove"}

    async def _save_trade_plan(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_trade_plan_changes_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        trade_plan = TradePlanUpsertSchema.parse_obj(change.get("changed_fields") or change)
        return await self.bots.save_trade_plan(int(change.get("plan_id") or payload.get("target", {}).get("target_id") or 0), trade_plan, user_id)

    async def _activate_paper_bot(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_paper_bot_activation_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        update = BotConfigUpdateSchema.parse_obj({"is_live": False, "mode": "paper", "is_active": True})
        return await self.bots.update_bot_config(int(change["bot_id"]), update, user_id)

    async def _activate_live_bot(self, user_id: int, payload: dict) -> dict:
        if not self.flags.execute_live_bot_activation_enabled():
            raise ValueError("execution_adapter_unavailable")
        change = payload["change"]
        update = BotConfigUpdateSchema.parse_obj({"is_live": True, "mode": "live", "is_active": True})
        return await self.bots.update_bot_config(int(change["bot_id"]), update, user_id)
