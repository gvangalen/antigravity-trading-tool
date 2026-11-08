"""Read-only, bounded audit of one prior protected trader QA namespace."""

from __future__ import annotations

import re
import json
from pathlib import Path

from backend.scripts import probe_protected_score2_stale_paper as fixture


LABEL = re.compile(r"audit-([1-9][0-9]{5,15})-([1-9][0-9]*)-([0-9a-f]{8})\Z")


def _verify_prior_report(workflow_id: str, attempt: str, sha_prefix: str) -> None:
    run_id = f"{workflow_id}-{attempt}"
    report = Path("/tmp") / f"finn-production-qa-{run_id}" / f"finn-production-qa-{run_id}.json"
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("trader_fixture_audit_prior_report_unavailable") from None
    if (data.get("workflow_run_id") != run_id
            or data.get("profile") != "trader_paper_exit_reconciliation"
            or not str(data.get("target_sha", "")).startswith(sha_prefix)
            or data.get("protected_profile_attempted") is not True
            or data.get("outcome") not in {"failed", "incomplete"}):
        raise RuntimeError("trader_fixture_audit_prior_report_mismatch")


def run(label: str) -> dict:
    match = LABEL.fullmatch(label)
    if not match:
        raise RuntimeError("trader_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = match.groups()
    _verify_prior_report(workflow_id, attempt, sha_prefix)
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
            unsafe = bool(owner_active or keys or any(active or live for active, live in bots))
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
