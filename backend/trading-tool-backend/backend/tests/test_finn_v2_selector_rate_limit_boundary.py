from backend.services.ai_usage_observability_service import ai_usage_context
from backend.utils import openai_client


def test_finn_selector_uses_its_bounded_dedicated_call_capacity(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_MAX_CALLS_PER_SCOPE_WINDOW", "20")
    monkeypatch.setenv("OPENAI_MAX_SELECTOR_CALLS_PER_SCOPE_WINDOW", "60")
    monkeypatch.setattr(
        openai_client,
        "acquire_ai_call_slot",
        lambda scope, **kwargs: captured.update(scope=scope, **kwargs) or True,
    )

    with ai_usage_context(entry_point="finn_v2_selector", user_id=388):
        assert openai_client._rate_limit_allows_call() is True

    assert captured == {
        "scope": "finn_v2_selector:388:GLOBAL",
        "scheduled": False,
        "limit_override": 60,
    }


def test_nonselector_call_keeps_the_generic_capacity(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        openai_client,
        "acquire_ai_call_slot",
        lambda scope, **kwargs: captured.update(scope=scope, **kwargs) or True,
    )

    with ai_usage_context(entry_point="finn_v2_reasoning", user_id=388):
        assert openai_client._rate_limit_allows_call() is True

    assert captured["limit_override"] is None
