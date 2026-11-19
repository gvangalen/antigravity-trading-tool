"""Durable, narrow FINN setup -> strategy -> score task state.

Only a verified action result can complete a mutating step.  The state is kept
in the owner-scoped conversation and never grants permission to execute a
proposal: every write still goes through the normal confirmation contract.
"""

from __future__ import annotations

import re
from typing import Any


STATE_KEY = "setup_strategy_score_task_v1"


def requested_task(message: str) -> dict[str, Any] | None:
    text = str(message or "").strip()
    lower = text.lower()
    create = re.search(r"\b(maak|maakt|aanmaken|cre[eë]er|create|make|build|save|sla op|erstelle|anlegen)\b", lower)
    setup = re.search(r"\bsetup\b", lower)
    if not (create and setup):
        return None
    strategy = bool(re.search(r"\b(strategie|strategy)\b", lower))
    score = bool(re.search(r"\b(score|benchmark)\b", lower))
    # This V1 deliberately handles only a setup alone or the complete chain.
    if strategy != score:
        return None
    asset = re.search(r"\b(BTC|ETH|SOL|XRP|ADA|AAPL|TSLA|NVDA|MSFT|SPY|QQQ)\b", text, re.I)
    return {
        "version": 1,
        "requested_results": ["setup", "strategy", "score"] if strategy else ["setup"],
        "completed_steps": {},
        "pending_step": "setup",
        "pending_question": None,
        "pending_action": None,
        "asset": asset.group(1).upper() if asset else None,
        "status": "in_progress",
    }


def advance_from_action(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Advance only from a successful, owner-bound execution projection."""
    current = dict(state or {})
    if current.get("version") != 1 or current.get("status") != "in_progress":
        return current
    if result.get("result_status") != "succeeded":
        return current
    operation = result.get("operation_id")
    pending = current.get("pending_step")
    entity = dict(result.get("canonical_entity") or {})
    completed = dict(current.get("completed_steps") or {})
    expected_asset = current.get("asset")
    actual_asset = str(entity.get("symbol") or entity.get("asset") or "").upper()
    if expected_asset and actual_asset and actual_asset != expected_asset:
        return current
    if pending == "setup" and operation == "create_setup":
        setup_id = entity.get("setup_id") or result.get("entity_id")
        if not setup_id:
            return current
        completed["setup"] = {"id": str(setup_id), "execution_id": result.get("execution_id"),
                              "name": result.get("canonical_name")}
        current["asset"] = actual_asset or expected_asset
        current["quote_currency"] = entity.get("quote_currency")
        current["market_id"] = entity.get("market_id")
        strategy_id = entity.get("strategy_id")
        if strategy_id and "strategy" in current.get("requested_results", []):
            completed["strategy"] = {"id": str(strategy_id), "execution_id": result.get("execution_id")}
        if "strategy" not in current.get("requested_results", []):
            current.update(status="completed", pending_step=None)
        else:
            current["pending_step"] = "score" if strategy_id else "strategy"
    elif pending == "strategy" and operation == "create_strategy":
        setup_id = str(completed.get("setup", {}).get("id") or "")
        parent_id = str(result.get("parent_entity_id") or entity.get("setup_id") or "")
        strategy_id = entity.get("strategy_id") or result.get("entity_id")
        if not setup_id or parent_id != setup_id or not strategy_id:
            return current
        completed["strategy"] = {"id": str(strategy_id), "execution_id": result.get("execution_id"),
                                 "name": result.get("canonical_name")}
        current["pending_step"] = "score"
    else:
        return current
    current["completed_steps"] = completed
    current["pending_question"] = None
    current["pending_action"] = None
    return current


def continuation(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return only the next read/proposal request, never an execution command."""
    if state.get("status") != "in_progress":
        return None
    completed = dict(state.get("completed_steps") or {})
    setup_id = completed.get("setup", {}).get("id")
    step = state.get("pending_step")
    if step == "strategy" and setup_id:
        return {"step": "strategy", "setup_id": setup_id, "asset": state.get("asset")}
    if step == "score" and setup_id and completed.get("strategy", {}).get("id"):
        return {"step": "score", "setup_id": setup_id,
                "strategy_id": completed["strategy"]["id"], "asset": state.get("asset"),
                "quote_currency": state.get("quote_currency")}
    return None


def continuation_message(next_step: dict[str, Any]) -> str | None:
    """Construct a server-owned chat turn from a verified task checkpoint."""
    setup_id = str(next_step.get("setup_id") or "")
    if not setup_id.isdecimal():
        return None
    if next_step.get("step") == "strategy":
        asset = str(next_step.get("asset") or "").upper()
        if asset and not re.fullmatch(r"[A-Z0-9]{2,12}", asset):
            return None
        setup_label = f"{asset}-setup" if asset else "setup"
        return (
            f"Maak nu een strategie voor de reeds opgeslagen {setup_label} met ID {setup_id}. "
            "Maak geen tweede setup. Vraag naar ontbrekende verplichte strategiekeuzes "
            "en leg de strategie ter bevestiging voor."
        )
    if next_step.get("step") == "score":
        strategy_id = str(next_step.get("strategy_id") or "")
        asset = str(next_step.get("asset") or "").upper()
        quote = str(next_step.get("quote_currency") or "").upper()
        if not strategy_id.isdecimal() or not re.fullmatch(r"[A-Z0-9]{2,12}", asset):
            return None
        if quote and not re.fullmatch(r"[A-Z0-9]{2,12}", quote):
            return None
        pair = f"{asset}/{quote}" if quote else asset
        return (
            f"Lees nu via get_current_asset_scores de actuele benchmarkscore voor {pair}. "
            f"Toon één eindresultaat met de opgeslagen setup ID {setup_id}, de opgeslagen "
            f"strategie ID {strategy_id} en de beschikbare score. Als de score ontbreekt, "
            "zeg welke bron of scorecomponent ontbreekt en behoud het gedeeltelijke resultaat."
        )
    return None


def score_from_trace(state: dict[str, Any], tool_trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract only a successful exact-asset score read from a verified run."""
    expected_asset = str(state.get("asset") or "").upper()
    expected_quote = str(state.get("quote_currency") or "").upper()
    expected_market = state.get("market_id")
    for call in tool_trace:
        for item in (call.get("result") or {}).get("results") or []:
            if not isinstance(item, dict) or item.get("scope") != "read_asset_scores":
                continue
            data = item.get("data") or {}
            if not isinstance(data, dict):
                continue
            asset = str(item.get("asset") or data.get("symbol") or "").upper()
            quote = str(data.get("quote_currency") or "").upper()
            if expected_asset and asset != expected_asset:
                continue
            if expected_quote and quote != expected_quote:
                continue
            if expected_market is not None and str(data.get("market_id") or "") != str(expected_market):
                continue
            if item.get("status") != "completed":
                return {"available": False, "reason": item.get("reason") or "score_read_unavailable"}
            score = data.get("benchmark_score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                return {"available": True, "value": score, "as_of": item.get("as_of"),
                        "source_status": data.get("source_status")}
            return {"available": False, "reason": data.get("source_status") or "benchmark_incomplete"}
    return None
