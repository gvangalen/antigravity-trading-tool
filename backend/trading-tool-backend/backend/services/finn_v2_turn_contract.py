"""The question, selected owner-scoped objects, and evidence for one FINN turn.

This contract checks answer coverage. It never chooses a tool or writes data.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from backend.services.finn_v2_verified_setup_reference import references_selected_setup


def referenced_setup_rows(
    *, message: str, rows: list[dict[str, Any]],
    previous_contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Select positive names, or re-read the previously verified pair."""
    positive = []
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        match = re.search(re.escape(name), message, re.I)
        if match and not re.search(r"\b(?:niet|not|kein|zonder)\s*$", message[max(0, match.start() - 12):match.start()], re.I):
            positive.append(row)
    if len(positive) >= 2:
        return positive
    prior_ids = {
        target.get("setup_id") for target in (previous_contract or {}).get("targets") or []
        if isinstance(target, dict) and isinstance(target.get("setup_id"), int)
    }
    pair_reference = bool(re.search(
        r"\b(?:beide|allebei|twee|genoemde|vorige|die|deze|both|those|same)\b", message, re.I,
    ))
    if len(prior_ids) == 2 and pair_reference and (
        not positive or positive[0].get("setup_id") in prior_ids
    ):
        pair = [row for row in rows if row.get("setup_id") in prior_ids]
        if len(pair) == 2:
            return pair
    return positive if positive else rows


def _requested_fields(message: str) -> list[str]:
    fields = {
        "asset": r"\b(?:asset|symbol|symbool)\b",
        "timeframe": r"\b(?:timeframe|tijdframe|4h|1d|1h|1w|15m|30m)\b",
        "setup_type": r"\b(?:type|soort)\b",
        "strategy_name": r"\b(?:strategienaam|strategy name|welke strategie|which strategy|welche strategie)\b",
        "entry": r"\b(?:entry\w*|instap(?!pen\b)\w*|entry level)\b",
        "confirmation": r"\b(?:trigger\w*|bevestig\w*|confirmation\w*|"
                        r"(?:instap|entry)\w*(?:bevestig|confirm)\w*)\b",
        "stop_distance": r"\b(?:stop\w*|exit\w*)\b",
        "position_size": r"\b(?:positie\w*|position\w*|inzet|size)\b",
    }
    return [field for field, pattern in fields.items() if re.search(pattern, message, re.I)]


def build_turn_contract(
    *, message: str, tool_trace: tuple[dict[str, Any], ...],
    previous_subject: Mapping[str, Any] | None = None,
    previous_contract: Mapping[str, Any] | None = None,
    answer_type: str | None = None,
) -> dict[str, Any]:
    """Bind named targets to completed reads, never to model-supplied IDs."""
    setups: dict[int, dict[str, Any]] = {}
    strategies: dict[int, dict[str, Any]] = {}
    evidence_fields = []
    attempted_scopes: set[str] = set()
    model_answer_type: str | None = None
    resolved_target_ids: list[int] = []
    for call in tool_trace:
        turn_request = (call.get("result") or {}).get("turn_request") or {}
        if isinstance(turn_request, dict):
            if turn_request.get("answer_type") in {"list", "compare", "explain"}:
                model_answer_type = turn_request["answer_type"]
            if isinstance(turn_request.get("target_ids"), list):
                resolved_target_ids = [
                    value for value in turn_request["target_ids"]
                    if isinstance(value, int)
                ]
        for item in (call.get("result") or {}).get("results") or []:
            if isinstance(item, dict) and isinstance(item.get("scope"), str):
                attempted_scopes.add(item["scope"])
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            evidence_fields.append({
                "scope": item.get("scope"), "fields": sorted(data.keys()),
            })
            if item.get("scope") == "read_saved_setup_inventory":
                rows = data.get("setups") or []
            elif item.get("scope") == "read_active_setup":
                rows = [data]
            else:
                rows = []
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("setup_id"), int):
                    setups[row["setup_id"]] = {**setups.get(row["setup_id"], {}), **row}
            if item.get("scope") == "read_linked_strategy" and isinstance(data.get("setup_id"), int):
                strategies[data["setup_id"]] = data

    all_rows = list(setups.values())
    selected_rows = referenced_setup_rows(
        message=message, rows=all_rows, previous_contract=previous_contract,
    )
    named_ids = [row["setup_id"] for row in selected_rows] if selected_rows is not all_rows else []
    prior_id = (previous_subject or {}).get("setup_id")
    prior_asset = str((previous_subject or {}).get("symbol") or "")
    if (
        not named_ids and isinstance(prior_id, int) and prior_id in setups
        and references_selected_setup(message, prior_asset)
    ):
        named_ids = [prior_id]

    bound_ids = [setup_id for setup_id in resolved_target_ids if setup_id in setups]
    target_ids = bound_ids or named_ids or ([next(iter(setups))] if len(setups) == 1 else [])
    targets = []
    for setup_id in target_ids:
        row = setups[setup_id]
        strategy = strategies.get(setup_id) or {}
        targets.append({
            "setup_id": setup_id,
            "name": row.get("name"),
            "evidence": {key: row[key] for key in ("symbol", "timeframe", "setup_type") if row.get(key) is not None},
            "strategy": {key: strategy[key] for key in ("name", "entry", "stop_loss") if strategy.get(key) is not None},
        })

    if answer_type in {"list", "compare", "weigh", "explain"}:
        selected_answer_type = answer_type
    elif re.search(r"\b(?:vergelijk\w*|verschil\w*|compare\w*|vergleich\w*)\b", message, re.I):
        selected_answer_type = "compare"
    elif re.search(r"\b(?:verstandiger|afweging|weeg|wegen|wise|trade.off)\b", message, re.I):
        selected_answer_type = "weigh"
    elif model_answer_type:
        selected_answer_type = model_answer_type
    else:
        selected_answer_type = "explain"
    if (
        selected_answer_type == "compare" and not targets
        and re.search(r"\b(?:die twee|deze twee|beide|allebei|those two|both)\b", message, re.I)
        and len((previous_contract or {}).get("targets") or []) == 2
    ):
        # A follow-up can compare the already verified pair without another
        # read. Preserve its identities even when this turn has no tool call.
        targets = [dict(target) for target in previous_contract["targets"]]
        evidence_fields = list(previous_contract.get("evidence_fields") or [])
    requested_fields = _requested_fields(message)
    if (
        selected_answer_type == "weigh"
        and (previous_contract or {}).get("answer_type") == "weigh"
        and "stop_distance" in requested_fields
        and "position_size" in ((previous_contract or {}).get("requested_fields") or [])
        and re.search(r"\b(?:afweging|trade.off|abwägung|deze|die|same|zelfde)\b", message, re.I)
        and "position_size" not in requested_fields
    ):
        # A direct continuation of the stop/size tradeoff keeps both sides of
        # that question even when the trader now asks about maximum loss.
        requested_fields.append("position_size")
    return {
        "question": message,
        "answer_type": selected_answer_type,
        "requested_fields": requested_fields,
        "targets": targets,
        "evidence_fields": evidence_fields,
        "attempted_scopes": sorted(attempted_scopes),
        "saved_subject_reference": bool(
            (isinstance(prior_id, int)
             and references_selected_setup(message, prior_asset))
            or re.search(
                r"\b(?:mijn|my|meine)\s+(?:opgeslagen\s+|saved\s+|gespeicherte\s+)?"
                r"(?:setup|plan|strateg\w*)\b",
                message, re.I,
            )
        ),
    }


def turn_contract_gap(contract: Mapping[str, Any], answer: str) -> str | None:
    """Only reject objectively missing selected objects or strategy fields."""
    targets = contract.get("targets") or []
    if contract.get("answer_type") == "compare" and len(targets) >= 2:
        if any(str(target.get("name") or "").casefold() not in answer.casefold() for target in targets):
            return "comparison_targets_missing"
        timeframes = [
            str((target.get("evidence") or {}).get("timeframe") or "")
            for target in targets
        ]
        if "timeframe" in (contract.get("requested_fields") or []) and all(timeframes) and len(set(timeframes)) > 1 and any(
            not re.search(rf"\b{re.escape(timeframe)}\b", answer, re.I)
            for timeframe in timeframes
        ):
            return "comparison_fields_missing"
    fields = contract.get("requested_fields") or []
    if (
        "entry" in fields
        and contract.get("saved_subject_reference")
        and "read_linked_strategy" not in (contract.get("attempted_scopes") or [])
    ):
        return "linked_strategy_not_checked"
    if contract.get("answer_type") == "weigh" and {"stop_distance", "position_size"} <= set(fields):
        if not re.search(r"\b(?:stop\w*|exit\w*)\b", answer, re.I) or not re.search(
            r"\b(?:positie\w*|omvang|grootte|inzet|aantal|size|units?)\b", answer, re.I,
        ):
            return "risk_tradeoff_topic_missing"
    if len(targets) == 1 and "strategy_name" in fields:
        name = str((targets[0].get("strategy") or {}).get("name") or "")
        if name and name.casefold() not in answer.casefold():
            return "strategy_name_missing"
    if len(targets) == 1 and "entry" in fields:
        entry = str((targets[0].get("strategy") or {}).get("entry") or "")
        digits = re.sub(r"\D", "", entry)
        answer_numbers = [
            re.sub(r"\D", "", token)
            for token in re.findall(r"\d[\d.,]*", answer)
        ]
        if digits and digits not in answer_numbers:
            return "strategy_entry_missing"
    return None


def can_compose_after_first_read(contract: Mapping[str, Any]) -> bool:
    """A general tradeoff needs a bounded explanation, not repeated account reads."""
    requested_facts = set(contract.get("requested_fields") or ())
    return bool(
        contract.get("answer_type") == "weigh"
        and not contract.get("targets")
        and {"stop_distance", "position_size"} <= requested_facts
        and not requested_facts & {
            "asset", "timeframe", "setup_type", "strategy_name", "entry", "confirmation",
        }
    )
