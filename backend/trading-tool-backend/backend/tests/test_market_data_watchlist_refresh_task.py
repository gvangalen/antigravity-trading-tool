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
    def __init__(self, values):
        self.values = values

    async def execute(self, _statement):
        return _Result(self.values)


class _SessionContext:
    def __init__(self, values):
        self.session = _Session(values)

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
