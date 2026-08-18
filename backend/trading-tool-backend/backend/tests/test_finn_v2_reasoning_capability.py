import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_returns_registry_grounded_capability_result_for_new_user():
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-cap-1",
        user_id=7,
        message="Hoi FINN, wat kun je voor mij doen?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={"missing_context": ["asset", "setup", "strategy"], "trader_profile_used": False},
        workspace_hints_json={},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-cap-1",
        run_id="run-cap-1",
        user_id=7,
        interaction_mode="CAPABILITY",
        analysis_version="2026-08-18.block6",
        subject_scopes_json=["capability"],
        required_domains_json=[],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-cap-1", "interaction_mode": "CAPABILITY", "max_tool_calls": 15},
        snapshot_id="snapshot-cap-1",
        validation_id="validation-cap-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-18.block6",
        created_at=datetime.now(timezone.utc),
    )

    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-cap-1", snapshot_id="snapshot-cap-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-cap-1", validation_id="validation-cap-1", integrity_status="valid", evidence_set_hash="hash-cap-1", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(decision_json={"policy_decision_id": "policy-cap-1", "run_id": "run-cap-1", "user_id": 7, "policy_class": "read", "allowed": True, "proposal_allowed": False, "confirmation_required": False, "step_up_required": False, "execution_allowed": False, "shadow_safe": True, "created_at": "2026-08-18T08:00:00+00:00"}))
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="CAPABILITY", locale="nl-NL", context_version="2026-08-18.block6", evidence_set_hash="hash-cap-1", evidence=[], subject_scopes=["capability"], required_domains=[], dict=lambda: {}))
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input-cap-1"
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)

    async def _persist_record(**kwargs):
        return kwargs

    service._persist_record = _persist_record

    result = asyncio.run(service.reason(user_id=7, run_id="run-cap-1", trace_id="trace-cap-1"))

    assert result["status"] == "ready"
    assert result["mode"] == "CAPABILITY"
    assert result["run_id"] == "run-cap-1"
    assert result["result"].direct_answer
    assert result["result"].proposal_candidate is None
