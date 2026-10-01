"""A single view of the preceding persisted FINN turn for model and verifier."""

from __future__ import annotations

from typing import Any, Mapping


def project_verified_turn(previous: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    terminal_reason = str(previous.get("terminal_reason") or "")
    evidence_limits = {
        "personal_fit_not_established": "Saved profile or plan facts alone do not establish whether the proposed change suits this user.",
        "current_market_claim_unverified": "No fresh, dated market source supports the claimed current reading.",
        "saved_action_claim_unverified": "No confirmed execution proves that the claimed change was saved.",
        "trading_outcome_claim_unverified": "The available facts do not establish a trading outcome.",
        "user_condition_bypass_blocked": "The answer suggested bypassing a prerequisite stated by the user.",
    }
    clarification = previous.get("terminal_status") == "clarification_required"
    evidence = []
    for call in previous.get("tool_trace") or []:
        for item in (call.get("result") or {}).get("results") or []:
            if not isinstance(item, dict) or not item.get("scope") or not item.get("status"):
                continue
            if clarification and item.get("status") != "completed" and item.get("reason") != terminal_reason:
                continue
            evidence.append({
                key: item.get(key) for key in
                ("scope", "status", "reason", "source", "asset", "timeframe", "as_of", "freshness", "data")
                if key in item
            })
    return {
        "run_id": previous.get("run_id"),
        "response_id": previous.get("response_id"),
        "answer": previous.get("answer"),
        "user_message": previous.get("user_message"),
        "terminal_kind": previous.get("terminal_kind") or previous.get("terminal_status"),
        "terminal_status": previous.get("terminal_status"),
        "terminal_reason": terminal_reason,
        "evidence_limit": evidence_limits.get(terminal_reason),
        "open_choice": (previous.get("open_choice") or terminal_reason) if clarification else None,
        "antecedent_verified_answer": previous.get("antecedent_verified_answer"),
        "turn_contract": previous.get("turn_contract"),
        "evidence": evidence,
    }
