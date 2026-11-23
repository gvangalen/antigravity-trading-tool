import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_tool_adapters.market_tool_adapter import MarketToolAdapter
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import SetupToolAdapter
from backend.services.finn_v2_tool_adapters.setup_inventory_tool_adapter import SetupInventoryToolAdapter
from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter
from backend.services.finn_v2_tool_adapters.asset_tool_adapter import AssetToolAdapter
from backend.services.finn_v2_tool_adapters.indicator_tool_adapter import IndicatorToolAdapter


def _reader(setups, indicator_scopes=()):
    service = FinnV2ToolExecutionService.__new__(FinnV2ToolExecutionService)
    service.resolver = SimpleNamespace(setups=SimpleNamespace(
        get_all_setups=AsyncMock(return_value=setups)))
    class Result:
        def fetchall(self):
            return [(value,) for value in indicator_scopes]
    service.session = SimpleNamespace(execute=AsyncMock(return_value=Result()))
    return service


def test_saved_pair_setup_scopes_score_reads_to_its_market():
    service = _reader([])
    scope = asyncio.run(service._resolve_read_market_scope(
        user_id=7, asset="ETH", selector={}, run=None,
        shared_state={"setup": {"symbol": "ETH", "market_id": 73,
                                "quote_currency": "EUR"}}))
    assert scope == {"market_id": 73, "quote_currency": "EUR"}
    service.session.execute.assert_not_awaited()


def test_explicit_saved_setup_outranks_a_different_page_quote():
    service = _reader([])
    scope = asyncio.run(service._resolve_read_market_scope(
        user_id=7, asset="BTC", selector={"setup_id": 9},
        run=SimpleNamespace(workspace_hints_json={"symbol": "BTC",
                                                   "quote_currency": "USDT"}),
        shared_state={"setup": {"id": 9, "symbol": "BTC", "market_id": 73,
                               "quote_currency": "EUR"}}))
    assert scope == {"market_id": 73, "quote_currency": "EUR"}


def test_bare_asset_with_two_owned_pair_scopes_requires_clarification():
    service = _reader([
        {"symbol": "BTC", "market_id": 11},
        {"symbol": "BTC", "market_id": 12},
    ])
    with pytest.raises(LookupError, match="market_pair_ambiguous"):
        asyncio.run(service._resolve_read_market_scope(
            user_id=7, asset="BTC", selector={}, run=None, shared_state={}))


def test_stock_usd_workspace_hint_reads_base_quote_without_pair_lookup():
    service = _reader([])
    scope = asyncio.run(service._resolve_read_market_scope(
        user_id=7, asset="AAPL", selector={"asset": "AAPL"},
        run=SimpleNamespace(workspace_hints_json={"symbol": "AAPL", "quote_currency": "USD"},
                            client_context_json={}), shared_state={}))
    assert scope == {"market_id": None, "quote_currency": "USD"}
    service.session.execute.assert_not_awaited()


def test_stock_quote_hint_cannot_select_a_different_currency():
    service = _reader([])
    with pytest.raises(LookupError, match="market_quote_not_supported"):
        asyncio.run(service._resolve_read_market_scope(
            user_id=7, asset="AAPL", selector={"asset": "AAPL"},
            run=SimpleNamespace(workspace_hints_json={"symbol": "AAPL", "quote_currency": "EUR"},
                                client_context_json={}), shared_state={}))
    service.session.execute.assert_not_awaited()


def test_explicit_stock_usd_quote_reads_the_base_source():
    service = _reader([])
    scope = asyncio.run(service._resolve_read_market_scope(
        user_id=7, asset="AAPL", selector={"asset": "AAPL", "quote_currency": "USD"},
        run=None, shared_state={}))
    assert scope == {"market_id": None, "quote_currency": "USD"}
    service.session.execute.assert_not_awaited()


def test_legacy_stock_setup_still_verifies_its_usd_base_source():
    service = _reader([])
    scope = asyncio.run(service._resolve_read_market_scope(
        user_id=7, asset="AAPL", selector={"asset": "AAPL"},
        run=SimpleNamespace(workspace_hints_json={"symbol": "AAPL", "quote_currency": "USD"},
                            client_context_json={}),
        shared_state={"setup": {"symbol": "AAPL", "market_id": None,
                                "quote_currency": None}}))
    assert scope == {"market_id": None, "quote_currency": "USD"}
    service.session.execute.assert_not_awaited()


def test_stock_setup_cannot_borrow_a_mismatched_base_quote():
    service = _reader([])
    with pytest.raises(LookupError, match="market_quote_mismatch"):
        asyncio.run(service._resolve_read_market_scope(
            user_id=7, asset="AAPL", selector={"asset": "AAPL"},
            run=None, shared_state={"setup": {"symbol": "AAPL", "market_id": None,
                                               "quote_currency": "EUR"}}))


def test_stock_setup_cannot_ignore_a_conflicting_workspace_quote():
    service = _reader([])
    with pytest.raises(LookupError, match="market_quote_mismatch"):
        asyncio.run(service._resolve_read_market_scope(
            user_id=7, asset="AAPL", selector={"asset": "AAPL"},
            run=SimpleNamespace(workspace_hints_json={"symbol": "AAPL", "quote_currency": "EUR"},
                                client_context_json={}),
            shared_state={"setup": {"symbol": "AAPL", "market_id": None,
                                    "quote_currency": None}}))


def test_base_quote_source_must_match_the_selected_stock_currency():
    adapter = MarketToolAdapter.__new__(MarketToolAdapter)
    adapter.repository = SimpleNamespace(
        get_latest_quoted_snapshot=AsyncMock(return_value=SimpleNamespace(
            symbol="AAPL", quote_currency="EUR", price=340)),
        get_latest_exact_market_snapshot=AsyncMock(side_effect=AssertionError("pair quote used")),
    )
    with pytest.raises(LookupError, match="base_quote_source_mismatch"):
        asyncio.run(adapter.execute(asset="AAPL", user_id=7, market_id=None,
                                    quote_currency="USD"))
    adapter.repository.get_latest_exact_market_snapshot.assert_not_awaited()


def test_dated_aapl_market_read_passes_usd_hint_to_base_adapter():
    service = _reader([])
    service.resolver.resolve_asset = AsyncMock(return_value={
        "asset": "AAPL", "resolution_source": "explicit_selector"})
    service.market_adapter = SimpleNamespace(execute=AsyncMock(return_value={
        "data": {"symbol": "AAPL", "price": 341.92, "quote_currency": "USD",
                 "source_observed_at": "2026-11-20T20:58:00+00:00"}}))
    run = SimpleNamespace(workspace_hints_json={"symbol": "AAPL", "quote_currency": "USD"},
                          client_context_json={})
    result = asyncio.run(service._dispatch_tool(
        tool_name="read_market_snapshot", user_id=7, selector={"asset": "AAPL"},
        run=run, shared_state={}))
    assert result["data"]["price"] == 341.92
    service.market_adapter.execute.assert_awaited_once_with(
        asset="AAPL", user_id=7, market_id=None, quote_currency="USD")


def test_pair_market_snapshot_never_borrows_other_quote():
    adapter = MarketToolAdapter.__new__(MarketToolAdapter)
    adapter.repository = SimpleNamespace(
        get_latest_exact_market_snapshot=AsyncMock(return_value=SimpleNamespace(
            symbol="ETH", quote_currency="USDT", price=2500)),
        get_latest_quoted_snapshot=AsyncMock(side_effect=AssertionError("base quote used")),
    )
    with pytest.raises(LookupError, match="exact_market_source_mismatch"):
        asyncio.run(adapter.execute(asset="ETH", user_id=7, market_id=73,
                                    quote_currency="EUR"))
    adapter.repository.get_latest_quoted_snapshot.assert_not_awaited()


def test_saved_setup_reads_expose_pair_identity():
    setup = {"id": 9, "symbol": "ETH", "market_id": 73,
             "quote_currency": "EUR", "name": "ETH EUR DCA"}
    active = asyncio.run(SetupToolAdapter().execute(
        setup=setup, setups=[setup], resolution_source="setup_id"))["data"]
    inventory = asyncio.run(SetupInventoryToolAdapter().execute(
        setups=[setup]))["data"]
    assert active.pair == "ETH/EUR"
    assert active.market_id == 73
    assert active.setups[0]["pair"] == "ETH/EUR"
    assert inventory.setups[0]["pair"] == "ETH/EUR"


def test_owner_inventory_keeps_named_strategy_amount_with_exact_pair():
    rows = [
        {"id": 9, "name": "QA BTC EUR", "symbol": "BTC", "quote_currency": "EUR"},
        {"id": 10, "name": "QA BTC USDT", "symbol": "BTC", "quote_currency": "USDT"},
    ]
    strategies = [
        {"id": 21, "setup_id": 9, "name": "QA BTC EUR Strategie", "base_amount": 20},
        {"id": 22, "setup_id": 10, "name": "QA BTC USDT Strategie", "base_amount": 10},
    ]
    evidence = asyncio.run(SetupInventoryToolAdapter().execute(
        setups=rows, strategies=strategies,
    ))["data"].setups
    assert evidence[0]["pair"] == "BTC/EUR"
    assert evidence[0]["linked_strategies"] == [
        {"strategy_id": 21, "name": "QA BTC EUR Strategie", "base_amount": 20,
         "currency": "EUR"},
    ]
    assert evidence[1]["pair"] == "BTC/USDT"
    assert evidence[1]["linked_strategies"] == [
        {"strategy_id": 22, "name": "QA BTC USDT Strategie", "base_amount": 10,
         "currency": "EUR"},
    ]


def test_linked_strategy_keeps_trade_pair_separate_from_investment_currency():
    evidence = asyncio.run(StrategyToolAdapter().execute(
        strategy={"id": 22, "setup_id": 9, "setup_symbol": "ETH",
                  "setup_market_id": 73, "market_quote_currency": "USDT",
                  "base_amount": 100, "execution_mode": "fixed"},
        resolution_source="strategy_id"))["data"]
    assert evidence.pair == "ETH/USDT"
    assert evidence.quote_currency == "USDT"
    assert evidence.currency == "EUR"


def test_crypto_catalog_default_is_not_reported_as_selected_trading_quote():
    adapter = AssetToolAdapter.__new__(AssetToolAdapter)
    adapter.assets = SimpleNamespace(get_asset=AsyncMock(return_value={
        "symbol": "BTC", "asset_class": "crypto", "quote_currency": "USDT"}))
    evidence = asyncio.run(adapter.execute(
        asset="BTC", resolution_source="explicit_selector"))["data"]
    assert evidence.market_id is None
    assert evidence.pair is None
    assert evidence.quote_currency is None


def test_pair_indicator_read_keeps_shared_defaults_with_pair_override(monkeypatch):
    import backend.services.finn_v2_tool_adapters.indicator_tool_adapter as module

    rows = [
        SimpleNamespace(id=1, user_id=7, symbol="ETH", category="technical",
                        indicator="rsi", priority=1, enabled=True,
                        asset_class="crypto", provenance="owner", market_id=73),
        SimpleNamespace(id=2, user_id=7, symbol="ETH", category="technical",
                        indicator="rsi", priority=1, enabled=True,
                        asset_class="crypto", provenance="owner", market_id=None),
        SimpleNamespace(id=3, user_id=7, symbol="ETH", category="macro",
                        indicator="dxy", priority=1, enabled=True,
                        asset_class="crypto", provenance="owner", market_id=None),
    ]
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    adapter = IndicatorToolAdapter.__new__(IndicatorToolAdapter)
    adapter.session = SimpleNamespace(execute=AsyncMock(return_value=result))
    adapter.source_registry = SimpleNamespace(get=lambda _: SimpleNamespace(
        validate_request=lambda **kwargs: None))
    monkeypatch.setattr(module, "AssetCatalogService", lambda _: SimpleNamespace(
        get_asset=AsyncMock(return_value={"asset_class": "crypto"})))
    evidence = asyncio.run(adapter.execute(user_id=7, asset="ETH", market_id=73,
                                           quote_currency="EUR"))["data"]
    assert [(item.indicator, item.source_record_id) for item in evidence.technical] == [("rsi", 1)]
    assert [(item.indicator, item.source_record_id) for item in evidence.macro] == [("dxy", 3)]
