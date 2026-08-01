from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, Optional

from backend.utils.db import get_db_connection, jsonb_param


logger = logging.getLogger(__name__)


def persist_finn_product_event(event: Dict[str, Any], *, table_name: str) -> None:
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {table_name} (
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
    finally:
        conn.close()


def fetch_finn_product_analytics_snapshot(*, table_name: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            event_count = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                SELECT event_name, COUNT(*)::int
                FROM {table_name}
                GROUP BY event_name
                """
            )
            event_counts = {event_name: count for event_name, count in cur.fetchall()}

            cur.execute(
                f"""
                SELECT prompt_text, COUNT(*)::int AS count
                FROM {table_name}
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
                FROM {table_name}
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
                    FROM {table_name}
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
                FROM {table_name}
                """
            )
            opened, confirmed, canceled = cur.fetchone()

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
                FROM {table_name}
                """
            )
            sessions_seen, step_clicked, step_completed, completed, dashboard_activated = cur.fetchone()

            cur.execute(
                f"""
                SELECT
                    COUNT(DISTINCT session_id)::int,
                    COUNT(DISTINCT CASE WHEN event_name = 'finn_prompt_submitted' THEN session_id END)::int,
                    COUNT(DISTINCT CASE WHEN event_name IN ('finn_confirm_opened', 'finn_confirm_confirmed', 'finn_confirm_canceled') THEN session_id END)::int,
                    COUNT(DISTINCT CASE WHEN event_name = 'screen_view' AND page = '/report' THEN session_id END)::int,
                    COUNT(DISTINCT CASE WHEN event_name = 'screen_view' AND page = '/dashboard' THEN session_id END)::int
                FROM {table_name}
                WHERE session_id IS NOT NULL
                """
            )
            sessions_total, sessions_with_prompt, sessions_with_confirm, sessions_reaching_report, sessions_reaching_dashboard = cur.fetchone()

            cur.execute(
                f"""
                SELECT COALESCE(action_type, event_name) AS action, COUNT(*)::int AS count
                FROM {table_name}
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
                    COALESCE(SUM(CASE WHEN event_name = 'decision_review_used' OR flow_type = 'decision_review' THEN 1 ELSE 0 END), 0)::int,
                    COALESCE(SUM(CASE WHEN event_name = 'priority_engine_used' OR flow_type = 'priority_engine' THEN 1 ELSE 0 END), 0)::int,
                    COALESCE(SUM(CASE WHEN event_name = 'behavioral_intervention_seen' THEN 1 ELSE 0 END), 0)::int,
                    COALESCE(SUM(CASE WHEN event_name = 'behavioral_intervention_acknowledged' THEN 1 ELSE 0 END), 0)::int
                FROM {table_name}
                """
            )
            decision_review_usage_count, priority_engine_usage_count, behavioral_intervention_seen_count, behavioral_intervention_ack_count = cur.fetchone()

            cur.execute(
                f"""
                SELECT
                    COALESCE(metadata->>'behavior_flag', metadata->>'primary_flag', metadata->>'behavior_label') AS flag,
                    COUNT(*)::int AS count
                FROM {table_name}
                WHERE COALESCE(metadata->>'behavior_flag', metadata->>'primary_flag', metadata->>'behavior_label') IS NOT NULL
                GROUP BY flag
                ORDER BY count DESC, flag ASC
                LIMIT 8
                """
            )
            top_behavioral_flags = [{"flag": flag, "count": count} for flag, count in cur.fetchall()]

            cur.execute(
                f"""
                SELECT COALESCE(surface, page, 'unknown') AS surface, COUNT(*)::int AS count
                FROM {table_name}
                WHERE event_name IN ('behavioral_intervention_seen', 'behavioral_intervention_acknowledged')
                GROUP BY surface
                ORDER BY count DESC, surface ASC
                LIMIT 8
                """
            )
            top_behavioral_surfaces = [{"surface": surface, "count": count} for surface, count in cur.fetchall()]

            cur.execute(
                f"""
                SELECT COUNT(*)::int
                FROM (
                    SELECT user_id
                    FROM {table_name}
                    WHERE session_id IS NOT NULL
                    GROUP BY user_id
                    HAVING COUNT(DISTINCT session_id) > 1
                ) repeated_users
                """
            )
            repeated_users = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                SELECT COUNT(DISTINCT user_id)::int
                FROM {table_name}
                WHERE session_id IS NOT NULL
                """
            )
            users_seen = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                SELECT
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
                FROM {table_name}
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """
            )
            latest_events = []
            for row in cur.fetchall():
                latest_events.append(
                    {
                        "user_id": row[0],
                        "session_id": row[1],
                        "event_name": row[2],
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
                        "metadata": row[16] or {},
                        "timestamp": row[17].isoformat() + "Z" if row[17] else None,
                    }
                )

            return {
                "metrics_scope": "persistent_store",
                "event_count": event_count,
                "event_counts": event_counts,
                "top_prompts": top_prompts,
                "top_screens": top_screens,
                "top_first_screens": top_first_screens,
                "confirm_funnel": {"opened": opened, "confirmed": confirmed, "canceled": canceled},
                "onboarding_funnel": {
                    "sessions_seen": sessions_seen,
                    "step_clicked": step_clicked,
                    "step_completed": step_completed,
                    "completed": completed,
                    "dashboard_activated": dashboard_activated,
                },
                "first_session_summary": {
                    "sessions_seen": sessions_total,
                    "sessions_with_prompt": sessions_with_prompt,
                    "sessions_with_confirm": sessions_with_confirm,
                    "sessions_reaching_report": sessions_reaching_report,
                    "sessions_reaching_dashboard": sessions_reaching_dashboard,
                },
                "top_cta_actions": top_cta_actions,
                "decision_review_usage_count": decision_review_usage_count,
                "priority_engine_usage_count": priority_engine_usage_count,
                "behavioral_intervention_seen_count": behavioral_intervention_seen_count,
                "behavioral_intervention_ack_count": behavioral_intervention_ack_count,
                "top_behavioral_flags": top_behavioral_flags,
                "top_behavioral_surfaces": top_behavioral_surfaces,
                "repeated_user_signal": {
                    "users_seen": users_seen,
                    "users_with_multiple_sessions": repeated_users,
                },
                "latest_events": latest_events,
            }
    except Exception as exc:
        logger.warning("⚠️ Kon FINN product analytics snapshot niet ophalen: %s", exc)
        return None
    finally:
        conn.close()


def fetch_finn_response_trace(
    *,
    user_id: int,
    trace_id: str,
    table_name: str,
) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT metadata, created_at
                FROM {table_name}
                WHERE user_id = %s
                  AND trace_id = %s
                  AND event_name = 'finn_response_trace'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (int(user_id), str(trace_id)),
            )
            row = cur.fetchone()
            if row:
                metadata, created_at = row
                trace = deepcopy(metadata or {})
                if isinstance(trace, dict) and not trace.get("recorded_at") and created_at:
                    trace["recorded_at"] = created_at.isoformat() + "Z"
                return trace if isinstance(trace, dict) else None
    except Exception as exc:
        logger.warning("Kon FINN response trace niet ophalen: %s", exc)
    finally:
        conn.close()
    return None
