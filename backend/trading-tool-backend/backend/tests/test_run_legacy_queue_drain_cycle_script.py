from backend.scripts import run_legacy_queue_drain_cycle as cycle_script


def test_run_drain_cycle_stops_when_reroute_ratio_drops(monkeypatch):
    samples = iter(
        [
            {
                "queue": "celery",
                "total_depth": 100,
                "rerouteable_count": 80,
                "reroute_ratio": 0.8,
                "top_tasks": [{"task_name": "task-a", "count": 80}],
            },
            {
                "queue": "celery",
                "total_depth": 100,
                "rerouteable_count": 80,
                "reroute_ratio": 0.8,
                "top_tasks": [{"task_name": "task-a", "count": 80}],
            },
            {
                "queue": "celery",
                "total_depth": 20,
                "rerouteable_count": 4,
                "reroute_ratio": 0.2,
                "top_tasks": [{"task_name": "task-b", "count": 4}],
            },
            {
                "queue": "celery",
                "total_depth": 20,
                "rerouteable_count": 4,
                "reroute_ratio": 0.2,
                "top_tasks": [{"task_name": "task-b", "count": 4}],
            },
        ]
    )
    drains = []

    monkeypatch.setattr(cycle_script, "inspect_legacy_queue", lambda *args, **kwargs: next(samples))

    def _fake_drain(queue_name, limit, *, runtime_cap_seconds):
        drains.append((queue_name, limit, runtime_cap_seconds))
        return {
            "processed": 50,
            "rerouted": 40,
            "kept": 10,
            "stop_reason": "limit_reached",
            "before_queue_depths": {"celery": 100},
            "after_queue_depths": {"celery": 50},
        }

    monkeypatch.setattr(cycle_script, "drain_legacy_queue", _fake_drain)
    monkeypatch.setattr(cycle_script.time, "sleep", lambda *_args, **_kwargs: None)

    result = cycle_script.run_drain_cycle(
        "celery",
        apply=True,
        sample_size=50,
        max_runs=5,
        limit_per_run=50,
        runtime_cap_seconds=10.0,
        sleep_seconds=0.1,
        min_reroute_ratio=0.5,
    )

    assert result["stop_reason"] == "reroute_ratio_below_threshold"
    assert result["totals"]["processed"] == 50
    assert result["totals"]["rerouted"] == 40
    assert result["operator_summary"]["reroute_ratio_before"] == 0.8
    assert result["operator_summary"]["reroute_ratio_after"] == 0.2
    assert result["operator_summary"]["processed"] == 50
    assert result["operator_summary"]["rerouted"] == 40
    assert result["operator_summary"]["kept"] == 10
    assert result["operator_summary"]["top_tasks_before"] == [{"task_name": "task-a", "count": 80}]
    assert result["operator_summary"]["top_tasks_after"] == [{"task_name": "task-b", "count": 4}]
    assert result["operator_summary"]["stop_reason"] == "reroute_ratio_below_threshold"
    assert len(result["runs"]) == 1
    assert drains == [("celery", 50, 10.0)]


def test_run_drain_cycle_respects_max_processed_total(monkeypatch):
    sample = {"queue": "celery", "total_depth": 500, "rerouteable_count": 500, "reroute_ratio": 1.0}
    monkeypatch.setattr(cycle_script, "inspect_legacy_queue", lambda *args, **kwargs: sample)
    monkeypatch.setattr(cycle_script.time, "sleep", lambda *_args, **_kwargs: None)

    requested_limits = []

    def _fake_drain(queue_name, limit, *, runtime_cap_seconds):
        requested_limits.append(limit)
        return {
            "processed": limit,
            "rerouted": limit,
            "kept": 0,
            "stop_reason": "limit_reached",
            "before_queue_depths": {"celery": 500},
            "after_queue_depths": {"celery": 500 - limit},
        }

    monkeypatch.setattr(cycle_script, "drain_legacy_queue", _fake_drain)

    result = cycle_script.run_drain_cycle(
        "celery",
        apply=True,
        sample_size=50,
        max_runs=5,
        limit_per_run=100,
        runtime_cap_seconds=10.0,
        sleep_seconds=0.0,
        min_reroute_ratio=0.5,
        max_processed_total=180,
    )

    assert result["stop_reason"] == "max_processed_total_reached"
    assert result["totals"]["processed"] == 180
    assert requested_limits == [100, 80]
    assert len(result["runs"]) == 2
