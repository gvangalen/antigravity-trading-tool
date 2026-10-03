from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_json_safety import to_json_safe


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
        "currency": "EUR",
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
    assert result["data"].bots[0].budget_total_eur == 400.0
    assert to_json_safe(result["data"])["bots"][0]["budget_total_eur"] == 400.0
    assert result["data"].covered_scopes == [
        "paper_bot_portfolio_valuation", "budget", "exposure",
    ]
    assert result["data"].excluded_scopes == [
        "trade_transaction_history", "tax_records", "tax_calculations",
    ]


def test_portfolio_adapter_returns_the_full_existing_owner_ledger_without_a_filter():
    adapter = _adapter()

    result = asyncio.run(adapter.execute(user_id=17))

    assert result["asset"] is None
    assert result["summary"]["bot_count"] == 2
    assert result["data"].global_.total_equity == 480.0
    assert {bot.symbol for bot in result["data"].bots} == {"ETH", "BTC"}
    assert {bot.name: bot.budget_total_eur for bot in result["data"].bots} == {
        "ETH plan": 400.0,
        "BTC plan": 125.0,
    }


def test_empty_portfolio_has_no_fabricated_allocation_and_keeps_currency():
    adapter = _adapter()

    async def empty(_user_id):
        return {"bots": []}

    adapter.repository.get_portfolio_intelligence_context = empty
    result = asyncio.run(adapter.execute(user_id=17))

    assert result["data"].global_.currency == "EUR"
    assert result["data"].global_.total_equity is None
    assert result["data"].global_.cash_balance is None
    assert result["data"].global_.allocations_pct == {}


def test_uninitialized_bot_portfolio_is_not_reported_as_zero_balance():
    adapter = _adapter()

    async def uninitialized(_user_id):
        return {"bots": [{
            "bot_id": 1, "name": "Paper", "symbol": "BTC", "cash": 0,
            "invested": 0, "position_value": 0, "equity": 0,
            "budget_total": 400, "portfolio_initialized": False,
            "is_active": True, "is_live": False,
        }]}

    adapter.repository.get_portfolio_intelligence_context = uninitialized
    result = asyncio.run(adapter.execute(user_id=17))

    assert result["data"].global_.total_equity is None
    assert result["data"].global_.cash_balance is None
    assert result["data"].global_.total_budget_limit == 400
    assert result["data"].bots[0].equity is None


def test_missing_position_price_does_not_become_zero_market_value():
    adapter = _adapter()

    async def unpriced(_user_id):
        return {"bots": [{
            "bot_id": 1, "name": "Paper", "symbol": "BTC", "cash": 100,
            "invested": 200, "position_value": 0, "equity": 100,
            "budget_total": 400, "portfolio_initialized": True,
            "price_available": False, "is_active": True, "is_live": False,
        }]}

    adapter.repository.get_portfolio_intelligence_context = unpriced
    result = asyncio.run(adapter.execute(user_id=17))

    assert result["data"].global_.cash_balance == 100
    assert result["data"].global_.invested_value == 200
    assert result["data"].global_.current_position_value is None
    assert result["data"].global_.total_equity is None
    assert result["data"].bots[0].equity is None


def test_portfolio_reports_read_time_separately_from_stale_position_price():
    adapter = _adapter()
    read_at = datetime(2026, 10, 3, 11, 0, tzinfo=timezone.utc)
    price_as_of = read_at - timedelta(days=2)

    async def priced(_user_id):
        return {"read_at": read_at, "bots": [{
            "bot_id": 1, "name": "Paper", "symbol": "BTC", "cash": 100,
            "qty": 0.01, "invested": 200, "position_value": 300,
            "budget_total": 1000, "portfolio_initialized": True,
            "price_available": True, "price_as_of": price_as_of,
            "is_active": True, "is_live": False,
        }]}

    adapter.repository.get_portfolio_intelligence_context = priced
    result = asyncio.run(adapter.execute(user_id=17))

    assert result["as_of"] == price_as_of
    assert result["data"].read_at == read_at
    assert result["data"].valuation_available is True
    assert result["data"].bots[0].price_as_of == price_as_of
    assert result["data"].global_.total_equity == 400
    assert result["data"].global_.total_budget_limit == 1000


def test_uninitialized_budget_has_read_time_but_no_valuation_date():
    adapter = _adapter()
    read_at = datetime(2026, 10, 3, 11, 0, tzinfo=timezone.utc)

    async def budget_only(_user_id):
        return {"read_at": read_at, "bots": [{
            "bot_id": 1, "name": "Paper", "symbol": "BTC", "cash": 0,
            "budget_total": 1000, "portfolio_initialized": False,
            "is_active": True, "is_live": False,
        }]}

    adapter.repository.get_portfolio_intelligence_context = budget_only
    result = asyncio.run(adapter.execute(user_id=17))

    assert result["as_of"] is None
    assert result["data"].read_at == read_at
    assert result["data"].valuation_available is False
    assert result["data"].global_.total_equity is None
    assert result["data"].global_.total_budget_limit == 1000


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
