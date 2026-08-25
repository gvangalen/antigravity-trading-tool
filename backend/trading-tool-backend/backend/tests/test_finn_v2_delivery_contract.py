import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_delivery_service import FinnV2DeliveryService


def test_delivery_contract_returns_verified_response_only():
    service = FinnV2DeliveryService(session=object())
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-1", conversation_id="conv-1", user_id=7, status="completed"))
    service.verified.get_latest_for_run = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            response_json={
                "verified_response_id": "vr-1",
                "run_id": "run-1",
                "user_id": 7,
                    "mode": "READ",
                "direct_answer": "De bot staat in paper mode.",
                "main_observation": "De status is onderbouwd door recente evidence.",
                "supporting_points": [],
                "claims": [],
                "uncertainty_summary": None,
                "uncertainty_codes": [],
                "next_step": None,
                "follow_up_question": None,
                "proposal_id": None,
                "confirmation_required": False,
                "verifier_status": "passed",
                "evidence_set_hash": "hash-1",
                "verifier_result_id": "verifier-1",
                "response_version": "2026-08-17.block7",
                "created_at": datetime.now(timezone.utc),
            }
        ),
    )

    envelope = asyncio.run(service.get_delivery_envelope(user_id=7, run_id="run-1"))

    assert envelope.status == "completed"
    assert envelope.delivery_source == "finn_v2_verified"
    assert envelope.response.mode == "READ"


def test_delivery_contract_returns_processing_status_without_verified_response():
    service = FinnV2DeliveryService(session=object())
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="run-1",
            conversation_id="conv-1",
            user_id=7,
            status="collecting",
            error_code=None,
            error_message=None,
        ),
    )
    service.verified.get_latest_for_run = lambda **_kwargs: asyncio.sleep(0, result=None)

    envelope = asyncio.run(service.get_delivery_envelope(user_id=7, run_id="run-1"))

    assert envelope.status == "collecting"
    assert envelope.response is None


def test_public_contract_trace_exposes_registry_policy_without_provider_payloads():
    trace = FinnV2DeliveryService._contract_trace(
        orchestrator=SimpleNamespace(
            tool_plan_json={
                "request_plan": {
                    "operation_id": "read_active_asset",
                    "operation_contract_version": "2026-08-23.operation-contracts.v1",
                    "interaction_mode": "READ",
                    "context_asset": "BTC",
                    "target_asset": None,
                    "referenced_asset": "BTC",
                    "conversation_reference": "verified-response-1",
                    "operation_state": {"status": "completed"},
                }
            }
        ),
        verifier=SimpleNamespace(
            result_json={
                "coverage": {
                    "required_scopes": ["active_asset"],
                    "covered_scopes": ["active_asset"],
                    "required_response_fields": ["asset"],
                    "covered_response_fields": ["asset"],
                },
                "reason_codes": [],
            }
        ),
        response=SimpleNamespace(
            mode="READ",
            proposal_id=None,
            reasoning_provenance={"source": "deterministic_read"},
            verifier_status="passed",
        ),
        run=SimpleNamespace(conversation_id="conversation-1"),
    )

    assert trace == {
        "operation_id": "read_active_asset",
        "contract_version": "2026-08-23.operation-contracts.v1",
        "requested_mode": "READ",
        "delivered_mode": "READ",
        "conversation_id": "conversation-1",
        "conversation_reference": "verified-response-1",
        "selector_source": None,
        "selector_confidence": None,
        "candidate_operation_ids": [],
        "context_asset": "BTC",
        "target_asset": None,
        "referenced_asset": "BTC",
        "active_operation_status": "completed",
        "missing_input_field": None,
        "proposal_id": None,
        "model_policy": "never",
        "reasoning_source": "deterministic_read",
        "verifier_status": "passed",
        "required_scopes": ["active_asset"],
        "covered_scopes": ["active_asset"],
        "required_response_fields": ["asset"],
        "covered_response_fields": ["asset"],
        "verifier_reasons": [],
    }
