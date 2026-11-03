import pytest

from backend.domain.finn_trade_plan_contract import split_confirmed_trade_plan


SIGNAL = {"version": 1, "event": "close_crosses_reference", "direction": "above", "timeframe": "1D", "reference": {"kind": "sma", "period": 50}}


def plan(**overrides):
    return {"setup_type": "trade", "plan_scope": "setup_and_strategy", "symbol": "BTC", "quote_currency": "EUR", "timeframe": "1D", "name": "BTC SMA50", "entry_signal": SIGNAL, "execution_mode": "fixed", "base_amount": 10, "entry": 68000, "stop_loss": 60000, "targets": [80000], "risk_profile": "balanced", "min_benchmark_score": 61, "max_benchmark_score": 75, **overrides}


def test_trade_plan_splits_exact_pair_and_signal():
    setup, strategy = split_confirmed_trade_plan(plan())
    assert setup["quote_currency"] == "EUR"
    assert (setup["min_benchmark_score"], setup["max_benchmark_score"]) == (61, 75)
    assert "entry_signal" not in setup
    assert strategy["entry_signal"] == SIGNAL
    assert strategy["price_currency"] == "EUR"
    assert strategy["name"] == "BTC SMA50 Strategy"


@pytest.mark.parametrize("overrides", [
    {"plan_scope": "setup_only"}, {"price_currency": "USDT"},
    {"base_amount": None}, {"stop_loss": 70000}, {"targets": [67000]},
    {"entry_signal": None},
    {"timeframe": "4H"},
    {"min_benchmark_score": None}, {"max_benchmark_score": None},
    {"min_benchmark_score": 80, "max_benchmark_score": 70},
])
def test_trade_plan_rejects_incomplete_or_mismatched_proposal(overrides):
    with pytest.raises(ValueError):
        split_confirmed_trade_plan(plan(**overrides))
