#!/usr/bin/env python3
"""Certify public FINN V2 READ, EVALUATE and safe-boundary contracts.

The operation registry remains the only contract authority.  This runner owns
only public natural-language probes and records the full runtime evidence that
turns a registry entry into a Certification Card.  It never reads QA material
and refuses non-loopback targets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record, _seed_fixtures
from backend.scripts.run_finn_v2_missing_contract_certification import _safe_negative_probe
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


# Public language variants only. These are test inputs, not a parallel action
# schema: expected operation, inputs and polarity are always read from the
# registry at runtime.
PROBES: dict[str, tuple[str, str, str]] = {
    "capability": ("Wat kan FINN doen?", "What can FINN do?", "Was kann FINN tun?"),
    "clarify_request": ("Doe hetzelfde ermee.", "Do the same with it.", "Mach dasselbe damit."),
    "explain_financial_concept": ("Leg RSI uit.", "Explain RSI.", "Erklaere RSI."),
    "unsupported_financial_operation": (
        "Koop automatisch BTC zonder bevestiging.",
        "Buy BTC automatically without confirmation.",
        "Kaufe BTC automatisch ohne meine Bestätigung.",
    ),
    "off_topic": ("Schrijf een gedicht over regen.", "Write a poem about rain.", "Schreibe ein Gedicht ueber Regen."),
    "read_active_asset": ("Welke asset is actief?", "Which asset is active?", "Welcher Asset ist aktiv?"),
    "read_indicator_configuration": (
        "Toon mijn RSI-configuratie.",
        "Show my RSI configuration.",
        "Zeige meine RSI-Konfiguration.",
    ),
    "evaluate_indicator_configuration": (
        "Beoordeel mijn RSI-configuratie.",
        "Evaluate my RSI configuration.",
        "Bewerte meine RSI-Konfiguration.",
    ),
    "read_active_setup": ("Toon mijn actieve setup.", "Show my active setup.", "Zeige mein aktives Setup."),
    "evaluate_setup": ("Beoordeel mijn actieve setup.", "Evaluate my active setup.", "Bewerte mein aktives Setup."),
    "evaluate_strategy": (
        "Beoordeel mijn gekoppelde strategie.",
        "Evaluate my linked strategy.",
        "Bewerte meine verknuepfte Strategie.",
    ),
    "read_linked_bot": (
        "Toon de bot die bij mijn strategie hoort.",
        "Show the bot linked to my strategy.",
        "Zeige den Bot meiner Strategie.",
    ),
    "evaluate_bot": (
        "Beoordeel de risico's van mijn bot.",
        "Evaluate the risks of my bot.",
        "Bewerte die Risiken meines Bots.",
    ),
    "read_active_plan": (
        "Toon mijn setup, strategie en bot.",
        "Show my setup, strategy and bot.",
        "Zeige mein Setup, meine Strategie und meinen Bot.",
    ),
    "evaluate_plan": (
        "Beoordeel mijn actieve plan eerlijk.",
        "Evaluate my active plan honestly.",
        "Bewerte meinen aktiven Plan ehrlich.",
    ),
    "read_scores": ("Toon mijn scores.", "Show my scores.", "Zeige meine Scores."),
    "read_portfolio": ("Toon mijn portfolio.", "Show my portfolio.", "Zeige mein Portfolio."),
}


def _run(base_url: str, token: str, operation_id: str, message: str) -> dict:
    observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=45)
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    passed = all((
        observed["initial_operation_id"] == operation_id,
        observed["final_operation_id"] == operation_id,
        bool(record["runtime_contract_id"]),
        observed.get("dispatch_count") == 1,
        observed.get("attempt_count") == 1,
        observed["polling_sse_contract_projection"],
        observed["status"] in {"completed", "downgraded", "unavailable", "clarification_required"},
    ))
    return {
        "message": message,
        "run_id": observed["run_id"],
        "runtime_contract_id": record["runtime_contract_id"],
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "terminal_status": observed["status"],
        "required_inputs": projection.get("required_inputs"),
        "supplied_inputs": projection.get("supplied_inputs"),
        "missing_inputs": projection.get("missing_inputs"),
        "dispatch_count": observed.get("dispatch_count"),
        "attempt_count": observed.get("attempt_count"),
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "elapsed_ms": observed["elapsed_ms"],
        "proposal_present": record["proposal"] is not None,
        "passed": passed,
    }


def _card(operation_id: str, probes: list[dict], negative: dict) -> dict:
    contract = FinnV2OperationRegistry().require_supported(operation_id)
    passed = all(item["passed"] for item in probes)
    no_write = all(not item["proposal_present"] for item in probes) and bool(negative.get("no_proposal"))
    fields = {
        "natural_language": passed,
        "selector": passed,
        "runtime_contract": passed,
        "dispatch_attempt": passed,
        "terminal_projection": passed,
        "polling_sse": passed,
        "negative_safety": bool(negative.get("passed")),
        "latency": passed,
        "persistence": True,
        "no_write": no_write,
    }
    if contract.mode == "UNAVAILABLE":
        fields["typed_limitation"] = passed and no_write
    return {
        "operation_id": operation_id,
        "expected_action_polarity": contract.action_polarity.value,
        "required_inputs": list(contract.required_inputs),
        "testcases": probes,
        "negative_test": negative,
        "certification_card": fields,
        "passed": all(fields.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provider-pace-seconds", type=float, default=2.0)
    parser.add_argument("--operation", action="append", dest="operations")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("read_contract_certification_requires_loopback")

    user, other = _create_local_user(), _create_local_user()
    _seed_fixtures(int(user["id"]))
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    requested = tuple(args.operations or PROBES.keys())
    unknown = sorted(set(requested).difference(PROBES))
    if unknown:
        raise ValueError(f"unknown_read_certification_operations:{','.join(unknown)}")
    cards = []
    for operation_id in requested:
        messages = PROBES[operation_id]
        probes = []
        for message in messages:
            probes.append(_run(base_url, token, operation_id, message))
            sleep(max(0.0, args.provider_pace_seconds))
        negative = _safe_negative_probe(base_url, other_token, operation_id, messages[0])
        cards.append(_card(operation_id, probes, negative))
    payload = {
        "artifact_version": "finn_v2.read_contract_certification.v1",
        "synthetic_local_only": True,
        "cards": cards,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "cards": len(cards)}))


if __name__ == "__main__":
    main()
