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
    assert "coach-fomo" in case_ids
    assert "mission-control-summary" in case_ids
    assert "mixed-06-mission-control" in case_ids


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
