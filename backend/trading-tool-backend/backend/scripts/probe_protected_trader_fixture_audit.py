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
    "audit-42564612181-1-d62ddf23",
    "audit-42567582048-1-376d3a95",
    "audit-42662037346-1-b2cc1d3b",
    "audit-42665642208-1-3c0ce3f4",
    "audit-42668760580-1-e20b92fb",
})
JOURNEY_CLEANUP_LABEL = "audit-44968391213-1-e2872eb9"
JOURNEY_EXECUTION_CODES = frozenset({
    "proposal_not_confirmed", "proposal_expired", "proposal_payload_hash_mismatch",
    "proposal_evidence_hash_mismatch", "step_up_required", "kill_switch_enabled",
    "feature_disabled", "setup_action_disabled", "strategy_action_disabled",
    "live_action_disabled", "shadow_mode_execution_blocked",
})


def _journey_execution_status(cur, user_id: int) -> dict:
    cur.execute(
        """SELECT operation_type,status,error_codes_json FROM finn_v2_executions
           WHERE user_id=%s""", (user_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {"setup_execution_status": "missing", "setup_execution_codes": [],
                "replay_status": "not_recorded"}
    if len(rows) != 1 or rows[0][0] != "create_setup":
        return {"setup_execution_status": "multiple_or_other", "setup_execution_codes": [],
                "replay_status": "not_recorded"}
    _, status, raw_codes = rows[0]
    codes = raw_codes if isinstance(raw_codes, list) else []
    return {
        "setup_execution_status": status if status in {
            "started", "blocked", "succeeded", "failed",
        } else "other",
        "setup_execution_codes": sorted({
            code if isinstance(code, str) and code in JOURNEY_EXECUTION_CODES else "other"
            for code in codes[:8]
        }),
        "replay_status": "not_recorded",
    }


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
    if expected_profile not in {"trader_paper_exit_reconciliation", "trader_paper_exit_review_chain", "trader_pair_score_continuity", "setup_strategy_journey"}:
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
            if expected_profile == "setup_strategy_journey":
                present = {}
                for table in ("setups", "strategies", "bot_configs", "bot_orders", "bot_executions"):
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                    present[table] = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM setups WHERE user_id=%s AND symbol='BTC'", (user_id,))
                btc_setups = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM strategies WHERE user_id=%s AND symbol='BTC'", (user_id,))
                btc_strategies = int(cur.fetchone()[0])
                execution_diagnostic = (
                    _journey_execution_status(cur, user_id)
                    if label == JOURNEY_CLEANUP_LABEL else {}
                )
                return {
                    "fixture_state": "UNSAFE_ACTIVE" if unsafe else "QUARANTINED_INACTIVE",
                    "cleanup_verified": False,
                    "owner_active": bool(owner_active),
                    "exchange_keys_present": bool(keys),
                    "setups_present": bool(present["setups"]),
                    "strategies_present": bool(present["strategies"]),
                    "bots_present": bool(present["bot_configs"]),
                    "active_or_live_bots_present": any(active or live for active, live in bots),
                    "journey_setup_present": bool(btc_setups),
                    "journey_strategy_present": bool(btc_strategies),
                    "orders_present": bool(present["bot_orders"]),
                    "executions_present": bool(present["bot_executions"]),
                    **execution_diagnostic,
                }
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
            review_progress = {}
            if expected_profile == "trader_paper_exit_review_chain":
                cur.execute("SELECT analysis_status FROM finn_trade_reviews WHERE user_id=%s", (user_id,))
                reviews = cur.fetchall()
                status = str(reviews[0][0]) if len(reviews) == 1 else "multiple" if reviews else "missing"
                if status not in {"pending", "running", "ready", "failed", "unavailable", "missing", "multiple"}:
                    status = "other"
                cur.execute("SELECT COUNT(*) FROM finn_v2_runs WHERE user_id=%s", (user_id,))
                review_progress = {
                    "review_present": bool(reviews),
                    "review_analysis_status": status,
                    "finn_run_present": bool(cur.fetchone()[0]),
                }
            return {
                "fixture_state": "UNSAFE_ACTIVE" if unsafe else "QUARANTINED_INACTIVE",
                "cleanup_verified": False,
                "paper_open_present": bool(decisions.get("assessment")),
                "paper_exit_decision_present": bool(decisions.get("paper_exit")),
                "paper_exit_order_present": bool(exit_orders),
                "paper_exit_execution_present": bool(exit_executions),
                "paper_exit_ledger_present": bool(exit_ledger),
                **review_progress,
            }
    finally:
        conn.close()


def cleanup_journey(label: str) -> dict:
    """Remove only the quarantined child from the failed setup confirmation run."""
    if label != JOURNEY_CLEANUP_LABEL:
        raise RuntimeError("journey_cleanup_label_not_allowed")
    match = LABEL.fullmatch(label)
    if not match:
        raise RuntimeError("trader_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = match.groups()
    _verify_prior_report(workflow_id, attempt, sha_prefix, "setup_strategy_journey")
    report_path = (Path("/tmp") / f"finn-production-qa-{workflow_id}-{attempt}"
                   / f"finn-production-qa-{workflow_id}-{attempt}.json")
    try:
        prior = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("trader_fixture_audit_prior_report_unavailable") from None
    journey = prior.get("setup_strategy_journey") or {}
    if (journey.get("fixture_state") != "quarantined"
            or journey.get("failure_stage") != "setup_confirmation"
            or journey.get("reason") != "journey_replay_failed"):
        raise RuntimeError("journey_cleanup_prior_state_mismatch")
    namespace_prefix = f"qa-{workflow_id}-{attempt}-{sha_prefix}-"
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,is_active,ai_preferences FROM users
                   WHERE ai_preferences->>'qa_fixture'=%s
                     AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            owners = cur.fetchall()
            if not owners:
                return {"fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": False}
            if len(owners) != 1:
                raise RuntimeError("journey_cleanup_scope_ambiguous")
            user_id, active, preferences = owners[0]
            namespace = (preferences or {}).get("qa_namespace", "")
            if (active or not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
                    or not namespace.startswith(namespace_prefix)):
                raise RuntimeError("journey_cleanup_owner_unsafe")
            cur.execute("SELECT id,is_active,is_live FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cur.fetchall()
            if len(bots) != 1 or bots[0][1:] != (False, False):
                raise RuntimeError("journey_cleanup_bot_unsafe")
            bot_id = bots[0][0]
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            if cur.fetchone()[0]:
                raise RuntimeError("journey_cleanup_keys_unsafe")
            for table in ("bot_trade_plans", "bot_orders", "bot_executions",
                          "bot_ledger", "bot_decisions"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cur.fetchone()[0]:
                    raise RuntimeError("journey_cleanup_trade_unsafe")
            for table in ("setups", "strategies"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s AND symbol='BTC'", (user_id,))
                if cur.fetchone()[0]:
                    raise RuntimeError("journey_cleanup_btc_row_unsafe")
    finally:
        conn.close()
    try:
        fixture._cleanup(namespace, user_id, bot_id, require_safe_pair_cleanup=True)
    except Exception:
        raise RuntimeError("journey_cleanup_failed") from None
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE id=%s", (user_id,))
            if cur.fetchone()[0]:
                raise RuntimeError("journey_cleanup_postcondition_failed")
            for table in ("setups", "strategies", "bot_configs", "bot_orders",
                          "bot_executions", "finn_v2_runs", "finn_v2_executions"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cur.fetchone()[0]:
                    raise RuntimeError("journey_cleanup_postcondition_failed")
    finally:
        conn.close()
    return {"fixture_state": "CLEANED", "cleanup_verified": True}


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


def cleanup_review(label: str) -> dict:
    """Remove only one exact failed, inactive Paper review-chain QA child."""
    match = LABEL.fullmatch(label)
    if not match:
        raise RuntimeError("trader_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = match.groups()
    _verify_prior_report(workflow_id, attempt, sha_prefix, "trader_paper_exit_review_chain")
    namespace_prefix = f"qa-{workflow_id}-{attempt}-{sha_prefix}-"
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,is_active,ai_preferences FROM users
                   WHERE ai_preferences->>'qa_fixture'=%s
                     AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            owners = cur.fetchall()
            if not owners:
                return {"fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": False}
            if len(owners) != 1:
                raise RuntimeError("trader_review_cleanup_scope_ambiguous")
            user_id, active, preferences = owners[0]
            namespace = (preferences or {}).get("qa_namespace", "")
            if (active or not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
                    or not namespace.startswith(namespace_prefix)):
                raise RuntimeError("trader_review_cleanup_owner_unsafe")
            cur.execute("SELECT id,is_active,is_live FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cur.fetchall()
            if len(bots) != 1 or bots[0][1:] != (False, False):
                raise RuntimeError("trader_review_cleanup_bot_unsafe")
            bot_id = bots[0][0]
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            if cur.fetchone()[0]:
                raise RuntimeError("trader_review_cleanup_keys_unsafe")
            cur.execute("SELECT COUNT(*) FROM bot_orders WHERE user_id=%s AND execution_environment IS DISTINCT FROM 'paper'", (user_id,))
            if cur.fetchone()[0]:
                raise RuntimeError("trader_review_cleanup_live_order_unsafe")
    finally:
        conn.close()
    try:
        fixture._cleanup(namespace, user_id, bot_id, require_safe_review_cleanup=True)
    except Exception:
        raise RuntimeError("trader_review_cleanup_failed") from None
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            for table in ("users", "finn_trade_reviews", "finn_v2_runs", "bot_orders", "bot_executions"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {'id' if table == 'users' else 'user_id'}=%s", (user_id,))
                if cur.fetchone()[0]:
                    raise RuntimeError("trader_review_cleanup_postcondition_failed")
    finally:
        conn.close()
    return {"fixture_state": "CLEANED", "cleanup_verified": True}
