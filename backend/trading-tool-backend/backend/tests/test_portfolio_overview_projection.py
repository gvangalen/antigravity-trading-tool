from datetime import datetime, timezone

from backend.services.portfolio_overview_service import project_portfolio


READ_AT = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def _bot(bot_id, *, live=False, cash=0, qty=0, value=0, invested=0, budget=1000,
         initialized=True, priced=True):
    return {
        "bot_id": bot_id, "name": f"Bot {bot_id}", "symbol": "ETH",
        "is_live": live, "cash": cash, "qty": qty, "position_value": value,
        "invested": invested, "realized_pnl": 0, "budget_total": budget,
        "portfolio_initialized": initialized, "price_available": priced,
        "price_as_of": READ_AT if qty else None,
    }


def test_paper_portfolio_sums_only_funded_cash_and_priced_positions():
    data = project_portfolio({"read_at": READ_AT, "bots": [
        _bot(1, cash=250, qty=0.01, value=800, invested=750),
        _bot(2, cash=1100, qty=0.02, value=1000, invested=900),
    ]}, environment="paper")
    assert data.global_.total_equity == 3150
    assert data.global_.cash_balance == 1350
    assert data.global_.current_position_value == 1800
    assert [bot.result_eur for bot in data.bots] == [50, 100]
    assert data.valuation_as_of == READ_AT


def test_budget_and_missing_quote_never_become_value_or_cash():
    data = project_portfolio({"bots": [
        _bot(1, initialized=False, budget=500),
        _bot(2, cash=80, qty=1, invested=100, priced=False, budget=500),
    ]}, environment="paper")
    assert data.global_.total_budget_limit == 1000
    assert data.global_.total_equity is None
    assert data.global_.cash_balance is None
    assert data.bots[0].cash_eur is None
    assert data.bots[1].position_value_eur is None

    funded = project_portfolio({"bots": [
        _bot(3, cash=80, qty=1, invested=100, priced=False),
    ]}, environment="paper")
    assert funded.global_.cash_balance == 80
    assert funded.global_.total_equity is None
    assert funded.bots[0].result_eur is None


def test_live_shared_broker_cash_is_not_attributed_to_multiple_bots():
    data = project_portfolio({"bots": [
        _bot(1, live=True, cash=1000, qty=1, value=200, invested=180),
        _bot(2, live=True, cash=1000, qty=1, value=300, invested=280),
        _bot(3, cash=50, budget=500),
    ]}, environment="live")
    assert len(data.bots) == 2
    assert data.valuation_status == "unreconciled_live"
    assert data.global_.cash_balance is None
    assert data.global_.total_equity is None
    assert all(bot.cash_eur is None and bot.equity is None for bot in data.bots)
    assert data.global_.current_position_value is None


def test_twenty_assets_filtering_keeps_owner_projected_rows_and_stable_scope():
    rows = [{**_bot(i), "symbol": f"ASSET{i}"} for i in range(20)]
    data = project_portfolio({"bots": rows}, environment="paper")
    assert len(data.bots) == 20
    one = project_portfolio({"bots": rows}, asset="ASSET17", environment="paper")
    assert [bot.symbol for bot in one.bots] == ["ASSET17"]


def test_live_broker_total_counts_shared_cash_once_and_keeps_unallocated_cash():
    data = project_portfolio({"read_at": READ_AT, "bots": [
        _bot(1, live=True, cash=1000, qty=0.1, value=400, invested=300, budget=5000),
        _bot(2, live=True, cash=1000, qty=0.2, value=800, invested=700, budget=5000),
    ], "live_account": {
        "exchange_name": "bitvavo", "cash_eur": 600, "total_eur": 650,
        "positions": {"ETH": 0.5}, "prices_eur": {"ETH": 4000},
        "position_value_eur": 2000, "as_of": READ_AT,
    }, "live_allocations": {1: 100, 2: 200}}, environment="live")
    assert data.global_.total_equity == 2650
    assert data.global_.cash_balance == 650
    assert data.global_.current_position_value == 2000
    assert data.available_cash_eur == 600
    assert data.reserved_cash_eur == 50
    assert data.unallocated_cash_eur == 300
    assert [bot.cash_eur for bot in data.bots] == [100, 200]
    assert [bot.equity for bot in data.bots] == [500, 1000]
    assert data.global_.total_budget_limit == 10000
    assert data.global_.realized_pnl is None


def test_live_overallocated_cash_never_becomes_bot_cash_or_negative_unallocated():
    data = project_portfolio({"read_at": READ_AT, "bots": [
        _bot(1, live=True), _bot(2, live=True),
    ], "live_account": {
        "exchange_name": "bitvavo", "cash_eur": 250, "total_eur": 250,
        "positions": {}, "prices_eur": {}, "position_value_eur": 0, "as_of": READ_AT,
    }, "live_allocations": {1: 200, 2: 200}}, environment="live")
    assert data.global_.total_equity == 250
    assert data.unallocated_cash_eur is None
    assert all(bot.cash_eur is None for bot in data.bots)


def test_live_missing_price_preserves_cash_but_not_total_or_position():
    data = project_portfolio({"read_at": READ_AT, "bots": [_bot(1, live=True, qty=1)],
        "live_account": {
            "exchange_name": "bitvavo", "cash_eur": 100, "total_eur": 100,
            "positions": {"ETH": 1}, "prices_eur": {}, "position_value_eur": None,
            "as_of": READ_AT,
        }, "live_allocations": {1: 50}}, environment="live")
    assert data.global_.cash_balance == 100
    assert data.global_.total_equity is None
    assert data.valuation_status == "missing_price"
    assert data.bots[0].cash_eur == 50
    assert data.bots[0].position_value_eur is None


def test_live_bot_ledger_larger_than_broker_holding_is_not_attributed():
    data = project_portfolio({"bots": [_bot(1, live=True, qty=2)],
        "live_account": {
            "exchange_name": "bitvavo", "cash_eur": 100, "total_eur": 100,
            "positions": {"ETH": 1}, "prices_eur": {"ETH": 2000},
            "position_value_eur": 2000, "as_of": READ_AT,
        }, "live_allocations": {1: 50}}, environment="live")
    assert data.global_.total_equity == 2100
    assert data.bots[0].position_value_eur is None
    assert data.bots[0].equity is None


def test_unverified_live_ledger_cannot_gain_bot_equity_from_cash_assignment():
    data = project_portfolio({"bots": [{**_bot(1, live=True, qty=1), "unverified_ledger": True}],
        "live_account": {
            "exchange_name": "bitvavo", "cash_eur": 100, "total_eur": 100,
            "positions": {"ETH": 1}, "prices_eur": {"ETH": 2000},
            "position_value_eur": 2000, "as_of": READ_AT,
        }, "live_allocations": {1: 50}}, environment="live")
    assert data.global_.total_equity == 2100
    assert data.bots[0].position_value_eur is None
    assert data.bots[0].equity is None
