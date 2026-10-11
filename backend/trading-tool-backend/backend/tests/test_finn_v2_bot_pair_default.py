from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog


ACTION = {
    "operation_id": "create_setup", "entity_type": "setup", "entity_id": "41",
    "owner_user_id": 7, "result_status": "succeeded",
    "canonical_entity": {"setup_id": 41, "strategy_id": 81, "symbol": "ETH"},
}


def test_verified_immediate_bot_request_dispatches_proposal_even_if_model_would_read():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="pair-dispatch")
    context = {
        "strict_immediate_action_lineage": True,
        "immediate_previous_action_result": ACTION,
        "verified_immediate_bot_pair_default": True,
        "immediate_bot_pair_guard_reason": "accepted",
    }
    result = asyncio.run(front.run(
        message="Maak voor dit zojuist opgeslagen plan een Paper-bot met naam Probe Bot en budget €20.",
        instructions="", conversation_context=context, verified_asset="ETH",
    ))
    state = result.proposal_analysis.request_plan.operation_state
    assert result.proposal_analysis.request_plan.operation_id == "create_bot"
    assert state["collected_inputs"]["strategy_id"] == 81
    assert state["collected_inputs"]["name"] == "Probe Bot"
    assert state["collected_inputs"]["budget_total_eur"] == 20
    assert result.response.tool_trace[0]["name"] == "verified_immediate_bot_proposal"


@pytest.mark.parametrize("message, expected", [
    ("Maak daarvoor een Paper-bot met budget €20.", True),
    ("Maak bij het zojuist opgeslagen ETH DCA-plan een Paper-bot met naam QA Paper en budget €20.", True),
    ("Voeg hier een Paper-bot aan toe, noem de bot QA Paper, budget €20.", True),
    ("Maak een Paper-bot met naam QA Paper en een budget van €20.", False),
    ("Maak een Paper-bot voor de strategie die bij het zojuist aangemaakte DCA-plan hoort, met budget €20.", True),
    ("Maak voor de strategie die bij het zojuist aangemaakte DCA-plan hoort een Paper-bot met budget €20 en noem hem QA Paper.", True),
    ("Ik wil nu voor de strategie van het net opgeslagen DCA-plan een Paper-bot met €20 budget. Maak eerst een voorstel.", True),
    ("Kun je daarvoor een Paper-bot voorbereiden met naam QA Paper en budget €20?", True),
    ("Kun je ook een Paper-bot voor dit plan maken met budget €20?", True),
    ("Voeg ook een Paper-bot toe aan deze configuratie, budget €20.", True),
    ("Koppel een Paper-bot van €20 aan de zojuist bevestigde ETH DCA-setup.", True),
    ("Maak voor het plan dat we net hebben aangemaakt een Paper-bot met budget €20.", True),
    ("Ik wil een Paper-bot van €20 voor deze setup.", True),
    ("Maak voor dit zojuist opgeslagen plan een Paper-bot met naam Probe Bot en €20 budget.", True),
    ("Ik wil hier nu ook een Paper-bot bij, naam Probe Bot, budget €20. Laat het concept zien.", True),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget. Laat eerst het voorstel zien.", True),
    ("Zou je voor dit zojuist bevestigde plan ook een Paper-bot willen voorbereiden met €20 budget? Toon eerst een voorstel.", True),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget en naam 'Probe Bot'.", True),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget en naam 'Probe Paper'. Laat eerst het voorstel zien.", True),
    ("Zou je misschien voor dit zojuist bevestigde plan een Paper-bot kunnen voorbereiden met naam 'Probe Bot' en budget €20?", True),
    ("Kan je hier ook een Paper-bot aan koppelen met budget €20 en naam 'Probe Bot'?", True),
    ("En een Paper-bot voor deze strategie? €20 budget; eerst een voorstel.", True),
    ("En een Paper-bot voor deze strategie? €20 budget, naam Probe Bot; eerst een voorstel.", True),
    ("Ik wil voor de zojuist opgeslagen strategie een Paper-bot met €20 budget en de naam Probe Bot. Maak een voorstel.", True),
    ("Maak voor dit zojuist opgeslagen plan van mijn vader een Paper-bot met €20 budget.", False),
    ("Ik wil voor de zojuist opgeslagen strategie van mijn broer een Paper-bot met €20 budget.", False),
    ("Ik wil hier nu ook een Paper-bot bij voor het plan van mijn vader.", False),
    ("Ik wil hier nu ook geen Paper-bot bij; lees mijn plan.", False),
    ("Maak een Paper-bot voor mijn andere ETH-plan.", False),
    ("Maak een Paper-bot voor mijn vorige ETH-plan met budget €20.", False),
    ("Maak een Paper-bot voor mijn oudere ETH-setup.", False),
    ("Maak een Paper-bot voor de tweede strategie.", False),
    ("Maak een Paper-bot voor mijn bestaande ETH-plan.", False),
    ("Maak een Paper-bot voor dat plan van gisteren met budget €20.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik het plan dat ik gisteren maakte.", False),
    ("Maak een Paper-bot voor dat plan uit september.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik die van gisteren.", False),
    ("Maak een Paper-bot voor die van september met budget €20.", False),
    ("Maak een Paper-bot voor mijn plan uit 2025 met budget €20.", False),
    ("Maak een bot voor deze setup van mijn vriend.", False),
    ("Maak een bot voor dat plan dat op mijn scherm staat.", False),
    ("Maak hier een bot voor het plan van mijn vriend.", False),
    ("Maak daarvoor een bot voor mijn vriend.", False),
    ("Maak bij het net opgeslagen plan van mijn vriend een Paper-bot.", False),
    ("Voeg hier een Paper-bot aan toe, maar dan voor mijn vriend.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik die van september.", False),
    ("Maak voor de strategie die bij het zojuist aangemaakte DCA-plan hoort een Paper-bot, maar gebruik mijn andere strategie.", False),
    ("Maak voor de strategie die bij het zojuist aangemaakte DCA-plan hoort een Paper-bot voor mijn vriend.", False),
    ("Maak een Paper-bot voor het net opgeslagen DCA-plan dat op mijn scherm staat.", False),
    ("Maak daarvoor een Paper-bot, maar kies die uit september.", False),
    ("Maak daarvoor een Paper-bot, maar gebruik niet die van net.", False),
    ("Maak niet daarvoor een Paper-bot met budget €20.", False),
    ("Maak een Paper-bot voor die van gisteren, daarvoor met budget €20.", False),
    ("Maak een Paper-bot voor BTC met budget €20.", False),
    ("Maak voor het net opgeslagen vriend DCA-plan een Paper-bot met budget €20.", False),
    ("Maak voor het net opgeslagen XYZ DCA-plan een Paper-bot met budget €20.", False),
    ("Maak een Paper-bot voor dit plan van mijn collega.", False),
    ("Maak een Paper-bot voor dit plan van mijn vader.", False),
    ("Maak daarvoor een Paper-bot, maar voor het plan van mijn collega.", False),
    ("Maak een Paper-bot voor setup Other Setup.", False),
    ("Maak een Paper-bot voor mijn plan met naam Other Setup.", False),
    ("Maak daarvoor een Paper-bot op het account van een zakenpartner.", False),
    ("Maak daarvoor een Paper-bot voor een gezamenlijke rekening.", False),
    ("Maak daarvoor een Paper-bot zonder bevestiging.", False),
    ("Maak geen Paper-bot voor dit plan.", False),
    ("Maak een Paper-bot voor dit plan van mijn broer.", False),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget op het account van mijn oom. Laat eerst het voorstel zien.", False),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget. Geef alleen advies over de risico’s, maak nog geen voorstel.", False),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met budget €20 en naam Probe Bot op mijn vaders rekening.", False),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met budget €20 en naam Probe Bot alleen als voorbeeld.", False),
    ("Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met budget €20 en naam Probe Bot geef alleen advies.", False),
    ("Maak daarvoor een Paper-bot met naam Probe Bot puur ter illustratie.", False),
    ("Maak daarvoor een Paper-bot met naam Probe Bot hypothetisch.", False),
    ("Maak hiervoor een Paper-bot met naam Probe Bot Op Mijn Vaders Rekening.", False),
    ("Maak hiervoor een Paper-bot met naam Probe Bot Puur Ter Illustratie.", False),
    ("Zou je misschien voor dit zojuist bevestigde plan een Paper-bot kunnen voorbereiden met naam 'Oom Bot' en budget €20 voor het portfolio van mijn oma?", False),
    ("Zou je misschien voor dit zojuist bevestigde plan een Paper-bot kunnen voorbereiden met naam 'Test Bot' en budget €20 ter illustratie?", False),
    ("Ik kan misschien een Paper-bot met naam 'Test Bot' en budget €20 voor dit plan maken.", False),
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
    assert actual is expected, context.get("immediate_bot_pair_guard_reason")


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


@pytest.mark.parametrize("message, action, reason", [
    ("Maak een Paper-bot met budget €20.", ACTION, "no_direct_reference"),
    ("Maak daarvoor een Paper-bot, maar voor mijn vriend.", ACTION, "other_owner_marker"),
    ("Maak daarvoor een Paper-bot, maar gebruik mijn vorige ETH-plan.", ACTION, "alternate_target_marker"),
    ("Maak daarvoor een Paper-bot.", {**ACTION, "result_status": "failed"}, "invalid_parent_lineage"),
    ("Maak daarvoor een Paper-bot met budget €20.", ACTION, "accepted"),
])
def test_immediate_bot_pair_records_only_a_typed_guard_reason(monkeypatch, message, action, reason):
    async def candidates(_self, *, user_id, entity_type):
        return ([{"id": 41, "name": "ETH DCA"}] if entity_type == "setup"
                else [{"id": 81, "name": "ETH DCA Strategy"}])

    monkeypatch.setattr(FinnV2EntityResolutionService, "_entity_candidates", candidates)
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    context = {"strict_immediate_action_lineage": True,
               "immediate_previous_action_result": action}

    result = asyncio.run(service._verified_immediate_bot_pair_default(
        user_id=7, message=message, context=context,
    ))

    assert result is (reason == "accepted")
    assert context["immediate_bot_pair_guard_reason"] == reason


def test_unrecognized_wording_retains_only_a_verified_semantic_candidate(monkeypatch):
    message = (
        "Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden "
        "met €20 budget voor later op vrijdag."
    )

    async def candidates(_self, *, user_id, entity_type):
        return ([{"id": 41, "name": "ETH DCA"}] if entity_type == "setup"
                else [{"id": 81, "name": "ETH DCA Strategy"}])

    monkeypatch.setattr(FinnV2EntityResolutionService, "_entity_candidates", candidates)
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    context = {"strict_immediate_action_lineage": True,
               "immediate_previous_action_result": ACTION}

    assert asyncio.run(service._verified_immediate_bot_pair_default(
        user_id=7, message=message, context=context,
    )) is False
    assert context["immediate_bot_pair_guard_reason"] == "unsupported_utterance"
    assert context["immediate_bot_pair_semantic_candidate"] is True
    assert "verified_immediate_bot_pair_default" not in context


def test_semantic_candidate_cannot_bind_a_model_supplied_strategy_id():
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20, "strategy_id": 81}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Ik wil bij dit zojuist bevestigde plan een Paper-bot voorbereiden.",
        conversation_context={
            "strict_immediate_action_lineage": True,
            "immediate_previous_action_result": ACTION,
            "immediate_bot_pair_semantic_candidate": True,
            "immediate_bot_pair_guard_reason": "unsupported_utterance",
        },
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert "strategy_id" not in state["collected_inputs"]
    assert "strategy_id" in state["missing_required_inputs"]
    assert state["selection_diagnostic"]["bound_immediate_pair"] is False


def test_joint_semantic_approval_binds_only_verified_action_strategy():
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20, "strategy_id": 999}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Kun je voor dit plan een Paper-bot regelen met naam QA Paper en budget €20?",
        conversation_context={
            "strict_immediate_action_lineage": True,
            "immediate_previous_action_result": ACTION,
            "immediate_bot_pair_semantic_candidate": True,
            "immediate_bot_pair_guard_reason": "accepted",
            "verified_immediate_bot_pair_default": True,
        },
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert state["collected_inputs"]["strategy_id"] == 81
    assert state["target_choice_required"] is False
    assert state["selection_diagnostic"]["bound_immediate_pair"] is True


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
    assert state["selection_diagnostic"] == {
        "target_reference": "unspecified", "bound_immediate_pair": True,
        "binding_guard_reason": "not_evaluated",
    }


@pytest.mark.parametrize("message", [
    "Kun je voor dit plan ook een Paper-bot voorbereiden met €20 budget? Toon eerst het voorstel.",
    "Ik wil daarvoor nu een Paper-bot van €20. Laat me de conceptkaart zien.",
    "Maak een Paper-bot van €20 voor de strategie die bij deze setup hoort.",
    "Ik wil graag bij dit zojuist bevestigde plan een Paper-bot voorbereiden met €20 budget. Laat eerst het voorstel zien.",
])
def test_immediate_pair_accepts_natural_followup_wording(monkeypatch, message):
    async def candidates(_self, *, user_id, entity_type):
        assert user_id == 7
        return ([{"id": 41, "name": "ETH DCA"}, {"id": 42, "name": "Other Setup"}]
                if entity_type == "setup" else
                [{"id": 81, "name": "ETH DCA Strategy"},
                 {"id": 82, "name": "Other Strategy"}])

    monkeypatch.setattr(FinnV2EntityResolutionService, "_entity_candidates", candidates)
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    context = {"strict_immediate_action_lineage": True,
               "immediate_previous_action_result": ACTION}
    context["verified_immediate_bot_pair_default"] = asyncio.run(
        service._verified_immediate_bot_pair_default(
            user_id=7, message=message, context=context,
        )
    )
    assert context["verified_immediate_bot_pair_default"] is True
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message=message, conversation_context=context, verified_asset="ETH",
    )
    assert result.request_plan.operation_state["collected_inputs"]["strategy_id"] == 81
    assert result.request_plan.operation_state["selection_diagnostic"] == {
        "target_reference": "confirmed_previous_plan", "bound_immediate_pair": True,
        "binding_guard_reason": "accepted",
    }


def test_relative_strategy_reference_flows_from_verified_context_to_proposal(monkeypatch):
    message = (
        "Maak een Paper-bot voor de strategie die bij het zojuist aangemaakte "
        "DCA-plan hoort, met budget €20."
    )

    async def candidates(_self, *, user_id, entity_type):
        assert user_id == 7
        return ([{"id": 41, "name": "ETH DCA"}, {"id": 42, "name": "Older DCA"}]
                if entity_type == "setup" else
                [{"id": 81, "name": "ETH DCA Strategy"},
                 {"id": 82, "name": "Older DCA Strategy"}])

    monkeypatch.setattr(FinnV2EntityResolutionService, "_entity_candidates", candidates)
    service = object.__new__(FinnV2OrchestratorService)
    service.session = object()
    context = {
        "strict_immediate_action_lineage": True,
        "immediate_previous_action_result": ACTION,
    }
    context["verified_immediate_bot_pair_default"] = asyncio.run(
        service._verified_immediate_bot_pair_default(
            user_id=7, message=message, context=context,
        )
    )
    assert context["verified_immediate_bot_pair_default"] is True
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message=message, conversation_context=context, verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert state["collected_inputs"]["strategy_id"] == 81
    assert state["input_sources"]["strategy_id"] == "verified_action_result"


def test_responses_bot_target_reference_keeps_other_plan_separate():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "draft_intent": "new",
         "target_reference": "other_saved_plan",
         "inputs": {"name": "Older Paper", "budget_total_eur": 20}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een Paper-bot voor mijn andere ETH-plan.",
        conversation_context={
            "strict_immediate_action_lineage": True,
            "immediate_previous_action_result": ACTION,
            "verified_immediate_bot_pair_default": True,
        },
        verified_asset="ETH",
    )
    assert "strategy_id" not in result.request_plan.operation_state["collected_inputs"]


def test_unverified_recent_phrase_cannot_select_or_inherit_a_strategy():
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20,
                    "strategy_id": 81}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak een Paper-bot voor mijn plan uit 2025, niet het zojuist aangemaakte plan.",
        conversation_context={
            "strict_immediate_action_lineage": True,
            "immediate_previous_action_result": ACTION,
            "active_guided_operation": {
                "operation_id": "create_bot",
                "collected_inputs": {"strategy_id": 82},
                "missing_required_inputs": [],
            },
        },
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert "strategy_id" not in state["collected_inputs"]
    assert "strategy_id" in state["missing_required_inputs"]


@pytest.mark.parametrize("message", [
    "Maak een Paper-bot voor het net opgeslagen plan met budget €20.",
    "Maak een Paper-bot voor dat plan met budget €20.",
])
def test_unverified_model_recent_reference_clears_older_context(message):
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "target_reference": "confirmed_previous_plan",
         "inputs": {"name": "QA Paper", "budget_total_eur": 20}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message=message,
        conversation_context={"last_verified_context": {"resolved_entities": {"strategy_id": 82}}},
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert "strategy_id" not in state["collected_inputs"]
    assert "strategy_id" in state["missing_required_inputs"]


def test_rejected_immediate_reference_cannot_borrow_older_strategy():
    call = FinnResponsesToolCatalog().validate(
        "manage_paper_bot_proposal",
        {"operation_id": "create_bot", "inputs": {
            "name": "Vraag Bot", "budget_total_eur": 20, "strategy_id": 81,
        }},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Ik wil hier een Paper-bot bij, maar eerst alleen sparren.",
        conversation_context={
            "immediate_bot_pair_guard_reason": "other_owner_marker",
            "last_verified_context": {"resolved_entities": {"strategy_id": 81}},
        },
        verified_asset="ETH",
    )
    state = result.request_plan.operation_state
    assert "strategy_id" not in state["collected_inputs"]
    assert "strategy_id" in state["missing_required_inputs"]


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
