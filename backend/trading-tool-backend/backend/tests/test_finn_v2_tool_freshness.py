import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
from backend.services.finn_v2_tool_adapters.technical_tool_adapter import TechnicalToolAdapter
from backend.services.finn_v2_tool_adapters.macro_tool_adapter import MacroToolAdapter
from backend.utils.scoring_utils import score_source_is_fresh


def test_freshness_service_marks_market_data_stale_after_threshold():
    service = FinnV2FreshnessService()
    stale = datetime.now(timezone.utc) - timedelta(seconds=901)
    fresh = datetime.now(timezone.utc) - timedelta(seconds=100)

    assert service.freshness_for("read_market_snapshot", stale) == "stale"
    assert service.freshness_for("read_market_snapshot", fresh) == "fresh"


def test_freshness_service_returns_not_applicable_for_profile():
    service = FinnV2FreshnessService()

    assert service.freshness_for("read_profile", None) == "not_applicable"


def test_daily_score_report_uses_report_day_not_rolling_midnight_age():
    service = FinnV2FreshnessService()
    today = datetime.now(timezone.utc).date()
    for tool in ("read_asset_scores", "read_setup_market_matches"):
        assert service.freshness_for(tool, today) == "fresh"
        assert service.freshness_for(tool, today - timedelta(days=1)) == "stale"


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


def test_macro_snapshot_uses_score_2_source_window_for_dxy():
    observed = datetime.now(timezone.utc) - timedelta(hours=12)
    assert score_source_is_fresh("macro", "DXY", observed, symbol="ETH")
    adapter = MacroToolAdapter(None)

    async def readings(_user_id, *, symbol):
        assert symbol == "ETH"
        return [SimpleNamespace(name="DXY", value=102.24, score=20,
                                trend=None, timestamp=observed,
                                source_observed_at=observed)]

    adapter.repository.get_active_day_macro_data = readings
    result = asyncio.run(adapter.execute(user_id=1, asset="ETH"))
    assert result["freshness_status"] == "fresh"
    assert result["data"].items[0].source_status == "fresh"
    assert result["data"].items[0].score == 20
    # No six-hour tool TTL may reclassify this measured macro source.
    assert FinnV2FreshnessService().freshness_for("read_macro_snapshot", observed) == "unknown"


def test_macro_snapshot_keeps_individual_freshness_when_sources_differ():
    current = datetime.now(timezone.utc)
    adapter = MacroToolAdapter(None)

    async def readings(_user_id, *, symbol):
        return [
            SimpleNamespace(name="DXY", value=102.24, score=20, trend=None,
                            timestamp=current, source_observed_at=current - timedelta(days=1)),
            SimpleNamespace(name="SP500", value=5500, score=80, trend=None,
                            timestamp=current, source_observed_at=current - timedelta(days=5)),
            SimpleNamespace(name="Inflation Rate", value=None, score=None, trend=None,
                            timestamp=current, source_observed_at=None),
        ]

    adapter.repository.get_active_day_macro_data = readings
    result = asyncio.run(adapter.execute(user_id=1, asset="ETH"))
    # A mixed macro snapshot has no single truthful source age.
    assert result["freshness_status"] == "unknown"
    assert [item.source_status for item in result["data"].items] == ["fresh", "stale", "unknown"]
    assert [item.score for item in result["data"].items] == [20, None, None]


def test_macro_snapshot_without_source_moment_is_unknown():
    adapter = MacroToolAdapter(None)

    async def readings(_user_id, *, symbol):
        return [SimpleNamespace(name="DXY", value=102.24, score=20,
                                trend=None, timestamp=datetime.now(timezone.utc),
                                source_observed_at=None)]

    adapter.repository.get_active_day_macro_data = readings
    result = asyncio.run(adapter.execute(user_id=1, asset="ETH"))
    assert result["freshness_status"] == "unknown"
    assert result["data"].items[0].source_status == "unknown"
    assert result["data"].items[0].score is None


def test_macro_snapshot_preserves_monthly_release_window():
    observed = datetime.now(timezone.utc) - timedelta(days=30)
    assert score_source_is_fresh("macro", "Inflation Rate", observed, symbol="ETH")
    adapter = MacroToolAdapter(None)

    async def readings(_user_id, *, symbol):
        return [SimpleNamespace(name="Inflation Rate", value=2.4, score=50,
                                trend=None, timestamp=observed,
                                source_observed_at=observed)]

    adapter.repository.get_active_day_macro_data = readings
    result = asyncio.run(adapter.execute(user_id=1, asset="ETH"))
    assert result["freshness_status"] == "fresh"
    assert result["data"].items[0].source_status == "fresh"
    assert result["data"].items[0].score == 50
