"""The question, selected owner-scoped objects, and evidence for one FINN turn.

This contract checks answer coverage. It never chooses a tool or writes data.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from backend.services.finn_v2_verified_setup_reference import references_selected_setup
from backend.services.finn_v2_coach_evidence_plan import CoachEvidencePlan, coach_answer_gap


def requests_comparison(message: str) -> bool:
    """Recognize a comparison regardless of whether the user says 'compare'."""
    return bool(re.search(
        r"\b(?:vergelijk\w*|verschil\w*|compare\w*|differ\w*|"
        r"difference\w*|contrast\w*|vergleich\w*|unterschied\w*)\b",
        message, re.I,
    ))


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
        r"\b(?:beide|allebei|twee|elk|ieder|per|genoemde|vorige|die|deze|both|those|same|each|every)\b", message, re.I,
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
        # An historical *instapbeslissing* in a trade dossier describes the
        # decision event, not the current linked strategy's entry level.
        "entry": r"\b(?:entry\w*|instap(?!pen\b|beslissing\w*\b)\w*|entry level)\b",
        "confirmation": r"\b(?:trigger\w*|bevestig\w*|confirmation\w*|"
                        r"(?:instap|entry)\w*(?:bevestig|confirm)\w*)\b",
        "stop_distance": r"\b(?:stop\w*|exit\w*)\b",
        "position_size": r"\b(?:positie\w*|position\w*|inzet|size)\b",
        "cash": r"\b(?:kas|cash|saldo|balance)\b",
    }
    return [field for field, pattern in fields.items() if re.search(pattern, message, re.I)]


def _display_decimal(raw: str) -> Decimal | None:
    raw = raw.rstrip(".,")
    last_separator = max(raw.rfind("."), raw.rfind(","))
    decimal_separator = (
        raw[last_separator]
        if last_separator >= 0 and len(raw) - last_separator <= 3 else ""
    )
    normalized = "".join(
        "." if char == decimal_separator else char
        for char in raw if char.isdigit() or char == decimal_separator
    )
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


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
    focused_strategy_id: int | None = None
    focused_setup_id: int | None = None
    paper_cash_total: float | None = None
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
            if isinstance(turn_request.get("focused_setup_id"), int) and isinstance(
                turn_request.get("focused_strategy_id"), int,
            ):
                focused_setup_id = turn_request["focused_setup_id"]
                focused_strategy_id = turn_request["focused_strategy_id"]
        for item in (call.get("result") or {}).get("results") or []:
            if isinstance(item, dict) and isinstance(item.get("scope"), str):
                attempted_scopes.add(item["scope"])
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            if item.get("scope") == "read_portfolio" and re.search(r"\bPaper\b", message, re.I):
                global_cash = (data.get("global") or {}).get("cash_balance")
                if isinstance(global_cash, (int, float)) and not isinstance(global_cash, bool):
                    paper_cash_total = float(global_cash)
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
            if item.get("scope") == "read_linked_strategies" and isinstance(data.get("setup_id"), int):
                linked = [
                    row for row in data.get("strategies") or []
                    if isinstance(row, dict) and row.get("setup_id") == data["setup_id"]
                ]
                if data.get("complete") is True and len(linked) == 1:
                    strategies[data["setup_id"]] = linked[0]

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
    symbol_counts: dict[str, int] = {}
    for row in all_rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    for setup_id in target_ids:
        row = setups[setup_id]
        strategy = strategies.get(setup_id) or {}
        targets.append({
            "setup_id": setup_id,
            "name": row.get("name"),
            "evidence": {key: row[key] for key in ("symbol", "timeframe", "setup_type") if row.get(key) is not None},
            "asset_alias_unique": symbol_counts.get(str(row.get("symbol") or "").upper(), 0) == 1,
            "strategy": {key: strategy[key] for key in ("name", "entry", "stop_loss") if strategy.get(key) is not None},
        })
    if focused_setup_id not in target_ids or (
        strategies.get(focused_setup_id, {}).get("strategy_id") != focused_strategy_id
    ):
        focused_setup_id = None
        focused_strategy_id = None

    if answer_type in {"list", "compare", "weigh", "explain"}:
        selected_answer_type = answer_type
    elif requests_comparison(message):
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
        "focused_setup_id": focused_setup_id,
        "focused_strategy_id": focused_strategy_id,
        "evidence_fields": evidence_fields,
        "attempted_scopes": sorted(attempted_scopes),
        "paper_cash_total": paper_cash_total,
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
    coach = contract.get("coach_evidence_plan")
    if isinstance(coach, dict):
        required = set(coach.get("read_tools") or ())
        attempted = set(contract.get("attempted_scopes") or ())
        if not required <= attempted:
            return "coach_sources_not_checked"
        gap = coach_answer_gap(CoachEvidencePlan(
            topics=tuple(coach.get("topics") or ()),
            read_tools=tuple(required),
            decision_required=coach.get("decision_required") is True,
            next_step_required=coach.get("next_step_required") is True,
        ), answer)
        if gap:
            return gap
        score = coach.get("benchmark_score")
        if "score" in (coach.get("topics") or ()) and isinstance(score, (int, float)):
            expected_score = Decimal(str(score))
            values = [
                value for raw in re.findall(r"\b\d[\d.,]*\b", answer)
                if (value := _display_decimal(raw)) is not None
            ]
            if not any(abs(value - expected_score) < Decimal("0.05") for value in values):
                return "coach_verified_score_missing"
    expected_cash = contract.get("paper_cash_total")
    if isinstance(expected_cash, (int, float)):
        expected = Decimal(str(expected_cash))
        total_claims = re.findall(
            r"\b(?:gezamenlijk\w*|totaal\w*|total|combined|gesamt\w*)"
            r"[^.!?\n]{0,80}?\bPaper[\s-]*(?:kas\w*|cash|saldo|balance)\b"
            r"[^.!?\n\d€]{0,80}?(?:€\s*|EUR\s*)?(\d[\d.,]*)",
            answer, re.I,
        )
        if any(
            value is not None and abs(value - expected) >= Decimal("0.005")
            for value in map(_display_decimal, total_claims)
        ):
            return "paper_cash_total_conflict"
        requested = set(contract.get("requested_fields") or [])
        aggregate_requested = bool(re.search(
            r"\b(?:gezamenlijk\w*|totaal\w*|total|combined|gesamt\w*)\b",
            str(contract.get("question") or ""), re.I,
        ))
        if ({"cash", "position_size"} <= requested or
                ("cash" in requested and aggregate_requested)):
            values = [
                value for raw in re.findall(r"\b\d[\d.,]*\b", answer)
                if (value := _display_decimal(raw)) is not None
            ]
            if not any(abs(value - expected) < Decimal("0.005") for value in values):
                return "paper_cash_total_missing"
    targets = contract.get("targets") or []
    if contract.get("answer_type") == "compare" and len(targets) >= 2:
        strategy_name_counts: dict[str, int] = {}
        for target in targets:
            strategy_name = str((target.get("strategy") or {}).get("name") or "").casefold()
            if strategy_name:
                strategy_name_counts[strategy_name] = strategy_name_counts.get(strategy_name, 0) + 1
        def identifies_target(target: Mapping[str, Any]) -> bool:
            strategy_name = str((target.get("strategy") or {}).get("name") or "")
            names = (
                str(target.get("name") or ""),
                strategy_name if strategy_name_counts.get(strategy_name.casefold(), 0) == 1 else "",
            )
            if any(name and name.casefold() in answer.casefold() for name in names):
                return True
            # A natural asset-plan label is unambiguous only when the selected
            # owner-scoped comparison contains one setup for this asset.
            symbol = str((target.get("evidence") or {}).get("symbol") or "")
            return bool(target.get("asset_alias_unique") and symbol and re.search(
                rf"\b{re.escape(symbol)}\b(?:/[A-Z0-9]+)?[\s-]*"
                r"(?:concept\w*|setup\w*|plan\w*|strateg\w*)\b",
                answer, re.I,
            ))

        if any(not identifies_target(target) for target in targets):
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
        and not {"read_linked_strategy", "read_linked_strategies"}.intersection(
            contract.get("attempted_scopes") or []
        )
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
