import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_schema import ReasoningResult
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_unavailable_when_ai_disabled(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(id="run-1", user_id=7, message="Welke setup gebruik ik?", client_context_json={}, workspace_hints_json={})
    orchestrator_row = SimpleNamespace(
        id="orchestrator-1",
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
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="FACT", context_version="2026-08-17.block6", evidence_set_hash="hash", evidence=[], subject_scopes=[], required_domains=[], dict=lambda : {},))
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    service._persist_record = lambda **kwargs: asyncio.sleep(0, result=kwargs)
    monkeypatch.setattr(service.flags, "should_run_block6_shadow", lambda _user_id: False)

    result = asyncio.run(service.reason(user_id=7, run_id="run-1", trace_id="trace-1"))

    assert result["status"] == "unavailable"


def test_visible_reasoning_bypasses_shadow_gate_when_runtime_is_live(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-2",
        user_id=7,
        message="Welke setup gebruik ik?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-2",
        run_id="run-2",
        user_id=7,
        interaction_mode="FACT",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["setup"],
        required_domains_json=["plan_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-2", "interaction_mode": "FACT", "max_tool_calls": 15},
        snapshot_id="snapshot-2",
        validation_id="validation-2",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-2", snapshot_id="snapshot-2"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-2", validation_id="validation-2", integrity_status="valid", evidence_set_hash="hash", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(decision_json={"policy_decision_id": "policy-2", "run_id": "run-2", "user_id": 7, "policy_class": "read", "allowed": True, "proposal_allowed": False, "confirmation_required": False, "step_up_required": False, "execution_allowed": False, "shadow_safe": True, "created_at": "2026-08-17T10:00:00+00:00"}))
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="FACT", context_version="2026-08-17.block6", evidence_set_hash="hash", evidence=[], subject_scopes=[], required_domains=[], dict=lambda: {}))
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    service._run_model_reasoning = lambda **_kwargs: asyncio.sleep(0, result="model-called")
    monkeypatch.setattr(service.flags, "should_run_block6_shadow", lambda _user_id: False)
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True, "model": "gpt-test"})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})

    result = asyncio.run(service.reason(user_id=7, run_id="run-2", trace_id="trace-2"))

    assert result == "model-called"


def test_reasoning_persistence_serializes_datetime_payloads():
    service = FinnV2ReasoningService(session=object())
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(created_at=datetime.now(timezone.utc), **kwargs)

    service.reasoning.create = _create
    result = ReasoningResult(
        reasoning_result_id="reasoning-3",
        run_id="run-3",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Niet beschikbaar.",
        main_observation="Reasoning is tijdelijk niet beschikbaar.",
        supporting_points=[],
        claims=[],
        uncertainty_summary=None,
        uncertainty_codes=[],
        next_step=None,
        follow_up_question=None,
        proposal_candidate=None,
        evidence_refs_used=[],
        model="gpt-test",
        created_at=datetime.now(timezone.utc),
    )

    persisted = asyncio.run(
        service._persist_record(
            run_id="run-3",
            user_id=7,
            orchestrator_result_id="orchestrator-3",
            policy_decision_id="policy-3",
            snapshot_id="snapshot-3",
            validation_id="validation-3",
            status="unavailable",
            mode="UNAVAILABLE",
            context_version="2026-08-17.block6",
            evidence_set_hash="hash-3",
            input_hash="input-3",
            model="gpt-test",
            result=result,
            error_codes=["ai_unavailable_configuration"],
            retry_count=0,
        )
    )

    assert isinstance(captured["result_json"]["created_at"], str)
    assert persisted.result.created_at == result.created_at
