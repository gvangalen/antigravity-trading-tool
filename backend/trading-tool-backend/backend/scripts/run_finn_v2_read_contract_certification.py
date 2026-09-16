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
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _insert_bot,
    _insert_setup,
    _insert_strategy,
    _runtime_record,
    _seed_fixtures,
    sync_engine,
)
from backend.scripts.run_finn_v2_missing_contract_certification import _safe_negative_probe
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


# Public language variants only. These are test inputs, not a parallel action
# schema: expected operation, inputs and polarity are always read from the
# registry at runtime.
PROBES: dict[str, tuple[str, str, str]] = {
    "capability": ("Wat kan FINN doen?", "What can FINN do?", "Was kann FINN tun?"),
    # ``unavailable`` is a system fallback rather than a user-selectable
    # intent.  Its public lifecycle is run only with the local, fail-closed
    # selector fault injection enabled.
    "unavailable": (
        "Leg RSI uit.",
        "Explain RSI.",
        "Erklaere RSI.",
    ),
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
    "read_linked_strategy": (
        "Toon de strategie die aan mijn setup is gekoppeld.",
        "Show the strategy linked to my setup.",
        "Zeige die mit meinem Setup verknuepfte Strategie.",
    ),
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


def _run(
    base_url: str,
    token: str,
    operation_id: str,
    message: str,
    *,
    workspace_hints: dict[str, int] | None = None,
    conversation_id: str | None = None,
) -> dict:
    observed = run_gate(
        base_url=base_url,
        bearer_token=token,
        message=message,
        timeout_seconds=45,
        workspace_hints=workspace_hints,
        conversation_id=conversation_id,
    )
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    contract = FinnV2OperationRegistry().require_supported(operation_id)
    response = dict(projection.get("response") or {})
    response_text = " ".join(
        str(response.get(key) or "")
        for key in ("content", "response", "direct_answer", "main_observation")
    ).strip()
    verifier = dict(projection.get("verifier") or {})
    missing_response_fields = list(verifier.get("missing_response_fields") or [])
    internal_codes_visible = any(
        code in response_text
        for code in (
            "response_scope_incomplete",
            "response_field_incomplete",
            "response_not_answering_question",
            "lifecycle_deadline_exceeded",
        )
    )
    passed = all((
        observed["initial_operation_id"] == operation_id,
        observed["final_operation_id"] == operation_id,
        bool(record["runtime_contract_id"]),
        observed.get("dispatch_count") == 1,
        observed.get("attempt_count") == 1,
        observed["polling_sse_contract_projection"],
        observed["status"] == "completed",
        not missing_response_fields,
        bool(response_text),
        not internal_codes_visible,
    ))
    return {
        "message": message,
        "run_id": observed["run_id"],
        "conversation_id": observed["conversation_id"],
        "conversation_reference": projection.get("conversation_reference"),
        "conversation_reference_kind": projection.get("conversation_reference_kind"),
        "runtime_contract_id": record["runtime_contract_id"],
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "terminal_status": observed["status"],
        "required_response_fields": list(contract.required_response_fields),
        "missing_response_fields": missing_response_fields,
        "response_text": response_text,
        "internal_codes_visible": internal_codes_visible,
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
    reference_probes = [item for item in probes if item.get("context_mode") == "previous_response"]
    persistence = bool(reference_probes) and all(
        item.get("passed")
        and item.get("conversation_reference")
        and item.get("conversation_reference_kind") == "previous_verified_response"
        and bool((item.get("reference_primer") or {}).get("passed"))
        for item in reference_probes
    )
    fields = {
        "natural_language": passed,
        "selector": passed,
        "runtime_contract": passed,
        "dispatch_attempt": passed,
        "terminal_projection": passed,
        "polling_sse": passed,
        "negative_safety": bool(negative.get("passed")),
        "latency": passed,
        "persistence": persistence,
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
    parser.add_argument("--runs-per-operation", type=int)
    parser.add_argument("--operation", action="append", dest="operations")
    args = parser.parse_args()
    if args.runs_per_operation is not None and args.runs_per_operation < 1:
        raise ValueError("read_contract_certification_runs_must_be_positive")
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("read_contract_certification_requires_loopback")

    other = _create_local_user()
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    requested = tuple(args.operations or PROBES.keys())
    unknown = sorted(set(requested).difference(PROBES))
    if unknown:
        raise ValueError(f"unknown_read_certification_operations:{','.join(unknown)}")
    cards = []
    for operation_id in requested:
        if operation_id == "unavailable" and not (
            os.getenv("APP_ENV") == "local_finn"
            and os.getenv("FINN_V2_TEST_FORCE_SELECTOR_UNAVAILABLE") == "1"
        ):
            raise ValueError("unavailable_contract_certification_requires_local_forced_provider_failure")
        messages = PROBES[operation_id]
        setup_name = "Atlas Setup"
        strategy_name = "Atlas Strategy"
        bot_name = "Atlas Paper Bot"
        user = _create_local_user()
        _seed_fixtures(int(user["id"]))
        with sync_engine.begin() as connection:
            setup_id = _insert_setup(
                connection, int(user["id"]), setup_name
            )
            strategy_id = _insert_strategy(
                connection,
                int(user["id"]),
                setup_id,
                strategy_name,
            )
            bot_id = _insert_bot(
                connection,
                int(user["id"]),
                strategy_id,
                bot_name,
            )
        workspace_hints = {
            "setup_id": setup_id,
            "strategy_id": strategy_id,
            "bot_id": bot_id,
        }
        token = create_access_token({"sub": str(user["id"]), "role": "user"})
        reference_user = _create_local_user()
        _seed_fixtures(int(reference_user["id"]))
        with sync_engine.begin() as connection:
            reference_setup_id = _insert_setup(
                connection,
                int(reference_user["id"]),
                setup_name,
            )
            reference_strategy_id = _insert_strategy(
                connection,
                int(reference_user["id"]),
                reference_setup_id,
                strategy_name,
            )
            reference_bot_id = _insert_bot(
                connection,
                int(reference_user["id"]),
                reference_strategy_id,
                bot_name,
            )
        reference_token = create_access_token(
            {"sub": str(reference_user["id"]), "role": "user"}
        )
        natural_messages = {
            "read_active_setup": f'Toon setup "{setup_name}".',
            "read_linked_strategy": f'Toon strategie "{strategy_name}".',
            "read_linked_bot": f'Toon bot "{bot_name}".',
        }
        reference_messages = {
            "read_active_setup": "Toon diezelfde setup opnieuw.",
            "read_linked_strategy": "Toon diezelfde strategie opnieuw.",
            "read_linked_bot": "Toon diezelfde bot opnieuw.",
        }
        probes = []
        run_count = args.runs_per_operation or len(messages)
        for index in range(run_count):
            context_mode = ("active_context", "natural_name", "previous_response")[index % 3]
            if context_mode == "active_context" or operation_id not in natural_messages:
                probe = _run(
                    base_url,
                    token,
                    operation_id,
                    messages[index % len(messages)],
                    workspace_hints=workspace_hints,
                )
            elif context_mode == "natural_name":
                probe = _run(
                    base_url,
                    token,
                    operation_id,
                    natural_messages[operation_id],
                )
            else:
                primer = _run(
                    base_url,
                    reference_token,
                    operation_id,
                    natural_messages[operation_id],
                )
                probe = _run(
                    base_url,
                    reference_token,
                    operation_id,
                    reference_messages[operation_id],
                    conversation_id=primer["conversation_id"],
                )
                probe["reference_primer"] = primer
            probe["context_mode"] = context_mode
            probe["sequence"] = index + 1
            if context_mode == "previous_response" and (
                not probe.get("conversation_reference")
                or probe.get("conversation_reference_kind") != "previous_verified_response"
            ):
                probe["passed"] = False
            probes.append(probe)
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
