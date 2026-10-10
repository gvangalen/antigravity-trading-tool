import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services import admin_log_service


def test_admin_log_analysis_uses_explicit_responses_model(monkeypatch):
    captured = {}

    class Session:
        async def execute(self, _statement):
            row = SimpleNamespace(
                created_at=datetime.now(timezone.utc), source="api",
                message="test failure", endpoint="/api/example", metadata_json={},
            )
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))

    async def provider(**kwargs):
        captured.update(kwargs)
        return {"root_cause": "Test failure"}

    monkeypatch.setenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna")
    monkeypatch.delenv("ADMIN_LOG_ANALYSIS_MODEL", raising=False)
    monkeypatch.setattr(admin_log_service, "ai_usage_context", lambda **_: nullcontext())
    monkeypatch.setattr(admin_log_service, "ask_gpt_json_async", provider)

    result = asyncio.run(admin_log_service.AdminLogService(Session()).analyze_errors_with_ai())

    assert result["root_cause"] == "Test failure"
    assert captured["model_override"] == "gpt-6-luna"
    assert captured["reasoning_effort"] == "none"
