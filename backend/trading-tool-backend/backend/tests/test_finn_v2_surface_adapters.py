import asyncio

from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryService


def test_mission_control_surface_uses_visible_delivery_summary():
    service = FinnV2VisibleDeliveryService(session=object())
    service.deliver_assistant_envelope = lambda **kwargs: asyncio.sleep(
        0,
        result={
            "response": "BTC briefing",
            "summary": "BTC briefing",
            "next_best_action": "Review proposal",
            "response_trace": {"trace_id": "trace-1"},
        },
    )

    payload = asyncio.run(
        service.deliver_mission_control(
            user_id=1,
            context_payload={"page": "dashboard"},
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert payload["generation_status"] == "completed"
    assert payload["finn_briefing"]["summary"] == "BTC briefing"
