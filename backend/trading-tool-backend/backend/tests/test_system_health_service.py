import asyncio
from datetime import date, datetime, timedelta, timezone

from backend.services.system_health_service import (
    CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS,
    SystemHealthService,
    _age_seconds,
    _as_utc,
)
from backend.services.platform_metrics import (
    increment_dispatcher_counter,
    increment_execution_safety_counter,
    increment_retry_counter,
    record_latency_sample,
    reset_process_metrics,
    runtime_identity_snapshot,
)


def test_as_utc_handles_naive_datetime_as_utc():
    value = datetime(2026, 5, 24, 8, 0, 0)

    result = _as_utc(value)

    assert result.tzinfo == timezone.utc
    assert result.isoformat() == "2026-05-24T08:00:00+00:00"


def test_age_seconds_handles_date_without_crashing():
    assert isinstance(_age_seconds(date.today()), int)


def test_queue_age_summary_uses_published_at_header(monkeypatch):
    fixed_now = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "backend.services.system_health_service._utcnow",
        lambda: fixed_now,
    )

    result = SystemHealthService._queue_age_summary([
        b'{"headers":{"published_at":"2026-05-25T09:59:00+00:00"}}',
        b'{"headers":{"published_at":"2026-05-25T09:58:00+00:00"}}',
        b'{"headers":{"task":"legacy.without.timestamp"}}',
    ])

    assert result["sample_size"] == 3
    assert result["timestamped_sample_size"] == 2
    assert result["timestamp_coverage_ratio"] == 0.6667
    assert result["oldest_message_age_seconds"] == 120
    assert result["newest_message_age_seconds"] == 60
    assert result["average_message_age_seconds"] == 90
    assert result["age_source"] == "celery_published_at_header"


def test_queue_age_summary_marks_unknown_when_no_timestamps():
    result = SystemHealthService._queue_age_summary([
        b'{"headers":{"task":"legacy.without.timestamp"}}',
    ])

    assert result["timestamped_sample_size"] == 0
    assert result["oldest_message_age_seconds"] is None
    assert result["age_source"] == "unavailable"


def test_queue_depth_trend_reports_drain_rate(monkeypatch):
    SystemHealthService._last_queue_depths_snapshot = {
        "checked_at_monotonic": 100.0,
        "queue_depths": {"celery": 100},
    }
    monkeypatch.setattr("backend.services.system_health_service.time.time", lambda: 160.0)

    result = SystemHealthService._queue_depth_trend({"celery": 70})

    assert result["celery"]["depth_delta_since_last_check"] == -30
    assert result["celery"]["depth_delta_per_minute"] == -30.0
    assert result["celery"]["estimated_drain_per_minute"] == 30.0
    assert result["celery"]["trend_source"] == "in_process_previous_health_check"


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
    reset_process_metrics()
    increment_dispatcher_counter("wave_lease_skip_count", 2)
    increment_execution_safety_counter("replay_block_hits", 1)
    increment_retry_counter("trading_bot_task", 3)
    record_latency_sample("dashboard_aggregation_latency_ms", 100)
    record_latency_sample("dashboard_aggregation_latency_ms", 250)
    record_latency_sample("assistant_context_latency_ms", 80)
    record_latency_sample("assistant_context_latency_ms", 160)

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
    assert response["metrics_scope"] == "process_lifetime"
    assert response["runtime_identity"]["instance_id"] == runtime_identity_snapshot()["instance_id"]
    assert response["observability_scope"]["cluster_rollup_ready"] is False
    assert response["dispatcher_counters"]["wave_lease_skip_count"] == 2
    assert response["execution_safety_counters"]["replay_block_hits"] == 1
    assert response["retry_counters"]["trading_bot_task"] == 3
    assert response["latency_metrics"]["dashboard_aggregation_latency_ms_p50"] == 100.0
    assert response["latency_metrics"]["assistant_context_latency_ms_p95"] == 160.0
    assert response["cluster_observability"]["instance_id"] == runtime_identity_snapshot()["instance_id"]
    assert response["cluster_observability"]["visible_worker_count"] == 1
    assert response["cluster_observability"]["degraded_components"] == ["broker"]
    assert response["duration_ms"] >= 0


def test_workers_by_queue_maps_active_queue_names():
    result = SystemHealthService._workers_by_queue({
        "worker-a": [{"name": "market_data"}, {"name": "scoring"}],
        "worker-b": [{"name": "market_data"}],
    })

    assert result["market_data"] == ["worker-a", "worker-b"]
    assert result["scoring"] == ["worker-a"]
    assert result["execution_critical"] == []


def test_celery_health_budget_exceeds_control_command_deadline():
    # A fresh API process can need to import the Celery app before it can
    # inspect a worker. Its outer health budget must not be shorter than the
    # inspector's own control-command deadline.
    assert SystemHealthService._celery_inspect_timeout_seconds > CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS


def test_check_celery_includes_rate_limit_summary(monkeypatch):
    monkeypatch.setattr(SystemHealthService, "_celery_ping", staticmethod(lambda: {"worker-a": {"ok": "pong"}}))
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_active_queues",
        staticmethod(lambda: {"worker-a": [{"name": "market_data"}, {"name": "finn_interactive"}]}),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_stats",
        staticmethod(lambda: {"worker-a": {"pid": 123}}),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_registered",
        staticmethod(
            lambda: {
                "worker-a": [
                    "backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing",
                    "backend.celery_task.onboarding_task.generate_first_dashboard_briefing",
                ]
            }
        ),
    )

    result = asyncio.run(SystemHealthService._check_celery())

    assert result["status"] == "ok"
    assert result["worker_discovery_sources"] == ["ping", "active_queues", "stats", "registered"]
    assert result["workers_by_queue"]["market_data"] == ["worker-a"]
    assert result["rate_limits_by_queue"]["market_data"]["rate_limit"] == "20/m"
    assert result["rate_limits_by_queue"]["portfolio"]["rate_limit"] is None
    assert result["registered_tasks"]["visible_worker_count"] == 1
    assert result["registered_tasks"]["workers_with_first_dashboard_tasks"]["worker-a"] == [
        "backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing",
        "backend.celery_task.onboarding_task.generate_first_dashboard_briefing",
    ]


def test_check_celery_falls_back_to_active_queues_and_stats_when_ping_is_empty(monkeypatch):
    monkeypatch.setattr(SystemHealthService, "_celery_ping", staticmethod(lambda: None))
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_active_queues",
        staticmethod(
            lambda: {
                "worker-a": [{"name": "market_data"}],
                "worker-b": [{"name": "execution_critical"}, {"name": "finn_interactive"}],
            }
        ),
    )
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_stats",
        staticmethod(lambda: {"worker-b": {"pid": 456}}),
    )
    monkeypatch.setattr(SystemHealthService, "_celery_registered", staticmethod(lambda: None))

    result = asyncio.run(SystemHealthService._check_celery())

    assert result["status"] == "ok"
    assert result["worker_count"] == 2
    assert result["workers"] == ["worker-a", "worker-b"]
    assert result["worker_discovery_sources"] == ["active_queues", "stats"]
    assert result["workers_by_queue"]["market_data"] == ["worker-a"]
    assert result["workers_by_queue"]["execution_critical"] == ["worker-b"]


def test_check_celery_requires_a_live_finn_interactive_queue(monkeypatch):
    monkeypatch.setattr(SystemHealthService, "_celery_ping", staticmethod(lambda: {"worker-a": {"ok": "pong"}}))
    monkeypatch.setattr(
        SystemHealthService,
        "_celery_active_queues",
        staticmethod(lambda: {"worker-a": [{"name": "celery"}]}),
    )
    monkeypatch.setattr(SystemHealthService, "_celery_stats", staticmethod(lambda: {"worker-a": {}}))
    monkeypatch.setattr(SystemHealthService, "_celery_registered", staticmethod(lambda: {"worker-a": []}))

    result = asyncio.run(SystemHealthService._check_celery())

    assert result["status"] == "down"
    assert result["missing_queue"] == "finn_interactive"


def test_check_celery_rejects_pm2_snapshot_when_inspect_is_empty(monkeypatch):
    monkeypatch.setattr(SystemHealthService, "_celery_ping", staticmethod(lambda: None))
    monkeypatch.setattr(SystemHealthService, "_celery_active_queues", staticmethod(lambda: None))
    monkeypatch.setattr(SystemHealthService, "_celery_stats", staticmethod(lambda: None))
    monkeypatch.setattr(SystemHealthService, "_celery_registered", staticmethod(lambda: None))
    monkeypatch.setattr(
        SystemHealthService,
        "_pm2_celery_workers_snapshot",
        staticmethod(
            lambda: {
                "workers": ["celery-worker-default", "celery-worker-scoring-execution"],
                "workers_by_queue": {
                    "celery": ["celery-worker-default"],
                    "scoring": ["celery-worker-scoring-execution"],
                    "execution_critical": ["celery-worker-scoring-execution"],
                },
                "worker_mapping_source": "pm2_process_list_static_queue_map",
            }
        ),
    )

    result = asyncio.run(SystemHealthService._check_celery())

    assert result["status"] == "down"
    assert result["worker_count"] == 0
    assert result["control_plane_ready"] is False
    assert result["pm2_workers"] == ["celery-worker-default", "celery-worker-scoring-execution"]


def test_queue_sample_summary_reports_legacy_breakdown():
    class _FakeRedis:
        async def llen(self, queue_name):
            assert queue_name == "celery"
            return 2

        async def lrange(self, queue_name, start, end):
            assert queue_name == "celery"
            return [
                b'{"headers":{"task":"backend.celery_task.dispatcher.dispatch_for_all_users"}}',
                b'{"headers":{"task":"backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores"}}',
            ]

    result = asyncio.run(
        SystemHealthService._queue_sample_summary(_FakeRedis(), queue_name="celery", sample_size=200)
    )

    assert result["queue"] == "celery"
    assert result["sample_size"] == 2
    assert result["rerouteable_count"] == 1
    assert result["kept_on_default_count"] == 1


def test_check_broker_includes_default_queue_sample(monkeypatch):
    SystemHealthService._last_queue_depths_snapshot = None

    class _FakeRedis:
        async def ping(self):
            return True

        async def llen(self, queue_name):
            if queue_name == "celery":
                return 3
            return 0

        async def lrange(self, queue_name, start, end):
            if queue_name == "celery":
                return [
                    b'{"headers":{"task":"backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores","published_at":"2026-05-25T09:59:00+00:00"}}',
                ]
            return []

        async def aclose(self):
            return None

    import redis.asyncio as redis

    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: _FakeRedis())

    result = asyncio.run(SystemHealthService._check_broker())

    assert result["status"] == "ok"
    assert result["default_queue_depth"] == 3
    assert result["default_queue_sample"]["rerouteable_count"] == 1
    assert result["queue_metrics"]["celery"]["depth"] == 3
    assert result["queue_metrics"]["celery"]["timestamped_sample_size"] == 1
    assert result["queue_metrics"]["market_data"]["depth"] == 0


def test_attach_queue_runtime_metadata_adds_workers_and_rate_limit():
    components = {
        "broker": {
            "queue_metrics": {
                "market_data": {"depth": 4},
                "portfolio": {"depth": 0},
            }
        },
        "celery": {
            "workers_by_queue": {"market_data": ["worker-a"], "portfolio": []},
            "rate_limits_by_queue": {
                "market_data": {"rate_limit": "20/m"},
                "portfolio": {"rate_limit": None},
            },
        },
    }

    SystemHealthService._attach_queue_runtime_metadata(components)

    assert components["broker"]["queue_metrics"]["market_data"]["workers"] == ["worker-a"]
    assert components["broker"]["queue_metrics"]["market_data"]["rate_limit"] == "20/m"
    assert components["broker"]["queue_metrics"]["market_data"]["worker_mapping_source"] == "celery_active_queues_inspect"
    assert components["broker"]["queue_metrics"]["market_data"]["rate_limit_source"] == "queue_policy_static"
    assert components["broker"]["queue_metrics"]["market_data"]["depth_source"] == "redis_llen"
    assert components["broker"]["queue_metrics"]["portfolio"]["workers"] == []
    assert components["broker"]["queue_metrics"]["portfolio"]["rate_limit"] is None


def test_cluster_observability_summary_explains_instance_scope():
    metrics = {
        "runtime_identity": {
            "instance_id": "production:host-a:123",
            "hostname": "host-a",
            "pid": 123,
            "app_env": "production",
            "process_started_at": "2026-06-06T10:00:00+00:00",
        },
        "observability_scope": {
            "queue_truth_scope": "broker_snapshot_at_check_time",
            "worker_truth_scope": "celery_inspect_snapshot_visible_from_current_instance",
            "counter_truth_scope": "instance_process_lifetime",
            "latency_truth_scope": "instance_process_window_last_256_samples",
            "cluster_rollup_ready": False,
            "cluster_rollup_note": "Aggregate externally.",
        },
    }
    components = {
        "database": {"status": "ok"},
        "broker": {"status": "ok", "total_queue_depth": 12},
        "celery": {"status": "ok", "worker_count": 2, "workers": ["worker-a", "worker-b"]},
        "scores": {"status": "stale"},
    }

    result = SystemHealthService._cluster_observability_summary(components, metrics)

    assert result["instance_id"] == "production:host-a:123"
    assert result["visible_worker_count"] == 2
    assert result["total_queue_depth"] == 12
    assert result["degraded_components"] == ["scores"]
    assert result["cluster_rollup_ready"] is False
