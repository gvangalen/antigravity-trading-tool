from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, text

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
from backend.services.portfolio_overview_service import project_portfolio
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
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
                    "strategy_id": 22,
                    "strategy_name": "ETH fixed DCA",
                    "setup_id": 11,
                    "setup_name": "ETH weekly setup",
                    "mode": "manual",
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
    assert result["data"].bots[0].strategy_name == "ETH fixed DCA"
    assert result["data"].bots[0].setup_name == "ETH weekly setup"
    assert result["data"].bots[0].mode == "manual"
    assert to_json_safe(result["data"])["bots"][0]["budget_total_eur"] == 400.0
    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts(
        result["data"].dict(by_alias=True), "read_portfolio",
    )
    assert facts["bots"][0]["strategy_name"] == "ETH fixed DCA"
    assert facts["bots"][0]["mode"] == "manual"
    assert facts["valuation_status"] == "available"
    assert result["data"].covered_scopes == [
        "paper_bot_portfolio_valuation", "budget", "exposure",
    ]
    assert result["data"].excluded_scopes == [
        "broker_account_total", "trade_transaction_history", "tax_records", "tax_calculations",
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


def test_portfolio_context_keeps_named_bot_beyond_first_eight_rows():
    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts({
        "global": {},
        "bots": [{"bot_id": index, "name": f"Bot {index}", "mode": "manual"}
                 for index in range(20)],
    }, "read_portfolio")

    assert len(facts["bots"]) == 20
    assert facts["bots"][-1]["name"] == "Bot 19"


def test_portfolio_repository_keeps_saved_asset_for_bot_without_linked_strategy():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT, strategy_id INTEGER, is_active INTEGER, is_live INTEGER, mode TEXT, budget_total_eur REAL, budget_daily_limit_eur REAL, risk_profile TEXT, market_id INTEGER)"))
        connection.execute(text("CREATE TABLE strategies (id INTEGER, user_id INTEGER, setup_id INTEGER, name TEXT)"))
        connection.execute(text("CREATE TABLE setups (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT)"))
        connection.execute(text("CREATE TABLE bot_portfolios (user_id INTEGER, bot_id INTEGER, symbol TEXT, cash_eur REAL, position_qty REAL, invested_eur REAL, avg_entry REAL, realized_pnl_eur REAL)"))
        connection.execute(text("CREATE TABLE portfolio_unverified_paper_bots (user_id INTEGER, bot_id INTEGER)"))
        connection.execute(text("CREATE TABLE bot_ledger (user_id INTEGER, bot_id INTEGER, entry_type TEXT, valuation_version INTEGER)"))
        connection.execute(text("CREATE TABLE asset_catalog (symbol TEXT, quote_currency TEXT)"))
        connection.execute(text("INSERT INTO bot_configs VALUES (1, 17, 'Apple Paper', 'AAPL', NULL, 1, 0, 'manual', 110, 0, 'balanced', NULL)"))
        connection.execute(text("INSERT INTO bot_portfolios VALUES (99, 1, 'AAPL', 900, 0, 0, 0, 0)"))

        class _Session:
            async def execute(self, query, parameters):
                return connection.execute(query, parameters)

        repository = BotRepository(_Session())
        repository.get_valuatable_market_prices = AsyncMock(return_value={})
        repository.get_portfolio_fx_rates = AsyncMock(return_value={})
        context = asyncio.run(repository.get_portfolio_intelligence_context(17))

    assert len(context["bots"]) == 1
    assert context["bots"][0]["symbol"] == "AAPL"
    assert context["bots"][0]["mode"] == "manual"
    assert context["bots"][0]["strategy_name"] is None
    assert context["bots"][0]["portfolio_initialized"] is False
    engine.dispose()


def test_native_usdt_quote_is_not_reported_as_eur_portfolio_value():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT, strategy_id INTEGER, is_active INTEGER, is_live INTEGER, mode TEXT, budget_total_eur REAL, budget_daily_limit_eur REAL, risk_profile TEXT, market_id INTEGER)"))
        connection.execute(text("CREATE TABLE strategies (id INTEGER, user_id INTEGER, setup_id INTEGER, name TEXT)"))
        connection.execute(text("CREATE TABLE setups (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT)"))
        connection.execute(text("CREATE TABLE bot_portfolios (user_id INTEGER, bot_id INTEGER, symbol TEXT, cash_eur REAL, position_qty REAL, invested_eur REAL, avg_entry REAL, realized_pnl_eur REAL)"))
        connection.execute(text("CREATE TABLE portfolio_unverified_paper_bots (user_id INTEGER, bot_id INTEGER)"))
        connection.execute(text("CREATE TABLE bot_ledger (user_id INTEGER, bot_id INTEGER, entry_type TEXT, valuation_version INTEGER)"))
        connection.execute(text("INSERT INTO bot_configs VALUES (1, 17, 'ETH Paper', 'ETH', NULL, 1, 0, 'manual', 500, 0, 'balanced', NULL)"))
        connection.execute(text("INSERT INTO bot_portfolios VALUES (17, 1, 'ETH', 100, 1, 2000, 2000, 0)"))

        class _Session:
            async def execute(self, query, parameters):
                return connection.execute(query, parameters)

        repository = BotRepository(_Session())
        repository.get_valuatable_market_prices = AsyncMock(return_value={"ETH": {"price": 2500.0, "observed_at": datetime.now(timezone.utc)}})
        repository.get_asset_quote_currencies = AsyncMock(return_value={"ETH": "USDT"})
        repository.get_portfolio_fx_rates = AsyncMock(return_value={})
        context = asyncio.run(repository.get_portfolio_intelligence_context(17))

    assert context["bots"][0]["price_available"] is False
    assert context["bots"][0]["price_quote_currency"] == "USDT"
    assert context["bots"][0]["position_value"] is None
    assert context["global"]["total_equity"] is None
    assert project_portfolio(context, environment="paper").valuation_status == "missing_price"


def test_dated_usdt_fx_values_a_position_without_treating_usdt_as_eur():
    now = datetime.now(timezone.utc)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT, strategy_id INTEGER, is_active INTEGER, is_live INTEGER, mode TEXT, budget_total_eur REAL, budget_daily_limit_eur REAL, risk_profile TEXT, market_id INTEGER)"))
        connection.execute(text("CREATE TABLE strategies (id INTEGER, user_id INTEGER, setup_id INTEGER, name TEXT)"))
        connection.execute(text("CREATE TABLE setups (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT)"))
        connection.execute(text("CREATE TABLE bot_portfolios (user_id INTEGER, bot_id INTEGER, symbol TEXT, cash_eur REAL, position_qty REAL, invested_eur REAL, avg_entry REAL, realized_pnl_eur REAL)"))
        connection.execute(text("CREATE TABLE portfolio_unverified_paper_bots (user_id INTEGER, bot_id INTEGER)"))
        connection.execute(text("CREATE TABLE bot_ledger (user_id INTEGER, bot_id INTEGER, entry_type TEXT, valuation_version INTEGER)"))
        connection.execute(text("INSERT INTO bot_configs VALUES (1, 17, 'ETH Paper', 'ETH', NULL, 1, 0, 'manual', 500, 0, 'balanced', NULL)"))
        connection.execute(text("INSERT INTO bot_portfolios VALUES (17, 1, 'ETH', 100, 1, 2000, 2000, 0)"))

        class _Session:
            async def execute(self, query, parameters=None):
                return connection.execute(query, parameters or {})

        repository = BotRepository(_Session())
        repository.get_valuatable_market_prices = AsyncMock(return_value={"ETH": {"price": 2500.0, "observed_at": now}})
        repository.get_asset_quote_currencies = AsyncMock(return_value={"ETH": "USDT"})
        repository.get_portfolio_fx_rates = AsyncMock(return_value={
            "USDT": {"eur_per_unit": 0.8, "observed_at": now},
        })
        context = asyncio.run(repository.get_portfolio_intelligence_context(17))

    bot = context["bots"][0]
    assert bot["position_value"] == 2000.0
    assert bot["equity"] == 2100.0
    assert bot["fx_eur_per_unit"] == 0.8
    projected = project_portfolio(context, environment="paper")
    assert projected.global_.total_equity == 2100.0
    assert projected.bots[0].fx_eur_per_unit == 0.8
    engine.dispose()
    engine.dispose()


def test_old_eur_quote_is_not_reported_as_current_value():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT, strategy_id INTEGER, is_active INTEGER, is_live INTEGER, mode TEXT, budget_total_eur REAL, budget_daily_limit_eur REAL, risk_profile TEXT, market_id INTEGER)"))
        connection.execute(text("CREATE TABLE strategies (id INTEGER, user_id INTEGER, setup_id INTEGER, name TEXT)"))
        connection.execute(text("CREATE TABLE setups (id INTEGER, user_id INTEGER, name TEXT, symbol TEXT)"))
        connection.execute(text("CREATE TABLE bot_portfolios (user_id INTEGER, bot_id INTEGER, symbol TEXT, cash_eur REAL, position_qty REAL, invested_eur REAL, avg_entry REAL, realized_pnl_eur REAL)"))
        connection.execute(text("CREATE TABLE portfolio_unverified_paper_bots (user_id INTEGER, bot_id INTEGER)"))
        connection.execute(text("CREATE TABLE bot_ledger (user_id INTEGER, bot_id INTEGER, entry_type TEXT, valuation_version INTEGER)"))
        connection.execute(text("INSERT INTO bot_configs VALUES (1, 17, 'EUR Paper', 'BTCEUR', NULL, 1, 0, 'manual', 500, 0, 'balanced', NULL)"))
        connection.execute(text("INSERT INTO bot_portfolios VALUES (17, 1, 'BTCEUR', 100, 1, 2000, 2000, 0)"))

        class _Session:
            async def execute(self, query, parameters):
                return connection.execute(query, parameters)

        repository = BotRepository(_Session())
        repository.get_valuatable_market_prices = AsyncMock(return_value={"BTCEUR": {"price": 2500.0, "observed_at": datetime.now(timezone.utc) - timedelta(days=3)}})
        repository.get_asset_quote_currencies = AsyncMock(return_value={"BTCEUR": "EUR"})
        repository.get_portfolio_fx_rates = AsyncMock(return_value={})
        context = asyncio.run(repository.get_portfolio_intelligence_context(17))

    assert context["bots"][0]["price_available"] is False
    assert context["global"]["total_equity"] is None
    engine.dispose()


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


def test_paper_and_live_cash_are_not_summed_as_one_spendable_balance():
    adapter = _adapter()

    async def mixed(_user_id):
        return {"bots": [
            {"bot_id": 1, "name": "Paper", "symbol": "ETH", "cash": 80,
             "position_value": 0, "invested": 0, "budget_total": 100,
             "portfolio_initialized": True, "price_available": True, "is_live": False},
            {"bot_id": 2, "name": "Live", "symbol": "BTC", "cash": 20,
             "position_value": 0, "invested": 0, "budget_total": 100,
             "portfolio_initialized": True, "price_available": True, "is_live": True},
        ]}

    adapter.repository.get_portfolio_intelligence_context = mixed
    result = asyncio.run(adapter.execute(user_id=17))
    assert result["data"].global_.cash_balance is None
    assert result["data"].global_.total_equity is None
    assert result["data"].bots[0].paper_cash_eur == 80
    assert result["data"].bots[1].paper_cash_eur is None


def test_live_only_ledger_delta_is_not_presented_as_exchange_equity():
    adapter = _adapter()

    async def live_only(_user_id):
        return {"bots": [{
            "bot_id": 2, "name": "Live", "symbol": "BTC", "cash": -100,
            "position_value": 100, "invested": 100, "equity": 0,
            "budget_total": 200, "portfolio_initialized": True,
            "price_available": True, "is_live": True,
        }]}

    adapter.repository.get_portfolio_intelligence_context = live_only
    result = asyncio.run(adapter.execute(user_id=17))
    assert result["data"].global_.cash_balance is None
    assert result["data"].global_.total_equity is None
    assert result["data"].bots[0].equity is None
    assert result["data"].global_.current_position_value == 100


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

    assert captured == {"user_id": 17, "asset": "SOL", "environment": None}
