import asyncio

import pytest
from fastapi import HTTPException

from backend.services.finn_trade_review_rollout import (
    allowed_trade_review_users, require_trade_review_access, trade_review_enabled,
)
from backend.services.finn_closed_trade_reflection_service import FinnClosedTradeReflectionService
from backend.celery_task import finn_trade_review_task as task
from backend.api.bot_api import (
    list_finn_trade_reviews, get_finn_trade_review,
    get_finn_trade_review_screenshot, put_finn_trade_review_screenshot,
    analyze_finn_trade_review, ask_finn_trade_review,
)


def test_rollout_defaults_off_and_rejects_malformed_allowlist(monkeypatch):
    monkeypatch.delenv("FINN_TRADE_REVIEW_ROLLOUT", raising=False)
    monkeypatch.delenv("FINN_TRADE_REVIEW_USER_IDS", raising=False)
    assert allowed_trade_review_users() == set()
    assert not trade_review_enabled(7)
    with pytest.raises(HTTPException) as exc:
        require_trade_review_access(7)
    assert exc.value.status_code == 404
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "allowlist")
    monkeypatch.setenv("FINN_TRADE_REVIEW_USER_IDS", "7,invalid")
    assert allowed_trade_review_users() == set()


def test_allowlist_and_explicit_all_mode(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "allowlist")
    monkeypatch.setenv("FINN_TRADE_REVIEW_USER_IDS", "7, 9")
    assert allowed_trade_review_users() == {7, 9}
    assert trade_review_enabled(7) and not trade_review_enabled(8)
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")
    assert allowed_trade_review_users() is None
    assert trade_review_enabled(8)


def test_disabled_api_and_coach_do_not_query_storage(monkeypatch):
    monkeypatch.delenv("FINN_TRADE_REVIEW_ROLLOUT", raising=False)

    class NoDB:
        async def execute(self, *_):
            raise AssertionError("disabled rollout must not query review storage")

    async def exercise():
        result = await list_finn_trade_reviews(None, current_user={"id": 7}, db=NoDB())
        assert result["status"] == "disabled" and result["items"] == []
        blocked = (
            get_finn_trade_review(81, current_user={"id": 7}, db=NoDB()),
            get_finn_trade_review_screenshot(81, current_user={"id": 7}, db=NoDB()),
            put_finn_trade_review_screenshot(81, None, current_user={"id": 7}, db=NoDB()),
            analyze_finn_trade_review(81, current_user={"id": 7}, db=NoDB()),
            ask_finn_trade_review(81, None, current_user={"id": 7}, db=NoDB()),
        )
        for call in blocked:
            with pytest.raises(HTTPException) as exc:
                await call
            assert exc.value.status_code == 404
        coach = await FinnClosedTradeReflectionService(NoDB()).recent(7)
        assert coach["status"] == "disabled" and coach["reviews"] == []
        assert await task._project_dirty_trade_reviews() == 0
        assert await task._analyze_pending_trade_reviews() == 0
        assert await task._sync_bybit_derivatives() == 0

    asyncio.run(exercise())


def test_worker_queries_only_allowlisted_users(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "allowlist")
    monkeypatch.setenv("FINN_TRADE_REVIEW_USER_IDS", "7")
    queries = []

    class Result:
        def fetchall(self):
            return []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, sql, params=None):
            queries.append((str(sql), params))
            return Result()

    monkeypatch.setattr(task, "async_session_factory", lambda: Session())
    asyncio.run(task._project_dirty_trade_reviews())
    asyncio.run(task._analyze_pending_trade_reviews())
    asyncio.run(task._sync_linked_exchange_fills())
    asyncio.run(task._sync_bybit_derivatives())
    assert len(queries) == 4
    assert all("ANY(CAST(:allowed AS INTEGER[]))" in sql for sql, _ in queries)
    assert all(params == {"allowed": [7]} for _, params in queries)
    assert "WHERE (analysis_status='pending' OR" in queries[1][0]
    assert "LEFT JOIN finn_exchange_import_attempts attempt" in queries[2][0]
    assert "attempt.last_attempt_at <= NOW() - INTERVAL '5 minutes'" in queries[2][0]
    assert "LOWER(k.exchange_name)='bybit'" in queries[3][0]
    assert "LEFT JOIN finn_bybit_derivative_attempts attempt" in queries[3][0]


def test_scheduled_derivative_sync_uses_owner_scoped_bounded_candidates(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "allowlist")
    monkeypatch.setenv("FINN_TRADE_REVIEW_USER_IDS", "7,8")
    called = []

    class Row:
        def __init__(self, user_id):
            self.user_id = user_id

    class Result:
        def fetchall(self):
            return [Row(7), Row(8)]

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, sql, params=None):
            statement = str(sql)
            assert "LIMIT 2" in statement
            assert "attempt.last_attempt_at NULLS FIRST" in statement
            assert params == {"allowed": [7, 8]}
            return Result()

    class Importer:
        def __init__(self, session):
            assert isinstance(session, Session)

        async def sync(self, user_id):
            called.append(user_id)

    monkeypatch.setattr(task, "FinnBybitDerivativeImportService", Importer)
    assert asyncio.run(task._sync_bybit_derivatives(lambda: Session())) == 2
    assert called == [7, 8]


def test_review_jobs_isolate_database_connections_across_celery_loops(monkeypatch):
    engines = []
    used = []

    class Engine:
        def __init__(self):
            self.disposed = False

        async def dispose(self):
            self.disposed = True

    def new_engine(*_args, **_kwargs):
        engine = Engine()
        engines.append(engine)
        return engine

    def new_sessions(engine, **_kwargs):
        return lambda: engine

    async def job(sessions):
        engine = sessions()
        assert not engine.disposed
        used.append(engine)
        return len(used)

    monkeypatch.setattr(task, "create_async_engine", new_engine)
    monkeypatch.setattr(task, "async_sessionmaker", new_sessions)
    monkeypatch.setattr(task, "_project_dirty_trade_reviews", job)
    monkeypatch.setattr(task, "_analyze_pending_trade_reviews", job)
    monkeypatch.setattr(task, "_sync_linked_exchange_fills", job)
    monkeypatch.setattr(task, "_sync_bybit_derivatives", job)

    assert task.project_dirty_trade_reviews.run() == 1
    assert task.analyze_pending_trade_reviews.run() == 2
    assert task.project_dirty_trade_reviews.run() == 3
    assert task.sync_linked_exchange_fills.run() == 4
    assert task.sync_linked_exchange_fills.run() == 5
    assert task.sync_bybit_derivatives.run() == 6
    assert len({id(engine) for engine in used}) == 6
    assert all(engine.disposed for engine in engines)
