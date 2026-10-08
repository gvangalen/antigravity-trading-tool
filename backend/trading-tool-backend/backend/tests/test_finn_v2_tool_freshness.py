import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
from backend.services.finn_v2_tool_adapters.technical_tool_adapter import TechnicalToolAdapter


def test_freshness_service_marks_market_data_stale_after_threshold():
    service = FinnV2FreshnessService()
    stale = datetime.now(timezone.utc) - timedelta(seconds=901)
    fresh = datetime.now(timezone.utc) - timedelta(seconds=100)

    assert service.freshness_for("read_market_snapshot", stale) == "stale"
    assert service.freshness_for("read_market_snapshot", fresh) == "fresh"


def test_freshness_service_returns_not_applicable_for_profile():
    service = FinnV2FreshnessService()

    assert service.freshness_for("read_profile", None) == "not_applicable"


def test_technical_snapshot_uses_score_source_freshness_for_closed_crypto_candle():
    observed = datetime.now(timezone.utc) - timedelta(hours=12)
    adapter = TechnicalToolAdapter(None)

    async def readings(_user_id, *, symbol):
        assert symbol == "ETH"
        return [SimpleNamespace(indicator="RSI", value=31.91, score=40,
                                advies=None, uitleg=None, timestamp=observed,
                                source_observed_at=observed)]

    adapter.service.get_day_indicators = readings
    result = asyncio.run(adapter.execute(user_id=1, asset="ETH"))
    assert result["freshness_status"] == "fresh"
    assert result["data"].items[0].score == 40
    assert result["data"].items[0].source_status == "fresh"
