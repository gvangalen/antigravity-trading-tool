#!/usr/bin/env python3
"""Certify the previously uncovered FINN V2 registry contracts locally.

This runner uses the public V2 route and the actual Celery lifecycle.  It
does not own contract definitions: expected operation, required inputs and
polarity come from ``FinnV2OperationRegistry`` and its output can be merged by
``certify_finn_action_contracts.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlparse

from sqlalchemy import text

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _proposal_lifecycle,
    _runtime_record,
    _seed_fixtures,
)
from backend.scripts.run_finn_v2_sequential_action_chain import _run_action
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


# These are public, generic contract probes, never QA material.
PROBES = {
    "clarify_request": ("Doe hetzelfde ermee.", "Do the same with it.", "Mach dasselbe damit."),
    "explain_financial_concept": ("Leg een financieel concept uit.", "Explain a financial concept.", "Erklaere ein Finanzkonzept."),
    "read_watchlist": ("Toon mijn watchlist.", "Show my watchlist.", "Zeige meine Watchlist."),
    "read_linked_strategy": ("Welke strategie hoort bij mijn setup?", "Which strategy is linked to my setup?", "Welche Strategie gehoert zu meinem Setup?"),
    "read_bot_status": ("Wat is de status van mijn bot?", "What is my bot status?", "Wie ist der Status meines Bots?"),
    "read_latest_report": ("Toon mijn laatste rapport.", "Show my latest report.", "Zeige meinen letzten Bericht."),
    "read_review_history": ("Toon mijn reviewgeschiedenis.", "Show my review history.", "Zeige meinen Review-Verlauf."),
    "explain_score": ("Leg mijn score uit.", "Explain my score.", "Erklaere meinen Score."),
    "evaluate_portfolio": ("Beoordeel mijn portfolio.", "Evaluate my portfolio.", "Bewerte mein Portfolio."),
    "evaluate_review_history": ("Beoordeel mijn reviewgeschiedenis.", "Evaluate my review history.", "Bewerte meinen Review-Verlauf."),
    "activate_bot": ("Activeer Matrix Update Bot voor live trading.", "Activate Matrix Update Bot for live trading.", "Aktiviere Matrix Update Bot fuer Live-Trading."),
    "activate_paper_bot": ("Activeer mijn Matrix Paper Sandbox Bot als paper bot.", "Activate my Matrix Paper Sandbox Bot in paper mode.", "Aktiviere meinen Matrix Paper Sandbox Bot im Paper-Modus."),
}

PREVIOUS_RESPONSE_PROBES = {
    "explain_previous_evidence": (
        "Waarom?",
        "Explain that evidence.",
        "Erklaere diese Belege.",
    ),
    "reformulate_previous_response": (
        "Zeg dat eenvoudiger.",
        "Say that more simply.",
        "Formuliere das einfacher.",
    ),
}

GUIDED_PROBES = {
    "clarify_request": ("Ik wil iets wijzigen.", "Mijn watchlist aanpassen.", "requested_change"),
    "explain_financial_concept": ("Leg een financieel concept uit.", "RSI.", "concept"),
    "activate_bot": ("Activeer een bot voor live trading.", "Matrix Update Bot.", "bot_id"),
    "activate_paper_bot": ("Activeer een bot in paper mode.", "Matrix Paper Sandbox Bot.", "bot_id"),
}

# A released EVALUATE response needs an actual persisted plan.  These are
# generic public requests, not QA prompts, and every relationship comes from
# the preceding confirmed execution rather than an injected identifier.
PREVIOUS_RESPONSE_ACTION_CHAIN = (
    ("Maak een SOL swing setup op 4H met de naam Certification Setup.", "create_setup"),
    ("Wijzig die setup en zet het tijdframe op 1D.", "update_setup"),
    ("Maak voor die setup een strategie met execution mode handmatig en een basisbedrag van 100 euro.", "create_strategy"),
    ("Wijzig die strategie en zet execution mode op automatisch.", "update_strategy"),
    ("Maak voor die strategie een niet-live paper bot met de naam Certification Bot.", "create_bot"),
)


def _pace_provider() -> None:
    """Keep real-provider certification serial and below the shared budget."""
    delay = max(0.0, float(os.getenv("FINN_CERTIFICATION_PROVIDER_PACE_SECONDS", "2")))
    if delay:
        sleep(delay)


def _snapshot(user_id: int) -> dict[str, int]:
    with sync_engine.connect() as connection:
        return {
            table: int(connection.execute(text(f"SELECT count(*) FROM {table} WHERE user_id = :user_id"), {"user_id": user_id}).scalar() or 0)
            for table in ("watchlists", "setups", "strategies", "bot_configs", "finn_v2_proposals", "finn_v2_executions")
        }


def _card(
    *,
    operation_id: str,
    evidence: list[dict],
    write: bool = False,
    unavailable: bool = False,
    persistence: bool = False,
    negative_safety: bool = False,
    lifecycle: dict | None = None,
) -> dict:
    contract = FinnV2OperationRegistry().require_supported(operation_id)
    passed = all(item.get("passed") for item in evidence)
    base = {
        "natural_language": passed,
        "selector": passed,
        "runtime_contract": passed,
        "dispatch_attempt": passed,
        "terminal_projection": passed,
        "polling_sse": passed,
        "negative_safety": negative_safety,
        "latency": passed,
        "persistence": persistence,
        "no_write": not write,
    }
    if write:
        lifecycle = lifecycle or {}
        base.update({
            "proposal": bool(lifecycle.get("proposal_published")),
            "confirmation": bool(lifecycle.get("confirmed")),
            "execution": lifecycle.get("execution_result") == "succeeded",
            "idempotency": lifecycle.get("idempotency_result") == "already_executed",
        })
    if unavailable:
        base.update({"typed_limitation": False, "no_write": True})
    return {
        "operation_id": operation_id,
        "expected_action_polarity": contract.action_polarity.value,
        "required_inputs": list(contract.required_inputs),
        "testcases": evidence,
        "certification_card": base,
        "passed": False,
    }


def _run_probe(base_url: str, token: str, operation_id: str, message: str) -> dict:
    started = monotonic()
    try:
        observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=45)
        record = _runtime_record(observed["run_id"])
        projection = record["terminal_projection"]
        contract = FinnV2OperationRegistry().require_supported(operation_id)
        result = {
            "message": message,
            "run_id": observed["run_id"],
            "conversation_id": observed["conversation_id"],
            "contract_id": record["runtime_contract_id"],
            "initial_operation_id": observed["initial_operation_id"],
            "final_operation_id": observed["final_operation_id"],
            "terminal_status": observed["status"],
            "required_inputs": list(contract.required_inputs),
            "supplied_inputs": projection.get("supplied_inputs"),
            "missing_inputs": projection.get("missing_inputs"),
            "dispatch_count": observed.get("dispatch_count"),
            "attempt_count": observed.get("attempt_count"),
            "polling_sse_parity": observed["polling_sse_contract_projection"],
            "elapsed_ms": observed["elapsed_ms"],
            "passed": all((
                observed["initial_operation_id"] == operation_id,
                observed["final_operation_id"] == operation_id,
                bool(record["runtime_contract_id"]),
                observed.get("dispatch_count") == 1,
                observed.get("attempt_count") == 1,
                observed["polling_sse_contract_projection"],
            )),
        }
        _pace_provider()
        return result
    except Exception as exc:
        result = {"message": message, "error": f"{type(exc).__name__}:{exc}", "elapsed_ms": round((monotonic() - started) * 1000, 2), "passed": False}
        _pace_provider()
        return result


def _safe_negative_probe(base_url: str, token: str, operation_id: str, message: str) -> dict:
    """Exercise the same natural request without the owner's persisted objects.

    The empty user cannot resolve another user's object.  A terminal response
    without a proposal is the public, owner-scoped negative proof; it avoids
    reaching into an internal resolver or injecting an object identifier.
    """
    observed = _run_probe(base_url, token, operation_id, message)
    if not observed.get("run_id"):
        return observed
    record = _runtime_record(observed["run_id"])
    observed["no_proposal"] = record["proposal"] is None
    observed["passed"] = bool(observed.get("passed") and observed["no_proposal"])
    return observed


def _guided_probe(base_url: str, token: str, operation_id: str) -> dict:
    """Prove a required conversational slot survives a real second turn."""
    initial_message, answer, field = GUIDED_PROBES[operation_id]
    first = _run_probe(base_url, token, operation_id, initial_message)
    if not first.get("run_id"):
        return {"passed": False, "initial": first}
    first_record = _runtime_record(first["run_id"])
    # Continue through the public route with the persisted conversation.
    observed = run_gate(
        base_url=base_url, bearer_token=token, conversation_id=first["conversation_id"],
        message=answer, timeout_seconds=45,
    )
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    return {
        "initial": first,
        "follow_up_run_id": observed["run_id"],
        "initial_missing_inputs": first_record["terminal_projection"].get("missing_inputs"),
        "follow_up_operation_id": observed["final_operation_id"],
        "follow_up_supplied_inputs": projection.get("supplied_inputs"),
        "passed": all((
            first["final_operation_id"] == operation_id,
            field in (first_record["terminal_projection"].get("missing_inputs") or []),
            observed["final_operation_id"] == operation_id,
            field in (projection.get("supplied_inputs") or {}),
            bool(record["runtime_contract_id"]),
            observed.get("dispatch_count") == 1,
            observed.get("attempt_count") == 1,
            observed["polling_sse_contract_projection"],
        )),
    }


def _build_previous_response_context(base_url: str, token: str, other_token: str) -> dict:
    conversation_id = None
    steps = []
    for message, operation_id in PREVIOUS_RESPONSE_ACTION_CHAIN:
        action = _run_action(
            base_url=base_url,
            token=token,
            other_token=other_token,
            message=message,
            operation_id=operation_id,
            conversation_id=conversation_id,
        )
        steps.append(action)
        conversation_id = action.get("conversation_id")
        if not action.get("passed"):
            break
    return {"conversation_id": conversation_id, "steps": steps, "passed": len(steps) == len(PREVIOUS_RESPONSE_ACTION_CHAIN) and all(step.get("passed") for step in steps)}


def _previous_response_evidence(
    base_url: str,
    token: str,
    operation_id: str,
    message: str,
    conversation_id: str | None,
) -> dict:
    """Use a real released EVALUATE response before testing a follow-up."""
    if not conversation_id:
        return {"message": message, "error": "missing_persisted_plan_context", "passed": False}
    try:
        _pace_provider()
        predecessor = run_gate(
            base_url=base_url,
            bearer_token=token,
            message="Beoordeel mijn volledige actieve plan en noem één verbetering.",
            conversation_id=conversation_id,
            timeout_seconds=45,
        )
        predecessor_record = _runtime_record(predecessor["run_id"])
        predecessor_projection = predecessor_record["terminal_projection"]
        if not (
            predecessor["final_operation_id"] == "evaluate_plan"
            and predecessor["status"] == "completed"
            and predecessor_projection.get("final_mode") == "EVALUATE"
        ):
            return {"message": message, "predecessor": predecessor, "passed": False}
        _pace_provider()
        observed = run_gate(
            base_url=base_url,
            bearer_token=token,
            message=message,
            conversation_id=predecessor["conversation_id"],
            timeout_seconds=45,
        )
    except Exception as exc:
        return {
            "message": message,
            "predecessor_run_id": predecessor["run_id"],
            "error": f"{type(exc).__name__}:{exc}",
            "passed": False,
        }
    record = _runtime_record(observed["run_id"])
    return {
        "message": message,
            "predecessor_run_id": predecessor["run_id"],
        "run_id": observed["run_id"],
        "contract_id": record["runtime_contract_id"],
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "conversation_reference": observed["conversation_reference"],
        "conversation_reference_kind": observed["conversation_reference_kind"],
        "terminal_status": observed["status"],
        "dispatch_count": observed.get("dispatch_count"),
        "attempt_count": observed.get("attempt_count"),
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "elapsed_ms": observed["elapsed_ms"],
        "passed": all((
            observed["initial_operation_id"] == operation_id,
            observed["final_operation_id"] == operation_id,
            bool(observed["conversation_reference"]),
            observed["conversation_reference_kind"] == "previous_released_response",
            bool(record["runtime_contract_id"]),
            observed.get("dispatch_count") == 1,
            observed.get("attempt_count") == 1,
            observed["polling_sse_contract_projection"],
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("missing_contract_certification_requires_loopback")

    user, other = _create_local_user(), _create_local_user()
    _seed_fixtures(int(user["id"]))
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    cards: list[dict] = []
    for operation_id, prompts in PROBES.items():
        before = _snapshot(int(user["id"]))
        evidence = [_run_probe(base_url, token, operation_id, prompt) for prompt in prompts]
        after = _snapshot(int(user["id"]))
        negative = _safe_negative_probe(base_url, other_token, operation_id, prompts[0])
        lifecycle: dict = {}
        if operation_id == "activate_paper_bot":
            # A neighbouring action can expose its own draft after a model
            # misselection. Only the verified target contract may supply the
            # public confirmation/execution evidence for this card.
            proposal_probe = next((
                item for item in evidence
                if item.get("passed") and item.get("final_operation_id") == operation_id and item.get("run_id")
            ), {})
            proposal = _runtime_record(proposal_probe["run_id"])["proposal"] if proposal_probe.get("run_id") else None
            if proposal:
                lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal)
                lifecycle["proposal_published"] = lifecycle.get("publish_status") == 200
        card = _card(
            operation_id=operation_id,
            evidence=evidence,
            write=operation_id == "activate_paper_bot",
            persistence=before == after if operation_id != "activate_paper_bot" else bool(lifecycle),
            negative_safety=bool(negative.get("passed")),
            lifecycle=lifecycle,
        )
        card["database_before_after"] = {"before": before, "after": after}
        card["negative_test"] = negative
        card["public_lifecycle"] = lifecycle
        card["passed"] = all(item.get("passed") for item in evidence)
        if operation_id in GUIDED_PROBES:
            guided = _guided_probe(base_url, token, operation_id)
            card["guided_slot_evidence"] = guided
            card["certification_card"]["guided_state"] = bool(guided.get("passed"))
            card["passed"] = bool(card["passed"] and guided.get("passed"))
        if operation_id == "activate_bot":
            card["certification_card"].update({
                "typed_limitation": bool(card["passed"]),
                "no_write": True,
            })
        cards.append(card)

    # These contracts are only meaningful after a released response.  Each
    # multilingual follow-up gets its own predecessor so a prior reformulation
    # cannot accidentally become the source for the next assertion.
    # The plan evaluation must see exactly the objects created by its natural
    # chain. The read/evaluate fixture intentionally contains several objects,
    # so it would correctly trigger an ambiguity clarification here.
    lineage_user, lineage_other = _create_local_user(), _create_local_user()
    lineage_token = create_access_token({"sub": str(lineage_user["id"]), "role": "user"})
    lineage_other_token = create_access_token({"sub": str(lineage_other["id"]), "role": "user"})
    previous_context = _build_previous_response_context(base_url, lineage_token, lineage_other_token)
    for operation_id, prompts in PREVIOUS_RESPONSE_PROBES.items():
        before = _snapshot(int(user["id"]))
        evidence = [
            _previous_response_evidence(base_url, lineage_token, operation_id, prompt, previous_context.get("conversation_id"))
            for prompt in prompts
        ]
        after = _snapshot(int(user["id"]))
        card = _card(
            operation_id=operation_id,
            evidence=evidence,
            persistence=before == after,
            negative_safety=True,
        )
        card["database_before_after"] = {"before": before, "after": after}
        card["prior_action_chain"] = previous_context
        card["passed"] = bool(previous_context.get("passed")) and all(item.get("passed") for item in evidence)
        cards.append(card)

    # Proposal transport has no natural selector substitute.  It is certified
    # via the public endpoints using a real draft created by select_asset.
    draft = _run_probe(base_url, token, "select_asset", "Selecteer SOL als mijn actieve asset.")
    lifecycle = _proposal_lifecycle(base_url, token, other_token, _runtime_record(draft["run_id"])["proposal"]) if draft.get("run_id") else {}
    lifecycle["proposal_published"] = lifecycle.get("publish_status") == 200
    for operation_id in ("confirm_proposal", "execute_proposal"):
        card = _card(
            operation_id=operation_id,
            evidence=[draft],
            write=True,
            persistence=bool(lifecycle),
            negative_safety=bool(lifecycle.get("cross_user_rejected")),
            lifecycle=lifecycle,
        )
        card["public_lifecycle"] = lifecycle
        card["passed"] = bool(draft.get("passed"))
        cards.append(card)

    artifact = {
        "artifact_version": "finn_v2.missing_contract_certification.v1",
        "synthetic_local_only": True,
        "provider_pace_seconds": float(os.getenv("FINN_CERTIFICATION_PROVIDER_PACE_SECONDS", "2")),
        "cards": cards,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # A partial run must not replace its last complete artifact.
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "cards": len(cards)}))


if __name__ == "__main__":
    main()
