import ast

from backend.celery_task.queue_policy import (
    ALLOWED_DEFAULT_TASKS,
    DISPATCHER_TASK_NAME,
    NAMED_QUEUES,
    QUEUE_RATE_LIMITS,
    TASK_QUEUE_ROUTES,
    celery_task_annotations,
    celery_task_routes,
    rate_limit_summary_by_queue,
    resolve_task_queue,
    resolve_task_rate_limit,
    resolve_workload_class,
    unmapped_task_names,
)


def test_pm2_config_splits_named_queue_workers():
    from pathlib import Path

    ecosystem_path = Path(__file__).resolve().parents[4] / "ecosystem.config.js"
    source = ecosystem_path.read_text()

    assert "celery-worker-default" in source
    assert "celery-worker-market-portfolio" in source
    assert "celery-worker-scoring-execution" in source
    assert "celery-worker-ai-reporting" in source
    assert "-Q celery -n default@%h" in source
    assert "-Q market_data,portfolio -n market-portfolio@%h" in source
    assert "-Q scoring,execution_critical -n scoring-execution@%h" in source
    assert "-Q ai_generation -n ai-reporting@%h" in source


def test_all_named_queues_are_assigned_to_pm2_workers():
    from pathlib import Path

    ecosystem_path = Path(__file__).resolve().parents[4] / "ecosystem.config.js"
    source = ecosystem_path.read_text()

    for queue_name in NAMED_QUEUES:
        assert queue_name in source


def test_named_queues_include_default_and_workload_classes():
    assert NAMED_QUEUES == [
        "celery",
        "market_data",
        "scoring",
        "portfolio",
        "ai_generation",
        "execution_critical",
    ]


def test_task_queue_resolution_is_deterministic():
    assert resolve_task_queue("backend.celery_task.market_task.fetch_market_data") == "market_data"
    assert resolve_task_queue("backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores") == "scoring"
    assert resolve_task_queue("backend.celery_task.trading_bot_task.run_daily_trading_bot") == "execution_critical"
    assert resolve_task_queue("unknown.task") == "celery"


def test_workload_class_resolution_follows_queue():
    assert resolve_workload_class("backend.celery_task.portfolio_snapshot_task.run_portfolio_snapshot") == "portfolio"
    assert resolve_workload_class("backend.celery_task.daily_report_task.generate_daily_report") == "ai_generation"
    assert resolve_workload_class("unknown.task") == "default_fallback"


def test_rate_limit_resolution_follows_queue_policy():
    assert resolve_task_rate_limit("backend.celery_task.market_task.fetch_market_data") == "20/m"
    assert resolve_task_rate_limit("backend.celery_task.daily_report_task.generate_daily_report") == "6/m"
    assert resolve_task_rate_limit("backend.celery_task.trading_bot_task.run_daily_trading_bot") == "30/m"
    assert resolve_task_rate_limit("backend.celery_task.portfolio_snapshot_task.run_portfolio_snapshot") is None


def test_celery_task_routes_shape_matches_policy():
    routes = celery_task_routes()

    assert routes["backend.celery_task.market_task.fetch_market_data"] == {"queue": "market_data"}
    assert routes["backend.celery_task.trading_bot_task.run_daily_trading_bot"] == {"queue": "execution_critical"}
    assert set(routes.keys()) == set(TASK_QUEUE_ROUTES.keys())


def test_celery_task_annotations_are_explicit_and_non_global():
    annotations = celery_task_annotations()

    assert "*" not in annotations
    assert annotations["backend.celery_task.market_task.fetch_market_data"] == {"rate_limit": "20/m"}
    assert annotations["backend.celery_task.daily_report_task.generate_daily_report"] == {"rate_limit": "6/m"}
    assert annotations["backend.celery_task.trading_bot_task.run_daily_trading_bot"] == {"rate_limit": "30/m"}
    assert "backend.celery_task.portfolio_snapshot_task.run_portfolio_snapshot" not in annotations


def test_rate_limit_summary_by_queue_matches_policy():
    summary = rate_limit_summary_by_queue()

    assert summary["market_data"]["rate_limit"] == QUEUE_RATE_LIMITS["market_data"]
    assert summary["ai_generation"]["rate_limit"] == QUEUE_RATE_LIMITS["ai_generation"]
    assert summary["execution_critical"]["rate_limit"] == QUEUE_RATE_LIMITS["execution_critical"]
    assert summary["portfolio"]["rate_limit"] is None
    assert summary["scoring"]["throttled"] is False


def test_all_shared_tasks_are_routed_or_explicit_default():
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    task_names = set()

    for path in backend_root.rglob("*.py"):
        module_name = ".".join(path.relative_to(backend_root.parent).with_suffix("").parts)
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Name) or decorator.func.id != "shared_task":
                    continue
                explicit_name = None
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                        explicit_name = keyword.value.value
                        break
                task_names.add(explicit_name or f"{module_name}.{node.name}")

    assert unmapped_task_names(task_names) == []
    assert DISPATCHER_TASK_NAME in ALLOWED_DEFAULT_TASKS


def test_beat_schedule_routes_dispatch_and_direct_tasks_to_policy_queue():
    from backend.celery_task.celery_app import celery_app

    for entry in celery_app.conf.beat_schedule.values():
        if entry["task"] == DISPATCHER_TASK_NAME:
            expected_queue = resolve_task_queue(entry["kwargs"]["task_name"])
        else:
            expected_queue = resolve_task_queue(entry["task"])

        assert entry["options"]["queue"] == expected_queue
