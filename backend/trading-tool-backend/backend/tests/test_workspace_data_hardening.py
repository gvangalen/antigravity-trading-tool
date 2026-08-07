import asyncio
import inspect
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.intelligence_service import IntelligenceService
from backend.services.workspace_data_service import (
    WorkspaceDataService,
    _aggregate_by_name,
    _enrich_indicator_rows,
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


def test_indicator_rows_expose_source_period_freshness_and_score_contribution():
    rows = _enrich_indicator_rows(
        [
            {"name": "rsi", "value": 54.0, "score": 50.0, "timestamp": "2026-07-21T08:00:00+00:00"},
            {"name": "ma_200", "value": 0.9, "score": 70.0, "timestamp": "2026-07-21T08:00:00+00:00"},
            {"name": "missing", "value": None, "score": 10.0, "timestamp": None},
        ],
        period="day",
        threshold=36 * 60 * 60,
        source="technical_indicators",
    )

    assert rows[0]["source"] == "technical_indicators"
    assert rows[0]["period"] == "day"
    assert rows[0]["freshness"]["status"] == "available"
    assert rows[0]["score_contribution"] == {
        "status": "available",
        "basis": "equal_indicator_average",
        "weight": 0.5,
        "weighted_points": 25.0,
    }
    assert rows[2]["data_status"] == "insufficient_data"
    assert rows[2]["score_contribution"]["weighted_points"] is None

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


def test_workspace_macro_rows_follow_active_asset_symbol():
    service = object.__new__(WorkspaceDataService)
    service.macro = SimpleNamespace(
        get_active_day_macro_data=AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="fear_greed_index",
                    value=Decimal("42"),
                    score=Decimal("55"),
                    trend="neutral",
                    interpretation="ok",
                    action="hold",
                    timestamp=datetime(2026, 8, 7, tzinfo=timezone.utc),
                )
            ]
        ),
        _get_data_by_days=AsyncMock(return_value=[]),
    )

    rows = asyncio.run(service._macro_rows(7, "BTC", "day"))

    service.macro.get_active_day_macro_data.assert_awaited_once_with(7, "BTC")
    assert rows == [
        {
            "name": "fear_greed_index",
            "value": 42.0,
            "score": 55.0,
            "trend": "neutral",
            "interpretation": "ok",
            "action": "hold",
            "timestamp": "2026-08-07T00:00:00+00:00",
            "sample_size": 1,
            "period_aggregate": False,
        }
    ]


def test_watchlist_materializes_quotes_before_asset_catalog_fallback_rolls_back():
    class ExpiringQuote:
        def __init__(self, symbol: str, price: Decimal):
            self._symbol = symbol
            self._price = price
            self._change_24h = Decimal("1.5")
            self._timestamp = datetime.now(timezone.utc)
            self.expired = False

        @property
        def symbol(self):
            if self.expired:
                raise RuntimeError("quote expired after rollback")
            return self._symbol

        @property
        def price(self):
            if self.expired:
                raise RuntimeError("quote price expired after rollback")
            return self._price

        @property
        def change_24h(self):
            if self.expired:
                raise RuntimeError("quote change expired after rollback")
            return self._change_24h

        @property
        def timestamp(self):
            if self.expired:
                raise RuntimeError("quote timestamp expired after rollback")
            return self._timestamp

    quote = ExpiringQuote("BTC", Decimal("64000"))
    service = object.__new__(WorkspaceDataService)
    service.session = object()
    service.market = SimpleNamespace(get_latest_snapshots=AsyncMock(return_value=[quote]))
    service.scores = SimpleNamespace(
        fetch_daily_scores_batch=AsyncMock(
            return_value={
                "BTC": {
                    "market_score": Decimal("40"),
                    "macro_score": Decimal("50"),
                    "technical_score": Decimal("60"),
                    "report_date": date(2026, 8, 6),
                }
            }
        )
    )

    class FakeAssetCatalogService:
        def __init__(self, _session):
            pass

        async def get_assets(self, _symbols):
            quote.expired = True
            return {}

    with patch("backend.services.workspace_data_service.AssetCatalogService", FakeAssetCatalogService):
        result = asyncio.run(service._build_watchlist_payload(7, ["BTC"]))

    assert result["rows"][0]["symbol"] == "BTC"
    assert result["rows"][0]["price"] == 64000.0


def test_asset_catalog_read_failure_rolls_back_before_default_fallback():
    service = AssetCatalogService(AsyncMock())
    service.repository = SimpleNamespace(get_assets=AsyncMock(side_effect=RuntimeError("db read failed")))

    result = asyncio.run(service.get_assets(["btc", "ETH"]))

    service.session.rollback.assert_awaited_once()
    assert result["BTC"]["display_name"] == "Bitcoin"
    assert result["ETH"]["display_name"] == "Ethereum"


def test_workspace_reads_do_not_parallelize_a_shared_async_session():
    asset_source = inspect.getsource(WorkspaceDataService.get_asset_workspace)
    watchlist_source = inspect.getsource(WorkspaceDataService.get_watchlist)

    assert "asyncio.gather" not in asset_source
    assert "asyncio.gather" not in watchlist_source


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
    assert "watchlistSymbols" in hook
    assert "fetchWorkspaceWatchlist" not in hook
    assert "assistantChat" not in hook
    assert "requestIndicatorContext" in workspace
    assert "onClick={requestFinnContext}" in workspace


def test_each_explicit_review_flow_uses_one_ai_request():
    root = Path(__file__).resolve().parents[4] / "frontend" / "trading-tool-frontend"
    review_surfaces = [
        root / "components" / "setup" / "SetupList.jsx",
        root / "components" / "strategy" / "StrategyCard.jsx",
    ]

    for surface in review_surfaces:
        source = surface.read_text()
        assert source.count("assistantChat(") == 1, surface
        assert "Promise.all([\n          assistantChat(" not in source

    order_preview = (root / "components" / "bot" / "OrderPreviewModal.jsx").read_text()
    assert "assistantChat(" not in order_preview
