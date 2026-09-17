import asyncio

from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryService


def test_mission_control_surface_uses_owner_scoped_today_snapshot():
    service = FinnV2VisibleDeliveryService(session=object())
    service.mission_control.build_mission_control_response = lambda *_args, **_kwargs: asyncio.sleep(
        0,
        result={
            "generation_status": "ready",
            "first_dashboard_context": {
                "profile": {"trader_types": ["swing"]},
                "indicators": {"market": ["Volume"], "macro": ["DXY"], "technical": ["RSI"]},
                "setup": {"name": "BTC Swing", "timeframe": "4H"},
                "strategy": {"name": "BTC Pullback"},
                "bot": {"name": "BTC Paper", "is_live": False},
                "briefing_text": "Je BTC-plan op 4H is klaar voor review.",
            },
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

    assert payload["generation_status"] == "ready"
    assert payload["first_dashboard_context"]["setup"]["name"] == "BTC Swing"
    assert payload["first_dashboard_context"]["strategy"]["name"] == "BTC Pullback"
    assert payload["first_dashboard_context"]["bot"]["name"] == "BTC Paper"
