from backend.celery_task.queue_policy import (
    NAMED_QUEUES,
    TASK_QUEUE_ROUTES,
    celery_task_routes,
    resolve_task_queue,
    resolve_workload_class,
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


def test_celery_task_routes_shape_matches_policy():
    routes = celery_task_routes()

    assert routes["backend.celery_task.market_task.fetch_market_data"] == {"queue": "market_data"}
    assert routes["backend.celery_task.trading_bot_task.run_daily_trading_bot"] == {"queue": "execution_critical"}
    assert set(routes.keys()) == set(TASK_QUEUE_ROUTES.keys())
