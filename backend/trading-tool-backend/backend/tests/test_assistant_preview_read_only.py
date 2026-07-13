import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.ai_assistant_service import AiAssistantService


def _service() -> AiAssistantService:
    return AiAssistantService(
        score_repo=SimpleNamespace(db=None),
        setup_repo=SimpleNamespace(),
        report_repo=SimpleNamespace(),
        bot_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(first_name="Gerrit", ai_preferences={}))),
        market_data_repo=SimpleNamespace(),
        strategy_repo=SimpleNamespace(),
        state_repo=SimpleNamespace(),
        ai_gateway=SimpleNamespace(ask=AsyncMock(return_value={"unexpected": True})),
        context_repo=None,
    )


def test_preview_insight_does_not_fallback_to_ai_when_deterministic_path_fails(monkeypatch):
    service = _service()

    async def _raise_daily(*args, **kwargs):
        raise RuntimeError("deterministic preview unavailable")

    monkeypatch.setattr(
        "backend.services.ai_assistant_service.FinnPlanService.build_daily_coach_response",
        _raise_daily,
    )

    result = asyncio.run(
        service.get_assistant_insight(
            7,
            {"symbol": "BTC", "page_type": "Market", "preview_only": True},
        )
    )

    service.ai_gateway.ask.assert_not_awaited()
    assert result["bot_insight"]["action"] == "Stel een concrete vraag of start een actie in FINN."
    assert result["market_insight"]["conclusion"] == "BTC context staat klaar."
