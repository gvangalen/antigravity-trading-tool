"""Privacy-safe projection for operator product telemetry."""

from typing import Any


_FUNNELS = {
    "confirm_funnel": ("opened", "confirmed", "canceled"),
    "onboarding_funnel": ("sessions_seen", "step_clicked", "step_completed", "completed", "dashboard_activated"),
    "first_session_summary": (
        "sessions_seen", "sessions_with_prompt", "sessions_with_confirm",
        "sessions_reaching_report", "sessions_reaching_dashboard",
    ),
    "repeated_user_signal": ("users_seen", "users_with_multiple_sessions"),
}
_COUNTS = (
    "event_count", "decision_review_usage_count", "priority_engine_usage_count",
    "behavioral_intervention_seen_count", "behavioral_intervention_ack_count",
)
_PAGES = {
    "/onboarding", "/dashboard", "/report", "/portfolio", "/asset",
    "/market", "/macro", "/technical", "/setup", "/strategy", "/bot",
}
_ACTIONS = {
    "onboarding_step_clicked", "onboarding_dashboard_activated",
    "onboarding_complete_continue_clicked", "report_ask_finn_used",
    "finn_overlay_opened", "market", "macro", "technical", "setup",
    "strategy", "bot", "activate_dashboard",
}


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def admin_analytics_snapshot(snapshot: dict) -> dict:
    """Return aggregate numbers only, even when stored events contain user text."""
    result = {
        "metrics_scope": "persistent_store" if snapshot.get("metrics_scope") == "persistent_store" else "process_lifetime",
        "privacy_sanitized": True,
    }
    for key in _COUNTS:
        result[key] = _count(snapshot.get(key))
    for key, fields in _FUNNELS.items():
        source = snapshot.get(key) or {}
        result[key] = {field: _count(source.get(field)) for field in fields}
    for key in ("top_screens", "top_first_screens"):
        result[key] = [
            {"page": row["page"], "count": _count(row.get("count"))}
            for row in snapshot.get(key, [])
            if isinstance(row, dict) and row.get("page") in _PAGES
        ]
    result["top_cta_actions"] = [
        {"action": row["action"], "count": _count(row.get("count"))}
        for row in snapshot.get("top_cta_actions", [])
        if isinstance(row, dict) and row.get("action") in _ACTIONS
    ]
    return result
