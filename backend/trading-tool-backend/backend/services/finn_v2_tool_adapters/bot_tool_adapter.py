from __future__ import annotations

from datetime import datetime


class BotToolAdapter:
    async def execute_linked_bot(self, *, bot: dict, resolution_source: str, **_kwargs):
        payload = {
            "bot_id": bot.get("id"),
            "name": bot.get("name"),
            "symbol": bot.get("symbol") or bot.get("setup_symbol"),
            "strategy_id": bot.get("strategy_id"),
            "is_active": bool(bot.get("is_active")),
            "is_live": bool(bot.get("is_live")),
            "mode": bot.get("mode"),
        }
        return {"data": payload, "summary": {"title": "linked_bot", "bot_id": payload["bot_id"], "strategy_id": payload["strategy_id"]}, "as_of": bot.get("updated_at"), "resolution_source": resolution_source}

    async def execute_status(self, *, bot: dict, **_kwargs):
        last_run = bot.get("last_run")
        payload = {
            "bot_id": bot.get("id"),
            "is_active": bool(bot.get("is_active")),
            "is_live": bool(bot.get("is_live")),
            "last_run": last_run,
            "mode": bot.get("mode"),
            "cadence": bot.get("cadence"),
        }
        return {"data": payload, "summary": {"title": "bot_status", "bot_id": payload["bot_id"], "is_active": payload["is_active"]}, "as_of": last_run if isinstance(last_run, datetime) else bot.get("updated_at")}

