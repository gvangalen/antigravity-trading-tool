from __future__ import annotations

import asyncio

from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_run_service import (
    _complete_named_guided_strategy_proposal,
    _verified_feed_strategy_affirmative_message,
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


def test_feed_discussion_short_yes_prepares_only_owner_bound_strategy(monkeypatch):
    from types import SimpleNamespace
    from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
    from backend.infrastructure.repositories.setup_repository import SetupRepository
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    item_id = "feed-strategy-11"
    context = {"locale": "nl", "feed_event": {
        "item_id": item_id, "event_type": "strategy_next_step",
        "subject_type": "setup", "subject_id": "11", "symbol": "BTC",
        "read_only_context": True, "action_authorized": False,
    }, "responses_cursor": {"run_id": "discussion-run"}}
    async def previous(_self, *, run_id, user_id):
        assert (run_id, user_id) == ("discussion-run", 42)
        return SimpleNamespace(conversation_id="conversation-1", status="completed",
                               client_context_json={"feed_item_id": item_id})
    async def detail(_self, *, user_id, item_id):
        assert (user_id, item_id) == (42, "feed-strategy-11")
        return {"status": "handled", "event_type": "strategy_next_step", "subject_type": "setup",
                "subject_id": "11", "symbol": "BTC",
                "evidence": {"market_id": 31, "trading_pair": "BTC/USDT"}}
    async def setup(_self, setup_id, user_id):
        assert (setup_id, user_id) == (11, 42)
        return {"id": 11, "symbol": "BTC", "market_id": 31,
                "quote_currency": "USDT"}
    class Result:
        def scalar_one_or_none(self):
            return None
    class Session:
        async def execute(self, query, params):
            assert "FROM strategies" in str(query)
            assert params == {"user_id": 42, "setup_id": 11}
            return Result()
    monkeypatch.setattr(FinnV2RunRepository, "get_by_id_for_user", previous)
    monkeypatch.setattr(FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(SetupRepository, "get_setup_by_id", setup)
    answer = asyncio.run(_verified_feed_strategy_affirmative_message(
        Session(), context=context, message="ja", user_id=42,
        conversation_id="conversation-1",
    ))
    assert "BTC/USDT" in answer and "Sla nog niets op" in answer
    assert context["verified_feed_strategy_affirmative"] == {
        "operation_id": "create_strategy", "setup_id": 11,
        "source_run_id": "discussion-run",
    }
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=42,
                                   run_id="feed-strategy-test", model_led_coach=True)
    prepared = asyncio.run(front.run(
        message=answer, instructions="", conversation_context=context,
        verified_asset="BTC", locale="nl",
    ))
    assert prepared.proposal_analysis is not None
    assert prepared.proposal_analysis.request_plan.operation_id == "create_strategy"
    assert prepared.proposal_analysis.request_plan.operation_state.get(
        "collected_inputs", {}).get("setup_id") == 11


def test_feed_short_yes_rejects_other_turn_or_existing_strategy(monkeypatch):
    from types import SimpleNamespace
    from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
    from backend.infrastructure.repositories.setup_repository import SetupRepository
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    context = {"feed_event": {"item_id": "feed-11", "event_type": "strategy_next_step",
              "subject_type": "setup", "subject_id": "11", "symbol": "BTC",
              "read_only_context": True, "action_authorized": False},
              "responses_cursor": {"run_id": "previous-run"}}
    async def previous(_self, *, run_id, user_id):
        return SimpleNamespace(conversation_id="conversation-1", status="completed",
                               client_context_json={"feed_item_id": "other-feed"})
    monkeypatch.setattr(FinnV2RunRepository, "get_by_id_for_user", previous)
    assert asyncio.run(_verified_feed_strategy_affirmative_message(
        object(), context=context, message="ja", user_id=42,
        conversation_id="conversation-1",
    )) is None
    assert "verified_feed_strategy_affirmative" not in context
    async def edited_previous(_self, *, run_id, user_id):
        return SimpleNamespace(conversation_id="conversation-1", status="completed",
                               client_context_json={"feed_item_id": "feed-11",
                                                    "feed_draft_edited": True})
    monkeypatch.setattr(FinnV2RunRepository, "get_by_id_for_user", edited_previous)
    assert asyncio.run(_verified_feed_strategy_affirmative_message(
        object(), context=context, message="ja", user_id=42,
        conversation_id="conversation-1",
    )) is None
    async def exact_previous(_self, *, run_id, user_id):
        return SimpleNamespace(conversation_id="conversation-1", status="completed",
                               client_context_json={"feed_item_id": "feed-11"})
    async def detail(_self, *, user_id, item_id):
        return {"status": "handled", "event_type": "strategy_next_step", "subject_type": "setup",
                "subject_id": "11", "symbol": "BTC",
                "evidence": {"market_id": 31, "trading_pair": "BTC/USDT"}}
    async def setup(_self, setup_id, user_id):
        return {"id": 11, "symbol": "BTC", "market_id": 31,
                "quote_currency": "USDT"}
    class Result:
        def scalar_one_or_none(self):
            return 91
    class Session:
        async def execute(self, query, params):
            return Result()
    monkeypatch.setattr(FinnV2RunRepository, "get_by_id_for_user", exact_previous)
    monkeypatch.setattr(FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(SetupRepository, "get_setup_by_id", setup)
    assert asyncio.run(_verified_feed_strategy_affirmative_message(
        Session(), context=context, message="ja", user_id=42,
        conversation_id="conversation-1",
    )) is None
    assert "verified_feed_strategy_affirmative" not in context
    class NoStrategy:
        def scalar_one_or_none(self):
            return None
    class EmptySession:
        async def execute(self, query, params):
            return NoStrategy()
    for status in ("resolved", "archived", "read"):
        async def stale_detail(_self, *, user_id, item_id):
            return {"status": status, "event_type": "strategy_next_step",
                    "subject_type": "setup", "subject_id": "11", "symbol": "BTC",
                    "evidence": {"market_id": 31, "trading_pair": "BTC/USDT"}}
        monkeypatch.setattr(FinnCoachFeedService, "detail", stale_detail)
        assert asyncio.run(_verified_feed_strategy_affirmative_message(
            EmptySession(), context=context, message="ja", user_id=42,
            conversation_id="conversation-1",
        )) is None
        assert "verified_feed_strategy_affirmative" not in context
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
