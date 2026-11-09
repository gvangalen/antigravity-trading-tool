import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.market_source_ref import market_source_ref
from backend.services.finn_v2_tool_adapters.market_tool_adapter import MarketToolAdapter
from backend.engine import trading_bot_execution as worker


def test_source_ref_normalizes_offset_and_rejects_missing_measurement():
    observed = datetime(2026, 11, 8, 10, 30, tzinfo=timezone(timedelta(hours=1)))
    assert market_source_ref(market_id=43, measurement_id=987,
                             source_observed_at=observed) == {
        "market_id": 43, "measurement_id": 987,
        "source_observed_at_utc": "2026-11-08T09:30:00+00:00",
    }
    assert market_source_ref(market_id=43, measurement_id=None,
                             source_observed_at=observed) is None


def test_finn_market_read_binds_ref_to_selected_exact_quote():
    quote = SimpleNamespace(
        id=987, market_id=43, symbol="BTC", price=70000,
        quote_currency="EUR", price_provider="binance", change_24h=1.2,
        volume=5, source_observed_at=datetime(2026, 11, 8, 9, 30),
    )

    class Repository:
        async def get_latest_exact_market_snapshot(self, market_id):
            assert market_id == 43
            return quote

    adapter = object.__new__(MarketToolAdapter)
    adapter.repository = Repository()
    result = asyncio.run(adapter.execute(asset="BTC", user_id=7,
                                         market_id=43, quote_currency="EUR"))
    assert result["data"].source_ref.measurement_id == 987
    assert result["data"].source_ref.market_id == 43
    assert result["data"].source_ref.source_observed_at_utc == (
        datetime(2026, 11, 8, 9, 30, tzinfo=timezone.utc))


def test_paper_quote_context_preserves_selected_measurement_id():
    observed = datetime.now(timezone.utc) - timedelta(minutes=1)

    class Cursor:
        query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params=None):
            self.query = query

        def fetchone(self):
            if "FROM trading_markets" in self.query:
                return ("EUR",)
            if "FROM market_data" in self.query:
                return (70000, observed, "EUR", 987)
            raise AssertionError(self.query)

        def fetchall(self):
            assert "FROM portfolio_fx_rates" in self.query
            return []

    class Connection:
        def cursor(self):
            return Cursor()

    context = worker._get_trade_quote_fx_context(
        Connection(), "BTC", require_usd=False, market_id=43)
    assert context["source_ref"] == {
        "market_id": 43, "measurement_id": 987,
        "source_observed_at_utc": observed.isoformat(),
    }
    assert worker._paper_execution_quote_evidence(context)["execution_source_ref"] == context["source_ref"]


def test_paper_assessment_price_keeps_its_selected_quote_row():
    observed = datetime.now(timezone.utc) - timedelta(minutes=1)

    class Cursor:
        query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params=None):
            self.query = query

        def fetchone(self):
            assert "FROM market_data m" in self.query
            return (70000, 60, "EUR", observed, "EUR", 987)

    class Connection:
        def cursor(self):
            return Cursor()

    price = worker._get_live_price(Connection(), "BTC", paper_execution=True, market_id=43)
    assert price == 70000
    assert price.source_ref == {
        "market_id": 43, "measurement_id": 987,
        "source_observed_at_utc": observed.isoformat(),
    }
