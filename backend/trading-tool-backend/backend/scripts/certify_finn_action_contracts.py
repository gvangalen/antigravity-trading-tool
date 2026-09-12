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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--write-matrix", type=Path)
    parser.add_argument("--runtime-matrix", type=Path)
    parser.add_argument("--lineage-artifact", type=Path)
    args = parser.parse_args()
    write_matrix = load_artifact(args.write_matrix)
    runtime_matrix = load_artifact(args.runtime_matrix)
    lineage_artifact = load_artifact(args.lineage_artifact)
    measured = {
        item.get("expected_operation_id"): item
        for item in (write_matrix.get("steps") or []) + (runtime_matrix.get("cases") or [])
        if item.get("expected_operation_id")
    }
    for item in lineage_artifact.get("supporting_action_cases") or []:
        measured[item.get("expected_operation_id")] = item
    for item in (lineage_artifact.get("published_cases") or {}).values():
        if item:
            measured[item.get("expected_operation_id")] = item
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
            "certification": "PASS" if evidence and evidence.get("passed") else "NOT_TESTED",
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
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
