"""Run one versioned FINN selector dataset against the real structured provider.

This is selector-only: it never creates conversations, invokes FINN tools, or
creates/executes proposals.  ``FINN_V2_REAL_SELECTOR_EVAL=1`` is an explicit
guard because each case spends a real provider call.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any, Mapping

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService, FinnV2OperationClassificationValidator
from backend.services.finn_v2_selector_eval_registry import SelectorEvalCase, load_and_validate
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelectorService
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.utils import openai_client

DATASETS = ("development", "regression", "holdout")


def fixture_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures"
    return [root / f"finn_v2_selector_{dataset}.json" for dataset in DATASETS]


def same_entities(expected: Mapping[str, object], actual: Mapping[str, object]) -> bool:
    return all(str(actual.get(key) or "").casefold() == str(value).casefold() for key, value in expected.items())


def failure_category(raw: Mapping[str, Any], classification_error: str | None, validation_error: str | None) -> tuple[str, str, str | None]:
    error = str(raw.get("error") or classification_error or "")
    if error:
        if "timeout" in error:
            return "failed", "not_run", "timeout"
        if "schema" in error:
            return "failed", "not_run", "schema"
        if raw.get("error"):
            return "failed", "not_run", "provider"
        return "passed", "failed", "selector"
    return "passed", "failed" if validation_error else "passed", "validation" if validation_error else None


def run_case(case: SelectorEvalCase) -> dict[str, Any]:
    raw: dict[str, Any] = {}

    def provider(**kwargs: Any) -> Mapping[str, Any]:
        # Eval calls receive their own scope: they never contend with a user
        # request or another testcase in the product call-slot limiter.
        # entry_point is enough to isolate the call-slot scope. Keep user_id
        # absent: usage telemetry persists it as an integer foreign key.
        with ai_usage_context(entry_point=f"selector_eval:{case.eval_id}"):
            response = openai_client.ask_gpt_structured_response(**kwargs)
        raw.update(response)
        return response

    registry = FinnV2OperationRegistry()
    classifier = FinnV2OperationClassificationService(registry=registry, structured_selector=FinnV2StructuredOperationSelectorService(provider=provider))
    facts = classifier.preprocessor.preprocess(message=case.input_query)
    started = monotonic()
    classified = classifier.classify(message=case.input_query, conversation_context=case.conversation_context)
    latency_ms = int((monotonic() - started) * 1000)
    validation_error = FinnV2OperationClassificationValidator(registry).validation_error(classified, facts=facts, conversation_context=case.conversation_context)
    parsed = raw.get("parsed") if isinstance(raw.get("parsed"), Mapping) else {}
    # Grade the typed selector selection, not the raw provider text. The
    # selector normalizes schema-valid delimiter artefacts before any contract
    # consumer can observe them, so the eval trace must measure that boundary.
    entities = dict(classified.selected_entities or {})
    classification_error = classified.reason_code if classified.selector_source == "provider_unavailable" else None
    parse_status, validation_status, category = failure_category(raw, classification_error, validation_error)
    contract = registry.get(classified.operation_id)
    target_asset = classified.selected_target_asset
    conversation_reference = classified.selected_conversation_reference
    clarification = classified.operation_id == "clarify_request"
    actual_missing_inputs = list(classified.selected_missing_inputs)
    expected_missing_inputs = case.expected_missing_inputs
    return {
        "eval_id": case.eval_id,
        "input_query": case.input_query,
        "expected": case.dict(exclude={"eval_id", "dataset", "input_query", "conversation_context", "provider_call_expected"}),
        "actual": {
            "operation_id": classified.operation_id, "domain": contract.domain, "supported": contract.supported,
            "confidence": parsed.get("confidence"), "entities": entities, "context_asset": facts.workspace_context_asset,
            "target_asset": target_asset, "action_polarity": classified.action,
            "conversation_reference": conversation_reference, "clarification": clarification,
            "missing_inputs": actual_missing_inputs,
            "selector_source": classified.selector_source,
        },
        "provider_status": (raw.get("provider_metadata") or {}).get("response_status"),
        "provider_response_id": (raw.get("provider_metadata") or {}).get("response_id"),
        "provider_metadata": raw.get("provider_metadata") or {},
        "parse_status": parse_status, "validation_status": validation_status, "latency_ms": latency_ms,
        "failure_category": category, "error": raw.get("error") or classification_error or validation_error,
        "matches": {
            "operation": classified.operation_id == case.expected_operation_id,
            "domain": contract.domain == case.expected_domain,
            "supported": contract.supported == case.expected_supported,
            "entities": same_entities(case.expected_entities, entities),
            "target_asset": case.expected_target_asset is None or str(target_asset or "").casefold() == case.expected_target_asset.casefold(),
            "action_polarity": case.expected_action_polarity is None or classified.action == case.expected_action_polarity,
            "conversation_reference": case.expected_conversation_reference is None or conversation_reference == case.expected_conversation_reference,
            "clarification": clarification == case.expected_clarification,
            "missing_inputs": (
                actual_missing_inputs == expected_missing_inputs
            ),
        },
    }


def retry_delay(row: Mapping[str, Any], *, attempt: int, base_seconds: float) -> float | None:
    if row.get("failure_category") != "provider" or row.get("error") != "ai_rate_limited":
        return None
    metadata = row.get("provider_metadata") or {}
    retry_after = metadata.get("retry_after_seconds") if isinstance(metadata, Mapping) else None
    try:
        return max(0.0, float(retry_after)) if retry_after is not None else base_seconds * (2 ** (attempt - 1))
    except (TypeError, ValueError):
        return base_seconds * (2 ** (attempt - 1))


def run_case_with_retries(case: SelectorEvalCase, *, max_retries: int, backoff_seconds: float) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_retries + 2):
        row = run_case(case)
        attempts.append({
            "attempt": attempt,
            "error": row.get("error"),
            "failure_category": row.get("failure_category"),
            "provider_status": row.get("provider_status"),
            "provider_response_id": row.get("provider_response_id"),
            "latency_ms": row.get("latency_ms"),
        })
        delay = retry_delay(row, attempt=attempt, base_seconds=backoff_seconds)
        if delay is None or attempt > max_retries:
            row["attempts"] = attempts
            row["retry_count"] = attempt - 1
            return row
        time.sleep(delay)
    raise AssertionError("unreachable")


def rate(rows: list[dict[str, Any]], metric: str) -> float:
    return sum(row["matches"][metric] for row in rows) / len(rows) if rows else 0.0


def percentile(values: list[int], fraction: float) -> float:
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))] if values else 0.0


def build_report(dataset: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    confusion = Counter((r["expected"]["expected_operation_id"], r["actual"]["operation_id"]) for r in rows)
    latencies = sorted(row["latency_ms"] for row in rows)
    rows_for = lambda operation: [row for row in rows if row["expected"]["expected_operation_id"] == operation]
    failures = lambda category: sum(row["failure_category"] == category for row in rows) / len(rows) if rows else 0.0
    return {
        "dataset": dataset, "total_cases": len(rows), "operation_accuracy": rate(rows, "operation"),
        "confusion_matrix": {f"{expected}->{actual}": count for (expected, actual), count in sorted(confusion.items())},
        "entity_accuracy": rate(rows, "entities"), "targetasset_accuracy": rate(rows, "target_asset"),
        "action_polarity_accuracy": rate(rows, "action_polarity"), "conversation_reference_accuracy": rate(rows, "conversation_reference"),
        "clarification_accuracy": rate(rows, "clarification"),
        "missing_input_accuracy": rate(rows, "missing_inputs"),
        "missing_input_expectations_declared": 1.0,
        "off_topic_accuracy": rate(rows_for("off_topic"), "operation"),
        "unsupported_operation_accuracy": rate(rows_for("unsupported_financial_operation"), "operation"),
        "provider_failure_rate": failures("provider"), "schema_failure_rate": failures("schema"), "timeout_failure_rate": failures("timeout"),
        "parse_failure_rate": sum(row["parse_status"] != "passed" for row in rows) / len(rows) if rows else 0.0,
        "validation_failure_rate": sum(row["validation_status"] != "passed" for row in rows) / len(rows) if rows else 0.0,
        "p50_latency_ms": median(latencies) if latencies else 0.0, "p95_latency_ms": percentile(latencies, .95), "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-rate-limit-retries", type=int, default=3)
    parser.add_argument("--rate-limit-backoff-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if os.getenv("FINN_V2_REAL_SELECTOR_EVAL") != "1":
        raise SystemExit("FINN_V2_REAL_SELECTOR_EVAL=1 is required to spend provider calls")
    cases = [case for case in load_and_validate(fixture_paths()) if case.dataset == args.dataset]
    rows: list[dict[str, Any]] = []
    for case in cases:
        if rows:
            time.sleep(max(0.0, args.min_interval_seconds))
        row = run_case_with_retries(
            case,
            max_retries=max(0, args.max_rate_limit_retries),
            backoff_seconds=max(0.0, args.rate_limit_backoff_seconds),
        )
        rows.append(row)
    report = build_report(args.dataset, rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
