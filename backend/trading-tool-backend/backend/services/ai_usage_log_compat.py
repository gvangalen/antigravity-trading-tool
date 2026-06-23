from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


AI_USAGE_LOG_COLUMN_ORDER: Sequence[str] = (
    "user_id",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "cost",
    "purpose",
    "status",
    "response_time_ms",
    "estimated_cost_if_full",
    "similarity_score",
    "cache_age_seconds",
    "rejected_reason",
    "symbol",
    "trace_id",
    "completion_status",
    "parser_recovery_triggered",
    "confidence_score",
    "safety_guardrail_triggered",
    "request_source",
    "app_env",
    "run_kind",
    "entry_point",
    "user_email_snapshot",
)


def filter_ai_usage_log_values(
    values: Dict[str, Any],
    *,
    supported_columns: Optional[Iterable[str]] = None,
) -> Tuple[Sequence[str], Dict[str, Any]]:
    supported = set(supported_columns or AI_USAGE_LOG_COLUMN_ORDER)
    columns = [column for column in AI_USAGE_LOG_COLUMN_ORDER if column in supported and column in values]
    return columns, {column: values[column] for column in columns}
