#!/usr/bin/env python3
"""Run the seven published 346013 regressions through FINN's public runtime.

The source cases were explicitly declassified for Build. This runner preserves
their prompts and disclosed conversation context, but only against an isolated
loopback fixture. IDs remain in persisted action-results and never enter a
user message or selector input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_sequential_action_chain import _run_action
from backend.utils.auth_utils import create_access_token


DECLASSIFIED_ARTIFACT_SHA256 = "0da3aaaead747ff778bb551229be408a211a15c6826477e9e4738a3f0dc37d1f"


def _read_case(
    base_url: str,
    token: str,
    message: str,
    expected_operation_id: str,
    conversation_id: str | None = None,
    expected_conversation_reference_kind: str | None = None,
) -> dict:
    observed = run_gate(
        base_url=base_url,
        bearer_token=token,
        message=message,
        conversation_id=conversation_id,
        timeout_seconds=75,
    )
    return {
        "prompt": message,
        "expected_operation_id": expected_operation_id,
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "conversation_id": observed["conversation_id"],
        "run_id": observed["run_id"],
        "terminal_status": observed["status"],
        "conversation_reference": observed["conversation_reference"],
        "conversation_reference_kind": observed["conversation_reference_kind"],
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "passed": (
            observed["initial_operation_id"] == expected_operation_id
            and observed["final_operation_id"] == expected_operation_id
            and observed["status"] in {"completed", "downgraded", "unavailable", "failed"}
            and observed["polling_sse_contract_projection"]
            and (
                expected_conversation_reference_kind is None
                or observed["conversation_reference_kind"] == expected_conversation_reference_kind
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("declassified_regressions_require_loopback")

    primary, other = _create_local_user(), _create_local_user()
    token = create_access_token({"sub": str(primary["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    conversation_id = None
    action_cases: list[dict] = []
    # q28/q29 are disclosed prerequisite context for q30. They are recorded
    # as support turns, not counted among the seven released QA cases.
    actions = (
        ("q28_context", "Maak een SOL swing trade setup op 4H met de naam QA Lifecycle 31DD Setup.", "create_setup"),
        ("q29_context", "Wijzig de setup die je zojuist hebt gemaakt en zet de timeframe op 1D.", "update_setup"),
        ("q30", "Maak voor die setup een strategie met execution mode handmatig en een basisbedrag van 100 euro.", "create_strategy"),
        ("q31", "Wijzig die strategie en zet execution mode op automatisch.", "update_strategy"),
        ("q32", "Maak voor die strategie een niet-live paper bot met de naam QA Lifecycle 31DD Bot.", "create_bot"),
        ("q33", "Wijzig die bot en zet het budget op 100 euro.", "update_bot"),
        ("q34", "Deactiveer die bot maar verwijder hem niet.", "deactivate_bot"),
    )
    q04 = None
    for case_id, message, operation_id in actions:
        action = _run_action(
            base_url=base_url,
            token=token,
            other_token=other_token,
            message=message,
            operation_id=operation_id,
            conversation_id=conversation_id,
        )
        conversation_id = action["conversation_id"]
        action["case_id"] = case_id
        if case_id in {"q30", "q31", "q32", "q33", "q34"}:
            action["passed"] = action["passed"] and action.get("terminal_projection", {}).get("conversation_reference_kind") == "previous_action_result"
        action["conversation_reference"] = action["terminal_projection"].get("conversation_reference")
        action["conversation_reference_kind"] = action["terminal_projection"].get("conversation_reference_kind")
        action_cases.append(action)
        if case_id == "q31":
            q04 = _read_case(
                base_url,
                token,
                "Welke strategie is aan mijn actieve setup gekoppeld?",
                "read_linked_strategy",
                conversation_id,
            )

    # The disclosed evaluation turns refer to the linked bot just created in
    # the natural action chain. Keep that real persisted conversation rather
    # than seeding a parallel context or injecting an object ID.
    lineage_conversation = conversation_id
    prior_turns = []
    for message, expected in (
        ("Beoordeel mijn volledige actieve plan en noem precies één belangrijkste verbetering.", "evaluate_plan"),
        ("Welke opgeslagen feiten uit je vorige beoordeling ondersteunen die conclusie?", "explain_previous_evidence"),
        ("Herformuleer je vorige antwoord korter zonder de betekenis te wijzigen.", "reformulate_previous_response"),
    ):
        turn = _read_case(base_url, token, message, expected, lineage_conversation)
        lineage_conversation = turn["conversation_id"]
        prior_turns.append(turn)
    q13 = _read_case(
        base_url,
        token,
        "Wat betekent die eerdere beoordeling concreet voor mijn gekoppelde bot?",
        "evaluate_bot",
        lineage_conversation,
        "previous_released_response",
    )
    # Preserve the bot while verifying its contextual consequence. The
    # destructive tail then proves every downstream reference still resolves
    # through persisted owner-scoped action-results rather than runner memory.
    for case_id, message, operation_id in (
        ("delete_bot", "Verwijder die bot.", "delete_bot"),
        ("delete_strategy", "Verwijder die strategie.", "delete_strategy"),
        ("delete_setup", "Verwijder die setup.", "delete_setup"),
    ):
        action = _run_action(
            base_url=base_url,
            token=token,
            other_token=other_token,
            message=message,
            operation_id=operation_id,
            conversation_id=conversation_id,
        )
        conversation_id = action["conversation_id"]
        action["case_id"] = case_id
        action_cases.append(action)
    published = {"q04": q04, "q13": q13}
    for action in action_cases:
        if action["case_id"] in {"q30", "q31", "q32", "q33", "q34"}:
            published[action["case_id"]] = action
    artifact = {
        "artifact_version": "finn_v2.declassified_346013_regressions.v1",
        "source_artifact_sha256": DECLASSIFIED_ARTIFACT_SHA256,
        "sealed_qa_material_used": False,
        "public_routes": True,
        "injected_ids": False,
        "shared_in_memory_state": False,
        "fixture_namespace": f"build-346013-{uuid.uuid4().hex[:12]}",
        "supporting_action_cases": action_cases,
        "prior_conversation_turns": prior_turns,
        "published_cases": published,
        "published_passed": sum(bool(case and case.get("passed")) for case in published.values()),
        "published_total": 7,
        "downstream_delete_chain_passed": all(
            action["passed"] for action in action_cases if action["case_id"].startswith("delete_")
        ),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "passed": artifact["published_passed"], "total": 7}, sort_keys=True))
    if artifact["published_passed"] != 7 or not artifact["downstream_delete_chain_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
