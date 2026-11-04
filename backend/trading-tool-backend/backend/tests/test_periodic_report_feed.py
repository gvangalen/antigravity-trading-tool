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

    monkeypatch.setattr(database, "async_session_factory", Session)
    monkeypatch.setattr(FinnCoachFeedService, "publish", publish)
    publish_periodic_report_ready(7, report_type, date(2026, 11, 4))

    event = recorded[0]
    assert recorded[1] == "committed"
    assert event["user_id"] == 7
    assert event["event_key"] == f"{report_type}-report:2026-11-04"
    assert event["revision"] == "2026-11-04"
    assert event["evidence"]["report_type"] == report_type
    assert event["evidence"]["report_date"] == "2026-11-04"
