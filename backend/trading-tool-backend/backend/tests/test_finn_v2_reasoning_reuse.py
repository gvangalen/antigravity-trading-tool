from datetime import datetime, timezone
import asyncio
from types import SimpleNamespace

from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_reuses_existing_ready_result(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(id="run-1", user_id=7, message="Vraag", client_context_json={}, workspace_hints_json={})
    orchestrator_row = SimpleNamespace(
        id="o-1",
        run_id="run-1",
        user_id=7,
        interaction_mode="FACT",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["setup"],
        required_domains_json=["plan_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-1", "interaction_mode": "FACT", "max_tool_calls": 15},
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-1", snapshot_id="snapshot-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-1", validation_id="validation-1", integrity_status="valid", evidence_set_hash="hash", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(decision_json={"policy_decision_id": "policy-1", "run_id": "run-1", "user_id": 7, "policy_class": "read", "allowed": True, "proposal_allowed": False, "confirmation_required": False, "step_up_required": False, "execution_allowed": False, "shadow_safe": True, "created_at": "2026-08-17T10:00:00+00:00"}))
    reused = SimpleNamespace(
        id="reasoning-1",
        run_id="run-1",
        user_id=7,
        orchestrator_result_id="o-1",
        policy_decision_id="policy-1",
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        status="ready",
        mode="FACT",
        context_version="2026-08-17.block6",
        evidence_set_hash="hash",
        input_hash="input-hash",
        prompt_version="2026-08-17.block6",
        schema_version="2026-08-17.block6",
        reasoning_version="2026-08-17.block6",
        model="gpt-test",
        result_json={"reasoning_result_id": "reasoning-1", "run_id": "run-1", "user_id": 7, "mode": "FACT", "direct_answer": "Antwoord", "main_observation": "Observatie", "supporting_points": [], "claims": [], "uncertainty_summary": None, "uncertainty_codes": [], "next_step": None, "follow_up_question": None, "proposal_candidate": None, "evidence_refs_used": [], "prompt_version": "2026-08-17.block6", "reasoning_version": "2026-08-17.block6", "model": "gpt-test", "created_at": "2026-08-17T10:00:00+00:00"},
        error_codes_json=[],
        input_tokens=10,
        output_tokens=20,
        reasoning_tokens=0,
        latency_ms=123,
        retry_count=0,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="FACT", context_version="2026-08-17.block6", evidence_set_hash="hash", evidence=[], subject_scopes=[], required_domains=[], dict=lambda : {},))
    service.contexts.input_hash = lambda *_args, **_kwargs: "input-hash"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=reused)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    monkeypatch.setattr(service.flags, "should_run_block6_shadow", lambda _user_id: True)

    result = asyncio.run(service.reason(user_id=7, run_id="run-1", trace_id="trace-1"))

    assert result.reasoning_result_id == "reasoning-1"
