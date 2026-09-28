"""A single view of the preceding persisted FINN turn for model and verifier."""

from __future__ import annotations

from typing import Any, Mapping


def project_verified_turn(previous: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    terminal_reason = str(previous.get("terminal_reason") or "")
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
        "terminal_kind": previous.get("terminal_kind") or previous.get("terminal_status"),
        "terminal_status": previous.get("terminal_status"),
        "terminal_reason": terminal_reason,
        "open_choice": (previous.get("open_choice") or terminal_reason) if clarification else None,
        "antecedent_verified_answer": previous.get("antecedent_verified_answer"),
        "evidence": evidence,
    }
