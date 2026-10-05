from types import SimpleNamespace

from backend.ai_agents import report_ai_agent, weekly_report_agent, monthly_report_agent, quarterly_report_agent
from backend.ai_agents.report_model import TRADING_REPORT_MODEL, TRADING_REPORT_REASONING_EFFORT
from backend.utils import openai_client


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
    for module in (report_ai_agent, weekly_report_agent, monthly_report_agent, quarterly_report_agent):
        captured = []
        monkeypatch.setattr(module, "ask_gpt_text", lambda **kwargs: captured.append(kwargs) or "A sufficiently long report response.")
        if module is report_ai_agent:
            module.generate_text("prompt", "fallback")
        elif module is weekly_report_agent:
            module.generate_text("prompt", "fallback")
        else:
            module.generate_text("prompt", "fallback", [])
        assert captured[0]["model_override"] == "gpt-6-luna"
        assert captured[0]["reasoning_effort"] == "none"
