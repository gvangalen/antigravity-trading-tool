from __future__ import annotations

import logging
import threading
from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional

from backend.utils.db import get_db_connection, jsonb_param


logger = logging.getLogger(__name__)
PERSISTED_EVENTS_TABLE = "finn_product_events"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FinnProductAnalyticsService:
    """Lean FINN product analytics with persistent storage for operator review."""

    def __init__(self, *, max_events: int = 5000, screen_dedupe_seconds: int = 20) -> None:
        self.max_events = max_events
        self.screen_dedupe_seconds = screen_dedupe_seconds
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._screen_event_guard: Dict[str, datetime] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _serialize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **{k: v for k, v in event.items() if k != "timestamp"},
            "timestamp": event["timestamp"].isoformat() + "Z",
        }

    def _persist_event(self, event: Dict[str, Any]) -> None:
        conn = get_db_connection()
        if conn is None:
            return
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {PERSISTED_EVENTS_TABLE} (
                            user_id,
                            session_id,
                            event_name,
                            surface,
                            page,
                            asset,
                            flow_type,
                            action_type,
                            report_type,
                            decision_id,
                            bot_id,
                            setup_id,
                            strategy_id,
                            trace_id,
                            prompt_text,
                            next_best_action,
                            metadata,
                            created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            event["user_id"],
                            event.get("session_id"),
                            event.get("event_name"),
                            event.get("surface"),
                            event.get("page"),
                            event.get("asset"),
                            event.get("flow_type"),
                            event.get("action_type"),
                            event.get("report_type"),
                            event.get("decision_id"),
                            event.get("bot_id"),
                            event.get("setup_id"),
                            event.get("strategy_id"),
                            event.get("trace_id"),
                            event.get("prompt_text"),
                            event.get("next_best_action"),
                            jsonb_param(event.get("metadata") or {}),
                            event["timestamp"],
                        ),
                    )
        except Exception as exc:
            logger.warning("⚠️ Kon FINN product event niet persisteren: %s", exc)
        finally:
            conn.close()

    def _memory_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            events = list(self._events)

        event_counts = Counter(event["event_name"] for event in events)
        behavioral_flag_counts = Counter()
        behavioral_surface_counts = Counter()
        for event in events:
            metadata = event.get("metadata") or {}
            behavior_flag = (
                metadata.get("behavior_flag")
                or metadata.get("primary_flag")
                or metadata.get("behavior_label")
            )
            if behavior_flag:
                behavioral_flag_counts[str(behavior_flag)] += 1
            if event.get("event_name") in {"behavioral_intervention_seen", "behavioral_intervention_acknowledged"}:
                behavioral_surface_counts[str(event.get("surface") or event.get("page") or "unknown")] += 1
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
            "behavioral_intervention_seen_count": event_counts.get("behavioral_intervention_seen", 0),
            "behavioral_intervention_ack_count": event_counts.get("behavioral_intervention_acknowledged", 0),
            "top_behavioral_flags": [
                {"flag": flag, "count": count}
                for flag, count in behavioral_flag_counts.most_common(8)
            ],
            "top_behavioral_surfaces": [
                {"surface": surface, "count": count}
                for surface, count in behavioral_surface_counts.most_common(8)
            ],
            "repeated_user_signal": {
                "users_seen": len(repeated_user_sessions),
                "users_with_multiple_sessions": repeated_users,
            },
            "latest_events": [self._serialize_event(event) for event in events[-20:]],
        }

    def _persistent_snapshot(self) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        if conn is None:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {PERSISTED_EVENTS_TABLE}")
                event_count = int(cur.fetchone()[0] or 0)

                cur.execute(
                    f"""
                    SELECT event_name, COUNT(*)::int
                    FROM {PERSISTED_EVENTS_TABLE}
                    GROUP BY event_name
                    """
                )
                event_counts = {event_name: count for event_name, count in cur.fetchall()}

                cur.execute(
                    f"""
                    SELECT prompt_text, COUNT(*)::int AS count
                    FROM {PERSISTED_EVENTS_TABLE}
                    WHERE event_name = 'finn_prompt_submitted' AND prompt_text IS NOT NULL
                    GROUP BY prompt_text
                    ORDER BY count DESC, prompt_text ASC
                    LIMIT 10
                    """
                )
                top_prompts = [{"prompt": prompt, "count": count} for prompt, count in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT page, COUNT(*)::int AS count
                    FROM {PERSISTED_EVENTS_TABLE}
                    WHERE event_name = 'screen_view' AND page IS NOT NULL
                    GROUP BY page
                    ORDER BY count DESC, page ASC
                    LIMIT 10
                    """
                )
                top_screens = [{"page": page, "count": count} for page, count in cur.fetchall()]

                cur.execute(
                    f"""
                    WITH first_screen_per_session AS (
                        SELECT DISTINCT ON (session_id)
                            session_id,
                            page,
                            created_at
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name = 'screen_view'
                          AND session_id IS NOT NULL
                          AND page IS NOT NULL
                        ORDER BY session_id, created_at ASC, id ASC
                    )
                    SELECT page, COUNT(*)::int AS count
                    FROM first_screen_per_session
                    GROUP BY page
                    ORDER BY count DESC, page ASC
                    LIMIT 10
                    """
                )
                top_first_screens = [{"page": page, "count": count} for page, count in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN event_name = 'finn_confirm_opened' THEN 1 ELSE 0 END), 0)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'finn_confirm_confirmed' THEN 1 ELSE 0 END), 0)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'finn_confirm_canceled' THEN 1 ELSE 0 END), 0)::int
                    FROM {PERSISTED_EVENTS_TABLE}
                    """
                )
                opened, confirmed, canceled = cur.fetchone()
                confirm_funnel = {
                    "opened": opened,
                    "confirmed": confirmed,
                    "canceled": canceled,
                }

                cur.execute(
                    f"""
                    SELECT
                        COUNT(DISTINCT CASE
                            WHEN session_id IS NOT NULL AND page LIKE '/onboarding%%' THEN session_id
                            ELSE NULL
                        END)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'onboarding_step_clicked' THEN 1 ELSE 0 END), 0)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'onboarding_step_completed' THEN 1 ELSE 0 END), 0)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'onboarding_completed' THEN 1 ELSE 0 END), 0)::int,
                        COALESCE(SUM(CASE WHEN event_name = 'onboarding_dashboard_activated' THEN 1 ELSE 0 END), 0)::int
                    FROM {PERSISTED_EVENTS_TABLE}
                    """
                )
                sessions_seen, step_clicked, step_completed, completed, dashboard_activated = cur.fetchone()
                onboarding_funnel = {
                    "sessions_seen": sessions_seen,
                    "step_clicked": step_clicked,
                    "step_completed": step_completed,
                    "completed": completed,
                    "dashboard_activated": dashboard_activated,
                }

                cur.execute(
                    f"""
                    WITH screen_sessions AS (
                        SELECT DISTINCT session_id
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name = 'screen_view' AND session_id IS NOT NULL
                    ),
                    prompt_sessions AS (
                        SELECT DISTINCT session_id
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name = 'finn_prompt_submitted' AND session_id IS NOT NULL
                    ),
                    confirm_sessions AS (
                        SELECT DISTINCT session_id
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name IN ('finn_confirm_opened', 'finn_confirm_confirmed', 'finn_confirm_canceled')
                          AND session_id IS NOT NULL
                    ),
                    report_sessions AS (
                        SELECT DISTINCT session_id
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name = 'screen_view' AND page = '/report' AND session_id IS NOT NULL
                    ),
                    dashboard_sessions AS (
                        SELECT DISTINCT session_id
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE event_name = 'screen_view' AND page = '/dashboard' AND session_id IS NOT NULL
                    )
                    SELECT
                        (SELECT COUNT(*)::int FROM screen_sessions),
                        (SELECT COUNT(*)::int FROM prompt_sessions),
                        (SELECT COUNT(*)::int FROM confirm_sessions),
                        (SELECT COUNT(*)::int FROM report_sessions),
                        (SELECT COUNT(*)::int FROM dashboard_sessions)
                    """
                )
                sessions_seen, sessions_with_prompt, sessions_with_confirm, sessions_reaching_report, sessions_reaching_dashboard = cur.fetchone()
                first_session_summary = {
                    "sessions_seen": sessions_seen,
                    "sessions_with_prompt": sessions_with_prompt,
                    "sessions_with_confirm": sessions_with_confirm,
                    "sessions_reaching_report": sessions_reaching_report,
                    "sessions_reaching_dashboard": sessions_reaching_dashboard,
                }

                cur.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(action_type, ''), event_name) AS action,
                        COUNT(*)::int AS count
                    FROM {PERSISTED_EVENTS_TABLE}
                    WHERE event_name IN (
                        'onboarding_step_clicked',
                        'onboarding_dashboard_activated',
                        'onboarding_complete_continue_clicked',
                        'report_ask_finn_used',
                        'finn_overlay_opened'
                    )
                    GROUP BY action
                    ORDER BY count DESC, action ASC
                    LIMIT 10
                    """
                )
                top_cta_actions = [{"action": action, "count": count} for action, count in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE event_name = 'decision_review_used' OR flow_type = 'decision_review'
                        )::int,
                        COUNT(*) FILTER (
                            WHERE event_name = 'priority_engine_used' OR flow_type = 'priority_engine'
                        )::int,
                        COUNT(*) FILTER (
                            WHERE event_name = 'behavioral_intervention_seen'
                        )::int,
                        COUNT(*) FILTER (
                            WHERE event_name = 'behavioral_intervention_acknowledged'
                        )::int
                    FROM {PERSISTED_EVENTS_TABLE}
                    """
                )
                (
                    decision_review_usage_count,
                    priority_engine_usage_count,
                    behavioral_intervention_seen_count,
                    behavioral_intervention_ack_count,
                ) = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(metadata->>'behavior_flag', ''), NULLIF(metadata->>'primary_flag', ''), NULLIF(metadata->>'behavior_label', '')) AS flag,
                        COUNT(*)::int AS count
                    FROM {PERSISTED_EVENTS_TABLE}
                    WHERE COALESCE(NULLIF(metadata->>'behavior_flag', ''), NULLIF(metadata->>'primary_flag', ''), NULLIF(metadata->>'behavior_label', '')) IS NOT NULL
                    GROUP BY flag
                    ORDER BY count DESC, flag ASC
                    LIMIT 8
                    """
                )
                top_behavioral_flags = [{"flag": flag, "count": count} for flag, count in cur.fetchall()]

                cur.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(surface, ''), NULLIF(page, ''), 'unknown') AS surface_name,
                        COUNT(*)::int AS count
                    FROM {PERSISTED_EVENTS_TABLE}
                    WHERE event_name IN ('behavioral_intervention_seen', 'behavioral_intervention_acknowledged')
                    GROUP BY surface_name
                    ORDER BY count DESC, surface_name ASC
                    LIMIT 8
                    """
                )
                top_behavioral_surfaces = [{"surface": surface, "count": count} for surface, count in cur.fetchall()]

                cur.execute(
                    f"""
                    WITH user_sessions AS (
                        SELECT user_id, COUNT(DISTINCT session_id)::int AS session_count
                        FROM {PERSISTED_EVENTS_TABLE}
                        WHERE session_id IS NOT NULL
                        GROUP BY user_id
                    )
                    SELECT
                        COUNT(*)::int,
                        COUNT(*) FILTER (WHERE session_count > 1)::int
                    FROM user_sessions
                    """
                )
                users_seen, users_with_multiple_sessions = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT
                        event_name,
                        user_id,
                        session_id,
                        surface,
                        page,
                        asset,
                        flow_type,
                        action_type,
                        report_type,
                        decision_id,
                        bot_id,
                        setup_id,
                        strategy_id,
                        trace_id,
                        prompt_text,
                        next_best_action,
                        metadata,
                        created_at
                    FROM {PERSISTED_EVENTS_TABLE}
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                    """
                )
                latest_events_rows = cur.fetchall()

        except Exception as exc:
            logger.warning("⚠️ Kon persistente FINN telemetry snapshot niet laden: %s", exc)
            return None
        finally:
            conn.close()

        latest_events = [
            {
                "event_name": row[0],
                "user_id": row[1],
                "session_id": row[2],
                "surface": row[3],
                "page": row[4],
                "asset": row[5],
                "flow_type": row[6],
                "action_type": row[7],
                "report_type": row[8],
                "decision_id": row[9],
                "bot_id": row[10],
                "setup_id": row[11],
                "strategy_id": row[12],
                "trace_id": row[13],
                "prompt_text": row[14],
                "next_best_action": row[15],
                "metadata": deepcopy(row[16] or {}),
                "timestamp": row[17].isoformat() + "Z" if row[17] else None,
            }
            for row in latest_events_rows
        ]

        latest_events.reverse()

        return {
            "metrics_scope": "persistent_store",
            "event_count": event_count,
            "event_counts": event_counts,
            "top_prompts": top_prompts,
            "top_screens": top_screens,
            "top_first_screens": top_first_screens,
            "confirm_funnel": confirm_funnel,
            "onboarding_funnel": onboarding_funnel,
            "first_session_summary": first_session_summary,
            "top_cta_actions": top_cta_actions,
            "decision_review_usage_count": decision_review_usage_count,
            "priority_engine_usage_count": priority_engine_usage_count,
            "behavioral_intervention_seen_count": behavioral_intervention_seen_count,
            "behavioral_intervention_ack_count": behavioral_intervention_ack_count,
            "top_behavioral_flags": top_behavioral_flags,
            "top_behavioral_surfaces": top_behavioral_surfaces,
            "repeated_user_signal": {
                "users_seen": users_seen,
                "users_with_multiple_sessions": users_with_multiple_sessions,
            },
            "latest_events": latest_events,
        }

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

        self._persist_event(normalized)
        return normalized

    def snapshot(self) -> Dict[str, Any]:
        return self._persistent_snapshot() or self._memory_snapshot()


finn_product_analytics = FinnProductAnalyticsService()
