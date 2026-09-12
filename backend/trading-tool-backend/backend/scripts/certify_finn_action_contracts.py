#!/usr/bin/env python3
"""Materialize registry-owned FINN contract certification cards.

The script deliberately derives every card from ``FinnV2OperationRegistry``.
It is an inventory and evidence merger, not a second action schema: runtime
matrix artifacts supply measured facts while missing evidence remains explicit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


def category(contract: Any) -> str:
    if contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
        return "CREATE_PROPOSAL/ACTION_PROPOSAL"
    if contract.mode == "EVALUATE":
        return "EVALUATE"
    if contract.mode in {"UNAVAILABLE", "CLARIFICATION"} or not contract.supported:
        return "unsupported/safety"
    return "READ"


def load_artifact(path: Path | None) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path else {}


def complete_card(evidence: dict[str, Any] | None, contract: Any) -> bool:
    """Accept runtime proof only when it covers the contract's own boundary.

    Older matrix artifacts expose a useful ``passed`` summary, but that is not
    enough for a Contract Certification Card.  In particular, a write needs
    public proposal/confirmation/execution evidence while a read must prove it
    stayed read-only.  The dedicated certification runner emits these fields.
    """
    if not evidence or not evidence.get("passed"):
        return False
    card = evidence.get("certification_card") or {}
    common = {
        "natural_language",
        "selector",
        "runtime_contract",
        "dispatch_attempt",
        "terminal_projection",
        "polling_sse",
        "negative_safety",
        "latency",
    }
    # Confirmation and execution consume their required proposal resource in
    # the public HTTP path, not through a conversational slot. Their cards
    # require endpoint-level ownership/idempotency evidence instead.
    guided = {
        "guided_state"
    } if getattr(contract, "required_inputs", ()) and contract.mode not in {"CONFIRMATION", "EXECUTION"} else set()
    if getattr(contract, "policy_class", None) == "high_risk_action":
        # A live-action safety contract succeeds by publishing its typed
        # policy boundary without creating a proposal or execution.
        required = common | guided | {"typed_limitation", "no_write", "persistence"}
    elif contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
        required = common | guided | {"proposal", "confirmation", "execution", "idempotency", "persistence"}
    elif contract.mode == "UNAVAILABLE" or not contract.supported:
        required = common | guided | {"typed_limitation", "no_write"}
    else:
        required = common | guided | {"persistence", "no_write"}
    return all(card.get(field) is True for field in required)


def has_measured_runtime_evidence(evidence: dict[str, Any] | None) -> bool:
    """Distinguish incomplete proof from no test at all.

    Historic action-matrix artifacts predate Certification Cards.  They do
    contain real public-route measurements, but not every field the newer
    card requires.  Reporting those as NOT_TESTED hid existing evidence and
    made certification triage less trustworthy.
    """
    if not evidence:
        return False
    return bool(evidence.get("run_id") or evidence.get("runtime_contract_id") or evidence.get("testcases"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--write-matrix", type=Path)
    parser.add_argument("--runtime-matrix", type=Path)
    parser.add_argument("--lineage-artifact", type=Path)
    parser.add_argument("--contract-evidence", type=Path)
    parser.add_argument("--missing-contract-evidence", type=Path)
    parser.add_argument("--write-language-evidence", type=Path)
    args = parser.parse_args()
    write_matrix = load_artifact(args.write_matrix)
    runtime_matrix = load_artifact(args.runtime_matrix)
    lineage_artifact = load_artifact(args.lineage_artifact)
    contract_evidence = load_artifact(args.contract_evidence)
    missing_contract_evidence = load_artifact(args.missing_contract_evidence)
    write_language_evidence = load_artifact(args.write_language_evidence)
    measured = {
        item.get("expected_operation_id"): item
        for item in (
            (write_matrix.get("steps") or [])
            + (write_matrix.get("results") or [])
            + (runtime_matrix.get("cases") or [])
        )
        if item.get("expected_operation_id")
    }
    # The isolated action matrix uses ``operation_id`` rather than the public
    # matrix's ``expected_operation_id``.  Both are measurements of the same
    # registry key, not separate contract definitions.
    for item in write_matrix.get("results") or []:
        if item.get("operation_id"):
            measured[item["operation_id"]] = item
    for item in lineage_artifact.get("supporting_action_cases") or []:
        measured[item.get("expected_operation_id")] = item
    for item in (lineage_artifact.get("published_cases") or {}).values():
        if item:
            measured[item.get("expected_operation_id")] = item
    for item in contract_evidence.get("cards") or []:
        if item.get("operation_id"):
            measured[item["operation_id"]] = item
    for item in missing_contract_evidence.get("cards") or []:
        if item.get("operation_id"):
            measured[item["operation_id"]] = item
    language_cards = {
        item.get("operation_id"): item
        for item in write_language_evidence.get("cards") or []
        if item.get("operation_id")
    }
    # The isolated action matrix is the public lifecycle authority for safe
    # writes. The multilingual companion proves natural language selection;
    # guided-state coverage remains false until every registry-required slot
    # is individually exercised, rather than being inferred from one happy
    # path.
    for item in write_matrix.get("results") or []:
        operation_id = item.get("operation_id")
        language = language_cards.get(operation_id)
        if not operation_id or not language:
            continue
        if item.get("status") != "PASS" or not language.get("passed"):
            continue
        lifecycle = {
            "natural_language": True,
            "selector": True,
            "guided_state": bool((item.get("incomplete_follow_up") or {}).get("passed")),
            "runtime_contract": bool(item.get("runtime_contract_id")),
            "dispatch_attempt": item.get("dispatch_count") == 1 and item.get("attempt_count") == 1,
            "terminal_projection": bool(item.get("terminal_status")),
            "polling_sse": bool(item.get("polling_sse_parity")),
            "negative_safety": bool(item.get("cross_user_rejected")),
            "latency": item.get("elapsed_ms") is not None,
            "proposal": bool(item.get("proposal_id")),
            "confirmation": bool(item.get("confirmed")),
            "execution": item.get("execution_result") == "succeeded",
            "idempotency": item.get("idempotency_result") == "already_executed",
            "persistence": True,
        }
        measured[operation_id] = {
            **item,
            "passed": True,
            "multilingual_proposal_cases": language.get("testcases"),
            "certification_card": lifecycle,
        }
    registry = FinnV2OperationRegistry()
    cards = []
    for contract in registry.list():
        evidence = measured.get(contract.operation_id)
        cards.append({
            "operation_id": contract.operation_id,
            "group": category(contract),
            "action_polarity": contract.action_polarity.value,
            "purpose": contract.semantic_description,
            "required_inputs": list(contract.required_inputs),
            "optional_inputs": list(contract.optional_inputs),
            "contextual_reference_inputs": list(contract.contextual_reference_inputs),
            "canonical_scopes": list(contract.required_scopes),
            "allowed_context_policy": contract.context_policy,
            "owner_scoped_resolution": bool(contract.contextual_reference_inputs),
            "lineage_sources": ["verified", "released", "degraded"] if contract.requires_verified_context else [],
            "missing_input_behavior": contract.ambiguity_rule,
            "allowed_terminal_outcomes": list(contract.allowed_terminal_outcomes),
            "proposal": {"type": contract.proposal_type, "confirmation_required": contract.confirmation_required},
            "action_adapter": contract.execution_adapter,
            "idempotency_rule": contract.idempotency_rule,
            "postcondition": contract.postcondition,
            "safety": {"policy_class": contract.policy_class, "supported": contract.supported},
            "runtime_evidence": evidence or {"status": "NOT_TESTED"},
            "certification": (
                "PASS" if complete_card(evidence, contract)
                else "PARTIAL" if has_measured_runtime_evidence(evidence)
                else "NOT_TESTED"
            ),
        })
    artifact = {
        "artifact_version": "finn_action_contract_certification.v1",
        "registry_version": registry.VERSION,
        "contract_count": len(cards),
        "groups": {name: sum(card["group"] == name for card in cards) for name in {
            "READ", "EVALUATE", "CREATE_PROPOSAL/ACTION_PROPOSAL", "unsupported/safety"
        }},
        "cards": cards,
        "evidence_paths": {
            "write_matrix": str(args.write_matrix) if args.write_matrix else None,
            "runtime_matrix": str(args.runtime_matrix) if args.runtime_matrix else None,
            "lineage_artifact": str(args.lineage_artifact) if args.lineage_artifact else None,
            "contract_evidence": str(args.contract_evidence) if args.contract_evidence else None,
            "missing_contract_evidence": str(args.missing_contract_evidence) if args.missing_contract_evidence else None,
            "write_language_evidence": str(args.write_language_evidence) if args.write_language_evidence else None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
