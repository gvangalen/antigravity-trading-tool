import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_release_gate_service import FinnV2ReleaseGateService


def test_release_gates_fail_when_real_model_eval_is_blocked():
    service = FinnV2ReleaseGateService(session=object())
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    eval_run = SimpleNamespace(
        eval_run_id="eval-1",
        blocking_gate_results={gate: True for gate in ["schema_contract", "account_identity", "ownership", "cross_user_isolation", "critical_entity_resolution", "claim_grounding", "action_safety", "paper_live_accuracy", "a1_a3_b1_b4", "fallback_contract", "prompt_injection_safety"]},
        aggregate_scores={"question_relevance": 98.0, "context_coverage": 98.0, "verified_response_rate": 100.0, "technical_failure_rate": 0.0},
        latency_p95_ms=20,
        real_model_validation_blocked=True,
        blocker_code="REAL_MODEL_EVAL_BLOCKED",
        created_at=datetime.now(timezone.utc),
    )

    result = asyncio.run(service.evaluate(eval_run=eval_run))

    assert result.passed is False
    assert "REAL_MODEL_EVAL_BLOCKED" in result.reason_codes
