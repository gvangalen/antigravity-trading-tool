import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.services.finn_bybit_derivative_service import (
    closed_episodes, derivative_page, initial_cursor, normalize_execution, normalize_order,
)


START = datetime(2026, 10, 16, tzinfo=timezone.utc)
MARKET = {"id": "BTCUSDT", "contract": True, "linear": True, "inverse": False,
          "settle": "USDT"}


def execution(index, side, qty, *, idx=0, closed=None, at=None, seq=None):
    return {"id": index, "exec_id": f"exec-{index}", "category": "linear",
            "symbol": "BTCUSDT", "position_idx": idx, "exec_type": "Trade",
            "side": side, "qty": Decimal(str(qty)),
            "closed_size": Decimal(str(closed)) if closed is not None else None,
            "traded_at": at or START + timedelta(minutes=index),
            "seq": seq if seq is not None else index}


def test_long_addons_partial_closes_and_complete_close():
    episodes, balance = closed_episodes([
        execution(1, "buy", 2, idx=1, closed=0),
        execution(2, "buy", 1, idx=1, closed=0),
        execution(3, "sell", 1, idx=1, closed=1),
        execution(4, "sell", 2, idx=1, closed=2),
    ])
    assert balance == 0 and len(episodes) == 1
    assert episodes[0]["direction"] == "long"
    assert [part["qty"] for part in episodes[0]["slices"]] == [2, 1, 1, 2]


def test_hedge_short_is_separate_stream_and_closes_on_buy():
    episodes, balance = closed_episodes([
        execution(1, "sell", 2, idx=2, closed=0),
        execution(2, "buy", 0.5, idx=2, closed=0.5),
        execution(3, "buy", 1.5, idx=2, closed=1.5),
    ])
    assert balance == 0 and episodes[0]["direction"] == "short"
    with pytest.raises(ValueError, match="één positie-stream"):
        closed_episodes([execution(1, "buy", 1, idx=1), execution(2, "sell", 1, idx=2)])


def test_one_way_reversal_splits_one_execution_into_close_and_open():
    episodes, balance = closed_episodes([
        execution(1, "buy", 2, closed=0),
        execution(2, "sell", 3, closed=2),
        execution(3, "buy", 1, closed=1),
    ])
    assert balance == 0 and [episode["direction"] for episode in episodes] == ["long", "short"]
    assert episodes[0]["slices"][-1]["qty"] == 2
    assert episodes[1]["slices"][0]["qty"] == 1
    assert episodes[0]["slices"][-1]["execution_id"] == episodes[1]["slices"][0]["execution_id"] == 2


def test_unknown_preexisting_position_is_not_called_a_complete_trade():
    episodes, balance = closed_episodes([
        execution(1, "sell", 1, closed=1),
        execution(2, "buy", 1, closed=0),
        execution(3, "sell", 1, closed=1),
    ], initial_signed_qty=Decimal(1))
    assert balance == 0 and len(episodes) == 1
    assert episodes[0]["slices"][0]["execution_id"] == 2


def test_truncated_leading_history_can_only_yield_attestable_suffix():
    history = [
        execution(1, "sell", 1, closed=1),  # prior opening is outside provider history
        execution(2, "buy", 2, closed=0),
        execution(3, "sell", 2, closed=2),
    ]
    with pytest.raises(ValueError, match="closedSize"):
        closed_episodes(history)
    episodes, balance = closed_episodes(history[1:], stop_after_first=True)
    assert balance == 0 and len(episodes) == 1
    assert [part["execution_id"] for part in episodes[0]["slices"]] == [2, 3]


@pytest.mark.parametrize("rows", [
    [execution(1, "buy", 1, idx=1), execution(2, "sell", 2, idx=1)],
    [execution(1, "sell", 1, idx=2), execution(2, "buy", 2, idx=2)],
    [execution(1, "buy", 1, closed=0), execution(2, "sell", 1, closed=0)],
    [execution(1, "buy", 1, at=START, seq=1), execution(2, "sell", 1, at=START, seq=1)],
])
def test_ambiguous_or_inconsistent_derivative_episode_rejected(rows):
    with pytest.raises(ValueError):
        closed_episodes(rows)


def test_derivative_normalization_keeps_native_value_and_unmodeled_event_gap():
    raw = {"execId": "ex-1", "orderId": "ord-1", "symbol": "BTCUSDT",
           "execType": "Trade", "side": "Sell", "execQty": "2", "execPrice": "100",
           "execValue": "200", "execFee": "-0.01", "feeCurrency": "USDT",
           "closedSize": "1", "execTime": "1792152000000", "seq": 9}
    fill = normalize_execution(raw, category="linear", market=MARKET)
    assert fill["qty"] == 2 and fill["closed_size"] == 1
    assert fill["fee_amount"] == Decimal("-0.01")
    assert fill["settle_currency"] == "USDT"
    assert "pnl_eur" not in fill
    event = normalize_execution({**raw, "execId": "ex-2", "execType": "MovePosition"},
                                category="linear", market=MARKET)
    assert event["evidence_status"] == "material_event_unmodeled"
    future_event = normalize_execution({**raw, "execId": "ex-3", "execType": "NewProviderEvent"},
                                       category="linear", market=MARKET)
    assert future_event["evidence_status"] == "material_event_unmodeled"
    delisted = normalize_execution({**raw, "execId": "ex-4"},
                                   category="linear", market=None)
    assert delisted["evidence_status"] == "material_event_unmodeled"
    assert delisted["settle_currency"] == "UNKNOWN" and "price" not in delisted

    inverse = normalize_execution({**raw, "symbol": "BTCUSD", "execId": "ex-inverse",
                                   "execValue": "0.01", "feeCurrency": "BTC"},
                                  category="inverse", market={"id": "BTCUSD", "contract": True,
                                      "linear": False, "inverse": True, "settle": "BTC",
                                      "base": "BTC", "quote": "USD", "contractSize": 1})
    assert inverse["execution_value"] == Decimal("0.01")
    assert inverse["quote_currency"] == "USD" and inverse["settle_currency"] == "BTC"


def test_order_join_requires_exact_order_and_index():
    order = {"orderId": "ord-1", "symbol": "BTCUSDT", "positionIdx": 2,
             "side": "Sell", "reduceOnly": False, "orderStatus": "Filled"}
    assert normalize_order(order, category="linear", order_id="ord-1", symbol="BTCUSDT")["position_idx"] == 2
    with pytest.raises(ValueError):
        normalize_order({**order, "positionIdx": None}, category="linear", order_id="ord-1", symbol="BTCUSDT")


def test_bybit_derivative_cursor_paginates_without_skipping_same_timestamp():
    now_ms = int(START.timestamp() * 1000)
    raw = {"execId": "ex-1", "orderId": "ord-1", "symbol": "BTCUSDT",
           "execType": "Trade", "side": "Buy", "execQty": "1", "execPrice": "100",
           "execValue": "100", "execFee": "0.01", "feeCurrency": "USDT",
           "closedSize": "0", "execTime": str(now_ms - 1000), "seq": 9}

    class Client:
        requests = []

        def market(self, symbol):
            assert symbol == "BTCUSDT"
            return MARKET

        async def privateGetV5ExecutionList(self, params):
            self.requests.append(params)
            first = "cursor" not in params
            return {"retCode": 0, "result": {"category": "linear",
                    "nextPageCursor": "next%3A1" if first else "",
                    "list": [{**raw, "execId": "ex-1" if first else "ex-2"}]}}

    async def exercise():
        client = Client()
        cursor = initial_cursor(now_ms)
        cursor["window_start_ms"] = now_ms - 2000
        first, cursor, covered = await derivative_page(client, "linear", cursor, now_ms)
        assert covered is None and cursor["page_cursor"] == "next%3A1"
        second, cursor, covered = await derivative_page(client, "linear", cursor, now_ms)
        assert covered == now_ms and cursor["page_cursor"] is None
        assert {item["exec_id"] for item in first + second} == {"ex-1", "ex-2"}
        assert client.requests[1]["cursor"] == "next%3A1"

    asyncio.run(exercise())


def test_delisted_contract_does_not_block_cursor_and_is_a_material_gap():
    now_ms = int(START.timestamp() * 1000)

    class Client:
        def market(self, _symbol):
            raise KeyError("delisted")

        async def privateGetV5ExecutionList(self, _params):
            return {"retCode": 0, "result": {"category": "linear", "nextPageCursor": "",
                    "list": [{"symbol": "OLDUSDT", "execId": "old-1", "orderId": "old-order",
                              "execType": "Trade", "execTime": str(now_ms - 1000)}]}}

    async def exercise():
        cursor = initial_cursor(now_ms)
        cursor["window_start_ms"] = now_ms - 2000
        events, advanced, covered = await derivative_page(Client(), "linear", cursor, now_ms)
        assert len(events) == 1 and events[0]["evidence_status"] == "material_event_unmodeled"
        assert advanced["window_start_ms"] == now_ms - 2000 and covered == now_ms

    asyncio.run(exercise())


def test_derivative_finn_context_has_native_units_and_no_fabricated_eur_result():
    from backend.services.finn_trade_analysis_service import evidence_context, validate_analysis

    review = {
        "id": 91, "symbol": "BTCUSD", "execution_environment": "live",
        "entry_at": START, "exit_at": START + timedelta(minutes=2),
        "origin": "bybit_derivative_user_attested", "closure_basis": "user_confirmed",
        "attested_at": START + timedelta(minutes=3), "base_currency": "BTC",
        "derivative_category": "inverse", "position_idx": 2,
        "direction": "short", "settle_currency": "BTC",
        "native_pnl_status": "unavailable", "pnl_status": "not_comparable",
        "fee_legs_by_currency": [], "entry_value_eur": None,
        "exit_value_eur": None, "pnl_eur_before_fees": None,
        "plan_snapshot": None, "note": "", "candles_json": None,
        "candles_status": "unavailable", "candles_reason": "no candles",
        "has_screenshot": False,
        "fills": [{"derivative_execution_id": 17, "role": "open", "side": "sell",
                   "at": START.isoformat(), "qty": "1", "raw_exec_qty": "1",
                   "price_quote": "100", "quote_currency": "USD",
                   "settle_currency": "BTC", "position_idx": 2,
                   "category": "inverse", "fee_amount_raw_execution": "0.001",
                   "fee_currency": "BTC"}],
    }
    context, allowed = evidence_context(review)
    assert context["direction"] == "short"
    assert context["settle_currency"] == "BTC"
    assert context["pnl_eur_before_fees"] is None
    assert context["fills"][0]["price"] == "100"
    assert "derivative_exec:17:open" in allowed
    raw = {"summary": "Retrospectieve analyse", "uncertainty": "Onzeker",
           "question": "Waarom sloot je?", "observations": [
               {"text": "Uitvoering", "evidence_ids": ["derivative_exec:17:open"],
                "theme": "exit_process"}]}
    validated = validate_analysis(raw, allowed, context)
    assert "native PnL" in validated["uncertainty"]
    assert "€" not in validated["summary"]
