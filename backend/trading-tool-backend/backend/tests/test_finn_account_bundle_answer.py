import asyncio

from backend.services.finn_v2_account_bundle_answer import render_account_bundle_answer
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_loop import FinnResponsesResult


def _trace():
    return ({"result": {"results": [
        {"scope": "read_active_setup", "status": "completed", "data": {
            "setup_id": 11, "symbol": "ETH", "dca_frequency": "weekly",
        }},
        {"scope": "read_linked_strategy", "status": "completed", "data": {
            "strategy_id": 22, "setup_id": 11, "symbol": "ETH", "base_amount": 10.5,
        }},
        {"scope": "read_bot_status", "status": "completed", "data": {
            "bot_id": 33, "is_active": False, "is_live": False,
            "latest_decision": {"action": "hold", "decision_at": "2026-11-07T09:12:00+00:00"},
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "bots": [{"bot_id": 33, "setup_id": 11, "strategy_id": 22, "is_live": False,
                      "symbol": "ETH", "position_qty": 0.01}],
        }},
    ]}},)


def test_account_bundle_answer_uses_exact_source_instant_and_paper_state():
    answer = render_account_bundle_answer(_trace(), locale="nl")
    assert "weekly" in answer
    assert "10.5 EUR" in answer
    assert "gepauzeerd" in answer
    assert "Paper (niet live)" in answer
    assert "0.01 ETH" in answer
    assert "hold (aanhouden) op 2026-11-07 09:12:00 UTC" in answer
    assert "2026-11-07 10:12:00 CET" in answer


def test_account_bundle_answer_fails_closed_on_mismatched_or_missing_sources():
    trace = _trace()
    trace[0]["result"]["results"][3]["data"]["bots"][0]["strategy_id"] = 99
    assert render_account_bundle_answer(trace, locale="nl") is None
    assert render_account_bundle_answer(_trace(), locale="en") is None
    trace = _trace()
    trace[0]["result"]["results"][2]["data"]["latest_decision"]["decision_at"] = "2026-11-07 09:12"
    assert render_account_bundle_answer(trace, locale="nl") is None
    trace = _trace()
    trace[0]["result"]["results"][2]["data"]["is_live"] = True
    trace[0]["result"]["results"][3]["data"]["bots"][0]["is_live"] = True
    assert render_account_bundle_answer(trace, locale="nl") is None


def test_account_followup_projects_verified_source_facts_before_answer_verification(monkeypatch):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="account-followup")
    front.model_led_coach = True
    prior = {"terminal_status": "completed", "owner_user_id": 7,
             "tool_trace": [{"result": {"results": [
                 {"scope": scope, "status": "completed", "data": {}}
                 for scope in ("read_active_setup", "read_linked_strategy",
                               "read_bot_status", "read_portfolio")
             ]}}]}

    async def fake_loop(_self, **_kwargs):
        return FinnResponsesResult(
            "De laatste beslissing was gisteren om 09:12 CET.", "response-id", _trace(),
        )

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", fake_loop,
    )
    result = asyncio.run(front.run(
        message="Wat weet je daarvan zeker? Geef dezelfde vier feiten uit mijn opgeslagen gegevens.",
        instructions=front._model_led_instructions("nl"), conversation_context={},
        verified_asset="ETH", previous_response=prior,
        workspace_hints={"page": "/asset", "symbol": "ETH"},
    ))
    assert "hold (aanhouden) op 2026-11-07 09:12:00 UTC" in result.response.text
    assert "2026-11-07 10:12:00 CET" in result.response.text
    assert "gisteren" not in result.response.text
    assert result.response.model_owned_repair is False
    assert result.response.response_id_reusable is False
    assert result.response.account_source_projection is True
