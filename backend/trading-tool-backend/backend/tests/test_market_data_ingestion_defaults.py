import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest

from backend.schemas.market_provider_schema import AssetRecord, PriceSnapshotDTO
from backend.services.market_data_ingestion_service import MarketDataIngestionService


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
    base = {"symbol": "BTC", "provider": "binance", "provider_symbol": "BTCUSDT", "price": 100}
    verified = service._build_market_data_row(PriceSnapshotDTO(**base, observed_at=observed))
    unknown = service._build_market_data_row(PriceSnapshotDTO(**base, observed_at=None))

    assert verified.source_observed_at == observed.replace(tzinfo=None)
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
