from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class _PortfolioRepository:
    def __init__(self):
        self.user_ids: list[int] = []

    async def get_portfolio_intelligence_context(self, user_id: int):
        self.user_ids.append(user_id)
        return {
            "global": {"total_equity": 99999},
            "bots": [
                {
                    "bot_id": 1,
                    "name": "ETH plan",
                    "symbol": "ETH",
                    "cash": 100.0,
                    "invested": 200.0,
                    "position_value": 250.0,
                    "realized_pnl": 15.0,
                    "budget_total": 400.0,
                    "equity": 350.0,
                    "is_active": True,
                    "is_live": False,
                },
                {
                    "bot_id": 2,
                    "name": "BTC plan",
                    "symbol": "BTC",
                    "cash": 50.0,
                    "invested": 75.0,
                    "position_value": 80.0,
                    "realized_pnl": -2.0,
                    "budget_total": 125.0,
                    "equity": 130.0,
                    "is_active": False,
                    "is_live": False,
                },
            ],
        }


def _adapter():
    adapter = object.__new__(PortfolioToolAdapter)
    adapter.repository = _PortfolioRepository()
    return adapter


def test_portfolio_adapter_keeps_owner_scope_and_filters_only_the_existing_ledger():
    adapter = _adapter()

    result = asyncio.run(adapter.execute(user_id=17, asset="eth"))

    assert adapter.repository.user_ids == [17]
    assert result["asset"] == "ETH"
    assert result["summary"] == {
        "title": "portfolio",
        "total_equity": 350.0,
        "bot_count": 1,
        "requested_asset": "ETH",
    }
    assert result["data"].global_.dict() == {
        "total_equity": 350.0,
        "cash_balance": 100.0,
        "invested_value": 200.0,
        "current_position_value": 250.0,
        "realized_pnl": 15.0,
        "unrealized_pnl": 50.0,
        "total_budget_limit": 400.0,
        "allocations_pct": {"Cash": 28.57, "ETH": 71.43},
    }
    assert [bot.symbol for bot in result["data"].bots] == ["ETH"]


def test_portfolio_adapter_returns_the_full_existing_owner_ledger_without_a_filter():
    adapter = _adapter()

    result = asyncio.run(adapter.execute(user_id=17))

    assert result["asset"] is None
    assert result["summary"]["bot_count"] == 2
    assert result["data"].global_.total_equity == 480.0
    assert {bot.symbol for bot in result["data"].bots} == {"ETH", "BTC"}


def test_portfolio_tool_dispatch_passes_only_the_contract_derived_asset_filter():
    captured = {}

    class _Adapter:
        async def execute(self, **kwargs):
            captured.update(kwargs)
            return {"data": {}}

    service = object.__new__(FinnV2ToolExecutionService)
    service.portfolio_adapter = _Adapter()

    asyncio.run(
        service._dispatch_tool(
            tool_name="read_portfolio",
            user_id=17,
            selector={"asset": "SOL", "user_id": 999},
            run=SimpleNamespace(),
            shared_state={},
        )
    )

    assert captured == {"user_id": 17, "asset": "SOL"}
