"""Read-only, bounded audit of one prior protected trader QA namespace."""

from __future__ import annotations

import re
import json
from pathlib import Path

from backend.scripts import probe_protected_score2_stale_paper as fixture


LABEL = re.compile(r"audit-([1-9][0-9]{5,15})-([1-9][0-9]*)-([0-9a-f]{8})\Z")
PAIR_CLEANUP_LABELS = frozenset({
    "audit-42543306392-1-20322165",
    "audit-42546922438-1-169d0252",
    "audit-42549516935-1-1d8c6a3a",
    "audit-42551140172-1-43009b2a",
    "audit-42552626218-1-a30e0117",
    "audit-42556709762-1-30a20e36",
    "audit-42559343113-1-dcc45900",
    "audit-42561696534-1-7d0267d1",
})


def _verify_prior_report(workflow_id: str, attempt: str, sha_prefix: str,
                         expected_profile: str = "trader_paper_exit_reconciliation") -> None:
    run_id = f"{workflow_id}-{attempt}"
    report = Path("/tmp") / f"finn-production-qa-{run_id}" / f"finn-production-qa-{run_id}.json"
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("trader_fixture_audit_prior_report_unavailable") from None
    if (data.get("workflow_run_id") != run_id
            or data.get("profile") != expected_profile
            or not str(data.get("target_sha", "")).startswith(sha_prefix)
            or data.get("protected_profile_attempted") is not True
            or data.get("outcome") not in {"failed", "incomplete"}):
        raise RuntimeError("trader_fixture_audit_prior_report_mismatch")


def run(label: str, *, expected_profile: str = "trader_paper_exit_reconciliation") -> dict:
    if expected_profile not in {"trader_paper_exit_reconciliation", "trader_pair_score_continuity"}:
        raise RuntimeError("trader_fixture_audit_profile_invalid")
    match = LABEL.fullmatch(label)
    if not match:
        raise RuntimeError("trader_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = match.groups()
    _verify_prior_report(workflow_id, attempt, sha_prefix, expected_profile)
    namespace_prefix = f"qa-{workflow_id}-{attempt}-{sha_prefix}-"
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, is_active, ai_preferences FROM users
                   WHERE ai_preferences->>'qa_fixture'=%s
                     AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            owners = cur.fetchall()
            if not owners:
                return {"fixture_state": "NO_RETAINED_FIXTURE",
                        "cleanup_verified": False, "stage": "BEFORE_SEED_OR_CLEANED"}
            if len(owners) != 1:
                return {"fixture_state": "AMBIGUOUS", "cleanup_verified": False}
            user_id, owner_active, preferences = owners[0]
            namespace = (preferences or {}).get("qa_namespace", "")
            if not fixture.NAMESPACE_PATTERN.fullmatch(namespace) or not namespace.startswith(namespace_prefix):
                raise RuntimeError("trader_fixture_audit_scope_invalid")
            cur.execute("SELECT is_active,is_live FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = int(cur.fetchone()[0])
            unsafe = bool(owner_active or keys or any(active or live for active, live in bots))
            if expected_profile == "trader_pair_score_continuity":
                present = {}
                for table in ("user_indicator_configs", "market_data_indicators",
                              "technical_indicators", "daily_scores", "bot_orders",
                              "bot_executions"):
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                    present[table] = bool(cur.fetchone()[0])
                return {
                    "fixture_state": "UNSAFE_ACTIVE" if unsafe else "QUARANTINED_INACTIVE",
                    "cleanup_verified": False,
                    "pair_configs_present": present["user_indicator_configs"],
                    "pair_market_readings_present": present["market_data_indicators"],
                    "pair_technical_readings_present": present["technical_indicators"],
                    "pair_scores_present": present["daily_scores"],
                    "orders_present": present["bot_orders"],
                    "executions_present": present["bot_executions"],
                }
            cur.execute(
                """SELECT decision_kind,COUNT(*) FROM bot_decisions
                   WHERE user_id=%s GROUP BY decision_kind""", (user_id,),
            )
            decisions = dict(cur.fetchall())
            cur.execute(
                """SELECT COUNT(*) FROM bot_orders o JOIN bot_decisions d
                   ON d.id=o.decision_id AND d.user_id=o.user_id
                   WHERE o.user_id=%s AND d.decision_kind='paper_exit'""", (user_id,),
            )
            exit_orders = int(cur.fetchone()[0])
            cur.execute(
                """SELECT COUNT(*) FROM bot_executions e JOIN bot_orders o
                   ON o.id=e.bot_order_id AND o.user_id=e.user_id
                   JOIN bot_decisions d ON d.id=o.decision_id AND d.user_id=o.user_id
                   WHERE e.user_id=%s AND d.decision_kind='paper_exit'""", (user_id,),
            )
            exit_executions = int(cur.fetchone()[0])
            cur.execute(
                """SELECT COUNT(*) FROM bot_ledger l JOIN bot_decisions d
                   ON d.id=l.decision_id AND d.user_id=l.user_id
                   WHERE l.user_id=%s AND d.decision_kind='paper_exit'""", (user_id,),
            )
            exit_ledger = int(cur.fetchone()[0])
            return {
                "fixture_state": "UNSAFE_ACTIVE" if unsafe else "QUARANTINED_INACTIVE",
                "cleanup_verified": False,
                "paper_open_present": bool(decisions.get("assessment")),
                "paper_exit_decision_present": bool(decisions.get("paper_exit")),
                "paper_exit_order_present": bool(exit_orders),
                "paper_exit_execution_present": bool(exit_executions),
                "paper_exit_ledger_present": bool(exit_ledger),
            }
    finally:
        conn.close()


def cleanup_pair(label: str) -> dict:
    """Delete only a verified inactive, uncredentialed prior Gate3 child."""
    if label not in PAIR_CLEANUP_LABELS:
        raise RuntimeError("trader_pair_cleanup_label_not_allowed")
    match = LABEL.fullmatch(label)
    if not match:
        raise RuntimeError("trader_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = match.groups()
    _verify_prior_report(workflow_id, attempt, sha_prefix, "trader_pair_score_continuity")
    namespace_prefix = f"qa-{workflow_id}-{attempt}-{sha_prefix}-"
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,ai_preferences FROM users
                   WHERE ai_preferences->>'qa_fixture'=%s
                     AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            owners = cur.fetchall()
            if not owners:
                return {"fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": False}
            if len(owners) != 1:
                raise RuntimeError("trader_pair_cleanup_scope_ambiguous")
            user_id, preferences = owners[0]
            namespace = (preferences or {}).get("qa_namespace", "")
            if (not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
                    or not namespace.startswith(namespace_prefix)):
                raise RuntimeError("trader_pair_cleanup_owner_unsafe")
            cur.execute("SELECT id,is_active,is_live FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cur.fetchall()
            if len(bots) != 1:
                raise RuntimeError("trader_pair_cleanup_bot_unsafe")
            bot_id = bots[0][0]
    finally:
        conn.close()
    try:
        fixture._cleanup(namespace, user_id, bot_id, require_safe_pair_cleanup=True)
    except Exception:
        raise RuntimeError("trader_pair_cleanup_failed") from None
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM users WHERE ai_preferences->>'qa_fixture'=%s
                   AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            if cur.fetchone()[0]:
                raise RuntimeError("trader_pair_cleanup_postcondition_failed")
            for table in ("user_indicator_configs", "market_data_indicators",
                          "technical_indicators", "daily_scores", "bot_configs",
                          "bot_decisions", "bot_orders", "bot_executions", "bot_ledger"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cur.fetchone()[0]:
                    raise RuntimeError("trader_pair_cleanup_postcondition_failed")
    finally:
        conn.close()
    return {"fixture_state": "CLEANED", "cleanup_verified": True}
