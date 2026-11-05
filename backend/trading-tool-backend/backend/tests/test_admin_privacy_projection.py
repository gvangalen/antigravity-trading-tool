import asyncio
import json
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.admin_log_service import AdminLogService
from backend.services.admin_telemetry_privacy import admin_analytics_snapshot
from backend.api import system_api


def test_operator_analytics_excludes_user_text_and_metadata():
    secret = "private FINN conversation about my finances"
    snapshot = {
        "metrics_scope": "persistent_store",
        "event_count": 12,
        "confirm_funnel": {"opened": 4, "confirmed": 2},
        "top_prompts": [{"prompt": secret, "count": 1}],
        "latest_events": [{"prompt_text": secret, "metadata": {"trader_profile": secret}}],
        "top_screens": [{"page": "/report", "count": 3}, {"page": secret, "count": 1}],
        "top_cta_actions": [{"action": secret, "count": 1}],
        "top_behavioral_flags": [{"flag": secret, "count": 1}],
    }

    result = admin_analytics_snapshot(snapshot)

    assert result["event_count"] == 12
    assert result["confirm_funnel"]["confirmed"] == 2
    assert result["top_screens"] == [{"page": "/report", "count": 3}]
    assert result["privacy_sanitized"] is True
    assert secret not in json.dumps(result)
    assert "top_prompts" not in result
    assert "latest_events" not in result


def test_operator_analytics_route_returns_sanitized_projection(monkeypatch):
    secret = "private FINN conversation"
    monkeypatch.setattr(
        system_api.finn_product_analytics, "snapshot",
        lambda: {"metrics_scope": "persistent_store", "event_count": 2,
                 "top_prompts": [{"prompt": secret, "count": 1}]},
    )

    result = asyncio.run(system_api.system_finn_analytics(current_user={"role": "admin"}))

    assert result["event_count"] == 2
    assert secret not in json.dumps(result)


def test_admin_logs_do_not_return_raw_message_or_metadata():
    secret = "user said my private balance is 12345"
    row = SimpleNamespace(
        id=1, level="error", source="ai", message=secret,
        endpoint="/chat?message=" + secret, user_id=7,
        metadata_json={"prompt": secret}, created_at=datetime.now(timezone.utc),
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [row]

    class Session:
        async def execute(self, statement):
            return Result()

    result = asyncio.run(AdminLogService(Session()).get_logs())

    assert result[0]["level"] == "error"
    assert result[0]["source"] == "ai"
    assert result[0]["metadata"] is None
    assert result[0]["endpoint"] is None
    assert secret not in json.dumps(result, default=str)


def test_admin_log_analysis_sends_only_aggregate_categories(monkeypatch):
    secret = "private chat content"
    row = SimpleNamespace(
        level="error", source="ai", message=secret,
        endpoint="/chat?message=" + secret, metadata_json={"prompt": secret},
        created_at=datetime.now(timezone.utc),
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [row]

    class Session:
        async def execute(self, statement):
            return Result()

    captured = {}

    async def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"root_cause": "unknown"}

    monkeypatch.setattr("backend.services.admin_log_service.ai_usage_context", lambda **kwargs: nullcontext())
    monkeypatch.setattr("backend.services.admin_log_service.ask_gpt_json_async", fake_ask)

    asyncio.run(AdminLogService(Session()).analyze_errors_with_ai())

    assert '"level": "error"' in captured["prompt"]
    assert '"count": 1' in captured["prompt"]
    assert secret not in captured["prompt"]
    assert secret not in captured["system_role"]
