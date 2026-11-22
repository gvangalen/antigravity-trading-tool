from __future__ import annotations

import asyncio

from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_run_service import (
    _complete_named_guided_strategy_proposal,
    _verified_journey_affirmative_message,
)


def _context(operation: str, *, owner: int = 42, entity_id: str = "17",
             parent_id: str | None = None, canonical: dict | None = None) -> dict:
    return {
        "strict_immediate_action_lineage": True,
        "immediate_previous_action_result": {
            "operation_id": operation, "owner_user_id": owner,
            "result_status": "succeeded", "entity_id": entity_id,
            "parent_entity_id": parent_id, "canonical_entity": canonical or {},
        },
    }


def test_short_yes_resumes_only_the_confirmed_owner_setup(monkeypatch):
    seen = []

    async def next_step(self, user_id, operation, result):
        seen.append((user_id, operation, result))
        return {"step": "strategy", "setup_id": 17, "pair": "BTC/USDT"}

    monkeypatch.setattr(FinnV2ExecutionService, "_journey_next_step", next_step)
    context = _context("create_setup")
    answer = asyncio.run(_verified_journey_affirmative_message(
        object(), context=context, message="ja", user_id=42,
    ))
    assert "BTC/USDT" in answer
    assert "setup met ID 17" in answer
    assert "Maak geen nieuwe setup" in answer
    assert context["verified_journey_affirmative"] == {
        "operation_id": "create_strategy", "setup_id": 17,
    }
    assert seen == [(42, "create_setup", {"setup_id": 17})]
    assert asyncio.run(_verified_journey_affirmative_message(
        object(), context=_context("create_setup", owner=43), message="ja", user_id=42,
    )) is None
    assert asyncio.run(_verified_journey_affirmative_message(
        object(), context=context, message="Wat is mijn saldo?", user_id=42,
    )) is None
    assert asyncio.run(_verified_journey_affirmative_message(
        object(), context={**context, "strict_immediate_action_lineage": False},
        message="ja", user_id=42,
    )) is None
    assert len(seen) == 1
    english = {**context, "locale": "en-US"}
    assert "Do not create another setup" in asyncio.run(
        _verified_journey_affirmative_message(
            object(), context=english, message="yes", user_id=42,
        )
    )


def test_short_yes_resumes_confirmed_strategy_without_authorizing_trade(monkeypatch):
    async def next_step(self, user_id, operation, result):
        assert (user_id, operation, result) == (
            42, "create_strategy", {"setup_id": 9, "strategy_id": 17},
        )
        return {"step": "paper", "setup_id": 9, "strategy_id": 17,
                "pair": "BTC/USDT"}

    monkeypatch.setattr(FinnV2ExecutionService, "_journey_next_step", next_step)
    answer = asyncio.run(_verified_journey_affirmative_message(
        object(), context=_context("create_strategy", parent_id="9"),
        message="yes", user_id=42,
    ))
    assert "Paper-bot" in answer
    assert "Activeer niets en plaats geen order" in answer


def test_verified_short_yes_selects_next_contract_without_model_owned_parent():
    context = _context("create_setup")
    context["verified_journey_affirmative"] = {
        "operation_id": "create_strategy", "setup_id": 17,
    }
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=42,
                                   run_id="journey-strategy-test", model_led_coach=True)
    prepared = asyncio.run(front.run(
        message=("Bereid een strategie voor mijn bestaande BTC/USDT-setup met ID 17 voor. "
                 "Maak geen nieuwe setup. Vraag naar ontbrekende keuzes en leg de strategie ter bevestiging voor."),
        instructions="", conversation_context=context, verified_asset="BTC", locale="nl",
    ))
    assert prepared.proposal_analysis is not None
    plan = prepared.proposal_analysis.request_plan
    assert plan.operation_id == "create_strategy"
    assert plan.operation_state.get("collected_inputs", {}).get("setup_id") == 17
    assert prepared.response.response_id_reusable is False


def test_short_yes_rejects_combined_or_resolved_journey(monkeypatch):
    async def next_step(self, user_id, operation, result):
        return None

    monkeypatch.setattr(FinnV2ExecutionService, "_journey_next_step", next_step)
    assert asyncio.run(_verified_journey_affirmative_message(
        object(), context=_context("create_setup", canonical={"strategy_id": 22}),
        message="ja", user_id=42,
    )) is None
    assert asyncio.run(_verified_journey_affirmative_message(
        object(), context=_context("create_setup"), message="ja", user_id=42,
    )) is None


def test_complete_named_strategy_answer_keeps_verified_setup_proposal_path():
    answer = (
        "Noem die strategie QA BTC Strategy matrix-20261122-abc123def456ghi789. "
        "Vaste uitvoering van 10 euro, entry 76000 USDT, stop-loss 72000 USDT, "
        "target 83000 USDT, gebalanceerd risico. Toon eerst een voorstel, maak geen bot."
    )
    assert _complete_named_guided_strategy_proposal(answer, {"setup_id": 17})
    assert not _complete_named_guided_strategy_proposal(answer, {})
    assert not _complete_named_guided_strategy_proposal(answer, {"setup_id": "wrong"})
    assert not _complete_named_guided_strategy_proposal(
        answer.replace("entry 76000 USDT, ", ""), {"setup_id": 17},
    )
    assert not _complete_named_guided_strategy_proposal(
        "Noem die strategie straks, wat raad je aan?", {"setup_id": 17},
    )
