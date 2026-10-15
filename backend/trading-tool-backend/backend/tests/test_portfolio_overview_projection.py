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
    assert data.global_.current_position_value == 500


def test_twenty_assets_filtering_keeps_owner_projected_rows_and_stable_scope():
    rows = [{**_bot(i), "symbol": f"ASSET{i}"} for i in range(20)]
    data = project_portfolio({"bots": rows}, environment="paper")
    assert len(data.bots) == 20
    one = project_portfolio({"bots": rows}, asset="ASSET17", environment="paper")
    assert [bot.symbol for bot in one.bots] == ["ASSET17"]
