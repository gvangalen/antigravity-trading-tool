import asyncio
from datetime import date

import pytest

from backend.celery_task.report_feed import publish_periodic_report_ready
from backend.infrastructure import database
from backend.services.finn_coach_feed_service import FinnCoachFeedService


@pytest.mark.parametrize("report_type", ["weekly", "monthly", "quarterly"])
def test_periodic_feed_publication_has_owner_date_and_stable_key(monkeypatch, report_type):
    recorded = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def commit(self):
            recorded.append("committed")

    async def publish(_self, **kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(database, "run_celery_isolated_session",
                        lambda operation: asyncio.run(operation(Session())))
    monkeypatch.setattr(FinnCoachFeedService, "publish", publish)
    publish_periodic_report_ready(7, report_type, date(2026, 11, 4), {
        "score_source_snapshot": {"assets": [{"symbol": "BTC", "pair": "BTC/USDT",
                                             "score_status": "available", "benchmark_score": 57}]},
    })

    event = recorded[0]
    assert recorded[1] == "committed"
    assert event["user_id"] == 7
    assert event["event_key"] == f"{report_type}-report:2026-11-04"
    assert event["revision"] == "2026-11-04:benchmark_available:BTC/USDT"
    assert event["evidence"]["report_type"] == report_type
    assert event["evidence"]["report_date"] == "2026-11-04"
    assert event["evidence"]["attention_pair"] == "BTC/USDT"


def test_report_feed_session_uses_a_fresh_engine_per_event_loop(monkeypatch):
    engines = []
    loops = []

    class Engine:
        def __init__(self):
            self.disposed = False

        async def dispose(self):
            self.disposed = True

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    def create_engine(_url, **kwargs):
        assert kwargs["poolclass"] is database.NullPool
        engine = Engine()
        engines.append(engine)
        return engine

    def session_maker(**kwargs):
        assert kwargs["bind"] is engines[-1]
        return Session

    monkeypatch.setattr(database, "create_async_engine", create_engine)
    monkeypatch.setattr(database, "async_sessionmaker", session_maker)

    async def operation(_session):
        loops.append(asyncio.get_running_loop())

    database.run_celery_isolated_session(operation)
    database.run_celery_isolated_session(operation)

    assert len(engines) == 2
    assert engines[0] is not engines[1]
    assert all(engine.disposed for engine in engines)
    assert loops[0] is not loops[1]
