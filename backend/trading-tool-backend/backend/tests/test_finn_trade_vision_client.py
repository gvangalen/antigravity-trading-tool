"""The retrospective review may pass one owner-validated PNG to OpenAI."""

import base64
from types import SimpleNamespace

import pytest

from backend.utils import openai_client


PNG = b"\x89PNG\r\n\x1a\n" + b"safe-test-pixels"


def test_optional_vision_payload_uses_responses_message_shape():
    plain = openai_client._json_prompt_messages("facts", "role")
    assert plain[1]["content"] == "facts\n\nRETURN ONLY VALID JSON."
    responses = openai_client._json_prompt_messages("facts", "role", PNG)
    data_url = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
    assert responses[1]["content"][1] == {"type": "input_image", "image_url": data_url, "detail": "low"}
    with pytest.raises(ValueError, match="invalid_png"):
        openai_client._json_prompt_messages("facts", "role", b"not-a-png")
    with pytest.raises(ValueError, match="invalid_png"):
        openai_client._json_prompt_messages("facts", "role", PNG + b"x" * (3 * 1024 * 1024))


def test_json_client_forwards_image_to_responses_provider(monkeypatch):
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(
            output_text='{"summary":"ok"}',
            usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="test-model",
        )

    monkeypatch.setattr(openai_client, "get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(openai_client, "_rate_limit_allows_call", lambda: True)
    monkeypatch.setattr(openai_client, "_quota_breaker_active", lambda: False)
    monkeypatch.setattr(openai_client, "_log_openai_usage", lambda **kwargs: None)
    monkeypatch.setattr(openai_client, "client", SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = openai_client.ask_gpt_json(prompt="facts", system_role="role", image_png=PNG, retries=1)
    assert result == {"summary": "ok"}
    assert seen[0]["input"][1]["content"][1]["type"] == "input_image"
