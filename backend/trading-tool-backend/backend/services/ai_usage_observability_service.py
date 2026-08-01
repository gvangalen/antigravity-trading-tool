from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

from backend.infrastructure.repositories.ai_usage_log_sync_repository import (
    fetch_average_estimated_cost,
    fetch_supported_ai_usage_log_columns,
    fetch_user_email_snapshot,
    insert_ai_usage_log_row,
)
from backend.services.ai_usage_log_compat import AI_USAGE_LOG_COLUMN_ORDER, filter_ai_usage_log_values
from backend.utils.ai_cost_calculator import calculate_cost


logger = logging.getLogger(__name__)

_usage_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("ai_usage_context", default=None)
_supported_ai_usage_log_columns_sync: Optional[set[str]] = None

QA_EMAIL_HINTS = (
    "qa",
    "codex",
    "telemetry.",
    "staging.operator",
    "example.com",
)

DEFAULT_COST_TOKEN_BUDGETS = {
    "daily_report_generation": (2200, 900),
    "weekly_report_generation": (2600, 1100),
    "monthly_report_generation": (3000, 1300),
    "quarterly_report_generation": (3400, 1500),
    "daily_report_preview": (1800, 700),
    "finn_report_generation": (2200, 900),
    "decision_review": (1400, 500),
    "priority_engine": (1100, 400),
    "general_help": (750, 250),
    "chat_general": (1200, 450),
    "chat_analysis": (1500, 550),
    "chat_chat": (1100, 450),
    "setup_analysis": (1200, 350),
    "strategy_snapshot_analysis": (1600, 550),
    "master_score_generation": (2200, 750),
    "market_analysis": (1500, 500),
}


def get_app_env() -> str:
    return str(os.getenv("APP_ENV", "unknown") or "unknown").strip().lower()


def classify_request_source(
    *,
    user_email: Optional[str] = None,
    app_env: Optional[str] = None,
    source_hint: Optional[str] = None,
    run_kind: Optional[str] = None,
) -> str:
    if source_hint:
        return str(source_hint)

    env = str(app_env or get_app_env()).lower()
    email = (user_email or "").strip().lower()

    if run_kind == "scheduled":
        return "background_job"
    if not email:
        return "system"
    if any(hint in email for hint in QA_EMAIL_HINTS):
        return "qa_user"
    if env == "staging":
        return "staging_user"
    return "live_user"


def infer_entry_point(*, purpose: Optional[str], run_kind: Optional[str]) -> Optional[str]:
    purpose_value = str(purpose or "").strip().lower()
    if not purpose_value:
        return "scheduled_job" if run_kind == "scheduled" else None

    if purpose_value.endswith("_report_generation"):
        report_family = purpose_value.replace("_generation", "")
        return f"{report_family}_task"
    if purpose_value == "daily_report_preview":
        return "report_service:daily_preview"
    if purpose_value.startswith("chat_"):
        return f"assistant_service:{purpose_value.replace('chat_', '', 1)}"
    if purpose_value in {"decision_review", "priority_engine", "plan_adherence_review"}:
        return f"assistant_service:{purpose_value}"
    if run_kind == "scheduled":
        return "scheduled_job"
    return None


def estimate_blocked_cost(
    *,
    model: str,
    purpose: Optional[str],
    entry_point: Optional[str],
) -> float:
    historical = fetch_average_estimated_cost(
        model=model,
        purpose=purpose,
        entry_point=entry_point,
    )
    if historical is not None:
        return historical

    prompt_tokens, completion_tokens = DEFAULT_COST_TOKEN_BUDGETS.get(
        str(purpose or "").strip().lower(),
        (900, 300),
    )
    return calculate_cost(model, prompt_tokens, completion_tokens)


@contextmanager
def ai_usage_context(**kwargs: Any) -> Iterator[None]:
    existing = _usage_context.get() or {}
    merged = dict(existing)
    merged.update({key: value for key, value in kwargs.items() if value is not None})
    token = _usage_context.set(merged)
    try:
        yield
    finally:
        _usage_context.reset(token)


def get_ai_usage_context() -> Optional[Dict[str, Any]]:
    return _usage_context.get()


def log_ai_usage_sync(
    *,
    user_id: Optional[int],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float,
    purpose: str,
    status: str,
    response_time_ms: int = 0,
    estimated_cost_if_full: Optional[float] = None,
    similarity_score: Optional[float] = None,
    cache_age_seconds: Optional[int] = None,
    rejected_reason: Optional[str] = None,
    symbol: str = "GLOBAL",
    trace_id: Optional[str] = None,
    completion_status: str = "success",
    parser_recovery_triggered: bool = False,
    confidence_score: Optional[float] = None,
    safety_guardrail_triggered: bool = False,
    request_source: Optional[str] = None,
    app_env: Optional[str] = None,
    run_kind: Optional[str] = None,
    entry_point: Optional[str] = None,
    user_email_snapshot: Optional[str] = None,
) -> None:
    global _supported_ai_usage_log_columns_sync
    if _supported_ai_usage_log_columns_sync is None:
        _supported_ai_usage_log_columns_sync = (
            fetch_supported_ai_usage_log_columns() or set(AI_USAGE_LOG_COLUMN_ORDER)
        )
    values = {
        "user_id": user_id,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost": cost,
        "purpose": purpose,
        "status": status,
        "response_time_ms": response_time_ms,
        "estimated_cost_if_full": estimated_cost_if_full if estimated_cost_if_full is not None else cost,
        "similarity_score": similarity_score,
        "cache_age_seconds": cache_age_seconds,
        "rejected_reason": rejected_reason,
        "symbol": symbol,
        "trace_id": trace_id,
        "completion_status": completion_status,
        "parser_recovery_triggered": parser_recovery_triggered,
        "confidence_score": confidence_score,
        "safety_guardrail_triggered": safety_guardrail_triggered,
        "request_source": request_source or "unclassified",
        "app_env": app_env or get_app_env(),
        "run_kind": run_kind,
        "entry_point": entry_point,
        "user_email_snapshot": user_email_snapshot,
    }
    columns, params = filter_ai_usage_log_values(
        values,
        supported_columns=_supported_ai_usage_log_columns_sync,
    )
    insert_ai_usage_log_row(columns=columns, values=params)


def log_background_ai_skip(
    *,
    user_id: int,
    symbol: str,
    purpose: str,
    entry_point: str,
    reason: str = "input_unchanged",
) -> None:
    """Record a zero-cost reuse decision alongside normal AI usage rows."""
    log_ai_usage_sync(
        user_id=user_id,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
        purpose=purpose,
        status="input_unchanged",
        estimated_cost_if_full=estimate_blocked_cost(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            purpose=purpose,
            entry_point=entry_point,
        ),
        rejected_reason=reason,
        symbol=symbol,
        completion_status="skipped",
        request_source="background_job",
        app_env=get_app_env(),
        run_kind="scheduled",
        entry_point=entry_point,
        user_email_snapshot=get_user_email_snapshot(user_id),
    )


def get_user_email_snapshot(user_id: Optional[int]) -> Optional[str]:
    return fetch_user_email_snapshot(user_id)


def log_openai_usage_from_context(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    response_time_ms: int,
    status: str = "full_ai",
    rejected_reason: Optional[str] = None,
) -> None:
    context = get_ai_usage_context()
    if not context:
        return

    cost = calculate_cost(model, prompt_tokens, completion_tokens)
    app_env = context.get("app_env") or get_app_env()
    user_email = context.get("user_email")
    run_kind = context.get("run_kind")
    request_source = classify_request_source(
        user_email=user_email,
        app_env=app_env,
        source_hint=context.get("request_source"),
        run_kind=run_kind,
    )

    log_ai_usage_sync(
        user_id=context.get("user_id"),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
        purpose=str(context.get("purpose") or "unscoped_openai_call"),
        status=status,
        response_time_ms=response_time_ms,
        estimated_cost_if_full=cost,
        rejected_reason=rejected_reason,
        symbol=str(context.get("symbol") or "GLOBAL"),
        trace_id=context.get("trace_id"),
        completion_status=str(context.get("completion_status") or "success"),
        request_source=request_source,
        app_env=app_env,
        run_kind=run_kind,
        entry_point=context.get("entry_point"),
        user_email_snapshot=user_email,
    )


def log_openai_quota_skip_from_context(
    *,
    status: str = "quota_blocked",
    rejected_reason: str = "insufficient_quota",
) -> None:
    context = get_ai_usage_context()
    if not context:
        return

    app_env = context.get("app_env") or get_app_env()
    user_email = context.get("user_email")
    run_kind = context.get("run_kind")
    request_source = classify_request_source(
        user_email=user_email,
        app_env=app_env,
        source_hint=context.get("request_source"),
        run_kind=run_kind,
    )

    purpose = str(context.get("purpose") or "unscoped_openai_call")
    model = str(context.get("model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    entry_point = context.get("entry_point") or infer_entry_point(purpose=purpose, run_kind=run_kind)
    estimated_cost = estimate_blocked_cost(
        model=model,
        purpose=purpose,
        entry_point=entry_point,
    )

    log_ai_usage_sync(
        user_id=context.get("user_id"),
        model=model,
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
        purpose=purpose,
        status=status,
        response_time_ms=0,
        estimated_cost_if_full=estimated_cost,
        rejected_reason=rejected_reason,
        symbol=str(context.get("symbol") or "GLOBAL"),
        trace_id=context.get("trace_id"),
        completion_status=status,
        request_source=request_source,
        app_env=app_env,
        run_kind=run_kind,
        entry_point=entry_point,
        user_email_snapshot=user_email,
    )


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
