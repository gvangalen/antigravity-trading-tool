"""Diagnose a public legacy contract matrix without changing its verdict."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.scripts.run_finn_v2_full_action_matrix import _runtime_record


def classify(case: dict, runtime: dict) -> str:
    if case.get("passed"):
        return "legacy_checks_passed"
    if case.get("fixture_required_inputs_match_registry") is False:
        return "fixture_conflicts_with_registry"
    projection = runtime.get("terminal_projection") or {}
    expected = case.get("expected_operation_id")
    if expected in {"unavailable", "unsupported_financial_operation"} and (
        projection.get("terminal_status") == "completed"
        and not projection.get("final_operation_id")
    ):
        return "unsupported_request_answered_directly_review_safety"
    if projection.get("terminal_reason") in {
        "proposal_tool_validation_failed", "tool_relevance_unverified",
    }:
        return "product_tool_boundary_failure"
    if projection.get("terminal_reason") == "source_unavailable":
        return "evidence_unavailable_review_fixture"
    if case.get("classification") == "CASCADE" and projection.get("terminal_status") == "clarification_required":
        return "dependency_cascade_or_valid_missing_input"
    if (projection.get("terminal_status") == "completed"
            and not projection.get("final_operation_id")
            and (projection.get("response") or {}).get("content")):
        return "direct_response_requires_semantic_review"
    return "product_or_fixture_review_required"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    registry = FinnV2OperationRegistry()
    cases = []
    for case in source["cases"]:
        runtime = _runtime_record(case["run_id"]) if case.get("run_id") else {}
        projection = runtime.get("terminal_projection") or {}
        state = runtime.get("runtime_state") or {}
        exchange = state.get("responses_exchange") or {}
        calls = exchange.get("tool_trace") or []
        expected = case.get("expected_operation_id")
        contract = registry.get(expected) if expected else None
        track = (
            "action" if contract and contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}
            else "conversation"
        )
        direct_response = bool(
            projection.get("terminal_status") == "completed"
            and not projection.get("final_operation_id")
            and (not calls or all(call.get("name") == "answer_directly" for call in calls))
            and (projection.get("response") or {}).get("content")
        )
        if track == "action":
            track_result = "contract_passed" if case.get("passed") else "action_failure_requires_review"
        elif direct_response:
            track_result = "direct_answer_requires_grounding_review"
        else:
            track_result = "legacy_checks_passed" if case.get("passed") else "conversation_failure_requires_review"
        cases.append({
            "case_id": case["case_id"],
            "legacy_passed": bool(case.get("passed")),
            "diagnostic_category": classify(case, runtime),
            "track": track,
            "track_result": track_result,
            "direct_response_without_operation": direct_response,
            "expected_operation_id": case.get("expected_operation_id"),
            "observed_operation_id": projection.get("final_operation_id"),
            "terminal_status": projection.get("terminal_status"),
            "terminal_reason": projection.get("terminal_reason"),
            "response_content": (projection.get("response") or {}).get("content"),
            "tool_trace": [
                {"name": call.get("name"), "status": call.get("status"),
                 "result_status": (call.get("result") or {}).get("status"),
                 "result_reason": (call.get("result") or {}).get("reason")}
                for call in calls
            ],
            "fixture_required_inputs_match_registry": case.get("fixture_required_inputs_match_registry"),
            "failed_legacy_checks": [key for key, value in (case.get("checks") or {}).items() if value is False],
        })
    output = {
        "source_artifact": str(Path(args.input).resolve()),
        "legacy_verdict_unchanged": True,
        "total": len(cases),
        "legacy_passed": sum(item["legacy_passed"] for item in cases),
        "tracks": {
            track: dict(Counter(item["track_result"] for item in cases if item["track"] == track))
            for track in ("conversation", "action")
        },
        "categories": dict(Counter(item["diagnostic_category"] for item in cases)),
        "cases": cases,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "categories": output["categories"]}))


if __name__ == "__main__":
    main()
