import asyncio
from types import SimpleNamespace

from backend.services.exact_market_indicator_service import ExactMarketIndicatorService


def test_watched_pair_inherits_owner_indicators_without_setup():
    statements = []

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def all(self):
            return self.rows

        def scalars(self):
            return self

    class Session:
        async def execute(self, statement, _params=None):
            statements.append(str(statement))
            if len(statements) == 1:
                return Result([(7,)])
            if len(statements) == 2:
                return Result([])
            return Result([SimpleNamespace(user_id=7, symbol="BTC", category="market",
                                           indicator="price", market_id=None, enabled=True)])

    market = SimpleNamespace(id=73, asset_symbol="BTC")
    owners = asyncio.run(ExactMarketIndicatorService(Session())._configured_owners(market))

    assert "watchlists WHERE market_id" in statements[0]
    assert owners == {7: {"market": {"price"}, "technical": set()}}


def test_owner_repair_materializes_only_requested_owner(monkeypatch):
    from backend.services import exact_market_indicator_service as module

    locks = []

    class Session:
        async def execute(self, statement, params):
            locks.append((str(statement), params))

        async def commit(self):
            pass

    service = ExactMarketIndicatorService(Session())
    written = []

    async def configured(_market, _owner_ids, *, only_owner):
        assert only_owner is True
        return {
            7: {"market": {"price"}, "technical": set()},
            8: {"market": {"price"}, "technical": set()},
        }

    async def source_values(_market):
        from datetime import datetime, timezone
        return {"price": 100.0}, {}, datetime.now(timezone.utc), None

    async def upsert(_model, *, user_id, **_kwargs):
        written.append(user_id)

    async def to_thread(_func, *_args, **_kwargs):
        return {"score": 50}

    service._configured_owners = configured
    service._source_values = source_values
    service._upsert_reading = upsert
    monkeypatch.setattr(module.asyncio, "to_thread", to_thread)

    result = asyncio.run(service.materialize(
        SimpleNamespace(id=23, asset_symbol="BTC"), owner_ids={7}, only_owner=True))

    assert result["owners"] == [7]
    assert result["written"] == 1
    assert written == [7]
    assert "pg_advisory_xact_lock" in locks[0][0]
    assert locks[0][1]["market_id"] == 23


def test_older_owner_repair_cannot_replace_newer_shared_quote_reading():
    from datetime import datetime, timezone
    from backend.infrastructure.models import MarketDataIndicator

    newer = datetime(2026, 11, 9, 21, 10, tzinfo=timezone.utc).replace(tzinfo=None)
    older = datetime(2026, 11, 9, 21, 5, tzinfo=timezone.utc).replace(tzinfo=None)
    existing = SimpleNamespace(value=101.0, score=60, source_observed_at=newer)
    statements = []

    class Result:
        def scalars(self):
            return self

        def first(self):
            return existing

    class Session:
        async def execute(self, statement):
            statements.append(str(statement))
            return Result()

    service = ExactMarketIndicatorService(Session())
    asyncio.run(service._upsert_reading(
        MarketDataIndicator, market=SimpleNamespace(id=23, asset_symbol="BTC"),
        user_id=7, name="change_24h", value=99.0, observed_at=older,
        scored={"score": 20},
    ))

    assert "FOR UPDATE" in statements[0]
    assert existing.value == 101.0
    assert existing.score == 60
    assert existing.source_observed_at == newer


def test_owner_repair_queries_only_the_requested_owners_config():
    statements = []

    class Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class Session:
        async def execute(self, statement, _params=None):
            statements.append(str(statement))
            return Result()

    service = ExactMarketIndicatorService(Session())
    owners = asyncio.run(service._configured_owners(
        SimpleNamespace(id=23, asset_symbol="BTC"), {7}, only_owner=True))

    assert len(statements) == 1
    assert "user_indicator_configs.user_id IN" in statements[0]
    assert owners == {7: {"market": set(), "technical": set()}}


def test_parallel_first_materializations_serialize_on_pair_lock(monkeypatch):
    from backend.services import exact_market_indicator_service as module
    from datetime import datetime

    pair_lock = asyncio.Lock()
    rows = []

    class Session:
        async def execute(self, statement, params):
            assert "pg_advisory_xact_lock" in str(statement)
            assert params["market_id"] == 23
            await pair_lock.acquire()

        async def commit(self):
            pair_lock.release()

    async def configured(_market, _owner_ids, *, only_owner):
        return {7: {"market": {"price"}, "technical": set()}}

    async def source_values(_market):
        return {"price": 100.0}, {}, datetime(2026, 11, 9, 21, 10), None

    async def upsert(_model, **_kwargs):
        exists = bool(rows)
        await asyncio.sleep(0.01)
        if not exists:
            rows.append("price")

    async def to_thread(_func, *_args, **_kwargs):
        return {"score": 50}

    monkeypatch.setattr(module.asyncio, "to_thread", to_thread)

    async def run_one():
        service = ExactMarketIndicatorService(Session())
        service._configured_owners = configured
        service._source_values = source_values
        service._upsert_reading = upsert
        return await service.materialize(
            SimpleNamespace(id=23, asset_symbol="BTC"), owner_ids={7}, only_owner=True)

    async def run_both():
        return await asyncio.gather(run_one(), run_one())

    first, second = asyncio.run(run_both())
    assert first["written"] == second["written"] == 1
    assert rows == ["price"]
