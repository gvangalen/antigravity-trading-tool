import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.celery_task import market_task
from backend.celery_task.store_daily_scores_task import store_daily_scores_task


@pytest.fixture(autouse=True)
def _existing_refresh_cases_use_open_session(monkeypatch):
    async def due(_session, symbols, *, now):
        return symbols

    monkeypatch.setattr(market_task, "_due_scheduled_symbols", due)


@pytest.mark.parametrize("instant,expected", [
    (datetime(2026, 11, 16, 14, 29, tzinfo=timezone.utc), False),
    (datetime(2026, 11, 16, 14, 30, tzinfo=timezone.utc), True),
    (datetime(2026, 11, 16, 21, 5, tzinfo=timezone.utc), False),
    (datetime(2026, 7, 16, 13, 30, tzinfo=timezone.utc), True),
    (datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc), False),
])
def test_us_stock_scheduled_quote_respects_new_york_standard_and_summer_hours(instant, expected):
    asset = {"asset_class": "stock", "market_region": "us", "timezone": "America/New_York"}
    assert market_task._scheduled_quote_due(asset, now=instant) is expected
    assert market_task._scheduled_quote_due({**asset, "asset_class": "etf"}, now=instant) is expected
    assert market_task._scheduled_quote_due({"asset_class": "crypto"}, now=instant) is True


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _Session:
    def __init__(self, watchlist_symbols, configured_rows=()):
        self._results = iter((watchlist_symbols, configured_rows))
        self.committed = False

    async def execute(self, _statement):
        return _Result(next(self._results))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


class _SessionContext:
    def __init__(self, watchlist_symbols, configured_rows=()):
        self.session = _Session(watchlist_symbols, configured_rows)

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def test_configured_snapshot_refresh_uses_distinct_owner_selected_symbols(monkeypatch):
    captured = {}

    class _Ingestion:
        def __init__(self, session):
            captured["session"] = session

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error, release_catalog_read_transaction):
            captured.update({"symbols": symbols, "commit": commit, "continue_on_error": continue_on_error})
            return {"requested": symbols, "ingested": [{"symbol": "AAPL"}], "failed": [], "success_count": 1, "failure_count": 0}

    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext(["AAPL", "MSFT", "AAPL", "  "]))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", _Ingestion)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert captured["symbols"] == ["AAPL", "MSFT"]
    assert captured["commit"] is True
    assert captured["continue_on_error"] is True
    assert result["success_count"] == 1


def test_configured_snapshot_refresh_does_not_call_provider_without_watchlist_assets(monkeypatch):
    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext([]))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", lambda _session: (_ for _ in ()).throw(AssertionError("provider must not be created")))

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert result["requested"] == []
    assert result["success_count"] == 0


def test_closed_us_session_defers_quote_and_indicator_provider_calls(monkeypatch):
    config = SimpleNamespace(user_id=7, symbol="AAPL", category="technical", enabled=True)

    async def due(_session, _symbols, *, now):
        return []

    monkeypatch.setattr(market_task, "_due_scheduled_symbols", due)
    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext(["AAPL"], [config]))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", lambda _session: (_ for _ in ()).throw(AssertionError("provider must not be called")))
    monkeypatch.setattr(market_task, "TechnicalDataService", lambda _session: (_ for _ in ()).throw(AssertionError("indicator provider must not be called")))

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert result["requested"] == []
    assert result["deferred_closed_session_symbols"] == 1


def test_closed_stock_scopes_do_not_displace_due_crypto_scope(monkeypatch):
    rows = [SimpleNamespace(user_id=user_id, symbol="AAPL", category="technical",
                            updated_at=datetime(2026, 11, 16, tzinfo=timezone.utc))
            for user_id in range(1, 5)]
    rows.append(SimpleNamespace(user_id=9, symbol="BTC", category="technical",
                                updated_at=datetime(2026, 11, 16, tzinfo=timezone.utc)))
    captured = {}

    async def due(_session, _symbols, *, now):
        return ["BTC"]

    class Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, **_kwargs):
            captured["symbols"] = symbols
            return {"requested": symbols, "ingested": [], "failed": [],
                    "success_count": 0, "failure_count": 0}

    class CategoryService:
        def __init__(self, _session):
            pass

        async def sync_effective_indicators(self, user_id, symbol):
            captured["scope"] = (user_id, symbol)
            return {"failed": [], "synced": []}

    monkeypatch.setattr(market_task, "_due_scheduled_symbols", due)
    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext([], rows))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", Ingestion)
    monkeypatch.setattr(market_task, "MarketDataService", CategoryService)
    monkeypatch.setattr(market_task, "MacroDataService", CategoryService)
    monkeypatch.setattr(market_task, "TechnicalDataService", CategoryService)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert captured == {"symbols": ["BTC"], "scope": (9, "BTC")}
    assert result["deferred_closed_session_symbols"] == 1
    assert result["deferred_scope_count"] == 0


@pytest.mark.parametrize("market_id", [None, 73])
def test_exact_market_refresh_uses_persisted_pair_identity(monkeypatch, market_id):
    from backend.services import exact_market_indicator_service, indicator_history_bootstrap, pair_indicator_config_service

    calls = []
    row = {"id": 73, "asset_symbol": "BTC", "quote_currency": "EUR",
           "venue": "BINANCE", "provider": "binance",
           "provider_symbol": "BTCEUR", "tradingview_symbol": "BINANCE:BTCEUR",
           "source_verified_at": None}

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [row]

    class Session:
        async def execute(self, statement, params=None):
            # The scheduled job supplies None. PostgreSQL cannot infer the
            # type of an uncast bind in `:market_id IS NULL`.
            assert params == {"market_id": market_id}
            assert str(statement).count("CAST(:market_id AS INTEGER)") == 2
            return Result()

        async def rollback(self):
            pass

    class Context:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return False

    class Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_exact_market_snapshot(self, market):
            calls.append((market.id, market.provider_symbol, market.quote_currency))
            return {"observed_at": "2026-10-27T07:00:00Z"}

    class History:
        def __init__(self, _session):
            pass

        async def bootstrap_exact_market(self, market, *, required_days):
            assert required_days == 220
            calls.append((market.id, "history"))
            return {"status": "ready", "observed_days": 16}

    class Indicators:
        def __init__(self, _session):
            pass

        async def materialize(self, market):
            calls.append((market.id, "indicators"))
            return {"owners": [7], "written": 2}

    def build_score(user_id, market_id):
        calls.append((user_id, market_id, "score"))
        return {"market_id": market_id}

    monkeypatch.setattr(market_task, "async_session_factory", Context)
    monkeypatch.setattr(market_task, "MarketDataIngestionService", Ingestion)
    monkeypatch.setattr(indicator_history_bootstrap, "IndicatorHistoryBootstrap", History)
    monkeypatch.setattr(exact_market_indicator_service, "ExactMarketIndicatorService", Indicators)
    monkeypatch.setattr(pair_indicator_config_service, "PairIndicatorConfigService",
                        lambda _session: type("Preferences", (), {"rows": AsyncMock(return_value=[])})())
    monkeypatch.setattr("backend.celery_task.store_daily_scores_task.build_daily_scores_for_market", build_score)

    result = asyncio.run(market_task._sync_exact_market_snapshots(market_id=market_id))

    assert calls == [(73, "BTCEUR", "EUR"), (73, "history"),
                     (73, "indicators"), (7, 73, "score")]
    assert result["scopes"][0]["market_id"] == 73


def test_configured_snapshot_refresh_rehydrates_owner_scoped_indicator_without_watchlist(monkeypatch):
    captured = {"calls": []}
    config = SimpleNamespace(user_id=7, symbol="AAPL", category="technical", enabled=True)

    class _Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error, release_catalog_read_transaction):
            captured["symbols"] = symbols
            return {"requested": symbols, "ingested": [{"symbol": "AAPL"}], "failed": [], "success_count": 1, "failure_count": 0}

    class _Technical:
        def __init__(self, _session):
            pass

        async def sync_effective_indicators(self, user_id, symbol):
            captured["calls"].append((user_id, symbol))
            return {"synced": [{"indicator": "rsi"}], "failed": []}

    class _UnexpectedCategory:
        def __init__(self, _session):
            pass

    session_context = _SessionContext([], [config])
    monkeypatch.setattr(market_task, "async_session_factory", lambda: session_context)
    monkeypatch.setattr(market_task, "MarketDataIngestionService", _Ingestion)
    monkeypatch.setattr(market_task, "TechnicalDataService", _Technical)
    monkeypatch.setattr(market_task, "MarketDataService", _UnexpectedCategory)
    monkeypatch.setattr(market_task, "MacroDataService", _UnexpectedCategory)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert captured["symbols"] == ["AAPL"]
    assert captured["calls"] == [(7, "AAPL")]
    assert result["rehydrated_scopes"] == [{"user_id": 7, "symbol": "AAPL", "category": "technical"}]
    assert result["rehydration_failures"] == []
    assert session_context.session.committed is True


def test_configured_snapshot_refresh_marks_partial_materialization_as_failed(monkeypatch):
    config = SimpleNamespace(user_id=8, symbol="BTC", category="technical", enabled=True)

    class _Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error, release_catalog_read_transaction):
            return {"requested": symbols, "ingested": [{"symbol": "BTC"}], "failed": [], "success_count": 1, "failure_count": 0}

    class _Technical:
        def __init__(self, _session):
            pass

        async def sync_effective_indicators(self, _user_id, _symbol):
            return {"synced": [], "failed": [{"indicator": "rsi"}]}

    class _UnexpectedCategory:
        def __init__(self, _session):
            pass

    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext([], [config]))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", _Ingestion)
    monkeypatch.setattr(market_task, "TechnicalDataService", _Technical)
    monkeypatch.setattr(market_task, "MarketDataService", _UnexpectedCategory)
    monkeypatch.setattr(market_task, "MacroDataService", _UnexpectedCategory)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert result["rehydrated_scopes"] == []
    assert result["rehydration_failures"] == [{"user_id": 8, "symbol": "BTC", "category": "technical"}]


def test_partial_indicator_failure_commits_successful_indicators(monkeypatch):
    config = SimpleNamespace(user_id=8, symbol="BTC", category="technical", enabled=True)
    context = _SessionContext([], [config])

    class _Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, **_kwargs):
            return {"requested": symbols, "ingested": [], "failed": [], "success_count": 0, "failure_count": 0}

    class _Technical:
        def __init__(self, _session):
            pass

        async def sync_effective_indicators(self, _user_id, _symbol):
            return {"synced": [{"indicator": "price"}], "failed": [{"indicator": "rsi"}]}

    monkeypatch.setattr(market_task, "async_session_factory", lambda: context)
    monkeypatch.setattr(market_task, "MarketDataIngestionService", _Ingestion)
    monkeypatch.setattr(market_task, "TechnicalDataService", _Technical)
    monkeypatch.setattr(market_task, "MarketDataService", lambda _session: None)
    monkeypatch.setattr(market_task, "MacroDataService", lambda _session: None)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert context.session.committed is True
    assert result["rehydration_failures"] == [{"user_id": 8, "symbol": "BTC", "category": "technical"}]


def test_configured_snapshot_refresh_bounds_provider_work_per_run(monkeypatch):
    configs = [
        SimpleNamespace(user_id=user_id, symbol=f"S{user_id}", category="technical", enabled=True, updated_at=None, created_at=None)
        for user_id in range(1, 7)
    ]
    calls = []

    class _Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error, release_catalog_read_transaction):
            return {"requested": symbols, "ingested": [], "failed": [], "success_count": 0, "failure_count": 0}

    class _Technical:
        def __init__(self, _session):
            pass

        async def sync_effective_indicators(self, user_id, symbol):
            calls.append((user_id, symbol))
            return {"synced": [{"indicator": "rsi"}], "failed": []}

    class _UnexpectedCategory:
        def __init__(self, _session):
            pass

    monkeypatch.setattr(market_task, "async_session_factory", lambda: _SessionContext([], configs))
    monkeypatch.setattr(market_task, "MarketDataIngestionService", _Ingestion)
    monkeypatch.setattr(market_task, "TechnicalDataService", _Technical)
    monkeypatch.setattr(market_task, "MarketDataService", _UnexpectedCategory)
    monkeypatch.setattr(market_task, "MacroDataService", _UnexpectedCategory)

    result = asyncio.run(market_task._sync_configured_market_snapshots())

    assert len(calls) == market_task.MAX_CONFIGURED_INDICATOR_SCOPES_PER_RUN
    assert result["deferred_scope_count"] == 2


def test_configured_scope_windows_eventually_cover_every_scope():
    scopes = [(user_id, f"S{user_id}", "technical") for user_id in range(1, 11)]

    first = market_task._configured_scope_window(scopes, window_index=0)
    second = market_task._configured_scope_window(scopes, window_index=1)
    third = market_task._configured_scope_window(scopes, window_index=2)

    assert len(first) == market_task.MAX_CONFIGURED_INDICATOR_SCOPES_PER_RUN
    assert len(second) == market_task.MAX_CONFIGURED_INDICATOR_SCOPES_PER_RUN
    assert set(first + second + third) == set(scopes)


def test_successful_indicator_refresh_queues_one_score_rebuild_per_owner(monkeypatch):
    async def refreshed():
        return {
            "success_count": 2, "failure_count": 0,
            "rehydrated_scopes": [
                {"user_id": 7, "symbol": "BTC", "category": "market"},
                {"user_id": 7, "symbol": "BTC", "category": "technical"},
                {"user_id": 8, "symbol": "ETH", "category": "macro"},
            ],
            "rehydration_failures": [{"user_id": 9, "symbol": "AAPL", "category": "technical"}],
        }

    queued = []
    monkeypatch.setattr(market_task, "_sync_configured_market_snapshots", refreshed)
    monkeypatch.setattr(store_daily_scores_task, "apply_async", lambda *, args: queued.append(args))

    result = market_task.sync_configured_market_snapshots()

    assert queued == [(7,), (8,)]
    assert result["score_rebuild_queued_users"] == [7, 8]
    assert result["score_rebuild_queue_failures"] == []


def test_score_queue_failure_keeps_refreshed_measurement_and_reports_retry_need(monkeypatch):
    async def refreshed():
        return {"success_count": 1, "failure_count": 0, "rehydrated_scopes": [
            {"user_id": 7, "symbol": "BTC", "category": "market"},
        ]}

    def unavailable_queue(*, args):
        raise ConnectionError("local broker unavailable")

    monkeypatch.setattr(market_task, "_sync_configured_market_snapshots", refreshed)
    monkeypatch.setattr(store_daily_scores_task, "apply_async", unavailable_queue)

    result = market_task.sync_configured_market_snapshots()

    assert result["score_rebuild_queued_users"] == []
    assert result["score_rebuild_queue_failures"] == [7]
    assert result["success_count"] == 1
