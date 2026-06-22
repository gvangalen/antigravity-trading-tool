from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "run_finn_qa_replay.py"
PROMPTSET_PATH = REPO_ROOT / "docs" / "operations" / "finn-qa-promptset-full.json"
DOC_PATH = REPO_ROOT / "docs" / "operations" / "finn-qa-release-gate.md"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_finn_qa_replay", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_promptset_exists_and_covers_required_cases():
    payload = json.loads(PROMPTSET_PATH.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in payload["cases"]}

    assert "general-help" in case_ids
    assert "education-rsi-simple" in case_ids
    assert "context-setup-open" in case_ids
    assert "context-current-asset" in case_ids
    assert "context-asset-bot" in case_ids
    assert "coach-fomo" in case_ids
    assert "coach-plan-deviation" in case_ids
    assert "coach-emotional-decision" in case_ids
    assert "mission-control-summary" in case_ids
    assert "mixed-06-mission-control" in case_ids
    assert "operator-priority-what-now" in case_ids
    assert "operator-priority-focus-today" in case_ids
    assert "operator-priority-top3-actions" in case_ids
    assert "operator-priority-what-not-to-do" in case_ids
    assert "operator-plan-stop-loss-removal" in case_ids
    assert "operator-outcome-fomo-history" in case_ids
    assert "operator-portfolio-btc-concentration" in case_ids
    assert "operator-portfolio-extra-btc-risk" in case_ids
    assert "operator-decision-natural-trade-review" in case_ids


def test_release_gate_doc_references_script_and_promptset():
    source = DOC_PATH.read_text(encoding="utf-8")
    assert "run_finn_qa_replay.py" in source
    assert "finn-qa-promptset-full.json" in source
    assert "no_generic_failures" in source
    assert "no_transactional_misroutes" in source
    assert "operational_qa_path" in source


def test_summarize_results_flags_generic_failures_and_misroutes():
    module = _load_script_module()
    summary = module.summarize_results(
        suite_name="demo",
        results=[
            {
                "id": "ok",
                "latency_ms": 120.0,
                "intent": "education",
                "conversation": None,
                "passed": True,
                "failures": [],
            },
            {
                "id": "bad",
                "latency_ms": 250.0,
                "intent": "bot_creation",
                "conversation": "mixed-20-turn",
                "passed": False,
                "failures": ["generic_failure", "forbidden_flow:bot_creation"],
            },
        ],
        chat_latency_budget_ms=5000,
        mission_control_latency_budget_ms=20000,
    )

    assert summary["generic_failures"] == 1
    assert summary["transactional_misroutes"] == 1
    assert summary["release_gate"]["no_generic_failures"] is False
    assert summary["release_gate"]["no_transactional_misroutes"] is False
    assert summary["release_gate"]["stable_mixed_session"] is False
    assert summary["release_gate"]["overall_pass"] is False
    assert summary["failure_buckets"]["product_quality"] == 1
    assert summary["failure_buckets"]["operational_qa_path"] == 0
    assert summary["latency_buckets"]["le_1s"] == 2
    assert summary["slowest_prompt_id"] == "bad"


def test_summarize_results_buckets_operational_failures():
    module = _load_script_module()

    summary = module.summarize_results(
        suite_name="ops",
        results=[
            {
                "id": "timeoutish",
                "latency_ms": 9000.0,
                "intent": None,
                "conversation": None,
                "http_status": 429,
                "passed": False,
                "failures": ["http_status:429"],
            }
        ],
        chat_latency_budget_ms=5000,
        mission_control_latency_budget_ms=20000,
    )

    assert summary["failure_buckets"]["operational_qa_path"] == 1
    assert summary["latency_buckets"]["gt_8s"] == 1


def test_operational_errors_are_bucketed_without_crashing():
    module = _load_script_module()

    result = module.evaluate_case(
        {
            "id": "ops-timeout",
            "query": "Hoi",
            "expected_intents": ["general_help"],
            "forbidden_flows": ["bot_creation"],
            "expected_mode": "read_only",
        },
        {"detail": "The read operation timed out", "error": "operational_qa_path"},
        latency_ms=45000.0,
        http_status=599,
    )

    assert result["passed"] is False
    assert "http_status:599" in result["failures"]


def test_run_suite_retries_transient_429_until_success(monkeypatch):
    module = _load_script_module()
    attempts = {"count": 0}

    def fake_chat_request(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {"detail": "Te veel verzoeken"}, 120.0, 429
        return {"intent": "general_help", "flow": "general_help", "response": "ok"}, 140.0, 200

    sleep_calls = []
    monkeypatch.setattr(module, "perform_chat_request", fake_chat_request)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    results, summary = module.run_suite(
        opener=None,
        default_headers={},
        base_url="https://example.com",
        promptset={
            "name": "demo",
            "cases": [
                {
                    "id": "general-help",
                    "query": "Hoi FINN, wat kun je voor mij doen?",
                    "expected_intents": ["general_help"],
                    "expected_mode": None,
                }
            ],
        },
        timeout_seconds=10.0,
        delay_seconds=0.0,
        max_attempts=3,
        retry_backoff_seconds=2.5,
    )

    assert attempts["count"] == 2
    assert results[0]["passed"] is True
    assert results[0]["attempts"] == 2
    assert summary["failed_cases"] == 0
    assert sleep_calls == [2.5]


def test_prepare_promptset_contexts_repairs_stale_setup_id_by_name():
    module = _load_script_module()
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs["url"])
        if kwargs["url"].endswith("/api/setups/62"):
            return {"detail": "Setup niet gevonden"}, 404
        if kwargs["url"].endswith("/api/setups"):
            return [
                {"id": 99, "name": "Breakout long test", "symbol": "BTC", "timeframe": "1W"},
                {"id": 100, "name": "Other setup", "symbol": "ETH", "timeframe": "4H"},
            ], 200
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")

    module._request_json = fake_request_json

    promptset = {
        "name": "demo",
        "cases": [
            {
                "id": "context-setup-open",
                "query": "Welke setup heb ik nu open?",
                "context": {
                    "setup_id": 62,
                    "setup_name": "Breakout long test",
                    "setup_symbol": "BTC",
                    "setup_timeframe": "1W",
                    "symbol": "BTC",
                },
            }
        ],
    }

    prepared = module.prepare_promptset_contexts(
        opener=None,
        default_headers={},
        base_url="https://example.com",
        promptset=promptset,
        timeout_seconds=10.0,
    )

    context = prepared["cases"][0]["context"]
    assert context["setup_id"] == 99
    assert context["setup_name"] == "Breakout long test"
    assert context["setup_symbol"] == "BTC"
    assert calls == ["https://example.com/api/setups/62", "https://example.com/api/setups"]


def test_evaluate_case_checks_variant_context_resolution_and_summary_quality():
    module = _load_script_module()

    result = module.evaluate_case(
        {
            "id": "mission-control-summary",
            "query": "Vat Mission Control samen in drie bullets",
            "expected_intents": ["mission_control_explain"],
            "expected_mode": "read_only",
            "response_must_not_contain": ["- None"],
            "forbid_duplicate_bullets": True,
            "require_analysis_variant": "direct_coach",
            "require_context_entity_type": "asset",
            "require_context_resolution_target": "asset",
        },
        {
            "intent": "mission_control_explain",
            "flow": "mission_control_explain",
            "response": "- Daily scores verversen\n- Daily scores verversen\n- None",
            "analysis": {
                "mode": "read_only",
                "behavioral_intelligence": {"variant": "behavioral_reflection"},
                "context_explain": {"entity_type": "score"},
                "context_entity_resolution": {"target": "score"},
            },
        },
        latency_ms=900.0,
        http_status=200,
    )

    assert result["passed"] is False
    assert "duplicate_bullets" in result["failures"]
    assert "forbidden_response_snippet:- none" in result["failures"]
    assert "unexpected_variant:behavioral_reflection" in result["failures"]
    assert "unexpected_context_entity_type:score" in result["failures"]
    assert "unexpected_context_resolution_target:score" in result["failures"]
