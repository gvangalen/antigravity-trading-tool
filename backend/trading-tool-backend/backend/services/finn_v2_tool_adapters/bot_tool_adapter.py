from __future__ import annotations

from datetime import datetime

from backend.schemas.finn_v2_evidence_schema import BotStatusData, LinkedBotData


class BotToolAdapter:
    async def execute_linked_bot(self, *, bot: dict, resolution_source: str, **_kwargs):
        payload = LinkedBotData(
            bot_id=bot.get("id"),
            name=bot.get("name"),
            symbol=bot.get("symbol") or bot.get("setup_symbol"),
            strategy_id=bot.get("strategy_id"),
            is_active=bool(bot.get("is_active")),
            is_live=bool(bot.get("is_live")),
            mode=bot.get("mode"),
        )
        return {
            "data": payload,
            "summary": {"title": "linked_bot", "bot_id": payload.bot_id, "strategy_id": payload.strategy_id},
            "as_of": bot.get("updated_at"),
            "resolution_source": resolution_source,
            "source": "bot_configs",
            "schema_name": "LinkedBotData",
            "entity_type": "bot",
            "entity_id": str(payload.bot_id),
            "asset": payload.symbol,
        }

    async def execute_status(self, *, bot: dict, **_kwargs):
        last_run = bot.get("last_run")
        payload = BotStatusData(
            bot_id=bot.get("id"),
            is_active=bool(bot.get("is_active")),
            is_live=bool(bot.get("is_live")),
            last_run=last_run if isinstance(last_run, datetime) else None,
            mode=bot.get("mode"),
            cadence=bot.get("cadence"),
        )
        return {
            "data": payload,
            "summary": {"title": "bot_status", "bot_id": payload.bot_id, "is_active": payload.is_active},
            "as_of": last_run if isinstance(last_run, datetime) else bot.get("updated_at"),
            "source": "bot_configs",
            "schema_name": "BotStatusData",
            "entity_type": "bot_status",
            "entity_id": str(payload.bot_id),
            "asset": bot.get("symbol") or bot.get("setup_symbol"),
        }
