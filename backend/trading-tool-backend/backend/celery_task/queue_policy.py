from typing import Dict, List


DEFAULT_QUEUE = "celery"
NAMED_QUEUES: List[str] = [
    DEFAULT_QUEUE,
    "market_data",
    "scoring",
    "portfolio",
    "ai_generation",
    "execution_critical",
]

TASK_QUEUE_ROUTES: Dict[str, str] = {
    "backend.celery_task.market_task.fetch_market_data": "market_data",
    "backend.celery_task.market_task.fetch_market_data_7d": "market_data",
    "backend.celery_task.market_task.save_market_data_daily": "market_data",
    "backend.celery_task.market_task.calculate_and_save_forward_returns": "market_data",
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
    "backend.celery_task.global_intelligence_task.run_global_intelligence": "ai_generation",
    "backend.celery_task.global_ingestion_task.run_global_ingestion": "market_data",
    "backend.celery_task.asset_initialization.initialize_asset_data": "market_data",
    "backend.celery_task.btc_price_history_task.update_btc_history": "market_data",
    "backend.celery_task.onboarding_task.run_onboarding_pipeline": "ai_generation",
    "backend.celery_task.bootstrap_agents_task.bootstrap_agents_task": "ai_generation",
    "backend.celery_task.celery_task_generate_pdf.generate_report_pdf": "ai_generation",
    "backend.celery_task.daily_usage_reset.reset_daily_ai_quotas": "scoring",
}

WORKLOAD_CLASS_BY_QUEUE = {
    DEFAULT_QUEUE: "default_fallback",
    "market_data": "market_data",
    "scoring": "scoring",
    "portfolio": "portfolio",
    "ai_generation": "ai_generation",
    "execution_critical": "execution_critical",
}


def resolve_task_queue(task_name: str) -> str:
    return TASK_QUEUE_ROUTES.get(task_name, DEFAULT_QUEUE)


def resolve_workload_class(task_name: str) -> str:
    return WORKLOAD_CLASS_BY_QUEUE.get(resolve_task_queue(task_name), "default_fallback")


def celery_task_routes() -> Dict[str, Dict[str, str]]:
    return {task_name: {"queue": queue} for task_name, queue in TASK_QUEUE_ROUTES.items()}
