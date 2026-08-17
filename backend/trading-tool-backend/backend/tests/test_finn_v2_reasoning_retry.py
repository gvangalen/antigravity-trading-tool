import asyncio
from types import SimpleNamespace

from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_retries_once_on_transient_provider_error(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    calls = {"count": 0}

    async def _run_model_reasoning(**_kwargs):
        return {"status": "ready"}

    monkeypatch.setattr(service, "_run_model_reasoning", _run_model_reasoning)
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 1)

    assert service.flags.reasoning_max_retries() == 1
