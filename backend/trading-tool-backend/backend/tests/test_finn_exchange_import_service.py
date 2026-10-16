import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.services.finn_exchange_import_service import (
    DAY_MS, FinnExchangeImportService, initial_cursor, normalize_bitvavo, normalize_bybit,
    provider_page,
)


NOW = int(time.time() * 1000) - 1000


def bitvavo_fill(**overrides):
    row = {"id": "fill-1", "orderId": "order-1", "market": "BTC-EUR",
           "side": "buy", "amount": "0.2", "price": "100.00", "fee": "0.02",
           "feeCurrency": "EUR", "timestamp": NOW, "settled": True}
    row.update(overrides)
    return row


def bybit_fill(**overrides):
    row = {"execId": "fill-1", "orderId": "order-1", "symbol": "BTCUSDT",
           "side": "Buy", "execQty": "0.2", "execPrice": "100", "execValue": "20",
           "execFee": "0.001", "feeCurrency": "BTC", "execTime": str(NOW),
           "execType": "Trade"}
    row.update(overrides)
    return row


def test_bitvavo_eur_and_bybit_non_eur_values_remain_separate():
    euro = normalize_bitvavo(bitvavo_fill(), "BTC/EUR")
    quote = normalize_bybit(bybit_fill(), "BTC/USDT")
    assert euro["quote_currency"] == "EUR" and euro["cost_quote"] == Decimal("20.000")
    assert quote["quote_currency"] == "USDT" and quote["cost_quote"] == Decimal("20")
    assert quote["fee_currency"] == "BTC"
    assert "pnl_eur" not in euro and "pnl_eur" not in quote


def test_bitvavo_negative_rebate_and_bybit_signed_fee_are_preserved():
    assert normalize_bitvavo(bitvavo_fill(fee="-0.01"), "BTC/EUR")["fee_amount"] == Decimal("-0.01")
    assert normalize_bybit(bybit_fill(execFee="-0.02"), "BTC/USDT")["fee_amount"] == Decimal("-0.02")


@pytest.mark.parametrize("row", [
    bitvavo_fill(settled=False),
    bitvavo_fill(market="BTC-USDT"),
    bitvavo_fill(orderId=""),
    bitvavo_fill(amount="NaN"),
    bitvavo_fill(timestamp=0),
])
def test_invalid_bitvavo_fill_fails_closed(row):
    with pytest.raises(ValueError):
        normalize_bitvavo(row, "BTC/EUR")


@pytest.mark.parametrize("row", [
    bybit_fill(execType="Funding"),
    bybit_fill(execValue="200"),
    bybit_fill(execId=""),
    bybit_fill(execTime="0"),
])
def test_invalid_bybit_execution_fails_closed(row):
    with pytest.raises(ValueError):
        normalize_bybit(row, "BTC/USDT")


def test_bybit_cursor_handles_same_timestamp_and_encoded_token():
    class Client:
        requests = []

        def market(self, symbol):
            assert symbol == "BTCUSDT"
            return {"spot": True, "symbol": "BTC/USDT"}

        async def privateGetV5ExecutionList(self, params):
            self.requests.append(params)
            cursor = params.get("cursor")
            return {"retCode": 0, "result": {"category": "spot",
                    "nextPageCursor": "a%3A2%2Cb%3A2" if cursor is None else "",
                    "list": [bybit_fill(execId="fill-1" if cursor is None else "fill-2")]}}

    async def exercise():
        client = Client()
        cursor = initial_cursor("bybit", NOW)
        cursor["window_start_ms"] = NOW - DAY_MS
        first, cursor, covered = await provider_page(client, "bybit", cursor, NOW)
        assert covered is None and cursor["page_cursor"] == "a%3A2%2Cb%3A2"
        second, cursor, covered = await provider_page(client, "bybit", cursor, NOW)
        assert covered is not None and cursor["page_cursor"] is None
        assert {item["exchange_trade_id"] for item in first + second} == {"fill-1", "fill-2"}
        assert client.requests[1]["cursor"] == "a%3A2%2Cb%3A2"
        assert client.requests[1]["endTime"] == client.requests[0]["endTime"]
        assert client.requests[0]["endTime"] - client.requests[0]["startTime"] < 7 * DAY_MS

    asyncio.run(exercise())


def test_owner_scoped_fill_page_hides_foreign_source(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def fetchone(self):
            return None

    class Session:
        statements = []

        async def execute(self, statement, params):
            self.statements.append((str(statement), params))
            return Result()

    async def exercise():
        session = Session()
        with pytest.raises(HTTPException) as exc:
            await FinnExchangeImportService(session).fills(12, 88)
        assert exc.value.status_code == 404
        assert len(session.statements) == 1
        sql, params = session.statements[0]
        assert "id=:source_id AND user_id=:user_id" in sql
        assert params == {"source_id": 88, "user_id": 12}

    asyncio.run(exercise())


def test_bybit_page_rejects_nonadvancing_cursor_without_checkpointing():
    class Client:
        def market(self, _symbol):
            return {"spot": True, "symbol": "BTC/USDT"}

        async def privateGetV5ExecutionList(self, _params):
            return {"retCode": 0, "result": {"category": "spot", "list": [bybit_fill()],
                                               "nextPageCursor": "same"}}

    async def exercise():
        cursor = initial_cursor("bybit", NOW)
        cursor["window_start_ms"] = NOW - DAY_MS
        cursor["page_cursor"] = "same"
        cursor["window_end_ms"] = NOW
        with pytest.raises(ValueError, match="did not advance"):
            await provider_page(Client(), "bybit", cursor, NOW)
        assert cursor["page_cursor"] == "same"

    asyncio.run(exercise())


@pytest.mark.parametrize("exchange_name", ["bitvavo", "bybit"])
def test_provider_page_rejects_fill_outside_requested_window(exchange_name):
    class Client:
        def market(self, _symbol):
            return {"spot": True, "symbol": "BTC/USDT"}

        async def privateGetV5ExecutionList(self, _params):
            return {"retCode": 0, "result": {"category": "spot", "list": [bybit_fill()],
                                               "nextPageCursor": ""}}

        async def privateGetTrades(self, _params):
            return [bitvavo_fill(timestamp=NOW - 2 * DAY_MS)]

    async def exercise():
        if exchange_name == "bybit":
            cursor = initial_cursor("bybit", NOW)
            with pytest.raises(ValueError, match="outside requested window"):
                await provider_page(Client(), "bybit", cursor, NOW)
        else:
            day = NOW // DAY_MS * DAY_MS
            cursor = {"phase": "trades", "snapshot_until_ms": NOW,
                      "markets": ["BTC/EUR"], "activity_days": {"BTC/EUR": [day]},
                      "market_index": 0, "day_index": 0, "trade_id_to": None}
            with pytest.raises(ValueError, match="outside requested window"):
                await provider_page(Client(), "bitvavo", cursor, NOW)

    asyncio.run(exercise())


def test_bitvavo_market_discovery_then_one_day_trade_window():
    class Client:
        requests = []

        async def request(self, path, scope, method, params):
            self.requests.append((path, scope, method, params))
            return {"currentPage": 1, "totalPages": 1,
                    "items": [{"type": "buy", "receivedCurrency": "BTC",
                               "sentCurrency": "EUR", "priceCurrency": "EUR",
                               "executedAt": datetime.fromtimestamp(NOW / 1000, tz=timezone.utc).isoformat()}]}

        async def privateGetTrades(self, params):
            self.requests.append(params)
            return [bitvavo_fill()]

    async def exercise():
        client = Client()
        cursor = initial_cursor("bitvavo", NOW)
        rows, cursor, coverage = await provider_page(client, "bitvavo", cursor, NOW)
        assert rows == [] and coverage is None
        assert cursor["phase"] == "trades" and cursor["markets"] == ["BTC/EUR"]
        rows, cursor, coverage = await provider_page(client, "bitvavo", cursor, NOW)
        assert rows[0]["exchange_order_id"] == "order-1"
        assert coverage == NOW
        assert client.requests[-1]["end"] - client.requests[-1]["start"] < DAY_MS
        assert client.requests[-1]["start"] == NOW // DAY_MS * DAY_MS

    asyncio.run(exercise())


def test_bitvavo_activity_days_avoid_empty_historical_windows_and_page_all_markets():
    first = NOW - 300 * DAY_MS
    second = NOW - 3 * DAY_MS

    class Client:
        requests = []

        async def request(self, path, scope, method, params):
            self.requests.append(params)
            at = first if params["page"] == 1 else second
            return {"currentPage": params["page"], "totalPages": 2,
                    "items": [{"type": "buy", "receivedCurrency": "BTC",
                               "priceCurrency": "EUR",
                               "executedAt": datetime.fromtimestamp(at / 1000, tz=timezone.utc).isoformat()}]}

        async def privateGetTrades(self, params):
            self.requests.append(params)
            return []

    async def exercise():
        client = Client()
        cursor = initial_cursor("bitvavo", NOW)
        _, cursor, _ = await provider_page(client, "bitvavo", cursor, NOW)
        _, cursor, _ = await provider_page(client, "bitvavo", cursor, NOW)
        assert cursor["activity_days"]["BTC/EUR"] == sorted({first // DAY_MS * DAY_MS,
                                                               second // DAY_MS * DAY_MS})
        _, cursor, covered = await provider_page(client, "bitvavo", cursor, NOW)
        assert covered is None
        _, cursor, covered = await provider_page(client, "bitvavo", cursor, NOW)
        assert covered == NOW
        trade_calls = [call for call in client.requests if "market" in call]
        assert len(trade_calls) == 2
        assert trade_calls[1]["start"] - trade_calls[0]["start"] > 290 * DAY_MS

    asyncio.run(exercise())


def test_bitvavo_unknown_buy_market_fails_coverage_instead_of_silent_omission():
    class Client:
        async def request(self, *_args):
            return {"currentPage": 1, "totalPages": 1,
                    "items": [{"type": "buy", "receivedCurrency": "BTC",
                               "priceCurrency": None, "executedAt": "2026-10-01T00:00:00Z"}]}

    async def exercise():
        with pytest.raises(ValueError, match="Unsupported provider spot pair"):
            await provider_page(Client(), "bitvavo", initial_cursor("bitvavo", NOW), NOW)

    asyncio.run(exercise())


def test_bitvavo_full_trade_page_keeps_same_day_until_cursor_advances():
    class Client:
        calls = []

        async def privateGetTrades(self, params):
            self.calls.append(params)
            if "tradeIdTo" not in params:
                return [bitvavo_fill(id=f"fill-{i}") for i in range(1000)]
            return [bitvavo_fill(id="last-fill")]

    async def exercise():
        client = Client()
        day = NOW // DAY_MS * DAY_MS
        cursor = {"phase": "trades", "since_ms": 0, "snapshot_until_ms": NOW,
                  "markets": ["BTC/EUR"], "activity_days": {"BTC/EUR": [day]},
                  "market_index": 0, "day_index": 0, "trade_id_to": None}
        rows, cursor, covered = await provider_page(client, "bitvavo", cursor, NOW)
        assert len(rows) == 1000 and covered is None
        assert cursor["day_index"] == 0 and cursor["trade_id_to"] == "fill-999"
        rows, cursor, covered = await provider_page(client, "bitvavo", cursor, NOW)
        assert len(rows) == 1 and covered == NOW
        assert client.calls[1]["tradeIdTo"] == "fill-999"

    asyncio.run(exercise())
