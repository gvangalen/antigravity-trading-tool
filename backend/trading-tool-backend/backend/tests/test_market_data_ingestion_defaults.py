import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from backend.schemas.market_provider_schema import AssetRecord, PriceSnapshotDTO
from backend.services.market_data_ingestion_service import MarketDataIngestionService
from backend.services.providers.twelve_data_market_data_adapter import TwelveDataMarketDataAdapter
from backend.infrastructure.models import MarketData
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository


def test_default_snapshot_ingestion_includes_supported_multi_asset_equities():
    service = MarketDataIngestionService(session=object())
    captured = {}

    async def fake_ingest(symbols, **kwargs):
        captured["symbols"] = list(symbols)
        captured["kwargs"] = kwargs
        return {"requested": list(symbols)}

    service.ingest_latest_snapshots = fake_ingest
    result = asyncio.run(service.ingest_default_v1_snapshots(commit=False))

    assert {"AAPL", "MSFT"}.issubset(captured["symbols"])
    assert captured["kwargs"] == {"commit": False, "continue_on_error": True}
    assert result["requested"] == captured["symbols"]


def test_equity_quote_routing_migration_is_explicit_and_idempotent():
    source = (Path(__file__).parents[1] / "scripts/migrations/2026_09_19_equity_quote_provider_routing.py").read_text()

    assert "symbol IN ('AAPL', 'MSFT')" in source
    assert "primary_provider = 'twelve_data'" in source
    assert "provider_symbol = symbol" in source


def test_market_ingestion_preserves_provider_time_separately_from_receipt_time():
    service = MarketDataIngestionService(session=object())
    observed = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    base = {"symbol": "BTC", "provider": "binance", "provider_symbol": "BTCUSDT",
            "price": 100, "currency": "USDT"}
    verified = service._build_market_data_row(PriceSnapshotDTO(**base, observed_at=observed))
    unknown = service._build_market_data_row(PriceSnapshotDTO(**base, observed_at=None))

    assert verified.source_observed_at == observed.replace(tzinfo=None)
    assert verified.timestamp == verified.source_observed_at
    assert verified.quote_currency == "USDT"
    assert verified.price_provider == "binance"
    assert unknown.source_observed_at is None
    assert unknown.timestamp is not None


def test_market_ingestion_refuses_provider_currency_different_from_catalog():
    service = MarketDataIngestionService(session=object())
    class Provider:
        async def fetch_latest_snapshot(self, _asset):
            return PriceSnapshotDTO(symbol="BTC", provider="test", provider_symbol="BTCEUR",
                                    price=100, currency="EUR", observed_at=datetime.now(timezone.utc))

    service.provider_registry.resolve_for_asset = lambda _asset: Provider()
    asset = AssetRecord(symbol="BTC", display_name="Bitcoin", asset_class="crypto", quote_currency="USDT")
    with pytest.raises(ValueError, match="market_quote_currency_mismatch"):
        asyncio.run(service._fetch_snapshot(asset))


def test_scheduled_ingestion_ends_catalog_transaction_before_provider_wait():
    events = []

    class Session:
        async def rollback(self):
            events.append("rollback")

        def add(self, _record):
            events.append("add")

        async def commit(self):
            events.append("commit")

    service = MarketDataIngestionService(Session())

    async def get_assets(_symbols):
        events.append("catalog")
        return {"BTC": {"symbol": "BTC", "display_name": "Bitcoin",
                        "asset_class": "crypto", "quote_currency": "USDT"}}

    async def fetch(_asset):
        events.append("provider")
        return PriceSnapshotDTO(symbol="BTC", provider="test", provider_symbol="BTCUSDT",
                                price=100, currency="USDT", observed_at=datetime.now(timezone.utc))

    service.asset_catalog_service.get_assets = get_assets
    service._fetch_snapshot = fetch
    result = asyncio.run(service.ingest_latest_snapshots(
        ["BTC"], release_catalog_read_transaction=True,
    ))

    assert result["success_count"] == 1
    assert events == ["catalog", "rollback", "provider", "add", "commit"]


def test_conflicting_equity_quote_uses_final_candle_without_writing_mutable_quote():
    minute = datetime(2026, 11, 10, 20, 59, tzinfo=timezone.utc)
    events = []

    class _Session:
        async def rollback(self):
            events.append("rollback")

        def add(self, record):
            events.append(("add", record))

        async def commit(self):
            events.append("commit")

    service = MarketDataIngestionService(_Session())
    asset = {"symbol": "AAPL", "display_name": "Apple Inc.", "asset_class": "stock",
             "provider": "twelve_data", "primary_provider": "twelve_data",
             "quote_currency": "USD", "provider_symbol": "AAPL"}

    async def get_assets(_symbols):
        return {"AAPL": asset}

    async def fetch(_asset):
        return PriceSnapshotDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
                                price=350.80, currency="USD", observed_at=minute)

    class _Provider:
        async def fetch_final_minute_snapshot(self, _asset, quote):
            assert quote.observed_at == minute
            events.append("final_candle")
            return PriceSnapshotDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
                                    price=350.81, currency="USD",
                                    observed_at=minute.replace(minute=0).replace(hour=21))

    service.asset_catalog_service.get_assets = get_assets
    service._fetch_snapshot = fetch
    async def source_rows(_symbol, _observed, *, final_only=False):
        events.append("read")
        return [] if final_only else [SimpleNamespace(
            symbol="AAPL", price=350.75, quote_currency="USD", price_provider="twelve_data",
        )]
    service._source_rows_at = source_rows
    service.provider_registry.resolve_for_asset = lambda _asset: _Provider()
    result = asyncio.run(service.ingest_latest_snapshots(
        ["AAPL"], release_catalog_read_transaction=True,
    ))

    assert result["success_count"] == 1
    assert events[0:4] == ["rollback", "read", "read", "final_candle"]
    record = events[4][1]
    assert record.is_final_candle is True
    assert record.price == 350.81
    assert record.source_observed_at == datetime(2026, 11, 10, 21, 0)
    assert events[5] == "commit"


def test_reconciled_equity_minute_is_not_fetched_again():
    minute = datetime(2026, 11, 10, 20, 59, tzinfo=timezone.utc)
    calls = []

    service = MarketDataIngestionService(object())
    async def source_rows(_symbol, _observed, *, final_only=False):
        calls.append("read")
        return [SimpleNamespace(symbol="AAPL", price=350.81 if final_only else 350.75,
                                quote_currency="USD", price_provider="twelve_data")]
    service._source_rows_at = source_rows
    service.provider_registry.resolve_for_asset = lambda _asset: pytest.fail("repeated provider call")
    asset = AssetRecord(symbol="AAPL", display_name="Apple Inc.", asset_class="stock",
                        provider="twelve_data", quote_currency="USD", provider_symbol="AAPL")
    quote = PriceSnapshotDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
                             price=350.80, currency="USD", observed_at=minute)
    resolved = asyncio.run(service._reconcile_conflicting_quote(asset, quote))
    assert resolved == (None, True)
    assert calls == ["read", "read"]


def test_ingestion_and_real_adapter_recover_aapl_conflict(monkeypatch):
    minute = datetime(2026, 11, 10, 20, 59, tzinfo=timezone.utc)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"meta": {"symbol": "AAPL", "currency": "USD"},
                    "values": [{"datetime": "2026-11-10 20:59:00", "close": "350.81",
                                "volume": "1000"}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient", Client,
    )
    provider = TwelveDataMarketDataAdapter(api_key="test-key")
    service = MarketDataIngestionService(object())
    async def source_rows(_symbol, _observed, *, final_only=False):
        return [] if final_only else [MarketData(
            symbol="AAPL", price=350.75, quote_currency="USD", price_provider="twelve_data",
        )]
    service._source_rows_at = source_rows
    service.provider_registry.resolve_for_asset = lambda _asset: provider
    asset = AssetRecord(symbol="AAPL", display_name="Apple Inc.", asset_class="stock",
                        provider="twelve_data", quote_currency="USD", provider_symbol="AAPL")
    quote = PriceSnapshotDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
                             price=350.80, previous_close=350, currency="USD", observed_at=minute)
    recovered, final = asyncio.run(service._reconcile_conflicting_quote(asset, quote))
    assert final is True
    row = service._build_market_data_row(recovered)
    row.is_final_candle = True
    assert row.source_observed_at == datetime(2026, 11, 10, 21, 0)
    assert row.change_24h is not None and row.volume == 1000
    older = [MarketData(symbol="AAPL", price=price, quote_currency="USD",
                        price_provider="twelve_data", is_final_candle=False,
                        source_observed_at=datetime(2026, 11, 10, 20, 59),
                        timestamp=datetime(2026, 11, 10, 20, 59)) for price in (350.75, 350.80)]
    assert MarketDataRepository._verified_top_quote([*older, row]) is row


def test_next_minute_quote_takes_precedence_over_prior_final_candle():
    moment = datetime(2026, 11, 10, 21, 0)
    final = MarketData(symbol="AAPL", price=350.81, quote_currency="USD",
                       price_provider="twelve_data", is_final_candle=True,
                       source_observed_at=moment, timestamp=moment)
    quote = MarketData(symbol="AAPL", price=350.82, quote_currency="USD",
                       price_provider="twelve_data", is_final_candle=False,
                       source_observed_at=moment, timestamp=moment)
    assert MarketDataRepository._verified_top_quote([final, quote]) is quote
    # A bounded SQL read could conceal another conflicting quote after these
    # rows.  The cap must be checked before candle rows are filtered out.
    assert MarketDataRepository._verified_top_quote([final] * 4095 + [quote]) is None


def test_interactive_ingestion_does_not_open_second_connection_for_recovery():
    class Session:
        def __init__(self):
            self.rows = []

        async def execute(self, _statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [
                SimpleNamespace(symbol="AAPL", price=350.75, quote_currency="USD",
                                price_provider="twelve_data"),
            ]))

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            pass

    session = Session()
    service = MarketDataIngestionService(session)

    async def get_assets(_symbols):
        return {"AAPL": {"symbol": "AAPL", "display_name": "Apple Inc.",
                         "asset_class": "stock", "provider": "twelve_data",
                         "quote_currency": "USD", "provider_symbol": "AAPL"}}

    async def fetch(_asset):
        return PriceSnapshotDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
                                price=350.80, currency="USD",
                                observed_at=datetime(2026, 11, 10, 20, 59, tzinfo=timezone.utc))

    async def forbidden_recovery(*_args, **_kwargs):
        pytest.fail("interactive path must not request a second DB connection")

    service.asset_catalog_service.get_assets = get_assets
    service._fetch_snapshot = fetch
    service._reconcile_conflicting_quote = forbidden_recovery
    result = asyncio.run(service.ingest_latest_snapshots(["AAPL"], commit=False))
    assert result["success_count"] == 0
    assert result["skipped"] == ["AAPL"]
    assert len(session.rows) == 0
