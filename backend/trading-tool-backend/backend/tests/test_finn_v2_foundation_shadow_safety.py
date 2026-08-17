from pathlib import Path
import asyncio

from backend.api import ai_assistant_api as api


ROOT = Path(__file__).resolve().parents[1]


def test_v1_shadow_enqueue_is_isolated_from_v1_response(monkeypatch):
    captured = {}

    class _FakeGateway:
        def __init__(self, _db):
            pass

        async def enqueue_shadow_run(self, **kwargs):
            captured.update(kwargs)
            return True

    monkeypatch.setattr(api, "FinnV2GatewayService", _FakeGateway)

    asyncio.run(
        api._enqueue_finn_v2_shadow_run(
            db=object(),
            user_id=7,
            message="Voeg BTC toe",
            transport="chat",
            request_path="/api/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
            context_payload={"symbol": "BTC"},
        )
    )

    assert captured["user_id"] == 7
    assert captured["message"] == "Voeg BTC toe"
    assert captured["transport"] == "chat"
    assert captured["workspace_hints"] == {"symbol": "BTC"}


def test_shadow_paths_do_not_import_ai_or_action_execution_runtime():
    source = (ROOT / "services" / "finn_v2_gateway_service.py").read_text(encoding="utf-8")
    task_source = (ROOT / "celery_task" / "finn_v2_task.py").read_text(encoding="utf-8")

    assert "AiActionEngine" not in source
    assert "openai" not in source.lower()
    assert "watchlist" not in source.lower()
    assert "AiActionEngine" not in task_source
    assert "openai" not in task_source.lower()


def test_shadow_adapter_is_hooked_after_v1_rate_limit_in_chat_and_stream():
    source = (ROOT / "api" / "ai_assistant_api.py").read_text(encoding="utf-8")

    chat_rate_limit_index = source.index('endpoint="/assistant/chat"')
    chat_shadow_index = source.index("await _enqueue_finn_v2_shadow_run(", chat_rate_limit_index)
    chat_router_index = source.index("_record_finn_product_event(", chat_shadow_index)

    stream_rate_limit_index = source.index('endpoint="/assistant/chat/stream"')
    stream_shadow_index = source.index("await _enqueue_finn_v2_shadow_run(", stream_rate_limit_index)
    stream_router_index = source.index("_record_finn_product_event(", stream_shadow_index)

    assert chat_rate_limit_index < chat_shadow_index < chat_router_index
    assert stream_rate_limit_index < stream_shadow_index < stream_router_index
