import asyncio
from datetime import date, datetime, timedelta, timezone

from backend.services.system_health_service import (
    SystemHealthService,
    _age_seconds,
    _as_utc,
)


def test_as_utc_handles_naive_datetime_as_utc():
    value = datetime(2026, 5, 24, 8, 0, 0)

    result = _as_utc(value)

    assert result.tzinfo == timezone.utc
    assert result.isoformat() == "2026-05-24T08:00:00+00:00"


def test_age_seconds_handles_date_without_crashing():
    assert isinstance(_age_seconds(date.today()), int)


def test_overall_status_degrades_on_stale_component():
    status = SystemHealthService._overall_status({
        "database": {"status": "ok"},
        "market_snapshot": {"status": "stale"},
    })

    assert status == "degraded"


def test_overall_status_degrades_on_non_ok_components():
    for component_status in ["down", "error", "unknown"]:
        status = SystemHealthService._overall_status({
            "database": {"status": "ok"},
            "broker": {"status": component_status},
        })

        assert status == "degraded"


def test_overall_status_ok_when_all_components_ok():
    status = SystemHealthService._overall_status({
        "database": {"status": "ok"},
        "broker": {"status": "ok"},
    })

    assert status == "ok"


def test_deep_health_returns_component_statuses(monkeypatch):
    async def ok_database():
        return {"status": "ok", "latency_ms": 1.0}

    async def down_broker():
        return {"status": "down", "error": "redis unavailable"}

    async def ok_celery():
        return {
            "status": "ok",
            "worker_count": 1,
            "workers": ["worker@example"],
            "rate_limits_by_queue": {
                "market_data": {"rate_limit": "20/m", "task_count": 1, "throttled": True},
            },
        }

    async def ok_market():
        return {
            "status": "ok",
            "symbol": "BTC",
            "age_seconds": 30,
            "latest_timestamp": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
        }

    async def ok_scores():
        return {"status": "ok", "symbol": "BTC", "age_seconds": 3600}

    monkeypatch.setattr(SystemHealthService, "_check_database", staticmethod(ok_database))
    monkeypatch.setattr(SystemHealthService, "_check_broker", staticmethod(down_broker))
    monkeypatch.setattr(SystemHealthService, "_check_celery", staticmethod(ok_celery))
    monkeypatch.setattr(SystemHealthService, "_check_latest_market_snapshot", staticmethod(ok_market))
    monkeypatch.setattr(SystemHealthService, "_check_latest_score", staticmethod(ok_scores))

    response = asyncio.run(SystemHealthService.deep_health())

    assert response["status"] == "degraded"
    assert response["components"]["database"]["status"] == "ok"
    assert response["components"]["broker"]["status"] == "down"
    assert response["components"]["celery"]["worker_count"] == 1
    assert response["components"]["celery"]["rate_limits_by_queue"]["market_data"]["rate_limit"] == "20/m"
    assert response["duration_ms"] >= 0


def test_workers_by_queue_maps_active_queue_names():
    result = SystemHealthService._workers_by_queue({
        "worker-a": [{"name": "market_data"}, {"name": "scoring"}],
        "worker-b": [{"name": "market_data"}],
    })

    assert result["market_data"] == ["worker-a", "worker-b"]
    assert result["scoring"] == ["worker-a"]
    assert result["execution_critical"] == []


def test_check_celery_includes_rate_limit_summary(monkeypatch):
    monkeypatch.setattr(SystemHealthService, "_celery_ping", staticmethod(lambda: {"worker-a": {"ok": "pong"}}))
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_active_queues",
        staticmethod(lambda: {"worker-a": [{"name": "market_data"}]}),
    )

    result = asyncio.run(SystemHealthService._check_celery())

    assert result["status"] == "ok"
    assert result["workers_by_queue"]["market_data"] == ["worker-a"]
    assert result["rate_limits_by_queue"]["market_data"]["rate_limit"] == "20/m"
    assert result["rate_limits_by_queue"]["portfolio"]["rate_limit"] is None
