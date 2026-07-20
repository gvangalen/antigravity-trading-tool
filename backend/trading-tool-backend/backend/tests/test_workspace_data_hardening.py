import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.intelligence_service import IntelligenceService
from backend.services.workspace_data_service import (
    WorkspaceDataService,
    _aggregate_by_name,
    _market_row,
    _score_summary,
)


def test_missing_indicator_data_never_becomes_an_artificial_score():
    summary = _score_summary(
        [{"name": "volume", "value": None, "score": 10}],
        "day",
    )

    assert summary == {
        "score": None,
        "period": "day",
        "basis": "indicator_average",
        "status": "insufficient_data",
        "reason": "no_scored_indicators",
        "sample_size": 0,
    }


def test_period_rows_are_aggregated_and_expose_their_sample_size():
    rows = [
        SimpleNamespace(
            name="volume",
            value=Decimal("10"),
            score=Decimal("20"),
            trend="stable",
            interpretation="older",
            action="wait",
            timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            name="volume",
            value=Decimal("30"),
            score=Decimal("60"),
            trend="improving",
            interpretation="latest",
            action="monitor",
            timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
        ),
    ]

    result = _aggregate_by_name(rows, "name", _market_row)

    assert result == [
        {
            "name": "volume",
            "value": 20.0,
            "score": 40.0,
            "trend": "improving",
            "interpretation": "latest",
            "action": "monitor",
            "timestamp": "2026-07-19T00:00:00+00:00",
            "sample_size": 2,
            "period_aggregate": True,
        }
    ]


def test_intelligence_read_returns_insufficient_data_without_running_engine():
    repository = SimpleNamespace(get_latest_daily_scores=AsyncMock(return_value=None))
    service = IntelligenceService(repository)
    service.invalidate_cached_result(7, "BTC")

    result = asyncio.run(service.get_market_intelligence(7, "BTC"))

    assert result["available"] is False
    assert result["data_status"] == "insufficient_data"
    assert result["reason"] == "daily_scores_missing"
    assert result["symbol"] == "BTC"


def test_watchlist_uses_one_batch_for_quotes_and_one_for_scores():
    service = object.__new__(WorkspaceDataService)
    service.market = SimpleNamespace(
        get_latest_snapshots=AsyncMock(
            return_value=[
                SimpleNamespace(
                    symbol="BTC",
                    price=Decimal("64000"),
                    change_24h=Decimal("1.5"),
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        )
    )
    service.scores = SimpleNamespace(
        fetch_daily_scores_batch=AsyncMock(
            return_value={
                "BTC": {
                    "market_score": Decimal("40"),
                    "macro_score": Decimal("50"),
                    "technical_score": Decimal("60"),
                    "report_date": date(2026, 7, 19),
                }
            }
        )
    )
    service.users = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                ai_preferences={
                    "intelligence_weights": {"market": 0.2, "macro": 0.3, "technical": 0.5}
                }
            )
        )
    )

    result = asyncio.run(service.get_watchlist(7, ["btc", "BTC", "eth"]))

    service.market.get_latest_snapshots.assert_awaited_once_with(["BTC", "ETH"])
    service.scores.fetch_daily_scores_batch.assert_awaited_once_with(7, ["BTC", "ETH"])
    service.users.get_by_id.assert_awaited_once_with(7)
    assert result["ai_calls"] == 0
    assert result["rows"][0]["score"] == 53.0
    assert result["rows"][1]["score"] is None
    assert result["rows"][1]["score_status"] == "insufficient_data"
    assert result["rows"][0]["score_freshness"]["source"] == "daily_scores"


def test_frontend_workspace_reads_are_centralized_and_ai_is_explicit():
    root = Path(__file__).resolve().parents[4]
    workspace = (
        root
        / "frontend"
        / "trading-tool-frontend"
        / "components"
        / "workspaces"
        / "asset"
        / "AssetWorkspaceV3.jsx"
    ).read_text()
    hook = (
        root
        / "frontend"
        / "trading-tool-frontend"
        / "hooks"
        / "useAssetWorkspaceData.js"
    ).read_text()

    assert "useAssetWorkspaceData" in workspace
    assert "fetchLatestPrice" not in workspace
    assert "getDailyScores" not in workspace
    assert "useOverviewSnapshot" not in workspace
    assert "btcLive?.as_of" in workspace
    assert "fetchAssetWorkspace" in hook
    assert "fetchWorkspaceWatchlist" in hook
    assert "assistantChat" not in hook


def test_each_explicit_review_flow_uses_one_ai_request():
    root = Path(__file__).resolve().parents[4] / "frontend" / "trading-tool-frontend"
    review_surfaces = [
        root / "components" / "setup" / "SetupList.jsx",
        root / "components" / "strategy" / "StrategyCard.jsx",
        root / "components" / "bot" / "OrderPreviewModal.jsx",
    ]

    for surface in review_surfaces:
        source = surface.read_text()
        assert source.count("assistantChat(") == 1, surface
        assert "Promise.all([\n          assistantChat(" not in source
