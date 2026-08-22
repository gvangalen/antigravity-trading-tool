import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_run_service import FinnV2RunService


def test_terminal_envelope_hydrates_persisted_v2_chain_without_rerunning_it():
    service = FinnV2RunService(session=object())
    calls = []
    artifacts = {
        "delivery_envelope": {"status": "completed"},
        "verified_response": {
            "verified_response_id": "verified-1",
            "reasoning_provenance": {
                "provider_called": True,
                "provider_status": "completed",
                "parse_status": "passed",
                "validation_status": "passed",
                "repair_status": "not_attempted",
            },
        },
        "orchestrator_result": {
            "orchestrator_result_id": "orchestrator-1",
            "interaction_mode": "EVALUATE",
            "required_domains": ["identity_context", "market_context"],
            "optional_domains": [],
            "outcome": "reasoning_ready",
            "snapshot_id": "snapshot-1",
            "validation_id": "validation-1",
        },
        "policy_result": {"allowed": True, "policy_class": "advice"},
        "validation_result": {"validation_id": "validation-1", "integrity_status": "valid"},
        "reasoning_result": {
            "reasoning_result_id": "reasoning-1",
            "status": "ready",
            "mode": "EVALUATE",
            "model": "gpt-4o-mini",
            "latency_ms": 1200,
            "error_codes": [],
            "result": {"reasoning_provenance": {"provider_called": True, "parse_status": "passed"}},
        },
        "verifier_result": {
            "verifier_result_id": "verifier-1",
            "passed": True,
            "action": "deliver",
            "reason_codes": [],
            "coverage": {"coverage_ok": True, "required_scopes": ["profile"]},
        },
        "tool_calls": [{"tool_call_id": 1, "tool_name": "read_profile", "status": "completed"}],
        "evidence_references": [{"artifact_id": "artifact-1", "tool_name": "read_profile", "user_scoped": True}],
    }

    async def get_artifacts(**kwargs):
        calls.append(kwargs)
        return artifacts

    service.delivery.get_delivery_artifacts = get_artifacts
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        conversation_id="conversation-1",
        status="completed",
        interaction_mode="EVALUATE",
        visibility="visible",
        response_json={
            "mode": "EVALUATE",
            "content": "Een grounded antwoord.",
            "response_source": "v2_runtime",
            "verifier_status": "passed",
            "evidence": [],
            "uncertainty": [],
            "proposal_id": None,
            "confirmation_required": False,
            "reasoning_provenance": {},
        },
        policy_json={"allowed": True, "policy_class": "advice"},
        created_at=now,
        updated_at=now,
        completed_at=now,
        error_code=None,
        error_message=None,
        retryable=False,
    )

    envelope = asyncio.run(service.envelope_from_run(run))

    assert calls == [{"user_id": 7, "run_id": "run-1"}]
    assert envelope.mode == "EVALUATE"
    assert envelope.response.reasoning_provenance["provider_status"] == "completed"
    assert envelope.runtime_trace["requested_mode"] == "EVALUATE"
    assert envelope.runtime_trace["verifier"]["coverage"]["coverage_ok"] is True
    assert envelope.runtime_trace["tool_calls"] == artifacts["tool_calls"]
    assert envelope.runtime_trace["evidence_references"] == artifacts["evidence_references"]


def test_rejected_run_keeps_verifier_reasoning_provenance_in_its_terminal_envelope():
    service = FinnV2RunService(session=object())
    transition = {}
    service.delivery.get_delivery_artifacts = lambda **_kwargs: asyncio.sleep(
        0,
        result={
            "delivery_envelope": {"status": "completed"},
            "verified_response": None,
            "policy_result": {"allowed": True},
            "reasoning_result": {
                "result": {"reasoning_provenance": {"provider_called": True, "parse_status": "schema_invalid"}},
            },
            "verifier_result": {"action": "reject", "reason_codes": ["response_scope_incomplete"]},
        },
    )

    async def _transition_run(*_args, **kwargs):
        transition.update(kwargs)

    service.transition_run = _transition_run
    asyncio.run(service.complete_run(run_id="run-rejected-1", user_id=7, interaction_mode="UNAVAILABLE"))

    assert transition["next_status"] == "completed"
    assert transition["response_json"]["uncertainty"] == ["response_scope_incomplete"]
    assert transition["response_json"]["reasoning_provenance"]["parse_status"] == "schema_invalid"
