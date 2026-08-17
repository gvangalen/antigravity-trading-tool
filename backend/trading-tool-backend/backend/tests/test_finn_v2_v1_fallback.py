import asyncio
from types import SimpleNamespace

from backend.api.ai_assistant_api import _try_v2_visible_delivery


def test_visible_delivery_returns_explicit_v2_unavailable_on_technical_error(monkeypatch):
    selection = SimpleNamespace(selected_runtime="v2", visible_allowed=True, fallback_allowed=False, dict=lambda: {"selected_runtime": "v2"})

    class Selector:
        def select(self, **kwargs):
            return selection

    class Delivery:
        async def deliver_assistant_envelope(self, **kwargs):
            raise ValueError("v2_timeout")

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2RuntimeSelectorService", Selector)
    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2VisibleDeliveryService", lambda db: Delivery())

    result = asyncio.run(
        _try_v2_visible_delivery(
            db=object(),
            user_id=1,
            message="Wat is mijn BTC setup?",
            context_payload={"page": "setup"},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert result["intent"] == "unavailable"
    assert result["response_trace"]["pipeline_version"] == "finn_v2"
    assert result["response_trace"]["error"] == "v2_timeout"
