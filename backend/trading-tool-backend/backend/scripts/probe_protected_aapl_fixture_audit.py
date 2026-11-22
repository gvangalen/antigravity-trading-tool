"""Exact-run audit and guarded cleanup for one failed AAPL coach QA child."""

from __future__ import annotations

import os

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.finn_v2_matrix_transport import TERMINAL_STATUSES
from backend.scripts.probe_protected_trader_fixture_audit import _verify_prior_report


LABEL = "audit-45033782172-1-775c4259"
NEW_LABEL = "audit-45061684671-1-0fc2d876"
LATEST_LABEL = "audit-45067081565-1-8b64780e"
RUNS = {
    LABEL: ("45033782172", "1", "775c4259"),
    NEW_LABEL: ("45061684671", "1", "0fc2d876"),
    LATEST_LABEL: ("45067081565", "1", "8b64780e"),
}
SAFE_ERRORS = frozenset({
    "dispatch_claim_timeout", "lifecycle_owner_failed", "orchestrator_failed",
    "selector_phase_timeout", "lifecycle_deadline_exceeded", "run_canceled",
    "responses_tool_round_limit", "responses_provider_error",
    "responses_provider_quota_unavailable", "responses_context_length_exceeded",
})
ERROR_CLASSES = {
    "responses_tool_round_limit": "tool_round_limit",
    "responses_provider_error": "provider",
    "responses_provider_quota_unavailable": "provider_quota",
    "responses_context_length_exceeded": "provider_context",
    "selector_phase_timeout": "selector_timeout",
    "lifecycle_deadline_exceeded": "runtime_timeout",
    "dispatch_claim_timeout": "dispatch_timeout",
    "quote_source_table_row_mismatch": "source_moment_claim",
    "current_quote_source_prose_mismatch": "source_moment_claim",
    "latest_price_context_clock_mismatch": "source_moment_claim",
}
PHASE_EVENTS = frozenset({
    "evidence_validation_started", "evidence_validation_failed",
    "response_draft_built", "response_verification_started",
    "response_verification_completed", "response_repair_started",
    "response_repair_completed", "verified_response_persisted",
    "delivery_envelope_built",
})
TERMINAL_EVENTS = frozenset({"orchestrator_failed", "orchestrator_rejected", "orchestrator_completed"})


def _code_class(codes) -> str:
    if not isinstance(codes, list):
        return "none"
    for code in codes:
        if isinstance(code, str) and code:
            return ERROR_CLASSES.get(code, "other")
    return "none"


def _bounded_phase(events) -> dict:
    phase, terminal = "none", "none"
    for event in events:
        if not isinstance(event, str):
            continue
        if event in PHASE_EVENTS:
            phase = event
        elif event in TERMINAL_EVENTS:
            terminal = event
    return {"last_phase": phase, "orchestrator_terminal": terminal}


def _failure_diagnostics(cur, user_id: int, run_ids: list[str]) -> list[dict]:
    result = []
    for run_id in run_ids:
        cur.execute(
            """SELECT outcome,unavailable_codes_json FROM finn_v2_orchestrator_results
               WHERE user_id=%s AND run_id=%s ORDER BY created_at DESC LIMIT 1""",
            (user_id, run_id),
        )
        row = cur.fetchone()
        outcome = row[0] if row and row[0] in {"completed", "unavailable", "failed"} else "other" if row else "missing"
        code_class = _code_class(row[1]) if row else "none"
        cur.execute(
            """SELECT event_type FROM finn_v2_run_traces
               WHERE user_id=%s AND run_id=%s ORDER BY event_order""",
            (user_id, run_id),
        )
        phase = _bounded_phase([event for (event,) in cur.fetchall() if isinstance(event, str)])
        result.append({"orchestrator_outcome": outcome,
                       "unavailable_code_class": code_class, **phase})
    return result


def _scope(label: str):
    run = RUNS.get(label)
    if run is None:
        raise RuntimeError("aapl_fixture_audit_label_invalid")
    workflow_id, attempt, sha_prefix = run
    namespace_prefix = f"qa-{workflow_id}-{attempt}-{sha_prefix}-"
    _verify_prior_report(workflow_id, attempt, sha_prefix, "aapl_paper_quote_coach")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s", (int(bound),))
            parent = cur.fetchone()
            if (not parent or parent[0] != "user" or parent[1] is not True
                    or (parent[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER):
                raise RuntimeError("fixture_binding_invalid")
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (int(bound),))
            if cur.fetchone()[0]:
                raise RuntimeError("fixture_binding_invalid")
            cur.execute(
                """SELECT id,is_active,ai_preferences,email FROM users
                   WHERE ai_preferences->>'qa_fixture'=%s
                     AND ai_preferences->>'qa_namespace' LIKE %s""",
                (fixture.FIXTURE_MARKER, namespace_prefix + "%"),
            )
            owners = cur.fetchall()
            if not owners:
                return None
            if len(owners) != 1:
                raise RuntimeError("aapl_fixture_audit_scope_ambiguous")
            user_id, active, preferences, email = owners[0]
            namespace = (preferences or {}).get("qa_namespace", "")
            if (not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
                    or not namespace.startswith(namespace_prefix)
                    or email != f"score2-stale-{namespace}@tradamind.example"):
                raise RuntimeError("aapl_fixture_audit_scope_ambiguous")
            return user_id, bool(active), namespace
    finally:
        conn.close()


def audit(label: str) -> dict:
    scoped = _scope(label)
    if scoped is None:
        return {"fixture_state": "NO_RETAINED_FIXTURE", "safe_to_cleanup": False}
    user_id, owner_active, _ = scoped
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,is_active,is_live,symbol FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = int(cur.fetchone()[0])
            counts = {}
            for table in ("setups", "strategies", "daily_reports", "bot_decisions",
                          "bot_trade_plans", "bot_orders", "bot_executions", "bot_ledger"):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                counts[table] = int(cur.fetchone()[0])
            cur.execute("SELECT symbol FROM setups WHERE user_id=%s", (user_id,))
            setup_symbols = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT symbol FROM strategies WHERE user_id=%s", (user_id,))
            strategy_symbols = [row[0] for row in cur.fetchall()]
            cur.execute(
                """SELECT bot_id,status,action FROM bot_decisions WHERE user_id=%s""",
                (user_id,),
            )
            decisions = cur.fetchall()
            cur.execute(
                """SELECT id,status,error_code,conversation_id FROM finn_v2_runs
                   WHERE user_id=%s AND client_context_json->>'surface'='qa_closed_paper_review'
                   ORDER BY created_at,id""",
                (user_id,),
            )
            rows = cur.fetchall()
        bot_safe = len(bots) == 1 and bots[0][1:] == (False, False, "AAPL")
        decision_safe = (len(decisions) == 1 and len(bots) == 1
                         and decisions[0] == (bots[0][0], "planned", "hold"))
        shape_safe = (counts["setups"] == counts["strategies"] == counts["daily_reports"] == 1
                      and setup_symbols == strategy_symbols == ["AAPL"]
                      and counts["bot_decisions"] == 1
                      and all(counts[table] == 0 for table in
                              ("bot_trade_plans", "bot_orders", "bot_executions", "bot_ledger")))
        turns_terminal = len(rows) == 3 and all(row[1] in TERMINAL_STATUSES for row in rows)
        safe = not owner_active and not keys and bot_safe and decision_safe and shape_safe and turns_terminal
        diagnostics = []
        if safe and label == LATEST_LABEL:
            with conn.cursor() as cur:
                diagnostics = _failure_diagnostics(cur, user_id, [row[0] for row in rows])
        return {
            "fixture_state": "QUARANTINED_INACTIVE" if safe else "UNSAFE_OR_AMBIGUOUS",
            "safe_to_cleanup": safe,
            "turns": [
                {"status": status if status in TERMINAL_STATUSES else "nonterminal_or_other",
                 "error_code": code if code in SAFE_ERRORS else "missing" if code is None else "other"}
                for _, status, code, _ in rows[:4]
            ],
            "terminal_diagnostics": diagnostics,
            "followup_same_conversation": (
                rows[2][3] == rows[0][3] if len(rows) == 3 else None
            ),
            "owner_active": owner_active,
            "active_or_live_bot": any(active or live for _, active, live, _ in bots),
            "keys_present": bool(keys),
            "trade_rows_present": any(counts[table] for table in
                                      ("bot_trade_plans", "bot_orders", "bot_executions", "bot_ledger")),
        }
    finally:
        conn.close()


def cleanup(label: str) -> dict:
    state = audit(label)
    if state["fixture_state"] == "NO_RETAINED_FIXTURE":
        return {"fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": True}
    if not state["safe_to_cleanup"]:
        raise RuntimeError("aapl_fixture_cleanup_unsafe")
    scoped = _scope(label)
    if scoped is None:
        raise RuntimeError("aapl_fixture_cleanup_scope_changed")
    user_id, _, namespace = scoped
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bot_configs WHERE user_id=%s", (user_id,))
            bot_rows = cur.fetchall()
            if len(bot_rows) != 1:
                raise RuntimeError("aapl_fixture_cleanup_scope_changed")
            bot_id = bot_rows[0][0]
    finally:
        conn.close()
    fixture._cleanup(namespace, user_id, bot_id, require_safe_pair_cleanup=True,
                     allow_planned_decisions=True, require_aapl_quote_fixture=True)
    if audit(label)["fixture_state"] != "NO_RETAINED_FIXTURE":
        raise RuntimeError("aapl_fixture_cleanup_postcondition_failed")
    return {"fixture_state": "CLEANED", "cleanup_verified": True}
