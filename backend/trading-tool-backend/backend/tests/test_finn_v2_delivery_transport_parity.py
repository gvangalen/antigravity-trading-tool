import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_delivery_service import FinnV2DeliveryService


def test_delivery_transport_parity_streams_same_verified_response():
    service = FinnV2DeliveryService(session=object())
    response_json = {
        "verified_response_id": "vr-1",
        "run_id": "run-1",
        "user_id": 7,
        "mode": "FACT",
        "direct_answer": "De setup is actief.",
        "main_observation": "Deze conclusie is geverifieerd.",
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
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-1", conversation_id="conv-1", user_id=7, status="completed"))
    service.verified.get_latest_for_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(response_json=response_json))

    envelope = asyncio.run(service.get_delivery_envelope(user_id=7, run_id="run-1"))

    async def _collect():
        return [event async for event in service.stream_delivery_events(user_id=7, run_id="run-1")]

    events = asyncio.run(_collect())

    assert events[0].payload["response"] == envelope.response.dict()
