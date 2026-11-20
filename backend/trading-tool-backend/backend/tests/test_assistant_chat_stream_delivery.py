import asyncio
import json
from types import SimpleNamespace

from fastapi import BackgroundTasks

from backend.api import ai_assistant_api as assistant_api
from backend.schemas.assistant_schema import AssistantChatRequest


def test_chat_stream_sends_first_byte_before_delivery_and_returns_envelope(monkeypatch):
    entered_delivery = asyncio.Event()
    release_delivery = asyncio.Event()

    monkeypatch.setattr(assistant_api, "_preflight_v2_runtime_selection",
                        lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(assistant_api, "_apply_assistant_rate_limit",
                        lambda **_kwargs: None)
    monkeypatch.setattr(assistant_api, "_record_finn_product_event",
                        lambda **_kwargs: None)

    async def deliver(**kwargs):
        assert kwargs["request_id"] == "trdm-chat-repeatable"
        entered_delivery.set()
        await release_delivery.wait()
        return {"response": "De opgeslagen botreden is gecontroleerd."}

    monkeypatch.setattr(assistant_api, "_try_v2_visible_delivery", deliver)

    async def check():
        response = await assistant_api.assistant_chat_stream(
            AssistantChatRequest(query="Waarom geen order?"), BackgroundTasks(),
            SimpleNamespace(
                scope={"path": "/api/assistant/chat/stream"},
                state=SimpleNamespace(trace_id="trdm-chat-repeatable"),
            ),
            x_trace_id="trdm-chat-repeatable", current_user={"id": 42}, db=object(),
        )
        assert response.headers["x-accel-buffering"] == "no"
        first = await response.body_iterator.__anext__()
        assert first == ": connected\n\n"
        next_chunk = asyncio.create_task(response.body_iterator.__anext__())
        await entered_delivery.wait()
        assert not next_chunk.done()
        release_delivery.set()
        envelope = await next_chunk
        assert envelope.startswith("event: envelope\n")
        payload = json.loads(envelope.split("data: ", 1)[1])
        assert payload["response"] == "De opgeslagen botreden is gecontroleerd."

    asyncio.run(check())
