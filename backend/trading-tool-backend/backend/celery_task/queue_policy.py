import os
from typing import Dict, Iterable, List, Optional


def _queue_name_prefix() -> str:
    explicit = os.getenv("CELERY_QUEUE_PREFIX")
    if explicit is not None:
        return explicit
    app_env = str(os.getenv("APP_ENV", "production") or "production").lower()
    return "staging-" if app_env == "staging" else ""


QUEUE_NAME_PREFIX = _queue_name_prefix()
DEFAULT_QUEUE_LOGICAL = "celery"
DEFAULT_QUEUE = f"{QUEUE_NAME_PREFIX}{DEFAULT_QUEUE_LOGICAL}"
DISPATCHER_TASK_NAME = "backend.celery_task.dispatcher.dispatch_for_all_users"
LOGICAL_NAMED_QUEUES: List[str] = [
    DEFAULT_QUEUE_LOGICAL,
    "market_data",
    "scoring",
    "portfolio",
    "ai_generation",
    "execution_critical",
]
NAMED_QUEUES: List[str] = [f"{QUEUE_NAME_PREFIX}{queue_name}" for queue_name in LOGICAL_NAMED_QUEUES]

TASK_QUEUE_ROUTES: Dict[str, str] = {
    "backend.ai_agents.score_ai_agent.generate_master_score": "ai_generation",
    "backend.celery_task.market_task.fetch_market_data": "market_data",
    "backend.celery_task.market_task.fetch_market_data_7d": "market_data",
    "backend.celery_task.market_task.save_market_data_daily": "market_data",
    "backend.celery_task.market_task.calculate_and_save_forward_returns": "market_data",
    "backend.celery_task.market_task.sync_crypto_forward_returns": "market_data",
    "backend.celery_task.market_task.fetch_market_indicators": "market_data",
    "backend.celery_task.market_task.run_market_agent_daily": "ai_generation",
    "backend.celery_task.macro_task.fetch_macro_data": "market_data",
    "backend.celery_task.macro_task.run_macro_agent_daily": "ai_generation",
    "backend.celery_task.macro_task.generate_macro_insight": "ai_generation",
    "backend.celery_task.technical_task.fetch_technical_data_day": "market_data",
    "backend.celery_task.technical_task.run_technical_agent_daily": "ai_generation",
    "backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores": "scoring",
    "backend.celery_task.store_daily_scores_task.run_master_score_ai": "ai_generation",
    "backend.celery_task.user_scoring_sync_task.sync_all_users_scores": "scoring",
    "backend.celery_task.portfolio_snapshot_task.run_portfolio_snapshot": "portfolio",
    "backend.celery_task.setup_task.run_setup_agent_daily": "scoring",
    "backend.celery_task.strategy_task.run_daily_strategy_snapshot": "portfolio",
    "backend.celery_task.strategy_task.generate_for_setup": "ai_generation",
    "backend.celery_task.strategy_task.analyze_strategy": "ai_generation",
    "backend.celery_task.strategy_task.generate_all": "ai_generation",
    "backend.celery_task.trading_bot_task.run_daily_trading_bot": "execution_critical",
    "backend.celery_task.regime_memory_task.run_regime_memory": "ai_generation",
    "backend.celery_task.daily_report_task.generate_daily_report": "ai_generation",
    "backend.celery_task.weekly_report_task.generate_weekly_report": "ai_generation",
    "backend.celery_task.monthly_report_task.generate_monthly_report": "ai_generation",
    "backend.celery_task.quarterly_report_task.generate_quarterly_report": "ai_generation",
    "backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing": "ai_generation",
    "backend.celery_task.onboarding_task.generate_first_dashboard_briefing": "ai_generation",
    "backend.celery_task.global_intelligence_task.run_global_intelligence": "ai_generation",
    "backend.celery_task.global_ingestion_task.run_global_ingestion": "market_data",
    "backend.celery_task.asset_initialization.initialize_asset_data": "market_data",
    "backend.celery_task.btc_price_history_task.update_btc_history": "market_data",
    "backend.celery_task.onboarding_task.run_onboarding_pipeline": "ai_generation",
    "backend.celery_task.bootstrap_agents_task.bootstrap_agents_task": "ai_generation",
    "backend.celery_task.celery_task_generate_pdf.generate_report_pdf": "ai_generation",
    "backend.celery_task.daily_usage_reset.reset_daily_ai_quotas": "scoring",
}

ALLOWED_DEFAULT_TASKS = {
    DISPATCHER_TASK_NAME,
}

WORKLOAD_CLASS_BY_QUEUE = {
    DEFAULT_QUEUE: "default_fallback",
    "market_data": "market_data",
    "scoring": "scoring",
    "portfolio": "portfolio",
    "ai_generation": "ai_generation",
    "execution_critical": "execution_critical",
}

QUEUE_RATE_LIMITS: Dict[str, str] = {
    "market_data": "20/m",
    "ai_generation": "6/m",
    "execution_critical": "30/m",
}

QUEUE_BACKLOG_LIMITS: Dict[str, int] = {
    "market_data": 2000,
    "scoring": 1500,
    "portfolio": 1500,
    "ai_generation": 800,
    "execution_critical": 400,
    DEFAULT_QUEUE_LOGICAL: 500,
}

DISPATCH_WINDOW_SECONDS: Dict[str, int] = {
    "backend.celery_task.macro_task.fetch_macro_data": 2 * 60 * 60,
    "backend.celery_task.technical_task.fetch_technical_data_day": 2 * 60 * 60,
    "backend.celery_task.market_task.fetch_market_indicators": 2 * 60 * 60,
    "backend.celery_task.portfolio_snapshot_task.run_portfolio_snapshot": 15 * 60,
    "backend.celery_task.setup_task.run_setup_agent_daily": 15 * 60,
    "backend.celery_task.trading_bot_task.run_daily_trading_bot": 15 * 60,
    "backend.celery_task.macro_task.run_macro_agent_daily": 24 * 60 * 60,
    "backend.celery_task.market_task.run_market_agent_daily": 24 * 60 * 60,
    "backend.celery_task.technical_task.run_technical_agent_daily": 24 * 60 * 60,
    "backend.celery_task.regime_memory_task.run_regime_memory": 24 * 60 * 60,
    "backend.celery_task.strategy_task.run_daily_strategy_snapshot": 12 * 60 * 60,
    "backend.celery_task.daily_report_task.generate_daily_report": 24 * 60 * 60,
    "backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing": 24 * 60 * 60,
    "backend.celery_task.onboarding_task.generate_first_dashboard_briefing": 24 * 60 * 60,
}


def _logical_queue_name(queue_name: str) -> str:
    if QUEUE_NAME_PREFIX and queue_name.startswith(QUEUE_NAME_PREFIX):
        return queue_name[len(QUEUE_NAME_PREFIX):]
    return queue_name


def resolve_task_queue(task_name: str) -> str:
    logical_queue = TASK_QUEUE_ROUTES.get(task_name, DEFAULT_QUEUE_LOGICAL)
    return f"{QUEUE_NAME_PREFIX}{logical_queue}"


def resolve_workload_class(task_name: str) -> str:
    return WORKLOAD_CLASS_BY_QUEUE.get(_logical_queue_name(resolve_task_queue(task_name)), "default_fallback")


def celery_task_routes() -> Dict[str, Dict[str, str]]:
    return {task_name: {"queue": queue} for task_name, queue in TASK_QUEUE_ROUTES.items()}


def resolve_task_rate_limit(task_name: str) -> Optional[str]:
    return QUEUE_RATE_LIMITS.get(_logical_queue_name(resolve_task_queue(task_name)))


def resolve_queue_backlog_limit(task_name: str) -> Optional[int]:
    return QUEUE_BACKLOG_LIMITS.get(_logical_queue_name(resolve_task_queue(task_name)))


def resolve_dispatch_window_seconds(task_name: str, *, fallback_seconds: int) -> int:
    return int(DISPATCH_WINDOW_SECONDS.get(task_name, fallback_seconds))


def celery_task_annotations() -> Dict[str, Dict[str, str]]:
    annotations: Dict[str, Dict[str, str]] = {}
    for task_name in TASK_QUEUE_ROUTES:
        rate_limit = resolve_task_rate_limit(task_name)
        if rate_limit:
            annotations[task_name] = {"rate_limit": rate_limit}
    return annotations


def build_task_schedule_entry(
    task_name: str,
    schedule,
    *,
    kwargs: dict | None = None,
    queue_override: str | None = None,
) -> Dict[str, object]:
    entry: Dict[str, object] = {
        "task": task_name,
        "schedule": schedule,
        "options": {"queue": queue_override or resolve_task_queue(task_name)},
    }
    if kwargs:
        entry["kwargs"] = kwargs
    return entry


def build_dispatch_schedule_entry(
    target_task_name: str,
    schedule,
    *,
    active_only: bool = True,
    batch_size: int | None = None,
    max_spread_seconds: int | None = None,
) -> Dict[str, object]:
    kwargs = {
        "task_name": target_task_name,
        "active_only": active_only,
    }
    if batch_size is not None:
        kwargs["batch_size"] = batch_size
    if max_spread_seconds is not None:
        kwargs["max_spread_seconds"] = max_spread_seconds

    return {
        "task": DISPATCHER_TASK_NAME,
        "schedule": schedule,
        "kwargs": kwargs,
        "options": {"queue": DEFAULT_QUEUE},
    }


def unmapped_task_names(task_names: Iterable[str]) -> List[str]:
    known_task_names = set(TASK_QUEUE_ROUTES) | set(ALLOWED_DEFAULT_TASKS)
    return sorted({task_name for task_name in task_names if task_name not in known_task_names})


def rate_limit_summary_by_queue() -> Dict[str, Dict[str, object]]:
    summary: Dict[str, Dict[str, object]] = {}
    for queue_name in NAMED_QUEUES:
        logical_queue = _logical_queue_name(queue_name)
        task_names = sorted(
            task_name for task_name, mapped_queue in TASK_QUEUE_ROUTES.items()
            if mapped_queue == logical_queue
        )
        rate_limit = QUEUE_RATE_LIMITS.get(logical_queue)
        summary[queue_name] = {
            "rate_limit": rate_limit,
            "task_count": len(task_names),
            "throttled": rate_limit is not None,
        }
    return summary
