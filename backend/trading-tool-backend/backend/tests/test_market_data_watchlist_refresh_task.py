import asyncio
from types import SimpleNamespace

from backend.celery_task import market_task


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

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error):
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


def test_configured_snapshot_refresh_rehydrates_owner_scoped_indicator_without_watchlist(monkeypatch):
    captured = {"calls": []}
    config = SimpleNamespace(user_id=7, symbol="AAPL", category="technical", enabled=True)

    class _Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_latest_snapshots(self, symbols, *, commit, continue_on_error):
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
