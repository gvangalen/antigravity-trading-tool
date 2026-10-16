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
    assert len(queries) == 2
    assert all("ANY(CAST(:allowed AS INTEGER[]))" in sql for sql, _ in queries)
    assert all(params == {"allowed": [7]} for _, params in queries)
    assert "WHERE (analysis_status='pending' OR" in queries[1][0]
