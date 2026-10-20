"""Safety contract cases that could otherwise place an unattended order."""

import math

import pytest

from backend.engine import trading_bot_execution
from backend.engine.guardrails_engine import apply_guardrails


BASE = dict(
    proposed_amount_eur=80, portfolio_value_eur=200,
    current_asset_value_eur=0, invested_eur=0,
    today_allocated_eur=0, cash_balance_eur=200,
    max_trade_risk_eur=100, daily_allocation_eur=100,
    max_asset_exposure_pct=100, total_budget_eur=200,
    min_order_eur=5,
)


@pytest.mark.parametrize("field,value", [
    ("proposed_amount_eur", float("nan")),
    ("proposed_amount_eur", float("inf")),
    ("cash_balance_eur", float("nan")),
    ("portfolio_value_eur", float("inf")),
    ("max_trade_risk_eur", -1),
    ("max_asset_exposure_pct", 101),
])
def test_invalid_guardrail_input_blocks_with_json_safe_amount(field, value):
    result = apply_guardrails(**{**BASE, field: value})
    assert result["allowed"] is False
    assert result["blocked_by"] == "guardrails_error"
    assert result["adjusted_amount_eur"] == 0
    assert math.isfinite(result["original_amount_eur"])


def test_zero_exposure_blocks_with_reason():
    result = apply_guardrails(**{**BASE, "max_asset_exposure_pct": 0})
    assert result["allowed"] is False
    assert result["blocked_by"] == "asset_exposure"
    assert result["guardrails"]["max_asset_exposure_pct"] == 0
    assert result["explanations"][-1]["code"] == "asset_exposure"


def test_no_proposal_is_not_a_safety_block():
    result = apply_guardrails(**{**BASE, "proposed_amount_eur": 0, "cash_balance_eur": 0})
    assert result["allowed"] is False
    assert result["blocked_by"] is None
    assert result["explanations"] == []


def test_every_reduction_is_explained_in_order():
    result = apply_guardrails(**{
        **BASE, "proposed_amount_eur": 100,
        "cash_balance_eur": 90, "invested_eur": 30,
        "total_budget_eur": 80, "max_trade_risk_eur": 40,
        "today_allocated_eur": 15, "daily_allocation_eur": 35,
        "portfolio_value_eur": 100, "max_asset_exposure_pct": 10,
    })
    assert result["allowed"] is True
    assert result["adjusted_amount_eur"] == 10
    assert [item["code"] for item in result["explanations"]] == [
        "cash_balance_trimmed", "total_budget_trimmed",
        "max_trade_risk_trimmed", "daily_allocation_trimmed",
        "asset_exposure_trimmed",
    ]
    assert result["explanations"][0]["from_amount_eur"] == 100
    assert result["explanations"][-1]["to_amount_eur"] == 10


def test_limit_trim_below_minimum_blocks_and_keeps_explanation():
    result = apply_guardrails(**{
        **BASE, "proposed_amount_eur": 30, "cash_balance_eur": 4,
    })
    assert result["blocked_by"] == "below_min_order"
    assert result["adjusted_amount_eur"] == 0
    assert [item["code"] for item in result["explanations"]] == [
        "cash_balance_trimmed", "below_min_order_size", "below_min_order",
    ]


def test_execution_recheck_uses_current_limits(monkeypatch):
    monkeypatch.setattr(trading_bot_execution, "get_bot_portfolio_state", lambda *_: {
        "qty": 0, "invested": 0,
    })
    monkeypatch.setattr(trading_bot_execution, "get_today_spent_eur", lambda *_: 20)
    current_bot = ("auto", False, True, 100, 200, 50, 5, 100)
    trading_bot_execution._recheck_auto_buy_limits(
        conn=None, user_id=1, bot_id=2, symbol="BTC", notional=20,
        price=100, cash=100, current_bot=current_bot,
    )
    with pytest.raises(trading_bot_execution.BotSafetyBlock, match="daglimiet"):
        trading_bot_execution._recheck_auto_buy_limits(
            conn=None, user_id=1, bot_id=2, symbol="BTC", notional=40,
            price=100, cash=100, current_bot=current_bot,
        )
    with pytest.raises(trading_bot_execution.BotSafetyBlock, match="daglimiet"):
        trading_bot_execution._recheck_auto_buy_limits(
            conn=None, user_id=1, bot_id=2, symbol="BTC", notional=30.01,
            price=100, cash=100, current_bot=current_bot,
        )
    with pytest.raises(trading_bot_execution.BotSafetyBlock, match="blootstelling"):
        trading_bot_execution._recheck_auto_buy_limits(
            conn=None, user_id=1, bot_id=2, symbol="BTC", notional=20,
            price=100, cash=100,
            current_bot=("auto", False, True, 0, 200, 50, 5, 100),
        )


def test_paper_reprice_preserves_approved_eur_spend():
    approved = 50
    old_qty = approved / 2000
    current_price = 2500
    qty = trading_bot_execution._paper_buy_quantity(approved, current_price)
    assert qty < old_qty
    assert qty * current_price <= approved
    assert round(qty * current_price, 2) == approved
