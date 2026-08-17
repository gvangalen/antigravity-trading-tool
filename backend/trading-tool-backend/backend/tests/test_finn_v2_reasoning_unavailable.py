import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

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
