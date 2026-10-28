import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import daily_report_trader_status_service as trader_status
from backend.services.finn_unified_report_service import _regular_session_at


def test_regular_session_only_claims_proven_outside_hours():
    assert _regular_session_at("2026-10-24T14:00:00+00:00", "stock", "America/New_York") == "outside_regular_hours"
    assert _regular_session_at("2026-10-23T14:00:00+00:00", "stock", "America/New_York") == "unknown"
    assert _regular_session_at("2026-10-24T14:00:00+00:00", "crypto", "UTC") == "not_applicable"
    assert _regular_session_at("2026-10-24T14:00:00+00:00", "stock", None) == "unknown"


def test_current_status_is_owner_scoped_and_does_not_claim_unrecorded_exit_check(monkeypatch):
    class Rows:
        def mappings(self):
            return [{
                "bot_id": 3, "last_run": datetime(2026, 10, 24, tzinfo=timezone.utc),
                "is_active": True, "is_live": False, "mode": "auto",
                "setup_type": "trade", "entry": 300, "stop_loss": 280,
                "targets": ["330", "360"],
                "strategy_data": {"price_currency": "USD", "price_currency_confirmed": True},
                "strategy_name": "AAPL swing", "setup_name": "AAPL",
                "decision_id": 4, "decision_kind": "assessment", "action": "HOLD",
                "decision_status": "completed",
                "decision_ts": datetime(2026, 10, 24, tzinfo=timezone.utc),
                "reason_json": ["Waiting for a signal"], "scores_json": {},
            }]

    class Session:
        async def execute(self, query, params):
            assert params == {"user_id": 7}
            sql = str(query)
            assert "WHERE b.user_id=:user_id" in sql
            assert "user_id=b.user_id AND bot_id=b.id" in sql
            return Rows()

    portfolios = [{
        "bot_id": 3, "name": "AAPL Paper", "symbol": "AAPL",
        "stats": {"net_qty": 2, "position_value_eur": 600, "price_source_at": None},
    }]
    monkeypatch.setattr(trader_status, "BotService", lambda session: SimpleNamespace(
        get_bot_portfolios=AsyncMock(return_value=portfolios),
    ))
    result = asyncio.run(trader_status.current_daily_trader_status(Session(), 7))
    bot = result["bots"][0]
    assert bot["position_qty"] == 2
    assert bot["first_target"] == 330
    assert bot["level_currency"] == "USD"
    assert bot["exit_monitoring"] == "configured_check_unverified"
    assert bot["latest_decision"]["action"] == "HOLD"
