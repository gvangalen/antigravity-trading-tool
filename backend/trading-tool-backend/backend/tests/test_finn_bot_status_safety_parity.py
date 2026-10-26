import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_tool_adapters.bot_tool_adapter import BotToolAdapter
from backend.services.bot_service import BotService


def test_finn_reads_saved_owner_bot_safety_state_instead_of_planned_label():
    checked_at = datetime.now(timezone.utc)

    class Decisions:
        async def get_latest_bot_decision(self, user_id, bot_id):
            assert user_id == 17 and bot_id == 130
            return {
                "id": 901, "bot_id": 130, "action": "hold", "status": "planned",
                "decision_ts": checked_at,
                "scores_json": {"guardrails_result": {
                    "allowed": False, "adjusted_amount_eur": 0,
                    "original_amount_eur": 0, "blocked_by": "market_price_stale",
                    "reason": "Geen actuele koers beschikbaar.",
                }, "guardrails_checked_at": checked_at.isoformat()},
            }

    adapter = BotToolAdapter()
    adapter.repository = Decisions()
    adapter.bot_service = BotService(object())
    result = asyncio.run(adapter.execute_status(
        user_id=17, bot={"id": 130, "is_active": True, "is_live": False, "mode": "auto"},
    ))
    latest = result["data"].latest_decision
    assert latest["decision_id"] == 901
    assert latest["persistence_status"] == "planned"
    assert latest["safety_state"] == "error"
    assert latest["reason_code"] == "market_price_stale"
