#!/usr/bin/env python3
"""Exercise every explicitly declassified Action Contract Acceptance record.

This runner intentionally consumes only the public fixture committed under
``backend/tests/fixtures``. It neither loads a sealed QA manifest nor injects
object IDs into user messages. Write lifecycle evidence remains covered by the
separate public action-chain and contract-certification runners.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import sleep
from urllib.parse import urlparse
import uuid

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _request_json, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_sequential_action_chain import _run_action
from backend.utils.auth_utils import create_access_token


SOURCE_SHA256 = "00f1e65a1bd2abaf487c92c33113972993ab3250a6bd2e8be018f43e6be001f0"
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "finn_v2_declassified_34746230528_regression.json"
SAFE_WRITE_OPERATIONS = {
    "select_asset", "watchlist_add", "watchlist_remove",
    "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration",
    "create_setup", "update_setup", "delete_setup", "create_strategy", "update_strategy",
    "delete_strategy", "create_bot", "update_bot", "deactivate_bot", "delete_bot",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--case-interval-seconds",
        type=float,
        default=0.25,
        help="Bounded production-runner-compatible pause after every case.",
    )
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("declassified_acceptance_requires_loopback")

    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("declassified_fixture_hash_mismatch")

    user, other = _create_local_user(), _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    conversations: dict[str, str] = {}
    proposals: dict[str, dict] = {}
    cases: list[dict] = []
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint() -> None:
        payload = {
            "artifact_version": "finn_v2.declassified_347462_runtime_acceptance.v1",
            "source_sha256": SOURCE_SHA256,
            "sealed_qa_material_used": False,
            "public_routes": True,
            "cases": cases,
            "total": len(fixture["failures"]),
            "attempted": len(cases),
            "passed": sum(case["passed"] for case in cases),
            "incomplete": True,
        }
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)

    def finish_case() -> None:
        checkpoint()
        sleep(max(0.0, args.case_interval_seconds))

    for record in fixture["failures"]:
        sequence = record["conversation_and_lineage"]["declassified_conversation_sequence"]
        sequence_key = sequence[0]
        expected = record["expected"]
        try:
            if expected["operation"] == "confirm_proposal":
                # The declassified prompt deliberately refers to the proposal
                # shown immediately before it. Create that prerequisite through
                # the same public run route, never by injecting a proposal ID.
                prerequisite = run_gate(
                    base_url=args.base_url.rstrip("/"), bearer_token=token,
                    message=(
                        "Create a swing setup named Confirmation prerequisite "
                        "for XLM on 4H."
                    ),
                    # Confirmation and execution are independently certified
                    # through their public routes. They must not replace the
                    # action-result lineage of the natural setup/bot chain.
                    conversation_id=None, timeout_seconds=75,
                )
                prerequisite_record = _runtime_record(prerequisite["run_id"])
                if not (prerequisite_record.get("proposal") or {}).get("id"):
                    raise RuntimeError("confirmation_prerequisite_proposal_missing")
                proposals[sequence_key] = prerequisite_record["proposal"]
            if expected["operation"] in {"confirm_proposal", "execute_proposal"}:
                proposal = proposals.get(sequence_key)
                if not proposal:
                    raise RuntimeError("proposal_lifecycle_dependency_missing")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                proposal_id = str(proposal["id"])
                if expected["operation"] == "confirm_proposal":
                    published, publish_status = _request_json(
                        url=f"{args.base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}/publish",
                        method="POST", headers=headers, body={}, timeout=10,
                    )
                    confirmed, confirmation_status = _request_json(
                        url=f"{args.base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}/confirm",
                        method="POST", headers=headers,
                        body={
                            "idempotency_key": f"declassified-confirm-{uuid.uuid4().hex}",
                            "confirmation_token": published.get("confirmation_token"),
                            "expected_payload_hash": proposal["payload_hash"],
                        }, timeout=10,
                    )
                    if publish_status != 200 or confirmation_status != 200 or not confirmed.get("confirmed"):
                        raise RuntimeError("public_confirmation_failed")
                    cases.append({
                        "case_id": record["case_id"], "classification": record["classification"],
                        "expected_operation_id": expected["operation"],
                        "public_confirmation_route": True, "proposal_id_present": True,
                        "passed": True,
                    })
                    finish_case()
                    continue
                executed, execution_status = _request_json(
                    url=f"{args.base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}/execute",
                    method="POST", headers=headers,
                    body={
                        "idempotency_key": f"declassified-execute-{uuid.uuid4().hex}",
                        "expected_payload_hash": proposal["payload_hash"],
                    }, timeout=20,
                )
                if execution_status != 200 or executed.get("status") != "succeeded":
                    raise RuntimeError("public_execution_failed")
                cases.append({
                    "case_id": record["case_id"], "classification": record["classification"],
                    "expected_operation_id": expected["operation"],
                    "public_execution_route": True, "proposal_id_present": True,
                    "passed": True,
                })
                finish_case()
                continue
            if expected["operation"] in SAFE_WRITE_OPERATIONS:
                observed = _run_action(
                    base_url=args.base_url.rstrip("/"), token=token, other_token=other_token,
                    message=record["declassified_user_question"], operation_id=expected["operation"],
                    conversation_id=conversations.get(sequence_key),
                    mutation_pace_seconds=3.1,
                )
                conversations[sequence_key] = observed["conversation_id"]
                actual = observed["terminal_projection"]
                status = observed["terminal_status"]
                http_status = observed["initial_http_status"]
                parity = observed["polling_sse_parity"]
            else:
                observed = run_gate(
                    base_url=args.base_url.rstrip("/"), bearer_token=token,
                    message=record["declassified_user_question"],
                    conversation_id=conversations.get(sequence_key), timeout_seconds=75,
                )
                conversations[sequence_key] = observed["conversation_id"]
                actual = _runtime_record(observed["run_id"])["terminal_projection"]
                status = observed["status"]
                http_status = observed["run_create_http_status"]
                parity = observed["polling_sse_contract_projection"]
        except Exception as error:
            cases.append({
                "case_id": record["case_id"],
                "classification": record["classification"],
                "passed": False,
                "error_category": type(error).__name__,
                "error": str(error),
            })
            finish_case()
            continue
        checks = {
            "http_200": http_status == 200,
            "initial_operation": observed["initial_operation_id"] == expected["operation"],
            "final_operation": observed["final_operation_id"] == expected["operation"],
            "action_polarity": actual.get("action_polarity") == expected["action_polarity"],
            "required_inputs": sorted(actual.get("required_inputs") or []) == sorted(expected["required_inputs"]),
            "missing_inputs": sorted(actual.get("missing_inputs") or []) == sorted(expected["missing_inputs"]),
            "terminal_status": status in expected["lifecycle_and_effects"]["terminal_statuses"],
            "polling_sse_parity": parity,
            "single_dispatch": actual.get("dispatch_count") == 1,
            "single_attempt": actual.get("attempt_count") == 1,
        }
        passed = all(checks.values())
        cases.append({
            "case_id": record["case_id"],
            "classification": record["classification"],
            "expected_operation_id": expected["operation"],
            "expected_action_polarity": expected["action_polarity"],
            "run_id": observed["run_id"],
            "runtime_contract_id": actual.get("contract_id"),
            "initial_http_status": http_status,
            "initial_operation_id": observed["initial_operation_id"],
            "final_operation_id": observed["final_operation_id"],
            "terminal_status": status,
            "required_inputs": actual.get("required_inputs"),
            "supplied_inputs": actual.get("supplied_inputs"),
            "missing_inputs": actual.get("missing_inputs"),
            "dispatch_count": actual.get("dispatch_count"),
            "attempt_count": actual.get("attempt_count"),
            "polling_sse_parity": parity,
            "checks": checks,
            "passed": passed,
        })
        finish_case()

    artifact = {
        "artifact_version": "finn_v2.declassified_347462_runtime_acceptance.v1",
        "source_sha256": SOURCE_SHA256,
        "sealed_qa_material_used": False,
        "public_routes": True,
        "cases": cases,
        "total": len(cases),
        "passed": sum(case["passed"] for case in cases),
    }
    artifact["attempted"] = len(cases)
    artifact["incomplete"] = False
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": artifact["passed"], "total": artifact["total"]}))
    if artifact["passed"] != artifact["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
