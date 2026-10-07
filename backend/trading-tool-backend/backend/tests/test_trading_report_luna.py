from types import SimpleNamespace

from backend.services import finn_unified_report_service as reports
from backend.utils import openai_client

TRADING_REPORT_MODEL = "gpt-6-luna"
TRADING_REPORT_REASONING_EFFORT = "none"


def _stub_report_provider(monkeypatch, output_text):
    requests = []

    class Responses:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                output_text=output_text,
                model="gpt-6-luna",
                usage=SimpleNamespace(input_tokens=21, output_tokens=13),
            )

    monkeypatch.setattr(openai_client, "client", SimpleNamespace(responses=Responses()))
    monkeypatch.setattr(openai_client, "get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(openai_client, "_rate_limit_allows_call", lambda: True)
    monkeypatch.setattr(openai_client, "_quota_breaker_active", lambda: False)
    monkeypatch.setattr(openai_client, "_log_openai_usage", lambda **kwargs: None)
    return requests


def test_report_json_uses_luna_responses_without_legacy_sampling(monkeypatch):
    requests = _stub_report_provider(monkeypatch, '{"executive_summary":"Markets are mixed."}')

    result = openai_client.ask_gpt_json(
        prompt="Write a JSON report", system_role="Report writer", max_tokens=3000,
        model_override=TRADING_REPORT_MODEL, reasoning_effort=TRADING_REPORT_REASONING_EFFORT,
    )

    assert result == {"executive_summary": "Markets are mixed."}
    assert requests == [{
        "model": "gpt-6-luna",
        "input": [
            {"role": "system", "content": "Report writer"},
            {"role": "user", "content": "Write a JSON report\n\nRETURN ONLY VALID JSON."},
        ],
        "reasoning": {"effort": "none"},
        "max_output_tokens": 3000,
        "text": {"format": {"type": "json_object"}},
    }]


def test_report_text_uses_luna_responses(monkeypatch):
    requests = _stub_report_provider(monkeypatch, "The market is mixed. ")

    result = openai_client.ask_gpt_text(
        prompt="Summarize the week", system_role="Report writer",
        model_override=TRADING_REPORT_MODEL, reasoning_effort=TRADING_REPORT_REASONING_EFFORT,
    )

    assert result == "The market is mixed."
    assert requests[0]["model"] == "gpt-6-luna"
    assert requests[0]["reasoning"] == {"effort": "none"}
    assert "text" not in requests[0]
    assert "temperature" not in requests[0]


def test_shared_client_default_keeps_legacy_chat_route(monkeypatch):
    requests = []

    class Completions:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Legacy answer"))],
                model="gpt-4o-mini",
                usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3),
            )

    monkeypatch.setattr(openai_client, "client", SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(openai_client, "get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(openai_client, "_rate_limit_allows_call", lambda: True)
    monkeypatch.setattr(openai_client, "_quota_breaker_active", lambda: False)
    monkeypatch.setattr(openai_client, "_log_openai_usage", lambda **kwargs: None)

    assert openai_client.ask_gpt_text(prompt="Question", system_role="General") == "Legacy answer"
    assert requests[0]["model"] == openai_client.model


def test_all_trading_report_generators_pin_luna(monkeypatch):
    captured = []
    shared = {"locale": "nl", "observed_at": "2026-10-07", "assets": []}

    async def load_daily(_user_id):
        return shared

    async def load_period(_user_id, period):
        return {"period": period, "period_start": "2026-10-01",
                "period_end": "2026-10-07", "shared": shared,
                "dated_scores": [], "bot_decisions": []}

    monkeypatch.setattr(reports, "_load_context", load_daily)
    monkeypatch.setattr(reports, "_load_period_context", load_period)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **kwargs: captured.append(kwargs) or {})
    for generate in (
        reports.generate_unified_daily_report_sections,
        reports.generate_weekly_report_sections,
        reports.generate_monthly_report_sections,
        reports.generate_quarterly_report_sections,
    ):
        generate(7)
    assert len(captured) == 4
    assert all(call["model_override"] == "gpt-6-luna" for call in captured)
    assert all(call["reasoning_effort"] == "none" for call in captured)
