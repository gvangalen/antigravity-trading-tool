import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import exact_market_workspace_service as module


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def test_exact_market_workspace_never_borrows_base_quote_or_score(monkeypatch):
    observed = datetime.now(timezone.utc).replace(tzinfo=None)
    market = SimpleNamespace(id=43, asset_symbol="ETH", quote_currency="EUR",
                             tradingview_symbol="BINANCE:ETHEUR")
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result([market]), _Result([]), _Result([]), _Result([]),
    ]))
    quote_reader = SimpleNamespace(get_latest_exact_market_snapshot=AsyncMock(
        return_value=SimpleNamespace(price=2400, change_24h=1, volume=100,
                                     quote_currency="USDT", source_observed_at=observed)))
    matcher = SimpleNamespace(for_asset=AsyncMock(return_value={
        "benchmark_score": None, "benchmark_weights": {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3},
        "reported_scores": {"market_score": None, "macro_score": None, "technical_score": None},
        "component_source_status": {"market_score": "missing_score", "macro_score": "missing_score",
                                    "technical_score": "missing_score"},
        "source_status": "missing_scores", "matches": [], "component_source_observed_at": {},
    }))
    workspace = SimpleNamespace(
        _macro_rows=AsyncMock(return_value=[]),
        get_watchlist=AsyncMock(return_value={"rows": []}),
        _category_payload=lambda rows, *_args, **_kwargs: {"rows": rows, "score": {}},
    )
    monkeypatch.setattr(module, "MarketDataRepository", lambda _session: quote_reader)
    monkeypatch.setattr(module, "SetupMarketMatchService", lambda _session: matcher)
    monkeypatch.setattr(module, "WorkspaceDataService", lambda _session: workspace)

    result = asyncio.run(module.ExactMarketWorkspaceService(session).get(7, "eth", "eur"))

    assert result["pair"] == "ETH/EUR"
    assert result["asset"]["tradingview_symbol"] == "BINANCE:ETHEUR"
    assert result["quote"]["price"] is None
    assert result["combined"]["score"] is None
    matcher.for_asset.assert_awaited_once_with(7, "ETH", market_id=43)
    quote_reader.get_latest_exact_market_snapshot.assert_awaited_once_with(43)


def test_unknown_exact_market_returns_no_legacy_workspace():
    session = SimpleNamespace(execute=AsyncMock(return_value=_Result([])))
    assert asyncio.run(module.ExactMarketWorkspaceService(session).get(7, "ETH", "EUR")) is None


def test_selected_pair_watchlist_row_uses_the_workspace_quote_and_score(monkeypatch):
    observed = datetime.now(timezone.utc).replace(tzinfo=None)
    market = SimpleNamespace(id=43, asset_symbol="ETH", quote_currency="EUR",
                             tradingview_symbol="BINANCE:ETHEUR")
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result([market]), _Result([]), _Result([]), _Result([]),
    ]))
    quote = SimpleNamespace(price=2400, change_24h=2, volume=100,
                            quote_currency="EUR", price_provider="binance",
                            source_observed_at=observed)
    matcher = SimpleNamespace(for_asset=AsyncMock(return_value={
        "benchmark_score": 65, "benchmark_weights": {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3},
        "reported_scores": {"market_score": 50, "macro_score": 80, "technical_score": 65},
        "component_source_status": {}, "source_status": "available", "matches": [],
        "component_source_observed_at": {}, "as_of": observed,
    }))
    watchlist = {"rows": [
        {"symbol": "ETH", "price": 2600, "quote_currency": "USDT", "score": 30},
        {"symbol": "BTC", "price": 81000, "quote_currency": "USDT", "score": 40},
    ]}
    workspace = SimpleNamespace(
        _macro_rows=AsyncMock(return_value=[]),
        get_watchlist=AsyncMock(return_value=watchlist),
        _category_payload=lambda rows, *_args, **_kwargs: {"rows": rows, "score": {}},
    )
    monkeypatch.setattr(module, "MarketDataRepository", lambda _session: SimpleNamespace(
        get_latest_exact_market_snapshot=AsyncMock(return_value=quote)))
    monkeypatch.setattr(module, "SetupMarketMatchService", lambda _session: matcher)
    monkeypatch.setattr(module, "WorkspaceDataService", lambda _session: workspace)

    result = asyncio.run(module.ExactMarketWorkspaceService(session).get(7, "ETH", "EUR"))

    assert result["quote"]["price"] == result["watchlist"]["rows"][0]["price"] == 2400
    assert result["combined"]["score"] == result["watchlist"]["rows"][0]["score"] == 65
    assert result["watchlist"]["rows"][0]["market_id"] == 43
    assert result["watchlist"]["rows"][0]["quote_currency"] == "EUR"
    assert result["watchlist"]["rows"][0]["tradingview_symbol"] == "BINANCE:ETHEUR"
    assert result["watchlist"]["rows"][1]["price"] == 81000
    assert result["watchlist"]["rows"][1]["quote_currency"] == "USDT"


def test_non_daily_period_does_not_show_daily_combined_score(monkeypatch):
    observed = datetime.now(timezone.utc).replace(tzinfo=None)
    market = SimpleNamespace(id=43, asset_symbol="ETH", quote_currency="EUR",
                             tradingview_symbol="BINANCE:ETHEUR")
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result([market]), _Result([]), _Result([]), _Result([]),
    ]))
    matcher = SimpleNamespace(for_asset=AsyncMock(return_value={
        "benchmark_score": 65, "benchmark_weights": {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3},
        "reported_scores": {"market_score": 50, "macro_score": 80, "technical_score": 65},
        "component_source_status": {}, "source_status": "available", "matches": [],
        "component_source_observed_at": {},
    }))
    workspace = SimpleNamespace(
        _macro_rows=AsyncMock(return_value=[]),
        get_watchlist=AsyncMock(return_value={"rows": []}),
        _category_payload=lambda rows, *_args, **_kwargs: {"rows": rows, "score": {}},
    )
    monkeypatch.setattr(module, "MarketDataRepository", lambda _session: SimpleNamespace(
        get_latest_exact_market_snapshot=AsyncMock(return_value=None)))
    monkeypatch.setattr(module, "SetupMarketMatchService", lambda _session: matcher)
    monkeypatch.setattr(module, "WorkspaceDataService", lambda _session: workspace)

    result = asyncio.run(module.ExactMarketWorkspaceService(session).get(
        7, "ETH", "EUR", periods={"market": "week", "macro": "day", "technical": "day"}))
    assert result["daily"]["benchmark_score"] == 65
    assert result["combined"]["score"] is None
    assert result["combined"]["source_status"] == "unsupported_period"


def test_exact_market_rows_show_only_verified_score_evidence(monkeypatch):
    observed = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = observed.isoformat()
    market = SimpleNamespace(id=43, asset_symbol="ETH", quote_currency="EUR",
                             tradingview_symbol="BINANCE:ETHEUR")
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        _Result([market]),
        _Result([SimpleNamespace(name="price", value=2400, score=None, trend=None,
                                 interpretation=None, action=None, timestamp=observed,
                                 source_observed_at=observed)]),
        _Result([]),
        _Result([SimpleNamespace(user_id=7, market_id=43, category="market",
                                 indicator="price", enabled=True),
                 SimpleNamespace(user_id=7, market_id=43, category="technical",
                                 indicator="ma_200", enabled=True)]),
    ]))
    evidence = {"price": {"value": 2400, "score": 30,
                          "source_observed_at": timestamp,
                          "rule_origin": "system_template", "weight": 1}}
    matcher = SimpleNamespace(
        last_source_row={"indicator_evidence": {"market": evidence}},
        for_asset=AsyncMock(return_value={
            "benchmark_score": None,
            "benchmark_weights": {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3},
            "reported_scores": {"market_score": 30, "macro_score": None,
                                "technical_score": None},
            "component_source_status": {"market_score": "fresh",
                                        "macro_score": "missing_score",
                                        "technical_score": "missing_score"},
            "source_status": "missing_scores", "matches": [],
            "component_source_observed_at": {},
        }),
    )
    workspace = SimpleNamespace(
        _macro_rows=AsyncMock(return_value=[]),
        get_watchlist=AsyncMock(return_value={"rows": []}),
        _category_payload=lambda rows, *_args, **_kwargs: {"rows": rows, "score": {}},
    )
    monkeypatch.setattr(module, "MarketDataRepository", lambda _session: SimpleNamespace(
        get_latest_exact_market_snapshot=AsyncMock(return_value=None)))
    monkeypatch.setattr(module, "SetupMarketMatchService", lambda _session: matcher)
    monkeypatch.setattr(module, "WorkspaceDataService", lambda _session: workspace)

    result = asyncio.run(module.ExactMarketWorkspaceService(session).get(7, "ETH", "EUR"))

    assert result["categories"]["market"]["rows"][0]["score"] == 30
    assert result["categories"]["technical"]["rows"] == [{
        "name": "ma_200", "value": None, "score": None, "trend": None,
        "interpretation": None, "action": None, "timestamp": None,
        "sample_size": 0, "period_aggregate": False, "configured": True,
        "data_status": "pending_refresh",
    }]
    assert result["daily"]["indicator_evidence"]["market"] == evidence
    assert "macro" not in result["daily"]["indicator_evidence"]

    matcher.component_source_status = "stale_source"
    assert module.ExactMarketWorkspaceService._verified_evidence(
        {"component_source_status": {"market_score": "stale_source"}},
        matcher.last_source_row,
    ) == {}
