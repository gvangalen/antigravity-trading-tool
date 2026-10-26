from __future__ import annotations

from datetime import datetime
import json

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.bot_service import BotService

from backend.schemas.finn_v2_evidence_schema import BotStatusData, LinkedBotData


class BotToolAdapter:
    def __init__(self, session=None):
        self.repository = BotRepository(session) if session is not None else None
        self.bot_service = BotService(session) if session is not None else None

    async def execute_linked_bot(self, *, bot: dict, resolution_source: str, **_kwargs):
        payload = LinkedBotData(
            bot_id=bot.get("id"),
            name=bot.get("name"),
            symbol=bot.get("symbol") or bot.get("setup_symbol"),
            strategy_id=bot.get("strategy_id"),
            strategy_name=bot.get("strategy_name"),
            setup_id=bot.get("setup_id"),
            setup_name=bot.get("setup_name"),
            is_active=bool(bot.get("is_active")),
            is_live=bool(bot.get("is_live")),
            mode=bot.get("mode"),
            budget_total_eur=bot.get("budget_total_eur"),
            budget_limit_enabled=(float(bot["budget_total_eur"]) > 0) if bot.get("budget_total_eur") is not None else None,
            paper_initial_cash_eur=bot.get("paper_initial_cash_eur"),
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

    async def execute_status(self, *, bot: dict, user_id: int | None = None, **_kwargs):
        last_run = bot.get("last_run")
        latest = None
        if self.repository is not None and user_id is not None and bot.get("id") is not None:
            decision = await self.repository.get_latest_bot_decision(user_id, int(bot["id"]))
            if decision:
                scores = decision.get("scores_json") or {}
                if isinstance(scores, str):
                    try:
                        scores = json.loads(scores)
                    except ValueError:
                        scores = {}
                if not isinstance(scores, dict):
                    scores = {}
                safety = self.bot_service._safety_contract({
                    "id": decision["id"], "bot_id": decision["bot_id"],
                    "status": decision["status"], "created_at": decision.get("decision_ts"),
                    "guardrails_result": scores.get("guardrails_result"),
                    "guardrails_checked_at": scores.get("guardrails_checked_at"),
                    "requested_amount_eur": scores.get("requested_amount_eur"),
                    "execution_failure": scores.get("execution_failure"),
                    "strategy_reason": scores.get("strategy_reason"),
                }, bool(bot.get("is_live")))
                latest = {
                    "decision_id": decision["id"], "action": decision["action"],
                    "persistence_status": decision["status"],
                    "decision_at": decision.get("decision_ts"),
                    "safety_state": safety["state"],
                    "reason_code": safety["reason_code"],
                    "reason": safety["reason"],
                    "next_step": safety["next_step"],
                    "safety_checked_at": safety["checked_at"],
                }
        payload = BotStatusData(
            bot_id=bot.get("id"),
            is_active=bool(bot.get("is_active")),
            is_live=bool(bot.get("is_live")),
            last_run=last_run if isinstance(last_run, datetime) else None,
            mode=bot.get("mode"),
            cadence=bot.get("cadence"),
            latest_decision=latest,
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
