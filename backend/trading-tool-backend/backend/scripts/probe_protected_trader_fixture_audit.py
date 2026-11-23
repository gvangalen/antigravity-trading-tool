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
JOURNEY_CARD_LABEL = "audit-44974889786-1-76d282df"
JOURNEY_TRANSPORT_LABEL = "audit-44977345882-1-f5cfb7a3"
JOURNEY_YES_DIAGNOSTIC_LABEL = "audit-45006104528-1-50cc25ca"
JOURNEY_STRATEGY_DIAGNOSTIC_LABEL = "audit-45015412389-1-999bd355"
JOURNEY_STRATEGY_RETEST_LABEL = "audit-45020771853-1-ea64f391"
JOURNEY_STRATEGY_SLOT_LABEL = "audit-45027057156-1-1c7ac643"
JOURNEY_FEED_YES_LABEL = "audit-45176449317-1-41a256b5"
JOURNEY_CLEANUP_LABELS = frozenset({
    JOURNEY_CLEANUP_LABEL,
    "audit-44972794086-1-da950aac",
    JOURNEY_CARD_LABEL,
    JOURNEY_TRANSPORT_LABEL,
    JOURNEY_YES_DIAGNOSTIC_LABEL,
    JOURNEY_STRATEGY_DIAGNOSTIC_LABEL,
    JOURNEY_STRATEGY_RETEST_LABEL,
    JOURNEY_STRATEGY_SLOT_LABEL,
    JOURNEY_FEED_YES_LABEL,
})
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


def _journey_yes_diagnostic(cur, user_id: int, namespace: str) -> dict:
    """Compare the three QA turns without exposing their content or identifiers."""
    cur.execute(
        "SELECT id FROM setups WHERE user_id=%s AND symbol='BTC' AND name=%s",
        (user_id, f"QA BTC Setup {namespace}"),
    )
    setups = cur.fetchall()
    if len(setups) != 1:
        return {"yes_diagnostic_state": "setup_missing_or_ambiguous"}
    setup_id = setups[0][0]
    cur.execute(
        """SELECT conversation_id FROM finn_v2_runs
           WHERE user_id=%s AND client_context_json->>'surface'='qa_setup_strategy_journey'
             AND message=%s""",
        (user_id, f"Ik wil los een swing-setup voor BTC/USDT op 4 uur, genaamd QA BTC Setup {namespace}. "
                  "Bereid alleen de setup voor en toon eerst het voorstel."),
    )
    setup_turns = cur.fetchall()
    cur.execute(
        """SELECT conversation_id FROM finn_v2_runs
           WHERE user_id=%s AND client_context_json->>'surface'='qa_coach_feed'
             AND message=%s""",
        (user_id, "Bespreek de volgende stap voor mijn BTC/USDT-setup. "
                  "Lees het opgeslagen plan; wijzig niets."),
    )
    feed_turns = cur.fetchall()
    cur.execute(
        """SELECT r.conversation_id,r.status,c.terminal_projection_json
           FROM finn_v2_runs r LEFT JOIN finn_v2_runtime_contracts c
             ON c.run_id=r.id AND c.user_id=r.user_id
           WHERE r.user_id=%s AND r.client_context_json->>'surface'='qa_setup_strategy_journey'
             AND r.message=%s""",
        (user_id, "ja"),
    )
    yes_turns = cur.fetchall()
    if len(setup_turns) != 1 or len(yes_turns) != 1:
        return {"yes_diagnostic_state": "turn_missing_or_ambiguous",
                "setup_turn_unique": len(setup_turns) == 1,
                "yes_turn_unique": len(yes_turns) == 1,
                "feed_turn_unique": len(feed_turns) == 1}
    setup_conversation = setup_turns[0][0]
    yes_conversation, status, raw_projection = yes_turns[0]
    projection = raw_projection if isinstance(raw_projection, dict) else {}
    action_draft = projection.get("action_draft") or {}
    if not isinstance(action_draft, dict):
        action_draft = {}
    inputs = projection.get("supplied_inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}
    operation = projection.get("final_operation_id") or projection.get("initial_operation_id")
    guided = action_draft.get("operation_id")
    def safe_operation(value: object) -> str:
        return value if value in {"create_setup", "create_strategy", "create_bot"} else (
            "missing" if value is None else "other")
    def safe_count(value: object) -> int | str:
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3 else "other"
    return {
        "yes_diagnostic_state": "available",
        "yes_status": status if status in {"completed", "clarification_required", "failed", "running"} else "other",
        "yes_operation": safe_operation(operation),
        "yes_guided_operation": safe_operation(guided),
        "yes_setup_id_match": str(inputs.get("setup_id")) == str(setup_id),
        "yes_setup_conversation_match": yes_conversation == setup_conversation,
        "feed_turn_unique": len(feed_turns) == 1,
        "feed_setup_conversation_match": (feed_turns[0][0] == setup_conversation
                                           if len(feed_turns) == 1 else None),
        "feed_yes_conversation_match": (feed_turns[0][0] == yes_conversation
                                         if len(feed_turns) == 1 else None),
        "yes_dispatch_count": safe_count(projection.get("dispatch_count")),
        "yes_attempt_count": safe_count(projection.get("attempt_count")),
    }


def _journey_feed_yes_diagnostic(cur, user_id: int, namespace: str) -> dict:
    """Report only typed conditions for the exact feed-discussion follow-up."""
    setup_name = f"QA BTC Setup {namespace}"
    cur.execute(
        "SELECT id FROM setups WHERE user_id=%s AND symbol='BTC' AND name=%s",
        (user_id, setup_name),
    )
    setups = cur.fetchall()
    if len(setups) != 1:
        return {"feed_yes_diagnostic_state": "setup_missing_or_ambiguous"}
    setup_id = setups[0][0]
    setup_message = (f"Ik wil los een swing-setup voor BTC/USDT op 4 uur, genaamd {setup_name}. "
                     "Bereid alleen de setup voor en toon eerst het voorstel.")
    feed_message = (
        f"Controleer of setup {setup_name} voor BTC/USDT nog bestaat en of er inmiddels "
        "een strategie aan is gekoppeld. Zo niet, adviseer welke strategie past en "
        "welke gegevens je van mij nodig hebt. Lees ook de actuele scorestatus en "
        "noem een ontbrekende bron eerlijk. Maak niets aan."
    )
    cur.execute(
        """SELECT conversation_id FROM finn_v2_runs
           WHERE user_id=%s AND client_context_json->>'surface'='qa_setup_strategy_journey'
             AND message=%s""",
        (user_id, setup_message),
    )
    setup_turns = cur.fetchall()
    cur.execute(
        """SELECT conversation_id,status,client_context_json FROM finn_v2_runs
           WHERE user_id=%s AND client_context_json->>'surface'='qa_setup_strategy_journey'
             AND message=%s""",
        (user_id, feed_message),
    )
    feed_turns = cur.fetchall()
    cur.execute(
        """SELECT r.conversation_id,r.status,r.error_code,r.response_json,
                  c.terminal_projection_json,c.state_json
           FROM finn_v2_runs r LEFT JOIN finn_v2_runtime_contracts c
             ON c.run_id=r.id AND c.user_id=r.user_id
           WHERE r.user_id=%s
             AND r.client_context_json->>'surface'='qa_setup_strategy_journey'
             AND r.message='ja'""",
        (user_id,),
    )
    yes_turns = cur.fetchall()
    if any(len(turns) != 1 for turns in (setup_turns, feed_turns, yes_turns)):
        return {
            "feed_yes_diagnostic_state": "turn_missing_or_ambiguous",
            "setup_turn_unique": len(setup_turns) == 1,
            "feed_turn_unique": len(feed_turns) == 1,
            "yes_turn_unique": len(yes_turns) == 1,
        }

    setup_conversation = setup_turns[0][0]
    feed_conversation, feed_status, raw_context = feed_turns[0]
    yes_conversation, yes_status, error_code, raw_response, raw_projection, raw_state = yes_turns[0]
    context = raw_context if isinstance(raw_context, dict) else {}
    response = raw_response if isinstance(raw_response, dict) else {}
    projection = raw_projection if isinstance(raw_projection, dict) else {}
    state = raw_state if isinstance(raw_state, dict) else {}
    draft = projection.get("action_draft")
    draft = draft if isinstance(draft, dict) else {}
    inputs = projection.get("supplied_inputs")
    inputs = inputs if isinstance(inputs, dict) else {}
    guided = state.get("guided_state")
    guided = guided if isinstance(guided, dict) else {}
    collected = guided.get("collected_inputs")
    collected = collected if isinstance(collected, dict) else {}
    raw_missing = guided.get("missing_required_inputs")
    raw_missing = raw_missing if isinstance(raw_missing, list) else []
    allowed_slots = {
        "setup_id", "name", "execution_mode", "base_amount", "entry",
        "stop_loss", "targets", "price_currency", "risk_profile",
        "symbol", "timeframe", "setup_type", "quote_currency",
    }
    missing_slots = sorted({
        slot if slot in allowed_slots else "other"
        for slot in raw_missing[:16] if isinstance(slot, str)
    })
    next_slot = guided.get("next_missing_input")
    feed_item_id = context.get("feed_item_id")
    feed_item_id = feed_item_id if isinstance(feed_item_id, str) else ""
    cur.execute(
        """SELECT status FROM finn_coach_feed_items
           WHERE id::text=%s AND user_id=%s AND event_type='strategy_next_step'
             AND subject_type='setup' AND subject_id=%s""",
        (feed_item_id, user_id, str(setup_id)),
    )
    cards = cur.fetchall()

    def safe_operation(value: object) -> str:
        return value if isinstance(value, str) and value in {
            "create_setup", "create_strategy", "create_bot",
        } else "missing" if value is None else "other"

    def safe_status(value: object) -> str:
        return value if isinstance(value, str) and value in {
            "completed", "clarification_required", "unavailable", "rejected",
            "blocked", "failed", "canceled",
        } else "other"

    def safe_count(value: object) -> int | str:
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3 else "other"

    return {
        "feed_yes_diagnostic_state": "available",
        "feed_turn_status": safe_status(feed_status),
        "feed_card_selected_and_owner_bound": len(cards) == 1,
        "feed_card_status": (cards[0][0] if len(cards) == 1 and cards[0][0] in
                             {"unread", "read", "resolved"} else "missing_or_other"),
        "feed_same_conversation_as_setup": feed_conversation == setup_conversation,
        "yes_same_conversation_as_feed": yes_conversation == feed_conversation,
        "yes_status": safe_status(yes_status),
        "yes_error_code": error_code if isinstance(error_code, str) and error_code in {
            "guided_proposal_tool_call_required", "responses_tool_round_limit",
            "responses_provider_error", "finn_v2_internal_error",
        } else "none" if error_code is None else "other",
        "yes_operation": safe_operation(projection.get("final_operation_id") or
                                        projection.get("initial_operation_id")),
        "yes_guided_operation": safe_operation(draft.get("operation_id")),
        "yes_state_guided_operation": safe_operation(guided.get("operation_id")),
        "yes_supplied_setup_match": str(inputs.get("setup_id")) == str(setup_id),
        "yes_guided_setup_match": str(collected.get("setup_id")) == str(setup_id),
        "yes_proposal_present": bool(response.get("proposal_id")),
        "yes_missing_slots": missing_slots,
        "yes_next_missing_slot": (next_slot if isinstance(next_slot, str) and
                                  next_slot in allowed_slots else
                                  "missing" if next_slot is None else "other"),
        "yes_dispatch_count": safe_count(projection.get("dispatch_count")),
        "yes_attempt_count": safe_count(projection.get("attempt_count")),
    }


def _journey_strategy_diagnostic(cur, user_id: int, namespace: str) -> dict:
    """Inspect one failed proposal turn, returning only typed conditions."""
    cur.execute(
        "SELECT id FROM setups WHERE user_id=%s AND symbol='BTC' AND name=%s",
        (user_id, f"QA BTC Setup {namespace}"),
    )
    setups = cur.fetchall()
    if len(setups) != 1:
        return {"strategy_diagnostic_state": "setup_missing_or_ambiguous"}
    cur.execute(
        """SELECT r.conversation_id,c.terminal_projection_json FROM finn_v2_runs r
           LEFT JOIN finn_v2_runtime_contracts c ON c.run_id=r.id AND c.user_id=r.user_id
           WHERE r.user_id=%s AND r.client_context_json->>'surface'='qa_setup_strategy_journey'
             AND r.message='ja'""",
        (user_id,),
    )
    yes_turns = cur.fetchall()
    strategy_name = f"QA BTC Strategy {namespace}"
    message = (
        f"Noem die strategie {strategy_name}. Vaste uitvoering van 10 euro, "
        "entry 76000 USDT, stop-loss 72000 USDT, target 83000 USDT, "
        "gebalanceerd risico. Toon eerst een voorstel, maak geen bot."
    )
    cur.execute(
        """SELECT r.conversation_id,r.status,r.error_code,r.response_json,
                  c.terminal_projection_json,c.state_json FROM finn_v2_runs r
           LEFT JOIN finn_v2_runtime_contracts c ON c.run_id=r.id AND c.user_id=r.user_id
           WHERE r.user_id=%s AND r.client_context_json->>'surface'='qa_setup_strategy_journey'
             AND r.message=%s""",
        (user_id, message),
    )
    strategy_turns = cur.fetchall()
    if len(yes_turns) != 1 or len(strategy_turns) != 1:
        return {"strategy_diagnostic_state": "turn_missing_or_ambiguous",
                "yes_turn_unique": len(yes_turns) == 1,
                "strategy_turn_unique": len(strategy_turns) == 1}
    yes_conversation, raw_yes_projection = yes_turns[0]
    conversation, status, error_code, raw_response, raw_projection, raw_state = strategy_turns[0]
    yes_projection = raw_yes_projection if isinstance(raw_yes_projection, dict) else {}
    projection = raw_projection if isinstance(raw_projection, dict) else {}
    response = raw_response if isinstance(raw_response, dict) else {}
    draft = projection.get("action_draft") or {}
    if not isinstance(draft, dict):
        draft = {}
    inputs = projection.get("supplied_inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}
    state = raw_state if isinstance(raw_state, dict) else {}
    guided = state.get("guided_state") or {}
    if not isinstance(guided, dict):
        guided = {}
    collected = guided.get("collected_inputs") or {}
    if not isinstance(collected, dict):
        collected = {}
    allowed_slots = {
        "setup_id", "name", "execution_mode", "base_amount", "entry",
        "stop_loss", "targets", "price_currency", "risk_profile",
        "symbol", "timeframe", "setup_type", "quote_currency",
    }
    raw_missing = guided.get("missing_required_inputs")
    missing = raw_missing if isinstance(raw_missing, list) else []
    safe_slots = sorted({slot if slot in allowed_slots else "other"
                         for slot in missing[:16] if isinstance(slot, str)})
    next_slot = guided.get("next_missing_input")
    operation = projection.get("final_operation_id") or projection.get("initial_operation_id")
    def safe_operation(value: object) -> str:
        return value if value in {"create_setup", "create_strategy", "create_bot"} else (
            "missing" if value is None else "other")
    def safe_count(value: object) -> int | str:
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3 else "other"
    return {
        "strategy_diagnostic_state": "available",
        "strategy_status": status if status in {
            "created", "queued", "collecting", "planned", "reasoning", "verifying",
            "clarification_required", "unavailable", "downgraded", "rejected",
            "blocked", "completed", "failed", "canceled",
        } else "other",
        "strategy_operation": safe_operation(operation),
        "strategy_guided_operation": safe_operation(draft.get("operation_id")),
        "prior_yes_guided_operation": safe_operation(
            (yes_projection.get("action_draft") or {}).get("operation_id")
            if isinstance(yes_projection.get("action_draft"), dict) else None),
        "strategy_proposal_present": bool(response.get("proposal_id")),
        "strategy_confirmation_required": response.get("confirmation_required") is True,
        "strategy_setup_id_match": str(inputs.get("setup_id")) == str(setups[0][0]),
        "strategy_same_conversation_as_yes": conversation == yes_conversation,
        "strategy_dispatch_count": safe_count(projection.get("dispatch_count")),
        "strategy_attempt_count": safe_count(projection.get("attempt_count")),
        "strategy_error_code": error_code if error_code in {
            "guided_proposal_tool_call_required", "responses_tool_round_limit",
            "responses_provider_error", "finn_v2_internal_error",
        } else "none" if error_code is None else "other",
        "strategy_state_guided_operation": safe_operation(guided.get("operation_id")),
        "strategy_state_setup_id_match": str(collected.get("setup_id")) == str(setups[0][0]),
        "strategy_state_name_present": bool(collected.get("name")),
        "strategy_missing_slots": safe_slots,
        "strategy_next_missing_slot": (next_slot if next_slot in allowed_slots else
                                       "missing" if next_slot is None else "other"),
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
    transport_diagnostic = {}
    if label == JOURNEY_TRANSPORT_LABEL and expected_profile == "setup_strategy_journey":
        state_dir = Path("/tmp") / f"finn-production-qa-{workflow_id}-{attempt}"
        marker = state_dir / "runner.exit"
        try:
            exit_code = marker.read_text(encoding="utf-8").strip()
        except OSError:
            exit_code = ""
        try:
            prior = json.loads((state_dir / f"finn-production-qa-{workflow_id}-{attempt}.json")
                               .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = {}
        journey = prior.get("setup_strategy_journey") or {}
        stage = journey.get("failure_stage")
        reason = journey.get("reason")
        transport_diagnostic = {
            "runner_terminal_status": ("succeeded" if exit_code == "0" else
                                       "failed" if exit_code.isdecimal() else "missing"),
            "checkpoint_present": bool(prior),
            "prior_failure_stage": stage if stage in {
                "setup_confirmation", "setup_card", "setup_discuss",
                "strategy_guided", "strategy_proposal", "strategy_confirmation",
                "paper_card", "paper_discuss", "paper_guided", "safety",
            } else "other",
            "prior_failure_reason": reason if reason in {
                "journey_strategy_card_missing", "journey_feed_discuss_failed",
                "journey_strategy_guided_failed", "journey_strategy_proposal_missing",
                "journey_setup_confirmation_failed", "journey_runtime_failed",
            } else "other",
        }
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
                        "cleanup_verified": False, "stage": "BEFORE_SEED_OR_CLEANED",
                        **transport_diagnostic}
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
                card_diagnostic = {}
                yes_diagnostic = (
                    _journey_yes_diagnostic(cur, user_id, namespace)
                    if label == JOURNEY_YES_DIAGNOSTIC_LABEL else {}
                )
                strategy_diagnostic = (
                    _journey_strategy_diagnostic(cur, user_id, namespace)
                    if label in {JOURNEY_STRATEGY_DIAGNOSTIC_LABEL,
                                 JOURNEY_STRATEGY_RETEST_LABEL,
                                 JOURNEY_STRATEGY_SLOT_LABEL} else {}
                )
                feed_yes_diagnostic = (
                    _journey_feed_yes_diagnostic(cur, user_id, namespace)
                    if label == JOURNEY_FEED_YES_LABEL else {}
                )
                if label == JOURNEY_CARD_LABEL:
                    cur.execute(
                        """SELECT id FROM setups WHERE user_id=%s AND symbol='BTC' AND name=%s""",
                        (user_id, f"QA BTC Setup {namespace}"),
                    )
                    setup_rows = cur.fetchall()
                    statuses = []
                    if len(setup_rows) == 1:
                        cur.execute(
                            """SELECT status FROM finn_coach_feed_items
                               WHERE user_id=%s AND event_type='strategy_next_step'
                                 AND subject_type='setup' AND subject_id=%s""",
                            (user_id, str(setup_rows[0][0])),
                        )
                        statuses = [row[0] for row in cur.fetchall()]
                    card_diagnostic = {
                        "strategy_card_count": min(len(statuses), 3),
                        "strategy_card_status": (
                            "missing" if not statuses else
                            statuses[0] if len(statuses) == 1 and statuses[0] in
                            {"unread", "read", "resolved"} else "multiple_or_other"
                        ),
                    }
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
                    **card_diagnostic,
                    **yes_diagnostic,
                    **strategy_diagnostic,
                    **feed_yes_diagnostic,
                    **transport_diagnostic,
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
    if label not in JOURNEY_CLEANUP_LABELS:
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
    expected_failure = (("setup_card", "journey_strategy_card_missing")
                        if label == JOURNEY_CARD_LABEL else
                        ("setup_confirmation", "journey_replay_failed"))
    transport_failure = label == JOURNEY_TRANSPORT_LABEL and (
        journey.get("failure_stage"), journey.get("reason")) in {
            ("setup_card", "journey_strategy_card_missing"),
            ("setup_discuss", "journey_feed_discuss_failed"),
            ("strategy_guided", "journey_strategy_guided_failed"),
            ("strategy_proposal", "journey_strategy_proposal_missing"),
        }
    guided_failure = label == JOURNEY_YES_DIAGNOSTIC_LABEL and (
        journey.get("failure_stage"), journey.get("reason")) == (
            "strategy_guided", "journey_strategy_guided_failed")
    feed_yes_failure = label == JOURNEY_FEED_YES_LABEL and (
        journey.get("failure_stage"), journey.get("reason")) == (
            "strategy_guided", "journey_strategy_guided_failed") and (
        prior.get("qa_status") == "COMPLETED"
        and journey.get("fixture_confirmations") == 1
        and journey.get("fixture_executions") == 1
        and (journey.get("execution_diagnostic") or {}).get("first_status") == "succeeded"
        and (journey.get("execution_diagnostic") or {}).get("replay_status") == "already_executed"
        and (prior.get("safety") or {}).get("live_trading_calls") == 0
        and (prior.get("safety") or {}).get("live_bot_activation_calls") == 0)
    proposal_failure = label in {JOURNEY_STRATEGY_DIAGNOSTIC_LABEL,
                                 JOURNEY_STRATEGY_RETEST_LABEL,
                                 JOURNEY_STRATEGY_SLOT_LABEL} and (
        journey.get("failure_stage"), journey.get("reason")) == (
            "strategy_proposal", "journey_strategy_proposal_missing")
    if (journey.get("fixture_state") != "quarantined"
            or not (transport_failure or guided_failure or feed_yes_failure or proposal_failure or
                    (journey.get("failure_stage"), journey.get("reason")) == expected_failure)):
        raise RuntimeError("journey_cleanup_prior_state_mismatch")
    if label == JOURNEY_TRANSPORT_LABEL:
        marker = Path("/tmp") / f"finn-production-qa-{workflow_id}-{attempt}" / "runner.exit"
        try:
            exit_code = marker.read_text(encoding="utf-8").strip()
        except OSError:
            exit_code = ""
        if not exit_code.isdecimal():
            raise RuntimeError("journey_cleanup_runner_not_terminal")
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
            if label in {JOURNEY_CARD_LABEL, JOURNEY_TRANSPORT_LABEL,
                         JOURNEY_YES_DIAGNOSTIC_LABEL,
                         JOURNEY_FEED_YES_LABEL,
                         JOURNEY_STRATEGY_DIAGNOSTIC_LABEL,
                         JOURNEY_STRATEGY_RETEST_LABEL,
                         JOURNEY_STRATEGY_SLOT_LABEL}:
                cur.execute("SELECT name,symbol FROM setups WHERE user_id=%s", (user_id,))
                expected_setups = {(namespace, "ETH"), (f"QA BTC Setup {namespace}", "BTC")}
                setups = cur.fetchall()
                if len(setups) != 2 or set(setups) != expected_setups:
                    raise RuntimeError("journey_cleanup_btc_row_unsafe")
                cur.execute("SELECT name,symbol FROM strategies WHERE user_id=%s", (user_id,))
                if cur.fetchall() != [(namespace, "ETH")]:
                    raise RuntimeError("journey_cleanup_btc_row_unsafe")
                cur.execute(
                    """SELECT s.name,s.symbol,m.quote_currency FROM setups s
                       LEFT JOIN trading_markets m ON m.id=s.market_id
                       WHERE s.user_id=%s AND s.symbol='BTC'""", (user_id,),
                )
                if cur.fetchall() != [(f"QA BTC Setup {namespace}", "BTC", "USDT")]:
                    raise RuntimeError("journey_cleanup_btc_row_unsafe")
                for table in ("strategies", "watchlists"):
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s AND symbol='BTC'", (user_id,))
                    if cur.fetchone()[0]:
                        raise RuntimeError("journey_cleanup_btc_row_unsafe")
            else:
                for table in ("setups", "strategies"):
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s AND symbol='BTC'", (user_id,))
                    if cur.fetchone()[0]:
                        raise RuntimeError("journey_cleanup_btc_row_unsafe")
    finally:
        conn.close()
    try:
        fixture._cleanup(
            namespace, user_id, bot_id, require_safe_pair_cleanup=True,
            **({"required_role": "user"} if label == JOURNEY_FEED_YES_LABEL else {}),
        )
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
