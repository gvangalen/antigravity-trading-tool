import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.indicator_history_bootstrap import IndicatorHistoryBootstrap
from backend.services.providers.twelve_data_macro_provider import (
    DXY_BASE_FACTOR, DXY_COMPONENT_WEIGHTS, TwelveDataMacroProvider,
)
from backend.utils import macro_interpreter
from backend.services.workspace_data_service import _enrich_indicator_rows
from unittest.mock import AsyncMock, patch

from backend.services.macro_data_service import MacroDataService
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from sqlalchemy.dialects import postgresql


def _day(offset):
    return date.today() - timedelta(days=offset)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self.rows)


class _MarketSession:
    def __init__(self):
        self.rows = []
        self.commits = 0

    async def execute(self, _query):
        return _Result([(row.source_observed_at, row.price, row.volume) for row in self.rows])

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        self.commits += 1


class _MacroSession:
    def __init__(self, owner_id=7):
        self.rows = []
        self.owner_id = owner_id
        self.commits = 0

    async def execute(self, _query):
        return _Result([row.source_observed_at for row in self.rows if row.user_id == self.owner_id])

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        self.commits += 1


def test_market_backfill_uses_closed_dated_candles_and_is_idempotent(monkeypatch):
    from backend.services import indicator_history_bootstrap as module

    class _Asset:
        async def get_asset(self, _symbol):
            return {"symbol": "BTC", "display_name": "Bitcoin", "asset_class": "crypto",
                    "provider": "binance", "primary_provider": "binance"}

    class _Provider:
        calls = 0

        async def fetch_candles(self, _asset, _timeframe, *, limit):
            self.calls += 1
            assert limit == 40
            return [SimpleNamespace(
                period_start=datetime.combine(_day(offset), datetime.min.time(), timezone.utc),
                is_final=True, close=100 + offset, volume=1000 + offset,
                open=99, high=103, low=98,
            ) for offset in range(0, 7)]

    provider = _Provider()
    monkeypatch.setattr(module, "AssetCatalogService", lambda _session: _Asset())
    monkeypatch.setattr(module, "MarketDataProviderRegistry",
                        lambda: SimpleNamespace(resolve_for_asset=lambda _asset: provider))
    session = _MarketSession()
    bootstrap = IndicatorHistoryBootstrap(session)

    first = asyncio.run(bootstrap.bootstrap_market("BTC", {"price", "volume"}))
    second = asyncio.run(bootstrap.bootstrap_market("BTC", {"price", "volume"}))

    assert first["status"] == "ready"
    assert first["inserted"] == 6
    assert second == {"inserted": 0, "status": "ready", "coverage": {"price": 6, "volume": 6}}
    assert provider.calls == 1
    assert session.commits == 1
    assert all(row.source_observed_at.date() < date.today() for row in session.rows)
    assert len({row.source_observed_at.date() for row in session.rows}) == 6


def test_macro_backfill_is_owner_scoped_and_never_creates_a_score(monkeypatch):
    from backend.services import indicator_history_bootstrap as module

    monkeypatch.setattr(module, "fetch_absolute_macro_history", lambda _name: [
        (datetime.combine(_day(offset), datetime.min.time()), 95.0 + offset)
        for offset in range(1, 7)
    ])
    session = _MacroSession(owner_id=7)
    bootstrap = IndicatorHistoryBootstrap(session)

    first = asyncio.run(bootstrap.bootstrap_macro(7, "dxy", "BTC"))
    second = asyncio.run(bootstrap.bootstrap_macro(7, "dxy", "ETH"))

    assert first == {"inserted": 6, "status": "ready", "observed_days": 6}
    assert second == {"inserted": 0, "status": "ready", "observed_days": 6}
    assert all(row.user_id == 7 and row.score is None for row in session.rows)
    assert session.commits == 1


def test_completed_history_queues_score_refresh_for_affected_owner(monkeypatch):
    from backend.celery_task import indicator_history_task as task_module
    from backend.celery_task import celery_app as celery_module

    rows = [SimpleNamespace(user_id=7, symbol="ETH", category="market", indicator="price"),
            SimpleNamespace(user_id=7, symbol="ETH", category="macro", indicator="dxy"),
            SimpleNamespace(user_id=8, symbol="ETH", category="market", indicator="price")]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def execute(self, _query):
            return _Result(rows)

    class _Bootstrap:
        def __init__(self, _session):
            pass

        async def bootstrap_market(self, _symbol, _names):
            return {"status": "ready", "inserted": 5}

        async def bootstrap_macro(self, _owner, _name, _symbol):
            return {"status": "ready", "inserted": 5}

    queued = []
    monkeypatch.setattr(task_module, "async_session_factory", _Session)
    monkeypatch.setattr(task_module, "IndicatorHistoryBootstrap", _Bootstrap)
    monkeypatch.setattr(celery_module.celery_app, "send_task",
                        lambda name, **kwargs: queued.append((name, kwargs)))

    result = asyncio.run(task_module._bootstrap_indicator_histories())

    assert len(result["scopes"]) == 2
    assert queued == [
        ("backend.celery_task.store_daily_scores_task.store_daily_scores_task",
         {"kwargs": {"user_id": 7}}),
        ("backend.celery_task.store_daily_scores_task.store_daily_scores_task",
         {"kwargs": {"user_id": 8}}),
    ]


def test_new_owner_reuses_existing_asset_history_without_waiting_for_new_days(monkeypatch):
    from backend.celery_task import indicator_history_task as task_module
    from backend.celery_task import celery_app as celery_module

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def execute(self, _query):
            return _Result([SimpleNamespace(
                user_id=9, symbol="BTC", category="market", indicator="price")])

    class _Bootstrap:
        def __init__(self, _session):
            pass

        async def bootstrap_market(self, _symbol, _names):
            return {"status": "ready", "inserted": 0}

    queued = []
    monkeypatch.setattr(task_module, "async_session_factory", _Session)
    monkeypatch.setattr(task_module, "IndicatorHistoryBootstrap", _Bootstrap)
    monkeypatch.setattr(celery_module.celery_app, "send_task",
                        lambda name, **kwargs: queued.append((name, kwargs)))

    asyncio.run(task_module._bootstrap_indicator_histories(
        user_id=9, symbol="BTC", category="market", indicator="price"))

    assert queued == [
        ("backend.celery_task.store_daily_scores_task.store_daily_scores_task",
         {"kwargs": {"user_id": 9}}),
    ]


def test_derived_dxy_history_uses_only_complete_currency_days(monkeypatch):
    common = _day(1).isoformat()
    incomplete = _day(2).isoformat()
    provider = TwelveDataMacroProvider(api_key="test-key")

    def fake_history(symbol, *, limit):
        assert limit == 12
        return {common: 1.2, **({incomplete: 1.1} if symbol != "USD/CHF" else {})}

    monkeypatch.setattr(provider, "fetch_daily_history", fake_history)
    history = provider.fetch_derived_dxy_history(limit=12)

    expected = DXY_BASE_FACTOR
    for _, exponent in DXY_COMPONENT_WEIGHTS.values():
        expected *= 1.2 ** exponent
    assert list(history) == [common]
    assert abs(history[common] - expected) < 1e-9


def test_fred_macro_history_keeps_real_source_dates(monkeypatch):
    csv_text = "DATE,SP500\n" + "\n".join(
        f"{_day(offset).isoformat()},{5000 + offset}" for offset in range(7, 0, -1)
    )
    monkeypatch.setattr(macro_interpreter, "_fetch_text", lambda *_args, **_kwargs: csv_text)

    readings = macro_interpreter.fetch_absolute_macro_history("sp500")

    assert len(readings) == 7
    assert readings[-1][0].date() == _day(1)
    assert readings[-1][1] == 5001.0


def test_workspace_explains_insufficient_history_without_turning_it_into_zero():
    rows = _enrich_indicator_rows([{
        "name": "dxy", "value": 98.2, "score": None,
        "source_observed_at": datetime.now(timezone.utc).isoformat(),
        "score_history_coverage": {"observed_days": 1, "required_days": 5, "window_days": 90},
    }], period="day", threshold=36 * 3600, source="macro_data")

    assert rows[0]["score_unavailable_reason"] == "insufficient_dated_history"
    assert rows[0]["score_contribution"]["weighted_points"] is None


def test_unchanged_macro_reading_is_rescored_after_history_arrives():
    source_at = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = SimpleNamespace(value=99.0, source_observed_at=source_at, score=None,
                               trend=None, interpretation=None, action=None)
    service = MacroDataService(AsyncMock())
    service.repository = SimpleNamespace(
        check_indicator_exists=AsyncMock(return_value=True),
        get_indicator_info=AsyncMock(return_value=None),
        get_latest_indicator=AsyncMock(return_value=existing),
        add_macro_data=AsyncMock(),
    )
    service._sync_fetch_macro_value = lambda *_args: {"value": 99.0, "observed_at": source_at}
    service._sync_score_indicator = lambda *_args: {
        "score": 80, "trend": "neutral", "interpretation": "measured", "action": "hold",
    }

    async def run():
        with patch("backend.services.macro_data_service.AssetCatalogService") as catalog:
            catalog.return_value.get_asset = AsyncMock(return_value={"asset_class": "crypto"})
            return await service.add_macro_indicator(
                7, "dxy", None, symbol="BTC", persist_preference=False,
                refresh_existing=True,
            )

    result = asyncio.run(run())
    assert result.score == 80
    assert existing.score == 80
    service.repository.add_macro_data.assert_not_awaited()


def test_macro_latest_readback_orders_by_source_time():
    statements = []

    async def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    session = SimpleNamespace(execute=execute)
    asyncio.run(MacroDataRepository(session).get_active_day_macro_data(7, "BTC"))

    assert "DISTINCT ON (macro_data.name)" in statements[0]
    assert "ORDER BY macro_data.name, macro_data.source_observed_at DESC NULLS LAST" in statements[0]
