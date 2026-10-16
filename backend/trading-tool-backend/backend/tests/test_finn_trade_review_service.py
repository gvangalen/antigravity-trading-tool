from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.services.finn_trade_review_service import build_closed_positions


START = datetime(2026, 10, 16, tzinfo=timezone.utc)


def fill(index, qty, cash, *, environment="paper", status="filled", bot_id=5, symbol="BTC",
         source="bot", valuation_version=2, exchange_symbol=None, exchange_order_id=None):
    return {
        "ledger_id": index, "bot_id": bot_id, "symbol": symbol,
        "order_id": index // 2 + 1, "qty_delta": Decimal(str(qty)),
        "cash_delta_eur": Decimal(str(cash)),
        "price_eur": Decimal(str(abs(cash / qty))),
        "ts": START + timedelta(minutes=index),
        "environment": environment, "order_status": status,
        "source": source, "valuation_version": valuation_version,
        "exchange_symbol": exchange_symbol or (f"{symbol}/EUR" if environment == "live" else None),
        "exchange_order_id": exchange_order_id or (f"exchange-{index}" if environment == "live" else None),
        "plan_snapshot": {"risk": {"max": 20}} if index == 1 else None,
    }


def test_partial_fills_and_partial_exits_become_one_completed_position():
    fills = [fill(1, 0.4, -40), fill(2, 0.6, -66), fill(3, -0.3, 36), fill(4, -0.7, 84)]
    reviews, excluded = build_closed_positions(fills, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    assert reviews[0]["opening_ledger_id"] == 1
    assert reviews[0]["closing_ledger_id"] == 4
    assert reviews[0]["pnl_eur_before_fees"] == Decimal(14)
    assert len(reviews[0]["fills"]) == 4
    assert reviews[0]["plan_snapshot"] == {"risk": {"max": 20}}
    assert excluded == {"legacy_or_ambiguous": 0, "inconsistent": 0}


def test_open_and_legacy_positions_do_not_get_reviews():
    rows = [fill(1, -0.5, 60), fill(2, 0.2, -20)]
    reviews, excluded = build_closed_positions(rows, {(5, "BTC"): Decimal("0.5")}, {(5, "BTC"): Decimal("0.2")})
    assert reviews == []
    assert excluded["legacy_or_ambiguous"] > 0


def test_new_complete_position_after_legacy_flat_is_reviewed():
    rows = [fill(1, -0.5, 60), fill(2, 1, -100), fill(3, -1, 110)]
    reviews, excluded = build_closed_positions(
        rows, {(5, "BTC"): Decimal("0.5")}, {(5, "BTC"): Decimal(0)},
    )
    assert [review["opening_ledger_id"] for review in reviews] == [2]
    assert excluded["legacy_or_ambiguous"] == 1


def test_unsettled_order_and_open_position_do_not_get_reviews():
    rows = [fill(1, 1, -100), fill(2, -1, 110, status="sent")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == []


def test_unknown_or_mixed_environment_is_excluded_until_flat():
    rows = [fill(1, 1, -100, environment=None), fill(2, -1, 120, environment="live")]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == []
    assert excluded["legacy_or_ambiguous"] == 1


def test_inconsistent_portfolio_blocks_projection():
    rows = [fill(1, 1, -100), fill(2, -1, 120)]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal("0.1")})
    assert reviews == []
    assert excluded["inconsistent"] == 1


def test_losses_are_reviewed_too():
    reviews, _ = build_closed_positions(
        [fill(1, 1, -100), fill(2, -1, 80)], {}, {(5, "BTC"): Decimal(0)},
    )
    assert len(reviews) == 1
    assert reviews[0]["pnl_eur_before_fees"] == Decimal(-20)


def test_manual_and_bot_orders_in_same_position_are_covered():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="bot")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    assert reviews[0]["execution_sources"] == ["bot", "manual"]
    assert reviews[0]["fills"][0]["source"] == "manual"


def test_manual_confirmed_decision_is_classified_manual_and_auto_decision_bot():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="bot")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews[0]["execution_sources"] == ["bot", "manual"]
    assert [part["source"] for part in reviews[0]["fills"]] == ["manual", "bot"]


def test_no_decision_manual_order_is_classified_manual():
    rows = [fill(1, 1, -100, source="manual"), fill(2, -1, 110, source="manual")]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews[0]["execution_sources"] == ["manual"]


def test_unknown_decision_executor_does_not_invent_source():
    rows = [fill(1, 1, -100, source=None), fill(2, -1, 110, source="bot")]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1


def test_unverified_paper_eur_amount_is_not_used_for_pnl():
    rows = [fill(1, 1, -100, valuation_version=1), fill(2, -1, 120)]
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1


def test_live_confirmed_eur_exchange_pair_is_required():
    rows = [fill(1, 1, -100, environment="live", valuation_version=1),
            fill(2, -1, 120, environment="live", valuation_version=1)]
    reviews, _ = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert len(reviews) == 1
    rows[1]["exchange_symbol"] = "BTC/USDT"
    reviews, excluded = build_closed_positions(rows, {}, {(5, "BTC"): Decimal(0)})
    assert reviews == [] and excluded["legacy_or_ambiguous"] == 1
