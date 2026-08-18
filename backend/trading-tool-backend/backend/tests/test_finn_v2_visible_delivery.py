import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import VerifiedResponse
from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryError, FinnV2VisibleDeliveryService


def test_visible_delivery_maps_verified_response_to_assistant_contract():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-1")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(
        0,
        result={
            "delivery_envelope": {"run_id": "run-1", "status": "completed", "delivery_source": "finn_v2_verified"},
            "verified_response": VerifiedResponse.parse_obj(
                {
                    "verified_response_id": "vr-1",
                    "run_id": "run-1",
                    "user_id": 1,
                    "mode": "PROPOSAL",
                    "direct_answer": "Ik kan een BTC-voorstel voorbereiden.",
                    "main_observation": "BTC voorstel klaar voor review.",
                    "supporting_points": [],
                    "claims": [],
                    "uncertainty_summary": None,
                    "uncertainty_codes": [],
                    "next_step": None,
                    "follow_up_question": None,
                    "proposal_id": "proposal-1",
                    "confirmation_required": True,
                    "verifier_status": "passed",
                    "evidence_set_hash": "hash-1",
                    "verifier_result_id": "verifier-1",
                    "created_at": datetime.now(timezone.utc),
                }
            ).dict(),
            "orchestrator_result": {"outcome": "reasoning_ready"},
            "policy_result": {"allowed": True},
            "reasoning_result": {"mode": "PROPOSAL"},
            "verifier_result": {"passed": True},
            "tool_calls": [{"tool_name": "read_active_asset"}],
            "validation_result": {"integrity_status": "valid"},
            "financial_state_snapshot": {"asset": "BTC"},
        },
    )

    envelope = asyncio.run(
        service.deliver_assistant_envelope(
            user_id=1,
            message="Werk mijn BTC setup bij.",
            context_payload={"page": "setup"},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert envelope["can_confirm"] is True
    assert envelope["actions"][0]["proposal_id"] == "proposal-1"
    assert envelope["response_trace"]["response_source"] == "finn_v2_verified"
    assert envelope["response_trace"]["pipeline_version"] == "finn_v2"
    assert envelope["response_trace"]["tool_calls"][0]["tool_name"] == "read_active_asset"


def test_visible_delivery_preserves_run_id_when_delivery_chain_fails():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-capability-1")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(0, result={"delivery_envelope": {"run_id": "run-capability-1"}})

    try:
        asyncio.run(
            service.deliver_assistant_envelope(
                user_id=1,
                message="Hoi FINN, wat kun je voor mij doen?",
                context_payload={"missing_context": ["asset", "setup"]},
                transport="chat",
                request_path="/assistant/chat",
                request_id="req-capability-1",
                trace_id="trace-capability-1",
            )
        )
    except FinnV2VisibleDeliveryError as exc:
        assert exc.code == "v2_delivery_failure"
        assert exc.run_id == "run-capability-1"
        assert exc.failure_stage == "delivery_envelope"
    else:
        raise AssertionError("expected visible delivery failure")
