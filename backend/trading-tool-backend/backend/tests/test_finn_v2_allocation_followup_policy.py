"""Keep allocation follow-ups anchored to the trader's focus and current question."""

import asyncio
from unittest.mock import AsyncMock

from backend.services.finn_v2_responses_front_door import (
    FinnResponsesFrontDoor, _personal_allocation_coaching,
)
from backend.services.finn_v2_responses_loop import FinnResponsesResult


def test_model_led_allocation_followup_avoids_stale_balance_recap_and_goal_drift():
    instructions = FinnResponsesFrontDoor._model_led_instructions("nl")

    assert "without recapping unchanged account facts" in instructions
    assert "Do not repeat the Paper cash, invested balance, or bot budget" in instructions
    assert "A bot budget remains a limit" in instructions
    assert "carry forward the trader's stated investment focus" in instructions
    assert "do not present an ETF-majority example" in instructions
    assert "Do not infer that BTC focus means all-in BTC" in instructions


def test_short_example_followup_requires_current_profile_read(monkeypatch):
    prior = {
        "terminal_status": "completed",
        "answer": "Wil je dat ik een voorbeeldverdeling voor jouw BTC-portefeuille maak?",
    }
    assert _personal_allocation_coaching("ja laat maar een voorbeeld zien.", prior)
    assert _personal_allocation_coaching("Hoe zou mijn portefeuille eruit moeten zien?", None)
    assert _personal_allocation_coaching(
        "Wat is een goede verdeling, hoeveel cash en hoeveel belegd?",
        {"terminal_status": "completed", "answer": "Jouw Paper-portefeuille bevat €10.000 cash."},
    )
    assert not _personal_allocation_coaching("Wat is een ETF?", prior)

    front = FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7, run_id="allocation-followup",
        model_led_coach=True,
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Een BTC-gericht voorbeeld vraagt eerst om jouw risicogrens.",
        response_id="profile-read", tool_trace=(), answer_kind="free_text",
        model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    asyncio.run(front.run(
        message="ja laat maar een voorbeeld zien.", instructions="",
        conversation_context={}, verified_asset="BTC", previous_response=prior,
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_my_profile_and_risk_style"
