import ast
import importlib

from backend.celery_task.queue_policy import (
    ALLOWED_DEFAULT_TASKS,
    DEFAULT_QUEUE,
    DISPATCHER_TASK_NAME,
    LOGICAL_NAMED_QUEUES,
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

    production_ecosystem = Path(__file__).resolve().parents[4] / "ecosystem.production.config.js"
    shared_ecosystem = Path(__file__).resolve().parents[4] / "ops" / "deploy" / "ecosystem.shared.js"
    source = production_ecosystem.read_text() + "\n" + shared_ecosystem.read_text()

    assert "celery-worker-default" in source
    assert "celery-worker-market-portfolio" in source
    assert "celery-worker-scoring-execution" in source
    assert "celery-worker-ai-reporting" in source
    assert "--concurrency=${WORKER_CONCURRENCY.default} -Q ${queuePrefix}celery -n ${environmentName}-default@%h" in source
    assert "--concurrency=${WORKER_CONCURRENCY.marketPortfolio} -Q ${queuePrefix}market_data,${queuePrefix}portfolio -n ${environmentName}-market-portfolio@%h" in source
    assert "--concurrency=${WORKER_CONCURRENCY.scoringExecution} -Q ${queuePrefix}scoring,${queuePrefix}execution_critical -n ${environmentName}-scoring-execution@%h" in source
    assert "--concurrency=${WORKER_CONCURRENCY.aiReporting} -Q ${queuePrefix}ai_generation -n ${environmentName}-ai-reporting@%h" in source


def test_worker_concurrency_is_centralized_in_shared_ecosystem_config():
    from pathlib import Path

    shared_ecosystem = Path(__file__).resolve().parents[4] / "ops" / "deploy" / "ecosystem.shared.js"
    source = shared_ecosystem.read_text()

    assert "const WORKER_CONCURRENCY = {" in source
    assert "default: 2" in source
    assert "marketPortfolio: 2" in source
    assert "scoringExecution: 2" in source
    assert "aiReporting: 1" in source


def test_all_named_queues_are_assigned_to_pm2_workers():
    from pathlib import Path

    production_ecosystem = Path(__file__).resolve().parents[4] / "ecosystem.production.config.js"
    shared_ecosystem = Path(__file__).resolve().parents[4] / "ops" / "deploy" / "ecosystem.shared.js"
    source = production_ecosystem.read_text() + "\n" + shared_ecosystem.read_text()

    for queue_name in NAMED_QUEUES:
        assert queue_name in source


def test_named_queues_include_default_and_workload_classes():
    assert NAMED_QUEUES == [
        "celery",
        "market_data",
        "scoring",
        "portfolio",
        "ai_generation",
        "finn_interactive",
        "execution_critical",
    ]
    assert LOGICAL_NAMED_QUEUES == NAMED_QUEUES


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
            expected_queue = DEFAULT_QUEUE
        elif entry["task"] == "backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores":
            expected_queue = DEFAULT_QUEUE
        else:
            expected_queue = resolve_task_queue(entry["task"])

        assert entry["options"]["queue"] == expected_queue


def test_celery_publisher_stamps_published_at_header():
    from backend.celery_task.celery_app import stamp_task_publish_time

    headers = {}
    stamp_task_publish_time(headers=headers)

    assert "published_at" in headers
    assert headers["published_at"].endswith("+00:00")


def test_staging_queue_names_are_prefixed_consistently(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("CELERY_QUEUE_PREFIX", raising=False)

    import backend.celery_task.queue_policy as queue_policy

    reloaded = importlib.reload(queue_policy)
    try:
        assert reloaded.DEFAULT_QUEUE == "staging-celery"
        assert reloaded.NAMED_QUEUES == [
            "staging-celery",
            "staging-market_data",
            "staging-scoring",
            "staging-portfolio",
            "staging-ai_generation",
            "staging-finn_interactive",
            "staging-execution_critical",
        ]
        assert reloaded.resolve_task_queue("backend.celery_task.trading_bot_task.run_daily_trading_bot") == "staging-execution_critical"
    finally:
        monkeypatch.setenv("APP_ENV", "production")
        importlib.reload(queue_policy)
