from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, Optional


def _utc_now() -> datetime:
    return datetime.utcnow()


class FinnProductAnalyticsService:
    """Lean in-memory product analytics for early FINN product validation."""

    def __init__(self, *, max_events: int = 5000, screen_dedupe_seconds: int = 20) -> None:
        self.max_events = max_events
        self.screen_dedupe_seconds = screen_dedupe_seconds
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._screen_event_guard: Dict[str, datetime] = {}
        self._lock = threading.Lock()

    def _event_key(self, event: Dict[str, Any]) -> str:
        return "|".join(
            [
                str(event.get("user_id") or "anon"),
                str(event.get("session_id") or "no-session"),
                str(event.get("event_name") or "unknown"),
                str(event.get("surface") or "unknown"),
                str(event.get("page") or "unknown"),
                str(event.get("asset") or "none"),
            ]
        )

    def _normalize_prompt(self, prompt_text: Optional[str]) -> Optional[str]:
        if not prompt_text:
            return None
        compact = " ".join(str(prompt_text).strip().split())
        return compact[:240] if compact else None

    def record_event(self, *, user_id: int, event: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                timestamp = None
        if not isinstance(timestamp, datetime):
            timestamp = _utc_now()

        normalized = {
            "event_name": event.get("event_name") or "unknown",
            "user_id": int(user_id),
            "session_id": event.get("session_id"),
            "surface": event.get("surface") or "unknown",
            "page": event.get("page"),
            "asset": event.get("asset"),
            "flow_type": event.get("flow_type"),
            "action_type": event.get("action_type"),
            "report_type": event.get("report_type"),
            "decision_id": event.get("decision_id"),
            "bot_id": event.get("bot_id"),
            "setup_id": event.get("setup_id"),
            "strategy_id": event.get("strategy_id"),
            "trace_id": event.get("trace_id"),
            "prompt_text": self._normalize_prompt(event.get("prompt_text")),
            "next_best_action": event.get("next_best_action"),
            "metadata": deepcopy(event.get("metadata") or {}),
            "timestamp": timestamp,
        }

        key = self._event_key(normalized)
        with self._lock:
            if normalized["event_name"] == "screen_view":
                expires_at = self._screen_event_guard.get(key)
                now = _utc_now()
                if expires_at and expires_at > now:
                    return normalized
                self._screen_event_guard[key] = now + timedelta(seconds=self.screen_dedupe_seconds)

            self._events.append(normalized)

        return normalized

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            events = list(self._events)

        event_counts = Counter(event["event_name"] for event in events)
        prompt_counts = Counter(
            event["prompt_text"]
            for event in events
            if event["event_name"] == "finn_prompt_submitted" and event.get("prompt_text")
        )
        screen_counts = Counter(
            event["page"]
            for event in events
            if event["event_name"] == "screen_view" and event.get("page")
        )
        first_screen_per_session: Dict[str, str] = {}
        for event in events:
            if event["event_name"] != "screen_view" or not event.get("page") or not event.get("session_id"):
                continue
            session_id = str(event["session_id"])
            first_screen_per_session.setdefault(session_id, str(event["page"]))

        first_screen_counts = Counter(first_screen_per_session.values())

        onboarding_sessions = {
            str(event.get("session_id"))
            for event in events
            if event.get("session_id") and str(event.get("page") or "").startswith("/onboarding")
        }
        onboarding_funnel = {
            "sessions_seen": len(onboarding_sessions),
            "step_clicked": event_counts.get("onboarding_step_clicked", 0),
            "step_completed": event_counts.get("onboarding_step_completed", 0),
            "completed": event_counts.get("onboarding_completed", 0),
            "dashboard_activated": event_counts.get("onboarding_dashboard_activated", 0),
        }

        first_session_summary = {
            "sessions_seen": len(first_screen_per_session),
            "sessions_with_prompt": len(
                {
                    str(event["session_id"])
                    for event in events
                    if event["event_name"] == "finn_prompt_submitted" and event.get("session_id")
                }
            ),
            "sessions_with_confirm": len(
                {
                    str(event["session_id"])
                    for event in events
                    if event["event_name"] in {"finn_confirm_opened", "finn_confirm_confirmed", "finn_confirm_canceled"}
                    and event.get("session_id")
                }
            ),
            "sessions_reaching_report": len(
                {
                    str(event["session_id"])
                    for event in events
                    if event["event_name"] == "screen_view" and event.get("session_id") and str(event.get("page")) == "/report"
                }
            ),
            "sessions_reaching_dashboard": len(
                {
                    str(event["session_id"])
                    for event in events
                    if event["event_name"] == "screen_view" and event.get("session_id") and str(event.get("page")) == "/dashboard"
                }
            ),
        }

        cta_counts = Counter()
        for event in events:
            event_name = event["event_name"]
            if event_name in {
                "onboarding_step_clicked",
                "onboarding_dashboard_activated",
                "onboarding_complete_continue_clicked",
                "report_ask_finn_used",
                "finn_overlay_opened",
            }:
                label = event.get("action_type") or event_name
                cta_counts[str(label)] += 1

        confirm_funnel = {
            "opened": event_counts.get("finn_confirm_opened", 0),
            "confirmed": event_counts.get("finn_confirm_confirmed", 0),
            "canceled": event_counts.get("finn_confirm_canceled", 0),
        }

        repeated_user_sessions: Dict[int, set[str]] = defaultdict(set)
        for event in events:
            session_id = event.get("session_id")
            if session_id:
                repeated_user_sessions[int(event["user_id"])].add(str(session_id))

        repeated_users = sum(1 for sessions in repeated_user_sessions.values() if len(sessions) > 1)

        return {
            "metrics_scope": "process_lifetime",
            "event_count": len(events),
            "event_counts": dict(event_counts),
            "top_prompts": [
                {"prompt": prompt, "count": count}
                for prompt, count in prompt_counts.most_common(10)
            ],
            "top_screens": [
                {"page": page, "count": count}
                for page, count in screen_counts.most_common(10)
            ],
            "top_first_screens": [
                {"page": page, "count": count}
                for page, count in first_screen_counts.most_common(10)
            ],
            "confirm_funnel": confirm_funnel,
            "onboarding_funnel": onboarding_funnel,
            "first_session_summary": first_session_summary,
            "top_cta_actions": [
                {"action": action, "count": count}
                for action, count in cta_counts.most_common(10)
            ],
            "decision_review_usage_count": sum(
                1
                for event in events
                if event["event_name"] == "decision_review_used" or event.get("flow_type") == "decision_review"
            ),
            "priority_engine_usage_count": sum(
                1
                for event in events
                if event["event_name"] == "priority_engine_used" or event.get("flow_type") == "priority_engine"
            ),
            "repeated_user_signal": {
                "users_seen": len(repeated_user_sessions),
                "users_with_multiple_sessions": repeated_users,
            },
            "latest_events": [
                {
                    **{k: v for k, v in event.items() if k != "timestamp"},
                    "timestamp": event["timestamp"].isoformat() + "Z",
                }
                for event in events[-20:]
            ],
        }


finn_product_analytics = FinnProductAnalyticsService()
