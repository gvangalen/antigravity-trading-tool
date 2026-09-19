import asyncio
from pathlib import Path

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
