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
