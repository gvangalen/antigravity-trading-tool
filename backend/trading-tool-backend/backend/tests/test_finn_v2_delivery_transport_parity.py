import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.api.finn_v2_api import _sse


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

    assert envelope.response.mode == "READ"
    assert events[0].payload["response"] == envelope.response.dict()


def test_sse_uses_the_same_iso8601_datetime_encoding_as_polling():
    created_at = datetime(2026, 8, 28, 10, 30, 0, tzinfo=timezone.utc)

    assert '"created_at": "2026-08-28T10:30:00+00:00"' in _sse(
        "run.completed", {"created_at": created_at}
    )


def test_terminal_indicator_and_bot_fields_survive_polling_and_sse_serialization():
    service = FinnV2DeliveryService(session=object())
    response_json = {
        "verified_response_id": "vr-fields", "run_id": "run-fields", "user_id": 7,
        "mode": "READ",
        "direct_answer": "Voor BTC zijn 2 indicatorconfiguraties opgeslagen: RSI, VWAP. Je gekoppelde BTC paper bot (bot 170) staat niet live.",
        "main_observation": "De opgeslagen configuratie en botstatus zijn geverifieerd.",
        "supporting_points": [], "claims": [], "uncertainty_summary": None,
        "uncertainty_codes": [], "next_step": None, "follow_up_question": None,
        "proposal_id": None, "confirmation_required": False, "verifier_status": "passed",
        "evidence_set_hash": "hash-fields", "verifier_result_id": "verifier-fields",
        "response_version": "2026-08-17.block7", "created_at": datetime.now(timezone.utc),
    }
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-fields", conversation_id="conv-fields", user_id=7, status="completed"))
    service.verified.get_latest_for_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(response_json=response_json))

    polling = asyncio.run(service.get_delivery_envelope(user_id=7, run_id="run-fields"))

    async def _collect():
        return [event async for event in service.stream_delivery_events(user_id=7, run_id="run-fields")]

    streamed = asyncio.run(_collect())[0].payload["response"]
    assert polling.response.direct_answer == streamed["direct_answer"]
    for value in ("2 indicatorconfiguraties", "RSI", "VWAP", "bot 170", "niet live"):
        assert value in polling.response.direct_answer
