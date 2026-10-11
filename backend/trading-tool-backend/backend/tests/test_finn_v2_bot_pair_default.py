from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog


ACTION = {
    "operation_id": "create_setup", "entity_type": "setup", "entity_id": "41",
    "owner_user_id": 7, "result_status": "succeeded",
    "canonical_entity": {"setup_id": 41, "strategy_id": 81, "symbol": "ETH"},
}


@pytest.mark.parametrize("message, expected", [
    ("Maak daarvoor een Paper-bot met budget €20.", True),
    ("Maak een Paper-bot voor mijn andere ETH-plan.", False),
    ("Maak een Paper-bot voor mijn vorige ETH-plan met budget €20.", False),
    ("Maak een Paper-bot voor mijn oudere ETH-setup.", False),
    ("Maak een Paper-bot voor de tweede strategie.", False),
    ("Maak een Paper-bot voor mijn bestaande ETH-plan.", False),
    ("Maak een Paper-bot voor dat plan van gisteren met budget €20.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik het plan dat ik gisteren maakte.", False),
    ("Maak een Paper-bot voor dat plan uit september.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik die van gisteren.", False),
    ("Maak daarvoor een Paper-bot, maar kies die uit september.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik niet die van net.", False),
    ("Maak niet daarvoor een Paper-bot met budget €20.", False),
    ("Maak een Paper-bot voor die van gisteren, daarvoor met budget €20.", False),
    ("Maak een Paper-bot voor BTC met budget €20.", False),
    ("Maak een Paper-bot voor setup Other Setup.", False),
    ("Maak een Paper-bot voor mijn plan met naam Other Setup.", False),
])
def test_immediate_bot_default_uses_verified_pair_only_without_competing_target(
    monkeypatch, message, expected,
):
    async def candidates(_self, *, user_id, entity_type):
        assert user_id == 7
        return ([{"id": 41, "name": "ETH DCA"}, {"id": 42, "name": "Other Setup"}]
                if entity_type == "setup" else
                [{"id": 81, "name": "ETH DCA Strategy"}, {"id": 82, "name": "Other Strategy"}])

    monkeypatch.setattr(FinnV2EntityResolutionService, "_entity_candidates", candidates)
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    context = {
        "strict_immediate_action_lineage": True,
        "immediate_previous_action_result": ACTION,
    }
    actual = asyncio.run(service._verified_immediate_bot_pair_default(
        user_id=7, message=message, context=context,
    ))
    assert actual is expected


def test_immediate_bot_default_rejects_other_owner_and_failed_action():
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    for action in ({**ACTION, "owner_user_id": 8}, {**ACTION, "result_status": "failed"}):
        actual = asyncio.run(service._verified_immediate_bot_pair_default(
            user_id=7, message="Maak daarvoor een Paper-bot.",
            context={"strict_immediate_action_lineage": True,
                     "immediate_previous_action_result": action},
        ))
        assert actual is False


def test_responses_proposal_binds_verified_immediate_pair_without_temporal_phrase():
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "inputs": {"name": "QA Paper", "budget_total_eur": 20,
                                                    "strategy_id": 999}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak daarvoor een Paper-bot met budget €20.",
        conversation_context={
            "strict_immediate_action_lineage": True,
            "immediate_previous_action_result": ACTION,
            "verified_immediate_bot_pair_default": True,
        },
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert state["collected_inputs"]["strategy_id"] == 81
    assert state["input_sources"]["strategy_id"] == "verified_action_result"


def test_confirmation_result_promoted_only_from_exact_parent_run():
    class Conversations:
        async def get_context(self, **_kwargs):
            return {}

    class Contracts:
        async def get_latest_for_conversation(self, **_kwargs):
            return SimpleNamespace(run_id="parent", state_json={})

        async def get_latest_action_result_for_conversation(self, **_kwargs):
            return SimpleNamespace(run_id=self.action_run, state_json={"action_result": ACTION})

    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    service.conversations = Conversations()
    service.runtime_contracts = Contracts()
    service._verified_immediate_bot_pair_default = AsyncMock(return_value=False)
    for action_run, expected in (("parent", True), ("older", False)):
        service.runtime_contracts.action_run = action_run
        context = asyncio.run(service._load_continuation_context(
            conversation_id="conv", user_id=7, run_id="child",
            message="Maak daarvoor een Paper-bot.",
        ))
        assert bool(context.get("immediate_previous_action_result")) is expected


def test_persisted_bot_default_flag_is_discarded_before_next_turn():
    class Conversations:
        async def get_context(self, **_kwargs):
            return {"verified_immediate_bot_pair_default": True}

    class Contracts:
        async def get_latest_for_conversation(self, **_kwargs):
            return SimpleNamespace(run_id="parent", state_json={"action_result": ACTION})

        async def get_latest_action_result_for_conversation(self, **_kwargs):
            return SimpleNamespace(run_id="parent", state_json={"action_result": ACTION})

    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    service.conversations = Conversations()
    service.runtime_contracts = Contracts()
    service._verified_immediate_bot_pair_default = AsyncMock(return_value=False)
    context = asyncio.run(service._load_continuation_context(
        conversation_id="conv", user_id=7, run_id="child",
        message="Maak een Paper-bot voor mijn vorige plan.",
    ))
    assert "verified_immediate_bot_pair_default" not in context


@pytest.mark.parametrize("overrides, expected", [
    ({}, True),
    ({"run_id": "older"}, False),
    ({"owner_user_id": 8}, False),
    ({"result_status": "failed"}, False),
])
def test_same_parent_verified_projection_bridges_missing_action_repository_result(overrides, expected):
    class Conversations:
        async def get_context(self, **_kwargs):
            return {"verified_action_result": {**ACTION, "run_id": "parent", **overrides}}

    class Contracts:
        async def get_latest_for_conversation(self, **_kwargs):
            return SimpleNamespace(run_id="parent", state_json={})

        async def get_latest_action_result_for_conversation(self, **_kwargs):
            return None

    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    service.conversations = Conversations()
    service.runtime_contracts = Contracts()
    service._verified_immediate_bot_pair_default = AsyncMock(return_value=False)
    context = asyncio.run(service._load_continuation_context(
        conversation_id="conv", user_id=7, run_id="child",
        message="Maak daarvoor een Paper-bot.",
    ))
    assert bool(context.get("immediate_previous_action_result")) is expected
