import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.finn_v2_execution_service import FinnV2ExecutionService


def test_confirmed_setup_and_strategy_reconcile_their_exact_market(monkeypatch):
    from backend.infrastructure import database
    from backend.services import finn_coach_feed_service

    calls = []
    commits = []

    @asynccontextmanager
    async def session_factory():
        async def commit():
            commits.append(True)

        yield SimpleNamespace(commit=commit)

    class Feed:
        def __init__(self, _session):
            pass

        async def reconcile_journey_next_steps(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(database, "async_session_factory", session_factory)
    monkeypatch.setattr(finn_coach_feed_service, "FinnCoachFeedService", Feed)
    service = FinnV2ExecutionService.__new__(FinnV2ExecutionService)
    service.session = AsyncSession()
    try:
        asyncio.run(service._reconcile_journey_feed_after_commit(
            user_id=7, operation_type="create_setup",
            result={"setup": {"id": 42, "symbol": "BTC", "market_id": 34}},
        ))
        asyncio.run(service._reconcile_journey_feed_after_commit(
            user_id=7, operation_type="create_strategy",
            result={"strategy_id": 91, "setup_id": 42, "symbol": "BTC", "market_id": 34},
        ))
    finally:
        asyncio.run(service.session.close())
    assert calls == [
        {"user_id": 7, "symbol": "BTC", "market_id": 34},
        {"user_id": 7, "symbol": "BTC", "market_id": 34},
    ]
    assert len(commits) == 2


def test_feed_failure_does_not_reverse_a_committed_action(monkeypatch):
    from backend.infrastructure import database
    from backend.services import finn_coach_feed_service

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace()

    class Feed:
        def __init__(self, _session):
            pass

        async def reconcile_journey_next_steps(self, **_kwargs):
            raise RuntimeError("temporary feed failure")

    monkeypatch.setattr(database, "async_session_factory", session_factory)
    monkeypatch.setattr(finn_coach_feed_service, "FinnCoachFeedService", Feed)
    service = FinnV2ExecutionService.__new__(FinnV2ExecutionService)
    service.session = AsyncSession()
    try:
        assert asyncio.run(service._reconcile_journey_feed_after_commit(
            user_id=7, operation_type="create_setup",
            result={"setup": {"symbol": "BTC", "market_id": 34}},
        )) is None
    finally:
        asyncio.run(service.session.close())
