import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_responses_loop import (
    FinnResponsesError, FinnResponsesLoop, _read_only_stop_loss_coaching,
    _saved_confirmation_readback, _hypothetical_trade_reflection,
)
from backend.services.finn_v2_responses_tool_catalog import (
    FinnResponsesToolCatalog,
    FinnResponsesToolError,
    _FORBIDDEN_MODEL_FIELDS,
    _PROPOSAL_OPERATIONS,
)
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_front_door import (
    FinnResponsesFrontDoor, _verified_listed_setup_reference, _explicit_rule_transfer_assets,
)
from backend.services.finn_v2_verified_setup_reference import (
    listed_setup_ordinal, references_selected_setup, verified_selected_setup,
    verified_selected_setup_asset,
)
from backend.services.finn_v2_turn_contract import (
    build_turn_contract, can_compose_after_first_read, turn_contract_gap,
)
from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier, FinnResponsesVerifiedAnswer
from backend.services.finn_v2_hard_claim_boundary import FinnV2HardClaimBoundary, HardClaimBoundaryResult
from backend.services.finn_v2_verified_turn_context import project_verified_turn
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_run_service import (
    FinnV2RunService, _simple_coach_experiment_enabled, _raw_coach_experiment_enabled,
    _minimal_read_answer, _minimal_read_answers_enabled,
)
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_entity_resolution_service import CanonicalEntityTarget
from backend.schemas.finn_v2_schema import VerifiedResponse


@pytest.fixture(autouse=True)
def no_provider_hard_claim_extraction(monkeypatch):
    async def assess(_self, **_kwargs):
        return HardClaimBoundaryResult(True, (), {})

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        assess,
    )


def test_model_only_coach_experiment_cannot_be_enabled_outside_local_fixture(monkeypatch):
    monkeypatch.setenv("FINN_SIMPLE_COACH_EXPERIMENT", "1")
    monkeypatch.setenv("APP_ENV", "production")
    assert _simple_coach_experiment_enabled() is False
    monkeypatch.setenv("APP_ENV", "local_finn")
    assert _simple_coach_experiment_enabled() is True
    assert VerifiedResponse(
        mode="READ", content="Een direct antwoord.", response_source="v2_runtime",
        verifier_status="not_run",
    ).verifier_status == "not_run"


def test_raw_coach_baseline_cannot_be_enabled_outside_local_fixture(monkeypatch):
    monkeypatch.setenv("FINN_RAW_COACH_EXPERIMENT", "1")
    monkeypatch.setenv("APP_ENV", "production")
    assert _raw_coach_experiment_enabled() is False
    monkeypatch.setenv("APP_ENV", "local_finn")
    assert _raw_coach_experiment_enabled() is True


def test_minimal_read_answers_uses_explicit_runtime_switch(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FINN_RAW_COACH_EXPERIMENT", "0")
    monkeypatch.setenv("FINN_MINIMAL_READ_ANSWERS", "1")
    assert _minimal_read_answers_enabled() is True
    monkeypatch.setenv("FINN_MINIMAL_READ_ANSWERS", "0")
    assert _minimal_read_answers_enabled() is False


def test_raw_coach_keeps_general_answer_but_rejects_unread_saved_strategy_claim():
    def prepared(text):
        return SimpleNamespace(response=SimpleNamespace(
            text=text, uses_previous_response=False, tool_trace=({
                "result": {"results": [
                    {"scope": "read_active_setup", "status": "completed",
                     "data": {"name": "BTC Basis"}},
                    {"scope": "read_linked_strategy", "status": "unavailable",
                     "reason": "strategy_not_resolved"},
                ]},
            },),
        ))

    general = _minimal_read_answer(
        message="Kan een kleinere positie een ruimere stop compenseren?",
        prepared=prepared("Ja, voor hetzelfde maximumbedrag daalt de positie als de stopafstand groeit."),
    )
    assert general.status == "completed"
    assert general.text.startswith("Ja, voor hetzelfde")
    unsupported = _minimal_read_answer(
        message="Wat moet ik doen terwijl ik wacht?",
        prepared=prepared("Ik kan die regel niet uit je opgeslagen strategie halen."),
    )
    assert unsupported.status == "unavailable"
    assert unsupported.reason == "saved_entity_type_unverified"


def test_minimal_read_answer_can_reuse_previous_owner_scoped_strategy_only_for_same_asset():
    previous = {
        "terminal_status": "completed",
        "turn_contract": {"targets": [{"evidence": {"symbol": "BTC"}}]},
        "tool_trace": [{"result": {"results": [{
            "scope": "read_linked_strategy", "status": "completed",
            "data": {"name": "BTC Strategy"},
        }]}}],
    }
    prepared = SimpleNamespace(
        previous_response=previous,
        response=SimpleNamespace(
            text="Je opgeslagen strategie heeft een entryprijs.",
            uses_previous_response=True, tool_trace=(),
        ),
    )
    assert _minimal_read_answer(message="En die strategie?", prepared=prepared).status == "completed"
    assert _minimal_read_answer(message="En mijn AAPL-strategie?", prepared=prepared).reason == (
        "saved_entity_type_unverified"
    )


def test_factual_tool_result_experiment_cannot_enable_outside_local_fixture(monkeypatch):
    monkeypatch.delenv("FINN_SIMPLE_COACH_EXPERIMENT", raising=False)
    monkeypatch.setenv("FINN_FACTS_ONLY_TOOL_RESULTS_EXPERIMENT", "1")
    monkeypatch.setenv("APP_ENV", "production")
    assert FinnResponsesReadExecutor._facts_only_local_experiment() is False
    monkeypatch.setenv("APP_ENV", "local_finn")
    assert FinnResponsesReadExecutor._facts_only_local_experiment() is True


@pytest.mark.parametrize(
    ("message", "expected_kind", "expected_asset"),
    [
        ("Welke BTC-setups staan er op Mijn Plan? Noem de namen.",
         "saved_setup_collection", "BTC"),
        ("Welke BTC-setups staan er op Mijn Plan? Noem de namen, zonder iets te maken of wijzigen.",
         "saved_setup_collection", "BTC"),
        ("Geldt mijn BTC-DCA-regel ook voor Apple/AAPL?",
         "cross_asset_rule_scope", None),
        ("Welke van mijn BTC-setups gebruik je en welke entrytrigger staat erin?",
         "saved_confirmation_collection", "BTC"),
    ],
)
def test_explicit_plan_scope_questions_read_owner_setup_collection_without_provider(
    message, expected_kind, expected_asset,
):
    rows = [
        {"setup_id": 11, "name": "BTC Maandag DCA", "symbol": "BTC", "setup_type": "dca"},
        {"setup_id": 12, "name": "BTC 4H terugtest", "symbol": "BTC", "setup_type": "trade"},
        {"setup_id": 13, "name": "BTC breakout", "symbol": "BTC", "setup_type": "trade"},
    ]
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="scope-read")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock(return_value={
        "kind": {
            "saved_setup_collection": "inventory",
            "saved_confirmation_collection": "confirmation_inventory",
            "cross_asset_rule_scope": "cross_asset_scope",
        }[expected_kind],
        "source_asset": "BTC" if expected_kind == "cross_asset_rule_scope" else "",
        "target_asset": "AAPL" if expected_kind == "cross_asset_rule_scope" else "",
    }))

    async def read(call):
        assert call.name == "get_saved_setup_inventory"
        assert call.inputs.get("asset") == expected_asset
        selected = [row for row in rows if not expected_asset or row["symbol"] == expected_asset]
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": selected, "setup_count": len(selected)},
        }]}

    front.reads = read
    response = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
    ))
    assert response.response.answer_kind == (
        "saved_confirmation_inventory" if expected_kind == "saved_confirmation_collection"
        else expected_kind
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=response.response, locale="nl",
    ))
    assert verified.status == "completed"
    if expected_kind == "saved_setup_collection":
        front.relevance_guard.saved_plan_query_kind.assert_not_awaited()
        assert all(row["name"] in verified.text for row in rows)
    elif expected_kind == "cross_asset_rule_scope":
        assert "niet automatisch" in verified.text
        assert "geen AAPL-plan" in verified.text
    else:
        assert "geen daarvan" in verified.text
        assert all(row["name"] in verified.text for row in rows)


def test_hypothetical_reflection_does_not_attribute_unread_entry_rule_to_saved_plan():
    message = (
        "Stel: ik nam deze maand 9 impulsieve trades, 7 verlies en 2 winst. "
        "Welk patroon zie je en welke ene regel zou ik volgende week testen?"
    )
    assert _hypothetical_trade_reflection(message)
    result = FinnResponsesResult(
        "Volgens je instapregel uit je plan had je moeten wachten.",
        "draft", (), model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.reason == "safe_hypothetical_reflection"
    assert "hypothetische voorbeeld" in verified.text
    assert "opgeslagen tradehistorie" in verified.text


def test_cross_asset_rule_answer_names_target_plan_when_one_is_saved():
    result = FinnResponsesResult(
        "Verified saved setup context.", "local-read", ({
            "name": "get_saved_setup_inventory", "status": "completed",
            "arguments": {"source_asset": "BTC", "target_asset": "AAPL"},
            "result": {"results": [{
                "scope": "read_saved_setup_inventory", "status": "completed",
                "data": {"setups": [
                    {"name": "BTC DCA", "symbol": "BTC"},
                    {"name": "AAPL geduldig", "symbol": "AAPL"},
                ]},
            }]},
        },), answer_kind="cross_asset_rule_scope", model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Geldt mijn BTC-regel ook voor AAPL?", result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert "niet automatisch" in verified.text
    assert "AAPL geduldig" in verified.text
    assert "geen AAPL-plan" not in verified.text


def test_cross_asset_rule_answer_leads_with_asset_scope_before_fomo_coaching():
    result = FinnResponsesResult(
        "Verified saved setup context.", "local-read", ({
            "name": "get_saved_setup_inventory", "status": "completed",
            "arguments": {"source_asset": "BTC", "target_asset": "AAPL"},
            "result": {"results": [{
                "scope": "read_saved_setup_inventory", "status": "completed",
                "data": {"setups": [{"setup_id": 1, "name": "BTC DCA", "symbol": "BTC"}],
                         "complete": True},
            }]},
        },), answer_kind="cross_asset_rule_scope", model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Ik voel FOMO. Mag ik mijn BTC-DCA-regel op AAPL toepassen?",
        result=result, locale="nl",
    ))
    assert verified.text.startswith("Nee, een regel voor BTC geldt niet automatisch voor AAPL.")
    assert "FOMO" in verified.text


def test_inventory_followup_reads_collection_again_instead_of_active_singleton():
    names = ("BTC Maandag DCA", "BTC 4H terugtest", "BTC breakout")
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="inventory-followup")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock(return_value={
        "kind": "confirmation_inventory", "source_asset": "", "target_asset": "",
    }))
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [
                {"setup_id": index, "name": name, "symbol": "BTC"}
                for index, name in enumerate(names, 1)
            ], "setup_count": 3, "complete": True},
        }]}

    front.reads = read
    message = "Bij welke van die drie staat een entrybevestiging?"
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
        previous_response={
            "terminal_kind": "saved_setup_collection", "answer": "Ik zie 3 setups.",
            "tool_trace": [{
                "name": "get_saved_setup_inventory", "status": "completed",
                "arguments": {"asset": "BTC"},
                "result": {"results": [{
                    "scope": "read_saved_setup_inventory", "status": "completed",
                    "data": {"setups": [
                        {"setup_id": index, "name": name, "symbol": "BTC"}
                        for index, name in enumerate(names, 1)
                    ]},
                }]},
            }],
        },
    ))
    assert len(calls) == 1
    assert calls[0].read_tools == ("read_saved_setup_inventory",)
    assert calls[0].inputs == {"asset": "BTC", "setup_ids": [1, 2, 3]}
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert answer.status == "completed"
    assert all(name in answer.text for name in names)
    assert "geen daarvan" in answer.text


@pytest.mark.parametrize("message", [
    "Welke is de tweede uit jouw lijst?",
    "De tweede uit jouw lijst. Vertel daar meer over.",
    "Bij de tweede uit jouw lijst: staat daar een entrybevestiging?",
])
def test_ordered_inventory_reference_uses_verified_id_not_model_name(message):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="ordered-reference")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock())
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC 4H terugtest",
                                "symbol": "BTC", "timeframe": "4H", "setup_type": "trade"}],
                     "setup_count": 1, "complete": True},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
        previous_response={
            "terminal_kind": "saved_setup_collection", "answer": "Ik zie drie setups.",
            "tool_trace": [{
                "name": "get_saved_setup_inventory", "status": "completed",
                "arguments": {"asset": "BTC"},
                "result": {"results": [{
                    "scope": "read_saved_setup_inventory", "status": "completed",
                    "data": {"setups": [
                        {"setup_id": 1, "name": "BTC Maandag DCA"},
                        {"setup_id": 2, "name": "BTC 4H terugtest"},
                        {"setup_id": 3, "name": "BTC breakout"},
                    ]},
                }]},
            }],
        },
    ))
    assert len(calls) == 1
    assert calls[0].name == "get_saved_setup_inventory"
    assert calls[0].inputs == {"asset": "BTC", "setup_ids": [2]}
    front.relevance_guard.saved_plan_query_kind.assert_not_awaited()
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert answer.status == "completed"
    assert "BTC 4H terugtest" in answer.text
    assert "BTC Maandag DCA" not in answer.text
    if "entrybevestiging" in message:
        assert "gekoppelde strategie" in answer.text


def test_evidence_followup_rereads_the_last_listed_setup_and_names_verified_fields():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="listed-evidence")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock())
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC Full Base",
                                "symbol": "BTC", "timeframe": "4H", "setup_type": "trade"}],
                     "setup_count": 1, "complete": True},
        }]}

    front.reads = read

    prior_list = {
        "name": "get_saved_setup_inventory", "status": "completed",
        "arguments": {"asset": "BTC"}, "result": {"results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 1, "name": "BTC Eerste"},
                                {"setup_id": 2, "name": "BTC Full Base"}]},
        }]},
    }
    prior_selection = {
        "name": "get_saved_setup_inventory", "status": "completed",
        "arguments": {"asset": "BTC", "setup_ids": [2], "listed_ordinal": 2},
        "result": {"results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC Full Base"}]},
        }]},
    }
    message = "Wat weet je daarvan zeker?"
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
        previous_response={"terminal_kind": "listed_setup_reference",
                           "answer": "Nummer 2 uit mijn lijst is ‘BTC Full Base’.",
                           "tool_trace": [prior_list, prior_selection]},
    ))
    assert len(calls) == 1
    assert calls[0].inputs == {"asset": "BTC", "setup_ids": [2]}
    assert result.response.answer_kind == "listed_setup_reference"
    assert result.response.tool_trace[0]["arguments"]["evidence_followup"] is True
    front.relevance_guard.saved_plan_query_kind.assert_not_awaited()
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "listed_setup_reference_evidence"
    assert "BTC Full Base" in answer.text
    assert "opgeslagen setupoverzicht" in answer.text
    assert "asset BTC" in answer.text
    assert "timeframe 4H" in answer.text
    assert "type trade" in answer.text
    assert "gekoppelde strategie" in answer.text
    assert "BTC Eerste" not in answer.text


def test_ordinal_and_evidence_request_in_one_turn_uses_verified_list():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="combined-evidence")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock())

    async def read(call):
        assert call.inputs == {"asset": "BTC", "setup_ids": [2]}
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC Full Base",
                                "symbol": "BTC", "timeframe": "4H", "setup_type": "trade"}],
                     "complete": True},
        }]}

    front.reads = read
    message = "De tweede uit jouw lijst: welke setup is dat en wat weet je daarvan zeker?"
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
        previous_response={"terminal_kind": "saved_setup_collection",
                           "answer": "BTC Breakout Full en BTC Full Base.",
                           "tool_trace": [{"name": "get_saved_setup_inventory", "status": "completed",
                                           "arguments": {"asset": "BTC"}, "result": {"results": [{
                                               "scope": "read_saved_setup_inventory", "status": "completed",
                                               "data": {"setups": [{"setup_id": 1, "name": "BTC Breakout Full"},
                                                                   {"setup_id": 2, "name": "BTC Full Base"}]},
                                           }]}}]},
    ))
    assert result.response.tool_trace[0]["arguments"]["evidence_followup"] is True
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert answer.reason == "listed_setup_reference_evidence"
    assert "BTC Full Base" in answer.text
    assert "opnieuw" in answer.text
    assert "gekoppelde strategie" in answer.text


@pytest.mark.parametrize(("phrase", "position"), [
    ("de tweede uit je lijst", 1), ("nummer twee", 1),
    ("nr. 2", 1), ("number two", 1), ("het derde plan", 2),
])
def test_list_position_uses_general_ordinal_and_cardinal_forms(phrase, position):
    assert listed_setup_ordinal(phrase) == position


def test_selected_setup_identity_comes_from_verified_read_not_previous_prose():
    selected = {"terminal_status": "completed", "terminal_kind": "listed_setup_reference",
                "answer": "Nummer 2 is BTC Full Base", "tool_trace": [{
                    "name": "get_saved_setup_inventory", "status": "completed",
                    "arguments": {"setup_ids": [2], "listed_ordinal": 2},
                    "result": {"results": [{"scope": "read_saved_setup_inventory",
                                           "status": "completed", "data": {"setups": [
                                               {"setup_id": 2, "name": "BTC Full Base", "symbol": "BTC"},
                                           ]}}]},
                }]}
    assert verified_selected_setup(selected) == (2, "BTC Full Base")
    assert verified_selected_setup_asset(selected, 2) == "BTC"
    assert references_selected_setup("Ik krijg FOMO bij dat plan. Wat staat er vast?")
    assert references_selected_setup("Beoordeel dat BTC-plan", "BTC")
    assert not references_selected_setup("Beoordeel dat breakout-plan", "BTC")
    assert not references_selected_setup("Ik weet dat BTC gisteren steeg")
    selected["answer"] = "Nummer 2 is BTC Breakout Full"
    assert verified_selected_setup(selected) is None
    selected["answer"] = "Nummer 2 is BTC Full Base"
    selected["tool_trace"][0]["arguments"]["setup_ids"] = [3]
    assert verified_selected_setup(selected) is None
    selected["tool_trace"][0]["arguments"]["setup_ids"] = [2]
    selected["terminal_kind"] = "saved_setup_collection"
    assert verified_selected_setup(selected) is None


def test_number_two_evidence_question_re_reads_verified_inventory_id():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="cardinal-evidence")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock())
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC Full Base",
                                "symbol": "BTC", "timeframe": "4H", "setup_type": "trade"}],
                     "complete": True},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Nummer twee: wat weet je daarvan uit mijn opgeslagen gegevens?",
        instructions="", conversation_context={}, verified_asset="BTC",
        previous_response={"terminal_kind": "saved_setup_collection",
                           "terminal_status": "completed", "answer": "Twee BTC-setups.",
                           "tool_trace": [{"name": "get_saved_setup_inventory", "status": "completed",
                                           "arguments": {"asset": "BTC"}, "result": {"results": [{
                                               "scope": "read_saved_setup_inventory", "status": "completed",
                                               "data": {"setups": [{"setup_id": 1, "name": "BTC Breakout Full"},
                                                                   {"setup_id": 2, "name": "BTC Full Base"}]},
                                           }]}}]},
    ))
    assert calls[0].inputs == {"asset": "BTC", "setup_ids": [2]}
    assert result.response.answer_kind == "listed_setup_reference"
    assert result.response.tool_trace[0]["arguments"]["evidence_followup"] is True


def test_selected_setup_coaching_does_not_turn_into_confirmation_inventory(monkeypatch):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="selected-coach")
    front.relevance_guard = SimpleNamespace(
        saved_plan_query_kind=AsyncMock(return_value={"kind": "confirmation_inventory"}),
        previous_answer_suffices=AsyncMock(return_value=False),
    )
    prior = {"terminal_kind": "listed_setup_reference", "terminal_status": "completed",
             "answer": "Nummer 2 is BTC Full Base.", "tool_trace": [{
                 "name": "get_saved_setup_inventory", "status": "completed",
                 "arguments": {"setup_ids": [2], "listed_ordinal": 2},
                 "result": {"results": [{"scope": "read_saved_setup_inventory",
                                        "status": "completed", "data": {"setups": [
                                            {"setup_id": 2, "name": "BTC Full Base"},
                                        ]}}]},
             }]}
    # A model loop may still read the selected setup, but the front door must
    # never emit a plural inventory answer for this coaching continuation.
    front.reads = AsyncMock(side_effect=AssertionError("inventory read forbidden"))
    front.model_led_coach = True
    monkeypatch.setattr("backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", AsyncMock(return_value=FinnResponsesResult(
        text="Pauzeer en toets je instapvoorwaarde.", response_id="model-coach",
        tool_trace=(), answer_kind="free_text", model_led_coach=True,
    )))
    result = asyncio.run(front.run(
        message="En als ik daardoor nu impulsief wil instappen?",
        instructions="", conversation_context={}, verified_asset="BTC",
        previous_response=prior,
    ))
    assert result.response.answer_kind != "saved_confirmation_inventory"


@pytest.mark.parametrize("message", [
    "Ik krijg FOMO bij Apple. Mag ik mijn BTC-DCA-regel daarop toepassen?",
    "Geldt mijn BTC-DCA-regel ook voor Apple/AAPL? Ik krijg FOMO.",
    "Mag ik mijn BTC-regel zomaar op AAPL toepassen door FOMO?",
    "Als ik Apple koop vanwege FOMO, mag ik dan dezelfde regel als bij BTC hanteren?",
])
def test_explicit_cross_asset_rule_transfer_survives_fomo_context(message):
    assert _explicit_rule_transfer_assets(message) == ("BTC", "AAPL")
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="asset-scope")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock(return_value=None))

    async def read(call):
        assert call.name == "get_saved_setup_inventory"
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 1, "name": "BTC maandag DCA", "symbol": "BTC"},
                                {"setup_id": 2, "name": "Apple swing", "symbol": "AAPL"}],
                     "complete": True},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
    ))
    assert result.response.answer_kind == "cross_asset_rule_scope"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert "BTC" in answer.text and "AAPL" in answer.text
    assert "niet automatisch" in answer.text
    front.relevance_guard.saved_plan_query_kind.assert_not_awaited()


def test_ambiguous_cross_asset_transfer_has_safe_typed_boundary():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="asset-scope-ambiguous")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock(return_value=None))
    result = asyncio.run(front.run(
        message="Kan dezelfde regel gelden voor BTC en Apple?",
        instructions="", conversation_context={}, verified_asset="BTC",
    ))
    assert result.response.answer_kind == "cross_asset_scope_unresolved"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Kan dezelfde regel gelden voor BTC en Apple?",
        result=result.response, locale="nl",
    ))
    assert answer.status == "completed"
    assert "niet automatisch" in answer.text
    assert "Welke opgeslagen regel" in answer.text


def test_listed_evidence_reference_rejects_unverified_or_other_turn_ids():
    trace = [{
        "name": "get_saved_setup_inventory", "status": "completed",
        "arguments": {"setup_ids": [99], "listed_ordinal": 2},
        "result": {"results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2, "name": "BTC Full Base"}]},
        }]},
    }]
    assert _verified_listed_setup_reference({
        "terminal_kind": "listed_setup_reference", "tool_trace": trace,
    }) is None
    trace[0]["arguments"]["setup_ids"] = [2]
    assert _verified_listed_setup_reference({
        "terminal_kind": "saved_setup_collection", "tool_trace": trace,
    }) is None


def test_failed_read_only_stop_loss_coaching_has_safe_process_answer():
    question = (
        "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. "
        "Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?"
    )
    rejected = FinnResponsesVerifiedAnswer(
        "unavailable", "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
        "responses_evidence_not_verified", (),
    )
    result = FinnResponsesAnswerVerifier.recover_read_only_coaching(
        message=question,
        result=FinnResponsesResult("rejected draft", "response-1", (), model_led_coach=True),
        answer=rejected, locale="nl",
    )
    assert result.status == "completed"
    assert result.reason == "safe_stop_loss_coaching"
    assert "stop-loss" in result.text
    assert "Ik wijzig niets" in result.text


def test_out_of_range_list_reference_asks_for_a_listed_name():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="out-of-range")
    front.reads = AsyncMock(side_effect=AssertionError("do not guess another setup"))
    result = asyncio.run(front.run(
        message="De vierde uit jouw lijst?", instructions="",
        conversation_context={}, verified_asset="BTC",
        previous_response={
            "terminal_kind": "saved_setup_collection", "answer": "Ik zie drie setups.",
            "tool_trace": [{"name": "get_saved_setup_inventory", "status": "completed",
                            "arguments": {"asset": "BTC"}, "result": {"results": [{
                                "scope": "read_saved_setup_inventory", "status": "completed",
                                "data": {"setups": [{"setup_id": 1}, {"setup_id": 2}, {"setup_id": 3}]},
                            }]}}],
        },
    ))
    assert result.response.answer_kind == "listed_setup_reference_out_of_range"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="De vierde uit jouw lijst?", result=result.response, locale="nl",
    ))
    assert "niet in de setup-lijst" in answer.text
    front.reads.assert_not_awaited()


def test_second_ordinal_followup_keeps_original_list_order():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="third-reference")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock())
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 3, "name": "BTC breakout"}]},
        }]}

    front.reads = read
    list_call = {
        "name": "get_saved_setup_inventory", "status": "completed",
        "arguments": {"asset": "BTC"}, "result": {"results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [
                {"setup_id": 1}, {"setup_id": 2}, {"setup_id": 3},
            ]},
        }]},
    }
    selected_call = {
        "name": "get_saved_setup_inventory", "status": "completed",
        "arguments": {"asset": "BTC", "setup_ids": [2], "listed_ordinal": 2},
        "result": {"results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 2}]},
        }]},
    }
    result = asyncio.run(front.run(
        message="En de derde uit jouw lijst?", instructions="",
        conversation_context={}, verified_asset="BTC",
        previous_response={"terminal_kind": "listed_setup_reference",
                           "answer": "Nummer 2 is BTC 4H terugtest.",
                           "tool_trace": [list_call, selected_call]},
    ))
    assert result.response.answer_kind == "listed_setup_reference"
    assert calls[0].inputs == {"asset": "BTC", "setup_ids": [3]}


def test_stop_loss_recovery_does_not_hide_proposal_failure():
    rejected = FinnResponsesVerifiedAnswer("unavailable", "failed", "proposal_failed", ())
    result = FinnResponsesAnswerVerifier.recover_read_only_coaching(
        message="Ik wil mijn stop-loss weghalen. Ik vraag om coaching, niet om iets te wijzigen.",
        result=FinnResponsesResult(
            "rejected draft", "response-1",
            ({"name": "update_strategy_proposal", "result": {"proposal_id": "p1"}},),
            model_led_coach=True,
        ), answer=rejected, locale="nl",
    )
    assert result is rejected


def test_inventory_router_never_intercepts_explicit_setup_creation(monkeypatch):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="action-boundary")
    classify = AsyncMock(return_value={"kind": "inventory", "source_asset": "", "target_asset": ""})
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=classify)
    front.reads = AsyncMock(side_effect=AssertionError("a creation request must not be answered by a read"))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run",
        AsyncMock(return_value=FinnResponsesResult("Model action route", "response-1", ())),
    )
    asyncio.run(front.run(
        message="Maak drie BTC-setups voor me.", instructions="",
        conversation_context={}, verified_asset="BTC",
    ))
    classify.assert_not_awaited()
    front.reads.assert_not_awaited()


@pytest.mark.parametrize("message", [
    "Ik twijfel tussen BTC Full Base op 4H en Apple Full Setup op 1D. Vergelijk de opgeslagen setupvoorwaarden naast elkaar en zeg wat je niet kunt vaststellen. Verander niets.",
    "Vergelijk BTC Full Base met Apple Full Setup. Verander niets.",
    "Welke opgeslagen setups staan er: BTC Full Base en Apple Full Setup? Vergelijk hun voorwaarden op 4H en 1D.",
])
@pytest.mark.parametrize("requested_tool", [
    "get_saved_setup_inventory", "get_active_plan_and_strategy",
])
def test_multi_setup_comparison_reaches_model_with_unfiltered_owner_inventory(message, requested_tool):
    fake = FakeResponses(
        response("compare-read", calls=[tool_call("call-inventory", requested_tool, {"timeframe": "4H"})]),
        response("compare-answer", text="BTC Full Base is een BTC-setup op 4H; Apple Full Setup is een AAPL-setup op 1D."),
    )
    front = FinnResponsesFrontDoor(client=SimpleNamespace(responses=fake), session=object(), user_id=7, run_id="compare-two")
    front.relevance_guard = SimpleNamespace(
        saved_plan_query_kind=AsyncMock(return_value={"kind": "inventory", "source_asset": "", "target_asset": ""}),
        is_relevant=AsyncMock(return_value=True),
    )
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL", "timeframe": "1D"},
                {"setup_id": 3, "name": "ETH Full Setup", "symbol": "ETH", "timeframe": "4H"},
            ], "complete": True},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=message, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
    ))
    assert len(calls) == 1
    assert calls[0].name == "get_saved_setup_inventory"
    assert calls[0].inputs == {}
    assert result.response.answer_kind != "saved_setup_collection"
    read_rows = [
        item["data"]["setups"]
        for trace in result.response.tool_trace
        for item in (trace.get("result") or {}).get("results") or []
        if item.get("scope") == "read_saved_setup_inventory"
    ]
    assert [[row["name"] for row in rows] for rows in read_rows] == [["BTC Full Base", "Apple Full Setup"]]
    assert result.response.tool_trace[0]["result"]["finalize_now"] is True
    assert "BTC Full Base" in result.response.text
    assert "Apple Full Setup" in result.response.text
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result.response, locale="nl",
    ))
    assert verified.status == "completed"
    assert "BTC Full Base" in verified.text and "Apple Full Setup" in verified.text


def test_model_owned_comparison_binds_exact_owner_scoped_pair():
    question = "Vergelijk BTC Full Base op 4H met Apple Full Setup op 1D."
    fake = FakeResponses(
        response("pair-read", calls=[tool_call("pair-call", "get_saved_setup_inventory", {
            "asset": None, "timeframe": "4H", "answer_mode": "compare",
            "setup_names": ["BTC Full Base", "Apple Full Setup"],
        })]),
        response("pair-answer", text=(
            "BTC Full Base is een BTC-setup op 4H; Apple Full Setup is een AAPL-setup op 1D."
        )),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="model-pair", model_led_coach=True,
    )
    reads = []

    async def read(call):
        reads.append(call)
        if call.name == "get_active_plan_and_strategy":
            setup_id = call.inputs["setup_id"]
            return {"status": "completed", "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {
                    "setup_id": setup_id,
                    "name": "BTC Full Base" if setup_id == 1 else "Apple Full Setup",
                }},
                {"scope": "read_linked_strategy", "status": "completed", "data": {
                    "setup_id": setup_id,
                    "name": "BTC Full Strategy" if setup_id == 1 else "Apple Full Strategy",
                    "entry": "76000" if setup_id == 1 else "210",
                }},
            ]}
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"complete": True, "setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL", "timeframe": "1D"},
                {"setup_id": 3, "name": "ETH Full Setup", "symbol": "ETH", "timeframe": "4H"},
            ]},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=question, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
    ))
    assert fake.requests[0]["tool_choice"] == "auto"
    assert reads[0].inputs == {}
    assert [call.inputs["setup_id"] for call in reads[1:]] == [1, 2]
    trace_result = result.response.tool_trace[0]["result"]
    assert trace_result["turn_request"] == {
        "answer_type": "compare", "target_ids": [1, 2],
    }
    assert [target["name"] for target in result.response.turn_contract["targets"]] == [
        "BTC Full Base", "Apple Full Setup",
    ]
    assert [target["strategy"]["entry"] for target in result.response.turn_contract["targets"]] == [
        "76000", "210",
    ]
    assert result.response.model_owned_repair


def test_single_saved_dca_explanation_reads_strategy_even_when_model_chooses_inventory():
    question = (
        "Lees mijn opgeslagen ETH Smart DCA Herhaal 0410 terug. Wat is het geplande bedrag "
        "bij een complete benchmarkscore van 72, en is er nu al een bot of aankoop actief?"
    )
    fake = FakeResponses(
        response("dca-inventory", calls=[tool_call("dca-call", "get_saved_setup_inventory", {
            "asset": "ETH", "timeframe": "1D", "answer_mode": "explain",
            "setup_names": ["ETH Smart DCA Herhaal 0410"],
        })]),
        response("dca-answer", text="De opgeslagen strategie plant €117 bij score 72; een aankoop is niet bewezen."),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="saved-dca-readback", model_led_coach=True,
    )
    reads = []

    async def read(call):
        reads.append(call)
        if call.name == "get_active_plan_and_strategy":
            assert call.inputs == {"setup_id": 41}
            return {"status": "completed", "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {
                    "setup_id": 41, "name": "ETH Smart DCA Herhaal 0410", "symbol": "ETH",
                    "dca_frequency": "monthly", "dca_month_day": 19,
                }},
                {"scope": "read_linked_strategy", "status": "completed", "data": {
                    "setup_id": 41, "strategy_id": 71, "base_amount": 90,
                    "dca_amount_mode": "score_bands", "low_threshold": 35,
                    "high_threshold": 65, "low_score_percent": 70,
                    "mid_score_percent": 100, "high_score_percent": 130,
                }},
            ]}
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed", "data": {
                "setups": [{"setup_id": 41, "name": "ETH Smart DCA Herhaal 0410",
                            "symbol": "ETH", "timeframe": "1D", "setup_type": "dca"}],
                "complete": True,
            },
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=question, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
    ))
    assert [call.name for call in reads] == [
        "get_saved_setup_inventory", "get_active_plan_and_strategy",
    ]
    scopes = [item.get("scope") for item in result.response.tool_trace[0]["result"]["results"]]
    assert scopes == ["read_saved_setup_inventory", "read_active_setup", "read_linked_strategy"]
    assert "€117" in result.response.text


def test_named_open_dca_draft_is_read_even_when_model_chooses_saved_inventory():
    name = "ETH Vast Concept Coach"
    context = {"proposal_revision": {
        "operation_id": "create_setup", "proposal_id": "owned-draft",
        "guided_state": {
            "operation_id": "create_setup", "open_proposal_id": "owned-draft",
            "collected_inputs": {
                "name": name, "symbol": "ETH", "setup_type": "dca",
                "dca_frequency": "weekly", "dca_day": "friday",
                "dca_amount_mode": "fixed", "base_amount": 75,
            },
        },
    }}
    fake = FakeResponses(
        response("wrong-read", calls=[tool_call("wrong-call", "get_saved_setup_inventory", {
            "asset": "ETH", "timeframe": None, "answer_mode": "explain",
            "setup_names": [name], "strategy_name": None,
        })]),
        response("draft-answer", text="De open conceptkaart koopt elke vrijdag voor €75; hij is nog niet opgeslagen."),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="open-dca-draft-read", model_led_coach=True,
    )

    async def unexpected_saved_read(_call):
        raise AssertionError("an open draft must not be read as a saved setup")

    front.reads = unexpected_saved_read
    result = asyncio.run(front.run(
        message=f"Kun je {name} uitleggen: is het bedrag altijd €75?",
        instructions=front._model_led_instructions("nl"),
        conversation_context=context, verified_asset=None,
    ))
    evidence = result.response.tool_trace[0]["result"]["results"][0]
    assert evidence["scope"] == "read_open_dca_draft"
    assert evidence["data"]["saved"] is False
    assert evidence["data"]["fields"]["base_amount"] == 75
    assert evidence["data"]["missing_benchmark_component_policy"] == "not_required_to_determine_fixed_amount"
    assert "€75" in result.response.text


def test_open_smart_dca_draft_holds_when_benchmark_component_is_missing():
    context = {"proposal_revision": {
        "operation_id": "create_setup", "proposal_id": "smart-draft",
        "guided_state": {
            "operation_id": "create_setup", "open_proposal_id": "smart-draft",
            "collected_inputs": {
                "name": "ETH Smart Concept", "symbol": "ETH",
                "setup_type": "dca", "dca_amount_mode": "score_bands",
                "base_amount": 75,
            },
        },
    }}
    fake = FakeResponses(
        response("smart-read", calls=[tool_call("smart-call", "get_open_dca_draft", {})]),
        response("smart-answer", text="Zonder complete benchmarkscore berekent dit concept geen aankoopbedrag."),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="open-smart-dca-policy", model_led_coach=True,
    )
    result = asyncio.run(front.run(
        message="Wat doet dit open Smart DCA-concept zonder macro-score?",
        instructions=front._model_led_instructions("nl"),
        conversation_context=context, verified_asset=None,
    ))
    evidence = result.response.tool_trace[0]["result"]["results"][0]
    assert evidence["data"]["missing_benchmark_component_policy"] == "hold_without_purchase"


def test_open_dca_draft_does_not_replace_a_different_named_saved_setup():
    context = {"proposal_revision": {
        "operation_id": "create_setup", "proposal_id": "open-draft",
        "guided_state": {
            "open_proposal_id": "open-draft",
            "collected_inputs": {
                "name": "ETH Open Concept", "symbol": "ETH", "setup_type": "dca",
                "dca_amount_mode": "fixed", "base_amount": 75,
            },
        },
    }}
    fake = FakeResponses(
        response("saved-read", calls=[tool_call("saved-call", "get_saved_setup_inventory", {
            "asset": "ETH", "timeframe": None, "answer_mode": "explain",
            "setup_names": ["ETH Bestaand Plan"], "strategy_name": None,
        })]),
        response("saved-answer", text="ETH Bestaand Plan is opgeslagen."),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="saved-plan-beside-open-draft", model_led_coach=True,
    )
    reads = []

    async def read(call):
        reads.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"setups": [{"setup_id": 41, "name": "ETH Bestaand Plan", "symbol": "ETH"}]},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Wat weet je over mijn opgeslagen ETH Bestaand Plan?",
        instructions=front._model_led_instructions("nl"),
        conversation_context=context, verified_asset=None,
    ))
    assert len(reads) == 1
    assert result.response.tool_trace[0]["result"]["results"][0]["scope"] == "read_saved_setup_inventory"


def test_cross_asset_followup_binds_verified_source_and_unique_target():
    question = "Mag ik dezelfde BTC-regel ook voor Apple gebruiken?"
    fake = FakeResponses(
        response("asset-read", calls=[tool_call("asset-call", "get_saved_setup_inventory", {
            "asset": "BTC", "timeframe": None, "answer_mode": "explain",
            "setup_names": ["BTC Full Base"],
        })]),
        response("asset-answer", text=(
            "De regel van BTC Full Base geldt niet automatisch voor Apple Full Setup op AAPL."
        )),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="cross-asset-source", model_led_coach=True,
    )

    async def read(_call):
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"complete": True, "setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC"},
                {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL"},
                {"setup_id": 3, "name": "BTC Breakout Full", "symbol": "BTC"},
            ]},
        }]}

    front.reads = read
    previous = {
        "terminal_status": "completed", "terminal_kind": "free_text",
        "owner_user_id": 7, "answer": "BTC Full Base is de tweede setup.",
        "verified_setup_subject": {"owner_id": 7, "setup_id": 1,
                                    "name": "BTC Full Base", "symbol": "BTC"},
    }
    result = asyncio.run(front.run(
        message=question, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
        previous_response=previous, previous_response_id="resp-prior",
    ))
    tool_result = result.response.tool_trace[0]["result"]
    assert tool_result["turn_request"] == {"answer_type": "explain", "target_ids": [1, 2]}
    assert tool_result["finalize_now"] is True
    assert [row["name"] for row in tool_result["results"][0]["data"]["setups"]] == [
        "BTC Full Base", "Apple Full Setup",
    ]


def test_complete_cross_asset_inventory_ends_read_round_without_guessing_source():
    question = "Als ik Apple koop vanwege FOMO, mag ik dezelfde regel als bij BTC hanteren?"
    fake = FakeResponses(
        response("cross-read", calls=[tool_call("cross-call", "get_active_plan_and_strategy", {
            "asset": "Apple", "timeframe": None, "setup_name": None,
            "reference": "current_request",
        })]),
        response("cross-answer", text=(
            "Nee, een BTC-regel geldt niet automatisch voor Apple. "
            "Er zijn twee BTC-setups; welke regel bedoel je?"
        )),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="cross-asset-ambiguous", model_led_coach=True,
    )

    async def read(_call):
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed",
            "data": {"complete": True, "setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC"},
                {"setup_id": 2, "name": "BTC Breakout Full", "symbol": "BTC"},
                {"setup_id": 3, "name": "Apple Full Setup", "symbol": "AAPL"},
            ]},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=question, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
    ))
    tool_result = result.response.tool_trace[0]["result"]
    assert tool_result["finalize_now"] is True
    assert "turn_request" not in tool_result
    assert result.response.turn_contract["targets"] == []
    assert fake.requests[1]["tool_choice"] == "none"


def test_current_risk_tradeoff_outweighs_tool_list_hint():
    contract = build_turn_contract(
        message=("Zou een kleinere positie met een ruimere stop verstandiger zijn? "
                 "Weeg stopafstand en positieomvang af."),
        tool_trace=({"result": {"turn_request": {"answer_type": "list"}}},),
    )
    assert contract["answer_type"] == "weigh"
    assert contract["targets"] == []
    assert turn_contract_gap(contract, "Een ruimere stop vraagt om een kleinere positie.") is None
    assert turn_contract_gap(contract, "Een wachttijd helpt.") == "risk_tradeoff_topic_missing"


def test_saved_entry_question_requires_linked_strategy_read_before_absence_claim():
    message = "Ik krijg FOMO bij dat plan. Wat zijn de instap en stop?"
    setup_read = ({"name": "evaluate_setup", "result": {"results": [{
        "scope": "read_active_setup", "status": "completed", "data": {
            "setup_id": 42, "name": "BTC Full Base", "symbol": "BTC",
        },
    }]}},)
    subject = {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC"}
    contract = build_turn_contract(
        message=message, tool_trace=setup_read, previous_subject=subject,
    )
    assert contract["saved_subject_reference"]
    assert turn_contract_gap(
        contract, "Bij BTC Full Base zie ik geen instap of stopniveau.",
    ) == "linked_strategy_not_checked"
    strategy_attempt = setup_read + ({"name": "get_active_plan_and_strategy", "result": {
        "results": [{"scope": "read_linked_strategy", "status": "unavailable",
                     "reason": "strategy_not_resolved", "data": None}],
    }},)
    attempted = build_turn_contract(
        message=message, tool_trace=strategy_attempt, previous_subject=subject,
    )
    assert turn_contract_gap(
        attempted, "Ik kon de gekoppelde strategie niet eenduidig lezen.",
    ) is None


def test_verified_single_inventory_row_becomes_durable_ordinal_subject():
    row = {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"}
    previous = {
        "terminal_status": "completed", "terminal_kind": "free_text",
        "user_message": "Nummer twee: wat weet je daarvan uit mijn opgeslagen gegevens?",
        "answer": "Nummer twee is BTC Full Base, een BTC-setup op 4H.",
        "turn_contract": {"targets": [{"setup_id": 42, "name": "BTC Full Base"}]},
        "tool_trace": [{"name": "get_saved_setup_inventory", "status": "completed",
                        "result": {"results": [{"scope": "read_saved_setup_inventory",
                                                "status": "completed", "data": {"setups": [row]}}]}}],
    }
    assert verified_selected_setup(previous) == (42, "BTC Full Base")
    assert verified_selected_setup_asset(previous, 42) == "BTC"
    previous["turn_contract"]["targets"] = [
        {"setup_id": 41, "name": "BTC Breakout Full"},
        {"setup_id": 42, "name": "BTC Full Base"},
    ]
    assert verified_selected_setup(previous) is None


def test_saved_strategy_levels_use_typed_source_without_semantic_rewrite():
    message = "En welke entry en stop horen daarbij volgens mijn opgeslagen strategie?"
    trace = ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"}},
            {"scope": "read_linked_strategy", "status": "completed",
             "data": {"setup_id": 42, "name": "BTC Full Base Strategy",
                      "entry": "76000", "stop_loss": "72000"}},
        ]},
    },)
    draft = "Volgens BTC Full Base Strategy is de entry 76.000 en de stop-loss 72.000."
    result = FinnResponsesResult(
        draft, "saved-levels", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("unexpected model judge")))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    assert answer.reason == "source_bound_strategy_fields"
    semantic.verify_async.assert_not_awaited()


    coaching_question = "Ik krijg FOMO bij dat plan. Wat zijn de instap en stop, en wat zou je eerst checken?"
    coaching_draft = (
        "Voor BTC Full Base staat in BTC Full Base Strategy een instap op 76.000 "
        "en een stop-loss op 72.000. Dat zijn opgeslagen niveaus, geen advies om nu in te stappen. "
        "Controleer eerst je vooraf bepaalde instapvoorwaarden; FOMO is geen bevestiging."
    )
    coaching_result = FinnResponsesResult(
        coaching_draft, "saved-levels-coach", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=coaching_question, tool_trace=trace),
    )
    coached = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=coaching_question, result=coaching_result, locale="nl",
    ))
    assert coached.status == "completed" and coached.text == coaching_draft
    semantic.verify_async.assert_not_awaited()


def test_strategy_entry_must_not_be_presented_as_a_setup_field():
    evidence = (
        {"scope": "read_active_setup", "status": "completed",
         "data": {"name": "BTC Full Base", "setup_id": 42}},
        {"scope": "read_linked_strategy", "status": "completed",
         "data": {"name": "BTC Full Strategy", "setup_id": 42, "entry": "76000"}},
    )
    guard = FinnResponsesAnswerVerifier._strategy_levels_attributed_to_setup
    assert guard("In BTC Full Base staat als concrete instapwaarde 76.000 opgeslagen.", evidence)
    assert guard("In BTC Full Base staat de instap op 76.000 in de gekoppelde strategie.", evidence)
    assert not guard("Bij BTC Full Base staat in je opgeslagen strategie een instap op 76.000.", evidence)
    assert not guard("Bij BTC Full Base staat in BTC Full Strategy een entry van 76.000.", evidence)


def test_impulsive_entry_verb_does_not_require_a_saved_entry_price():
    trace = ({"result": {"results": [
        {"scope": "read_active_setup", "status": "completed",
         "data": {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC"}},
        {"scope": "read_linked_strategy", "status": "completed",
         "data": {"setup_id": 42, "name": "BTC Full Strategy", "entry": "76000"}},
    ]}},)
    contract = build_turn_contract(
        message="En als ik daardoor nu impulsief wil instappen?", tool_trace=trace,
        previous_subject={"setup_id": 42, "symbol": "BTC"},
    )
    assert "entry" not in contract["requested_fields"]
    assert turn_contract_gap(contract, "Pauzeer eerst; FOMO bevestigt geen instapvoorwaarde.") is None


def test_saved_target_price_guard_distinguishes_risk_reward_ratio():
    evidence = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "name": "BTC Full Strategy", "entry": "76000", "stop_loss": "72000",
        "targets": ["84000"],
        "level_geometry": {"targets": [{"reward_to_risk": "2.00"}]},
    }},)
    guard = FinnResponsesAnswerVerifier._saved_strategy_levels_supported
    assert guard(
        "Entry 76.000, stop-loss 72.000 en target 84.000. "
        "De berekende risk/reward tot het target is 2,00.", evidence, "",
    )
    assert not guard("Entry 76.000 en target 85.000.", evidence, "")
    assert not guard("Risk/reward 2,00; target 85.000.", evidence, "")


def test_linked_strategy_identity_uses_typed_source_without_semantic_rewrite():
    message = "Welke strategie is gekoppeld aan BTC Full Base? Lees die opgeslagen strategie zonder iets te wijzigen."
    trace = ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"}},
            {"scope": "read_linked_strategy", "status": "completed",
             "data": {"setup_id": 42, "name": "BTC Full Base Strategy",
                      "entry": "76000", "stop_loss": "72000"}},
        ]},
    },)
    draft = "Aan BTC Full Base is BTC Full Base Strategy gekoppeld; de entry is 76.000 en de stop-loss 72.000."
    result = FinnResponsesResult(
        draft, "linked-strategy", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    assert "strategy_name" in result.turn_contract["requested_fields"]
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("unexpected model judge")))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    assert answer.reason == "source_bound_read"
    semantic.verify_async.assert_not_awaited()


def test_asset_transfer_boundary_survives_ambiguous_saved_source():
    message = "Als ik Apple koop vanwege FOMO, mag ik dan dezelfde regel als bij BTC hanteren?"
    rows = [
        {"setup_id": 1, "name": "BTC Breakout Full", "symbol": "BTC"},
        {"setup_id": 2, "name": "BTC Full Base", "symbol": "BTC"},
        {"setup_id": 3, "name": "Apple Full Setup", "symbol": "AAPL"},
    ]
    trace = ({"name": "get_saved_setup_inventory", "status": "completed", "result": {
        "results": [{"scope": "read_saved_setup_inventory", "status": "completed",
                     "data": {"setups": rows, "complete": True}}],
    }},)
    draft = (
        "Gebruik niet automatisch dezelfde regel voor Apple als voor BTC. "
        "Welke BTC-setup bedoel je: BTC Breakout Full of BTC Full Base?"
    )
    result = FinnResponsesResult(
        draft, "asset-boundary", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("unexpected model judge")))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    assert answer.reason == "source_bound_asset_transfer"
    semantic.verify_async.assert_not_awaited()


def test_comparison_can_explicitly_exclude_an_unselected_setup():
    message = "Vergelijk BTC Full Base met Apple Full Setup, niet ETH Full Setup."
    rows = [
        {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"},
        {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL", "timeframe": "1D"},
        {"setup_id": 3, "name": "ETH Full Setup", "symbol": "ETH", "timeframe": "4H"},
    ]
    trace = ({"name": "get_saved_setup_inventory", "status": "completed", "result": {
        "turn_request": {"answer_type": "compare", "target_ids": [1, 2]},
        "results": [{"scope": "read_saved_setup_inventory", "status": "completed",
                     "data": {"setups": rows, "complete": True}}],
    }},)
    draft = (
        "BTC Full Base is een BTC-setup op 4H; Apple Full Setup is een AAPL-setup op 1D. "
        "Ik heb geen ETH Full Setup gebruikt."
    )
    result = FinnResponsesResult(
        draft, "excluded-object", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("unexpected model judge")))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed" and answer.reason == "source_bound_read"
    semantic.verify_async.assert_not_awaited()


def test_verified_single_setup_overrides_only_spurious_ambiguity_verdict():
    message = "Ik krijg FOMO bij dat plan. Wat zijn de instap en stop?"
    evaluation = {"name": "evaluate_setup", "status": "completed", "result": {
        "evaluation_operation_id": "evaluate_setup",
        "assessment_status": "evidence_collected_not_yet_judged", "results": [],
    }}
    read = {"name": "get_active_plan_and_strategy", "status": "completed", "result": {
        "results": [
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 42, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H",
            }},
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 42, "name": "BTC Full Base Strategy",
                "entry": "76000", "stop_loss": "72000",
            }},
        ],
    }}
    trace = (evaluation, read)
    text = (
        "Bij BTC Full Base staat in je opgeslagen strategie een instap op 76.000 "
        "en een stop-loss op 72.000. Dit is geen bevestiging om nu te kopen."
    )
    result = FinnResponsesResult(
        text, "typed-target", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == text


def test_unselected_source_can_state_ambiguity_without_fixed_fallback():
    message = "Mag ik dezelfde BTC-regel ook voor Apple gebruiken?"
    draft = (
        "Een BTC-regel geldt niet automatisch voor Apple. Ik kan niet bevestigen "
        "welke BTC-regel je bedoelt of of die in de Apple-setup staat. Welke regel bedoel je?"
    )
    trace = ({"name": "get_saved_setup_inventory", "status": "completed", "result": {
        "results": [{"scope": "read_saved_setup_inventory", "status": "completed",
                     "data": {"complete": True, "setups": [
                         {"setup_id": 1, "name": "BTC Breakout Full", "symbol": "BTC"},
                         {"setup_id": 2, "name": "BTC Full Base", "symbol": "BTC"},
                         {"setup_id": 3, "name": "Apple Full Setup", "symbol": "AAPL"},
                     ]}}],
    }},)
    result = FinnResponsesResult(
        draft, "ambiguous-source", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    second_draft = (
        "Ga niet automatisch uit van dezelfde regel: er zijn aparte BTC- en Apple-setups, "
        "maar geen bevestigingsregel om gelijkheid vast te stellen. "
        "Welke BTC-regel bedoel je precies?"
    )
    second_result = FinnResponsesResult(
        second_draft, "ambiguous-source-2", trace, model_led_coach=True,
        model_owned_repair=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    second_answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=message, result=second_result, locale="nl",
    ))
    assert second_answer.status == "completed"
    assert second_answer.text == second_draft


def test_inventory_count_is_not_mistaken_for_asset_units():
    evidence = ({"status": "completed", "asset": "BTC", "scope": "read_saved_setup_inventory",
                 "data": {"setups": [{"name": "BTC Full Base"}, {"name": "BTC Breakout Full"}]}},)
    assert FinnResponsesAnswerVerifier._asset_quantities_supported(
        answer="Ik zie 2 BTC-setups.", message="Welke BTC-setups heb ik?", evidence=evidence,
    )
    assert FinnResponsesAnswerVerifier._asset_quantities_supported(
        answer="Je hebt 2 BTC plannen.", message="Welke BTC-plannen heb ik?", evidence=evidence,
    )
    assert not FinnResponsesAnswerVerifier._asset_quantities_supported(
        answer="Je bezit 2 BTC.", message="Welke BTC-setups heb ik?", evidence=evidence,
    )
    inventory_answer = (
        "Je hebt **2 BTC-setups** opgeslagen:\n\n"
        "- **BTC Breakout Full** — trade, 4H\n"
        "- **BTC Full Base** — trade, 4H"
    )
    assert FinnResponsesAnswerVerifier._language_matches(inventory_answer, "nl")
    detail_answer = (
        "Van **BTC Full Base** staat vast:\n\n"
        "- **Asset:** BTC\n- **Timeframe:** 4H\n- **Type:** trade\n\n"
        "Er zijn geen DCA-instellingen of minimuminvestering ingevuld."
    )
    assert FinnResponsesAnswerVerifier._language_matches(detail_answer, "nl")
    assert not FinnResponsesAnswerVerifier._language_matches(
        "You have two saved BTC setups and can review them now.", "nl",
    )


def test_strategy_field_followup_reads_linked_strategy_instead_of_setup_names():
    draft = "BTC Full Base Strategy heeft entry 76.000; een aparte trigger is niet bevestigd."
    fake = FakeResponses(
        response("strategy-read", calls=[tool_call(
            "call-strategy", "get_active_plan_and_strategy", {"setup_name": "BTC Full Base"},
        )]),
        response("strategy-answer", text=draft),
    )
    front = FinnResponsesFrontDoor(client=SimpleNamespace(responses=fake), session=object(), user_id=7, run_id="strategy-followup")
    front.relevance_guard = SimpleNamespace(
        saved_plan_query_kind=AsyncMock(return_value={"kind": "inventory", "source_asset": "", "target_asset": ""}),
        previous_answer_suffices=AsyncMock(return_value=False),
        is_relevant=AsyncMock(return_value=True),
    )
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"setup_id": 2, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"}},
            {"scope": "read_linked_strategy", "status": "completed",
             "data": {"setup_id": 2, "name": "BTC Full Base Strategy", "entry": 76000}},
        ]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Welke strategienaam, entryniveau en aparte trigger horen bij die BTC-setup uit mijn setups?",
        instructions=front._model_led_instructions("nl"), conversation_context={},
        verified_asset="BTC", previous_response={
            "answer": "Voor BTC Full Base heb ik de gekoppelde strategie gelezen.",
            "terminal_kind": "grounded_named_setup_coaching", "terminal_status": "completed",
            "owner_user_id": 7,
            "verified_setup_subject": {"owner_id": 7, "setup_id": 2, "name": "BTC Full Base", "symbol": "BTC"},
        },
    ))
    assert len(calls) == 1
    assert calls[0].name == "get_active_plan_and_strategy"
    # The mock has no session_factory, so owner-scoped target resolution is
    # exercised by the existing resolver tests rather than this route test.
    assert calls[0].inputs == {}
    assert result.response.answer_kind != "saved_setup_collection"
    assert result.response.text == draft
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Welke strategienaam, entryniveau en aparte trigger horen bij die BTC-setup uit mijn setups?",
        result=result.response, locale="nl",
    ))
    assert verified.status == "completed"
    assert "BTC Full Base Strategy" in verified.text
    assert "76.000" in verified.text


def test_typed_strategy_read_does_not_need_second_model_judgment():
    question = "Welke strategienaam, welk entryniveau en welke aparte trigger staan daarin?"
    trace = ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 2, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H",
            }},
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 2, "name": "BTC Full Base Strategy", "entry": "76000",
                "entry_type": None,
            }},
        ]},
    },)
    contract = build_turn_contract(message=question, tool_trace=trace)
    draft = (
        "Bij BTC Full Base heet de strategie BTC Full Base Strategy. "
        "Het entryniveau is 76.000 en een aparte trigger staat niet vast: "
        "`entry_type` is leeg."
    )
    semantic = SimpleNamespace(verify_async=AsyncMock())
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=question,
        result=FinnResponsesResult(
            draft, "typed-read", trace, model_led_coach=True,
            turn_contract=contract,
        ), locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    semantic.verify_async.assert_not_called()
    wrong_level = draft.replace("76.000", "80.000")
    rejected = asyncio.run(FinnResponsesAnswerVerifier(SimpleNamespace(
        verify_async=AsyncMock(return_value=SimpleNamespace(
            available=True, passes=False, reason_codes=["unverified_personal_claim"],
        )),
    )).verify(
        message=question,
        result=FinnResponsesResult(
            wrong_level, "wrong-level", trace, model_led_coach=True,
            turn_contract=contract,
        ), locale="nl",
    ))
    assert rejected.text != wrong_level


def test_turn_contract_keeps_comparison_targets_across_correction():
    trace = ({
        "name": "get_saved_setup_inventory", "status": "completed",
        "result": {"results": [{"scope": "read_saved_setup_inventory", "status": "completed", "data": {
            "setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL", "timeframe": "1D"},
                {"setup_id": 3, "name": "ETH Full Setup", "symbol": "ETH", "timeframe": "4H"},
            ],
        }}]},
    },)
    question = "Vergelijk BTC Full Base op 4H met Apple Full Setup op 1D."
    contract = build_turn_contract(message=question, tool_trace=trace)
    assert contract["answer_type"] == "compare"
    assert [target["setup_id"] for target in contract["targets"]] == [1, 2]
    assert contract["targets"][1]["evidence"]["timeframe"] == "1D"
    followup = build_turn_contract(
        message="Dat is een lijst, geen vergelijking. Wat verschilt er tussen die twee?",
        tool_trace=(), previous_contract=contract,
    )
    assert [target["setup_id"] for target in followup["targets"]] == [1, 2]
    assert turn_contract_gap(followup, "BTC verschilt van AAPL op 4H en 1D.") == "comparison_targets_missing"
    assert turn_contract_gap(contract, "BTC Full Base staat op 4H.") == "comparison_targets_missing"
    assert turn_contract_gap(contract, "Ik zie BTC Full Base en Apple Full Setup.") == "comparison_fields_missing"
    rejected = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question,
        result=FinnResponsesResult(
            "BTC Full Base staat op 4H.", "comparison-incomplete", trace,
            model_led_coach=True, turn_contract=contract,
        ),
        locale="nl",
    ))
    assert rejected.reason == "turn_contract_mismatch"
    assert rejected.rejection_details["gap"] == "comparison_targets_missing"
    correction = build_turn_contract(
        message="Ik vroeg Apple Full Setup, niet ETH Full Setup. Vergelijk die twee opnieuw.",
        tool_trace=trace, previous_contract=contract,
    )
    assert [target["setup_id"] for target in correction["targets"]] == [1, 2]
    assert turn_contract_gap(correction, "BTC Full Base staat op 4H; Apple Full Setup staat op 1D.") is None
    indirect = build_turn_contract(
        message="Dat is een lijst, geen vergelijking. Wat verschilt tussen precies die twee?",
        tool_trace=trace, previous_contract=correction,
    )
    assert [target["setup_id"] for target in indirect["targets"]] == [1, 2]
    risk_followup = build_turn_contract(
        message="Vergelijk alleen de instap- en risicovoorwaarden van BTC Full Base en Apple Full Setup.",
        tool_trace=trace, previous_contract=contract,
    )
    assert turn_contract_gap(
        risk_followup, "BTC Full Base heeft een andere instap dan Apple Full Setup.",
    ) is None


def test_comparison_correction_rereads_prior_pair_and_excludes_negated_setup():
    previous_contract = {
        "answer_type": "compare",
        "targets": [
            {"setup_id": 1, "name": "BTC Full Base"},
            {"setup_id": 2, "name": "Apple Full Setup"},
        ],
    }
    message = "Ik vroeg Apple Full Setup, niet ETH Full Setup. Vergelijk die twee opnieuw."
    fake = FakeResponses(
        response("correction-read", calls=[tool_call(
            "call-correction", "get_saved_setup_inventory", {"asset": "AAPL"},
        )]),
        response("correction-answer", text="BTC Full Base staat op 4H; Apple Full Setup staat op 1D."),
    )
    front = FinnResponsesFrontDoor(client=SimpleNamespace(responses=fake), session=object(), user_id=7, run_id="compare-correction", model_led_coach=True)
    front.relevance_guard = SimpleNamespace(
        saved_plan_query_kind=AsyncMock(return_value={"kind": "inventory", "source_asset": "", "target_asset": ""}),
        previous_answer_suffices=AsyncMock(return_value=False),
        is_relevant=AsyncMock(return_value=True),
    )
    calls = []

    async def read(call):
        calls.append(call)
        if call.name == "get_active_plan_and_strategy":
            setup_id = call.inputs["setup_id"]
            return {"status": "partial", "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {
                    "setup_id": setup_id,
                    "name": "BTC Full Base" if setup_id == 1 else "Apple Full Setup",
                }},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved", "data": None},
            ]}
        return {"status": "completed", "results": [{
            "scope": "read_saved_setup_inventory", "status": "completed", "data": {"setups": [
                {"setup_id": 1, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 2, "name": "Apple Full Setup", "symbol": "AAPL", "timeframe": "1D"},
                {"setup_id": 3, "name": "ETH Full Setup", "symbol": "ETH", "timeframe": "4H"},
            ], "complete": True},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message=message, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
        previous_response={
            "answer": "BTC Full Base en Apple Full Setup.", "terminal_status": "completed",
            "terminal_kind": "free_text", "turn_contract": previous_contract,
        },
    ))
    assert [call.inputs for call in calls] == [{}, {"setup_id": 1}, {"setup_id": 2}]
    read_rows = [
        row["name"] for trace in result.response.tool_trace
        for item in (trace.get("result") or {}).get("results") or []
        if item.get("scope") == "read_saved_setup_inventory"
        for row in item["data"]["setups"]
    ]
    assert read_rows == ["BTC Full Base", "Apple Full Setup"]
    assert [target["setup_id"] for target in result.response.turn_contract["targets"]] == [1, 2]


def test_turn_contract_rejects_incomplete_strategy_readback():
    trace = ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 2, "name": "BTC Full Base", "symbol": "BTC", "timeframe": "4H",
            }},
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 2, "name": "BTC Full Base Strategy", "entry": "76000",
            }},
        ]},
    },)
    question = "Welke strategienaam en welk entryniveau horen bij die BTC-setup?"
    contract = build_turn_contract(
        message=question, tool_trace=trace,
        previous_subject={"setup_id": 2, "name": "BTC Full Base", "symbol": "BTC"},
    )
    assert contract["targets"][0]["strategy"]["name"] == "BTC Full Base Strategy"
    assert turn_contract_gap(contract, "Ik zie een BTC-setup.") == "strategy_name_missing"
    assert turn_contract_gap(contract, "BTC Full Base Strategy is gekoppeld.") == "strategy_entry_missing"
    assert turn_contract_gap(contract, "BTC Full Base Strategy heeft een entry op 76.000.") is None


def test_turn_contract_keeps_explicit_strategy_focus_from_verified_comparison():
    trace = ({"name": "get_saved_setup_inventory", "result": {
        "turn_request": {"target_ids": [1, 2], "answer_type": "compare",
                         "focused_setup_id": 2, "focused_strategy_id": 22},
        "results": [
            {"scope": "read_saved_setup_inventory", "status": "completed", "data": {
                "setups": [{"setup_id": 1, "name": "First Setup"},
                           {"setup_id": 2, "name": "Second Setup"}],
            }},
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 2, "strategy_id": 22, "name": "Chosen Strategy", "entry": "210",
            }},
        ],
    }},)
    contract = build_turn_contract(
        message="Gebruik Chosen Strategy voor de vergelijking.", tool_trace=trace,
    )
    assert contract["focused_setup_id"] == 2
    assert contract["focused_strategy_id"] == 22
    assert turn_contract_gap(
        contract, "First Setup staat naast Chosen Strategy; entry 210.",
    ) is None


def test_comparison_requires_setup_names_when_strategy_names_repeat():
    contract = {
        "answer_type": "compare", "requested_fields": [],
        "targets": [
            {"setup_id": 1, "name": "BTC Base", "strategy": {"name": "Full Strategy"}},
            {"setup_id": 2, "name": "Apple Base", "strategy": {"name": "Full Strategy"}},
        ],
    }
    assert turn_contract_gap(contract, "Full Strategy heeft een entry.") == "comparison_targets_missing"
    assert turn_contract_gap(contract, "BTC Base en Apple Base hebben allebei Full Strategy.") is None


def test_verified_single_strategy_field_followup_skips_extra_semantic_audit():
    prior = {
        "turn_contract": {"focused_setup_id": 2, "focused_strategy_id": 22},
        "tool_trace": [{"result": {"results": [
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 1, "strategy_id": 11, "name": "First Strategy", "stop_loss": "72000",
            }},
            {"scope": "read_linked_strategy", "status": "completed", "data": {
                "setup_id": 2, "strategy_id": 22, "name": "Chosen Strategy", "stop_loss": "190",
            }},
        ]}}],
    }
    semantic = SimpleNamespace(verify_async=AsyncMock())
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    answer = asyncio.run(verifier.verify(
        message="En welke stop staat bij die strategie?",
        result=FinnResponsesResult(
            "Bij Chosen Strategy staat een stop-loss op 190.", "followup", (),
            model_led_coach=True,
        ),
        previous_response=prior, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "verified_strategy_followup"
    semantic.verify_async.assert_not_called()
    assert not verifier._verified_strategy_followup(
        "En welke stop staat bij die strategie?",
        "Bij Chosen Strategy staat een stop-loss op 195.", prior,
    )
    assert not verifier._verified_strategy_followup(
        "En welke stop staat bij die strategie?",
        "De actuele marktprijs bij Chosen Strategy is 190.", prior,
    )


def test_current_owner_scoped_strategy_field_read_skips_extra_semantic_audit():
    trace = ({"name": "get_active_plan_and_strategy", "result": {"results": [
        {"scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": 2, "strategy_id": 22, "name": "Chosen Strategy",
            "entry": "210", "stop_loss": "190", "targets": ["230"],
        }},
    ]}},)
    semantic = SimpleNamespace(verify_async=AsyncMock())
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    message = "Welke entry en stop staan in Chosen Strategy?"
    text = "In Chosen Strategy staan entry 210 en stop-loss 190."
    checked = asyncio.run(verifier.verify(
        message=message,
        result=FinnResponsesResult(text, "readback", trace, model_led_coach=True),
        locale="nl",
    ))
    assert checked.status == "completed" and checked.text == text
    assert checked.reason == "source_bound_strategy_fields"
    semantic.verify_async.assert_not_called()
    evidence = tuple(trace[0]["result"]["results"])
    assert not verifier._source_bound_strategy_fields(
        message, "In Chosen Strategy staan entry 215 en stop-loss 190.", evidence,
    )
    assert not verifier._source_bound_strategy_fields(
        message, "De huidige koers voor Chosen Strategy is 210 en stop-loss 190.", evidence,
    )


def test_turn_contract_keeps_stop_distance_and_position_size_as_the_topic():
    contract = build_turn_contract(
        message=("Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor "
                 "de stop niet verstandiger kunnen zijn?"),
        tool_trace=(),
    )
    assert contract["answer_type"] == "weigh"
    assert {"stop_distance", "position_size"} <= set(contract["requested_fields"])
    assert can_compose_after_first_read(contract)
    assert not can_compose_after_first_read({**contract, "targets": [{"setup_id": 42}]})
    assert not can_compose_after_first_read({
        **contract, "requested_fields": [*contract["requested_fields"], "entry"],
    })
    assert turn_contract_gap(contract, "Een strenge wachttijd is niet vanzelf veiliger.") == "risk_tradeoff_topic_missing"
    assert turn_contract_gap(contract, "Een ruimere stop vergroot verlies per eenheid; een kleinere positie begrenst het totaalrisico.") is None
    followup = build_turn_contract(
        message=("Leg de afweging concreet uit: hoe houd ik hetzelfde maximale "
                 "euroverlies als de stop verder weg komt?"),
        tool_trace=(), previous_contract=contract,
    )
    assert {"stop_distance", "position_size"} <= set(followup["requested_fields"])
    assert turn_contract_gap(followup, "Bij een ruimere stop verklein je de positie om hetzelfde maximale verlies te houden.") is None


def test_strategy_confirmation_followup_uses_the_previous_verified_read():
    question = (
        "Staat in die strategie ook een aparte instapbevestiging, of alleen "
        "een entryprijs? Wat zou ik vóór een trade nog moeten controleren?"
    )
    previous_trace = ({"name": "get_active_plan_and_strategy", "status": "completed",
                       "result": {"results": [
                           {"scope": "read_active_setup", "status": "completed", "data": {
                               "setup_id": 42, "name": "BTC Full Base", "symbol": "BTC",
                           }},
                           {"scope": "read_linked_strategy", "status": "completed", "data": {
                               "setup_id": 42, "name": "BTC Full Strategy", "entry": "76000",
                               "stop_loss": "72000", "entry_type": None,
                           }},
                       ]}},)
    previous = {
        "run_id": "previous-run", "response_id": "previous-response",
        "terminal_status": "completed", "terminal_kind": "free_text",
        "owner_user_id": 7,
        "user_message": "Welke strategie is aan BTC Full Base gekoppeld?",
        "answer": "BTC Full Base heeft BTC Full Strategy met entry 76.000 en stop 72.000.",
        "verified_setup_subject": {"owner_id": 7, "setup_id": 42,
                                   "name": "BTC Full Base", "symbol": "BTC"},
        "tool_trace": list(previous_trace),
    }
    draft = (
        "Die strategie bevat een opgeslagen entryprijs van 76.000, maar geen "
        "afzonderlijke instapbevestiging. Controleer vóór een trade of je "
        "instapvoorwaarde duidelijk is en hoeveel verlies je maximaal accepteert."
    )
    fake = FakeResponses(response("followup-response", text=draft))
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7,
        run_id="strategy-followup", model_led_coach=True,
    )
    front.reads = AsyncMock(side_effect=AssertionError("verified previous read is sufficient"))
    result = asyncio.run(front.run(
        message=question, instructions=front._model_led_instructions("nl"),
        conversation_context={}, verified_asset=None,
        previous_response=previous, previous_response_id=previous["response_id"],
    ))
    assert {"entry", "confirmation"} <= set(result.response.turn_contract["requested_fields"])
    assert result.response.turn_contract["targets"][0]["strategy"]["entry"] == "76000"
    assert turn_contract_gap(result.response.turn_contract, draft) is None
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError(
        "a source-bound factual continuation should not need a second model judge"
    )))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=question, result=result.response, previous_response=previous, locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == draft
    assert verified.reason == "source_bound_read"


def test_verified_static_stop_distance_percent_is_not_rejected_as_invented():
    evidence = ({
        "scope": "read_linked_strategy", "status": "completed",
        "data": {"setup_id": 42, "level_geometry": {
            "status": "completed", "entry_stop_distance_percent": "5.26",
        }},
    },)
    supported = FinnResponsesAnswerVerifier._percentage_claims_supported
    assert supported(
        answer="De opgeslagen stopafstand is 4.000 (5,26% van de instap).",
        message="Vergelijk mijn opgeslagen voorwaarden.", previous_answer="",
        evidence=evidence, response_focus=None,
    )
    assert not supported(
        answer="De opgeslagen stopafstand is 4.000 (6,26% van de instap).",
        message="Vergelijk mijn opgeslagen voorwaarden.", previous_answer="",
        evidence=evidence, response_focus=None,
    )
    paired_evidence = (*evidence, {
        "scope": "read_linked_strategy", "status": "completed",
        "data": {"setup_id": 43, "level_geometry": {
            "status": "completed", "entry_stop_distance_percent": "9.52",
        }},
    })
    assert supported(
        answer="Stopafstand als percentage van de instap: BTC 5,26%; Apple 9,52%.",
        message="Vergelijk beide setups.", previous_answer="",
        evidence=paired_evidence, response_focus=None,
    )
    assert not supported(
        answer="Stopafstand als percentage van de instap: BTC 5,26%; Apple 19,52%.",
        message="Vergelijk beide setups.", previous_answer="",
        evidence=paired_evidence, response_focus=None,
    )
    assert FinnResponsesAnswerVerifier._saved_strategy_levels_supported(
        "BTC: entry 76.000, stop 72.000 en afstand tot de stop 5,26%.",
        ({"scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": 42, "entry": "76000", "stop_loss": "72000", "targets": [],
        }},),
        "Vergelijk mijn opgeslagen niveaus.",
    )


def test_denial_of_a_write_is_not_a_saved_action_claim():
    boundary = FinnV2HardClaimBoundary()
    assert boundary._negated_saved_action("Ik heb niets gewijzigd.", "gewijzigd")
    assert boundary._negated_saved_action("Er is geen plan opgeslagen.", "plan opgeslagen")
    assert not boundary._negated_saved_action("Ik heb het plan gewijzigd.", "gewijzigd")
    assert not boundary._negated_saved_action(
        "Ik heb niet alleen gelezen, maar ook gewijzigd.", "gewijzigd",
    )
    assert boundary._read_only_saved_action_quote(
        "Ik heb BTC Full Base en Apple Full Setup opnieuw opgezocht",
    )
    assert not boundary._read_only_saved_action_quote(
        "Ik heb de setup gelezen en daarna gewijzigd",
    )


def test_inventory_read_failure_does_not_fall_back_to_active_setup_or_guess_count():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="inventory-unavailable")
    front.relevance_guard = SimpleNamespace(saved_plan_query_kind=AsyncMock(return_value={
        "kind": "inventory", "source_asset": "", "target_asset": "",
    }))
    front.reads = AsyncMock(return_value={"status": "partial", "results": [{
        "scope": "read_saved_setup_inventory", "status": "unavailable", "reason": "tool_timeout",
    }]})
    message = "Kun je mijn BTC-setups allemaal opsommen?"
    result = asyncio.run(front.run(
        message=message, instructions="", conversation_context={}, verified_asset="BTC",
    ))
    assert result.response.answer_kind == "saved_inventory_unavailable"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl",
    ))
    assert answer.status == "completed"
    assert "niet betrouwbaar uitlezen" in answer.text
    assert "Ik zie één" not in answer.text


def test_inventory_reference_ids_are_server_only_not_model_arguments():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("get_saved_setup_inventory", {"asset": "BTC"}).read_tools == (
        "read_saved_setup_inventory",
    )
    with pytest.raises(FinnResponsesToolError, match="read_arguments_invalid"):
        catalog.validate("get_saved_setup_inventory", {"setup_ids": [1, 2, 3]})


def test_selected_strategy_name_is_a_valid_owner_scoped_read_selector():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate("get_active_plan_and_strategy", {
        "asset": "AAPL", "setup_name": "Apple Full Setup",
        "strategy_name": "Apple Full Strategy", "reference": "current_request",
    })
    assert call.inputs["strategy_name"] == "Apple Full Strategy"


def test_saved_setup_bounds_read_never_requires_a_strategy():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate("get_saved_setup", {
        "asset": "BTC", "setup_name": "BTC Breakout Full", "reference": "current_request",
    })
    assert call.read_tools == ("read_active_setup",)
    assert call.inputs["setup_name"] == "BTC Breakout Full"
    definition = next(item for item in catalog.definitions() if item["name"] == "get_saved_setup")
    assert "independent of how many strategies" in definition["description"]
    with pytest.raises(FinnResponsesToolError, match="read_arguments_invalid"):
        catalog.validate("get_saved_setup", {"strategy_name": "BTC Breakout Full Strategy"})


def test_current_asset_score_read_uses_only_source_verified_score_tool():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("get_current_asset_scores", {"asset": "BTC"}).read_tools == (
        "read_active_asset", "read_asset_scores",
    )
    current_definition = next(item for item in catalog.definitions() if item["name"] == "get_current_asset_scores")
    assert "same source verification as Analyse" in current_definition["description"]
    assert "get_saved_asset_scores" not in {item["name"] for item in catalog.definitions()}


def test_saved_setup_bounds_question_uses_setup_read_without_strategy_disambiguation():
    fake = FakeResponses(
        response("bounds-read", calls=[tool_call(
            "bounds-call", "get_saved_setup", {"setup_name": "BTC Breakout Full"},
        )]),
        response("bounds-answer", text=(
            "BTC Breakout Full heeft markt 20–60, macro 30–70 en technisch 40–80 "
            "als opgeslagen scoregrenzen."
        )),
    )
    front = FinnResponsesFrontDoor(
        client=SimpleNamespace(responses=fake), session=object(), user_id=7, run_id="bounds-read",
    )
    front.relevance_guard = SimpleNamespace(
        saved_plan_query_kind=AsyncMock(return_value={"kind": "detail", "source_asset": "BTC", "target_asset": "BTC"}),
        previous_answer_suffices=AsyncMock(return_value=False),
        is_relevant=AsyncMock(return_value=True),
    )
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"setup_id": 9, "name": "BTC Breakout Full", "symbol": "BTC",
                     "min_market_score": 20, "max_market_score": 60,
                     "min_macro_score": 30, "max_macro_score": 70,
                     "min_technical_score": 40, "max_technical_score": 80},
        }]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Welke markt-, macro- en technische scoregrenzen heeft BTC Breakout Full?",
        instructions=front._model_led_instructions("nl"), conversation_context={}, verified_asset="BTC",
    ))
    assert [call.name for call in calls] == ["get_saved_setup"]
    assert calls[0].read_tools == ("read_active_setup",)
    assert result.response.answer_kind == "free_text"
    assert "20–60" in result.response.text


def test_rejected_proposal_does_not_override_later_valid_clarification():
    trace = (
        {"name": "create_or_update_trade_plan_proposal", "status": "retry"},
        {"name": "ask_for_clarification", "status": "needs_input"},
    )
    assert not FinnV2RunService._unanalysed_proposal_selected(trace)
    assert not FinnV2RunService._unanalysed_proposal_selected((
        {"name": "create_dca_plan_proposal", "status": "unsupported"},
    ))
    assert FinnV2RunService._unanalysed_proposal_selected((
        {"name": "create_or_update_trade_plan_proposal", "status": "needs_input"},
    ))


def test_read_repair_uses_available_lifecycle_budget_without_consuming_terminal_reserve():
    assert FinnV2RunService._read_repair_has_budget(11.5, explain_limit=False)
    assert not FinnV2RunService._read_repair_has_budget(8, explain_limit=False)
    assert FinnV2RunService._read_repair_has_budget(7.5, explain_limit=True)
    assert not FinnV2RunService._read_repair_has_budget(7, explain_limit=True)


@pytest.mark.parametrize("message", [
    "Welke strategie is gekoppeld aan deze setup?",
    "Which bot is linked to this strategy?",
    "Welche Strategie ist mit diesem Setup verknüpft?",
])
def test_explicit_linked_read_interrupts_guided_slot_without_becoming_slot_answer(message):
    assert FinnV2RunService._independent_linked_read(message)


def test_question_about_guided_slot_is_not_an_independent_linked_read():
    assert not FinnV2RunService._independent_linked_read("Voor totaal of per keer?")


@pytest.mark.parametrize("field,expected", [
    ("setup_id", "Welke bestaande setup bedoel je?"),
    ("strategy_id", "Welke bestaande strategie bedoel je?"),
    ("bot_id", "Welke bestaande paper-bot bedoel je?"),
])
def test_missing_entity_reference_asks_for_a_name_not_an_internal_id(field, expected):
    assert FinnV2OperationStateService.clarification_question(field) == expected


def test_wrong_proposal_tool_recommends_registry_bound_tool_without_executing():
    catalog = FinnResponsesToolCatalog()
    with pytest.raises(FinnResponsesToolError, match="operation_not_allowed_for_tool") as exc:
        catalog.validate(
            "manage_asset_watchlist_proposal",
            {"payload": {"operation_id": "delete_strategy", "inputs": {}, "draft_intent": "new"}},
        )
    assert exc.value.details == {
        "recommended_tool_name": catalog.proposal_tool_for_operation("delete_strategy")
    }


def test_relevance_retry_exposes_only_recommended_registry_operation():
    catalog = FinnResponsesToolCatalog()
    definitions = catalog.definitions(retry_operation_id="delete_strategy")
    proposal_definitions = [
        definition for definition in definitions
        if catalog.is_proposal_tool(definition["name"])
    ]
    assert [definition["name"] for definition in proposal_definitions] == [
        catalog.proposal_tool_for_operation("delete_strategy")
    ]
    payload = proposal_definitions[0]["parameters"]["properties"]["payload"]
    assert payload["properties"]["operation_id"]["enum"] == ["delete_strategy"]


def test_local_per_operation_proposal_tools_keep_registry_as_contract_authority():
    catalog = FinnResponsesToolCatalog(individual_proposals=True)
    definitions = {
        item["name"]: item for item in catalog.definitions()
        if catalog.is_proposal_tool(item["name"])
    }
    operations = {
        operation_id
        for grouped in _PROPOSAL_OPERATIONS.values()
        for operation_id in grouped
    }
    assert set(definitions) == {f"propose_{operation_id}" for operation_id in operations}
    for operation_id in operations:
        name = catalog.proposal_tool_for_operation(operation_id)
        payload = definitions[name]["parameters"]["properties"]["payload"]
        assert payload["properties"]["operation_id"]["enum"] == [operation_id]
        contract = catalog.registry.require_supported(operation_id)
        assert set(payload["properties"]["inputs"]["properties"]) == (
            set(contract.input_fields) - _FORBIDDEN_MODEL_FIELDS - set(contract.server_resolved_inputs)
        )
    guided = catalog.definitions(guided_operation_id="update_setup")
    assert [item["name"] for item in guided] == ["propose_update_setup"]
    call = catalog.validate("propose_update_setup", {
        "payload": {"operation_id": "update_setup", "draft_intent": "new",
                    "inputs": {"changed_fields": {"timeframe": "1H"}}},
    })
    assert call.operation_id == "update_setup"
    assert call.inputs == {"changed_fields": {"timeframe": "1H"}}


def test_unavailable_market_evidence_keeps_typed_source_limitation():
    evidence = (
        {"scope": "read_active_asset", "status": "completed"},
        {"scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable"},
    )
    assert FinnResponsesAnswerVerifier._typed_failure_reason(evidence) == "source_unavailable"


def test_typed_fallback_uses_language_of_current_question():
    copy = FinnResponsesAnswerVerifier._fallback_copy
    assert copy("setup_ambiguous", message="Explain what my plan can safely conclude.").startswith("I found")
    assert copy("setup_ambiguous", message="Erkläre mir meinen gesamten Handelsplan.").startswith("Ich sehe")
    assert copy("previous_source_unavailable", message="Why?").startswith("I can't")
    assert copy("previous_source_unavailable", message="Warum?").startswith("Ich kann")


def test_typed_fallback_respects_effective_turn_locale():
    copy = FinnResponsesAnswerVerifier._fallback_copy
    assert copy("setup_ambiguous", message="Why?", locale="nl").startswith("Ik zie")
    assert copy("limited_evaluation", message="Warum?", locale="en").startswith("I can't")
    assert copy("source_unavailable", message="Waarom?", locale="de").startswith("Mir fehlen")


@pytest.mark.parametrize("locale,message,expected", [
    ("nl", "Ik denk aan 100 euro per week.", "Je overweegt 100 euro per week."),
    ("en", "I am considering 100 euros per week.", "You are considering 100 euros per week."),
    ("de", "Ich erwäge 100 Euro pro Woche.", "Du erwägst 100 Euro pro Woche."),
])
def test_limited_evaluation_fallback_preserves_user_proposal(locale, message, expected):
    answer = FinnResponsesAnswerVerifier._limited_evaluation_copy(message=message, locale=locale)
    assert answer.startswith(expected)
    assert "100" in answer


def test_limited_evaluation_fallback_does_not_invent_proposal():
    answer = FinnResponsesAnswerVerifier._limited_evaluation_copy(
        message="Is Bitcoin nu 100 euro waard?", locale="nl",
    )
    assert "Je overweegt" not in answer


def test_limited_evaluation_fallback_does_not_change_the_question_domain():
    answer = FinnResponsesAnswerVerifier._limited_evaluation_copy(
        message="Leg mijn huidige totaalscore uit.", locale="nl",
    )
    assert "risicostijl" not in answer
    assert "instellingen" not in answer


def test_terminal_runtime_failure_uses_owner_preference_not_default_dutch():
    service = object.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(get_by_id_for_user=AsyncMock(
        return_value=SimpleNamespace(message="Can you assess my BTC plan?"),
    ))
    service.session = SimpleNamespace(get=AsyncMock(
        return_value=SimpleNamespace(ai_preferences={"locale": "en"}),
    ))
    content = asyncio.run(service._localized_runtime_failure_content(run_id="run-1", user_id=1))
    assert content == "FINN couldn't complete this answer. Please try again."


def test_provider_quota_failure_has_honest_localized_copy_without_internal_code():
    service = object.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(get_by_id_for_user=AsyncMock(
        return_value=SimpleNamespace(message="Can we discuss my plan?"),
    ))
    service.session = SimpleNamespace(get=AsyncMock(
        return_value=SimpleNamespace(ai_preferences={"locale": "en"}),
    ))
    content = asyncio.run(service._localized_runtime_failure_content(
        run_id="run-quota", user_id=1, error_code="responses_provider_quota_unavailable",
    ))
    assert "AI connection is currently unavailable" in content
    assert "quota" not in content.lower()
    assert "responses_provider" not in content


def test_markdown_formatting_cannot_hide_internal_setup_identifier():
    assert FinnResponsesAnswerVerifier._contains_internal_identifier("**Setup ID:** 11363")
    assert FinnResponsesAnswerVerifier._contains_internal_identifier("Strategy ID: 42")
    assert not FinnResponsesAnswerVerifier._contains_internal_identifier("Setup: BTC 4H")


def test_unverified_trading_outcome_promises_are_not_grounded_process_coaching():
    check = FinnResponsesAnswerVerifier._promises_unverified_trading_outcome
    assert check("Wachten verhoogt de kans op succesvolle trades.")
    assert check("Confirmation can reduce the risk of losses.")
    assert check("Das kann das Verlustrisiko senken.")
    assert check("Door te wachten kun je voorkomen dat je in een ongunstige positie komt.")
    assert check("Wachten kan helpen om onnodige verliezen te vermijden.")
    assert check("Dit verhoogt de kans dat je in de juiste richting handelt.")
    assert not check("Je zegt dat je op bevestiging wilt wachten; welk signaal bedoel je?")
    assert not check(
        "Welk signaal wacht je af, en welk risico moet het volgens jou helpen beperken?"
    )
    assert not check(
        "Een ruimere stop betekent meer risico per eenheid; "
        "een kleinere positie kan dat risico beperken."
    )
    assert check("Bevestiging kan het risico op verlies beperken.")


def test_locale_check_preserves_saved_proper_names_in_short_field_rows():
    check = FinnResponsesAnswerVerifier._language_matches
    assert check("Je hebt een setup opgeslagen.\n**Naam:** Coach NL BTC Setup", "nl")
    assert check("**Setupvelden — BTC Full Base**\nIk heb de gekoppelde strategie gecontroleerd.", "nl")
    assert not check("This answer is entirely in English and ignores the selected language.", "nl")


def test_autonomous_trade_is_a_typed_policy_refusal_not_a_generic_failure():
    from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService

    service = object.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(get_by_id_for_user=AsyncMock(
        return_value=SimpleNamespace(message="Buy BTC automatically without confirmation."),
    ))
    service.session = SimpleNamespace(get=AsyncMock(
        return_value=SimpleNamespace(ai_preferences={"locale": "en"}),
    ))
    assert FinnV2RequestPreprocessorService().preprocess(
        message="Buy BTC automatically without confirmation."
    ).financial_execution_intent
    assert FinnV2RunService._requests_unconfirmed_financial_execution(
        "Buy BTC automatically without confirmation."
    )
    assert FinnV2RunService._requests_unconfirmed_financial_execution(
        "Koop BTC automatisch zonder bevestiging."
    )
    assert not FinnV2RunService._requests_unconfirmed_financial_execution(
        "Is it sensible to buy BTC automatically every week?"
    )
    content = asyncio.run(service._localized_runtime_failure_content(
        run_id="run-1", user_id=1, error_code="financial_execution_not_available",
    ))
    assert "can't place buy or sell orders automatically" in content
    assert "explicit confirmation" in content
    assert "try again" not in content.lower()


def test_live_bot_activation_policy_does_not_block_paper_bot():
    assert FinnV2RunService._requests_live_bot_activation(
        "Activate this bot for live trading now."
    )
    assert not FinnV2RunService._requests_live_bot_activation(
        "Activate this paper bot now."
    )
    service = object.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(get_by_id_for_user=AsyncMock(
        return_value=SimpleNamespace(message="Activate this bot for live trading now."),
    ))
    service.session = SimpleNamespace(get=AsyncMock(
        return_value=SimpleNamespace(ai_preferences={"locale": "en"}),
    ))
    content = asyncio.run(service._localized_runtime_failure_content(
        run_id="run-2", user_id=1, error_code="live_bot_activation_disabled",
    ))
    assert "can't activate this bot for live trading" in content
    assert "Paper mode" in content


def test_model_cannot_claim_missing_previous_answer_as_conversation_evidence():
    result = FinnResponsesResult(
        "Diversificatie kan schommelingen dempen.", "resp-orphan", (),
        uses_previous_response=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Waarom kan dat schommelingen dempen?", result=result,
        previous_response=None, locale="nl",
    ))
    assert answer.status == "clarification_required"
    assert answer.reason == "previous_response_unavailable"
    assert "Waar verwijs je naar?" in answer.text


def test_grounded_coach_answer_must_not_narrate_user_request_as_internal_report():
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._avoids_internal_user_frame(
        "De gebruiker wil weten wat de score betekent. De score is niet beschikbaar."
    )
    assert not verifier._avoids_internal_user_frame(
        "The user asks what their portfolio means."
    )
    assert verifier._avoids_internal_user_frame(
        "Ik kan je score nu niet beoordelen omdat de bron ontbreekt."
    )


def test_tool_error_uses_effective_turn_locale():
    result = FinnResponsesResult("", "resp-1", ({"status": "error", "result": {}},))
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Why?", result=result, locale="nl",
    ))
    assert verified.status == "unavailable"
    assert verified.text.startswith("Ik heb hiervoor")


def test_verified_saved_risk_profile_cannot_be_reported_missing():
    evidence = ({
        "scope": "read_profile", "status": "completed",
        "data": {"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
    },)
    supported = FinnResponsesAnswerVerifier._profile_presence_claim_supported
    assert not supported("De actuele marktcijfers en je risicoprofiel ontbreken.", evidence)
    assert not supported("Current market data and your risk profile are missing.", evidence)
    assert not supported("Die aktuellen Marktdaten und deine spezifischen Risikoeinstellungen fehlen.", evidence)
    assert not supported("We hebben geen inzicht in je risicoprofiel.", evidence)
    assert not supported("We have no insight into your risk profile.", evidence)
    assert supported("Je risicoprofiel is voorzichtig, maar de actuele marktdata ontbreken.", evidence)
    assert supported("Dein Risikoprofil ist vorsichtig, aber aktuelle Marktdaten fehlen.", evidence)


def test_chart_timeframe_and_dca_cadence_do_not_prove_personal_horizon():
    evidence = ({"scope": "read_active_setup", "status": "completed",
                 "data": {"name": "BTC DCA", "timeframe": "4H", "dca_frequency": "daily"}},)
    supported = FinnResponsesAnswerVerifier._saved_horizon_claim_supported
    assert not supported("Dus je DCA-setup is meer gericht op langetermijnopbouw.", evidence)
    assert not supported("Your saved setup is geared toward long-term accumulation.", evidence)
    assert not supported(
        "Dein DCA-Setup im 4-Stunden-Zeitrahmen deutet eher auf einen kurzfristigen Ansatz hin, "
        "der typischerweise mit Swingtrading verbunden ist.", evidence,
    )
    assert not supported(
        "Dieses Setup eignet sich eher für langfristigen Vermögensaufbau als für Swingtrading.", evidence,
    )
    assert not supported(
        "Je DCA-setup is geen swingtrade, maar meer geschikt voor langetermijnopbouw.", evidence,
    )
    assert not supported(
        "Dein DCA-Setup verwendet 4H und investiert täglich. Dies deutet eher auf einen "
        "langfristigen Vermögensaufbau hin und nicht auf Swingtrading.", evidence,
    )
    assert not supported(
        "Your 4H DCA setup invests daily. This approach typically aligns more with "
        "long-term accumulation than swing trading.", evidence,
    )
    assert supported("DCA wordt vaak voor opbouw gebruikt, maar jouw horizon is niet vastgelegd. Wat beoog je?", evidence)
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Ein 4H-DCA-Setup könnte sowohl zügigen Vermögensaufbau als auch Swing-Trading unterstützen."
    )


def test_saved_levels_are_not_turn_into_unsupported_advice():
    unsafe = FinnResponsesAnswerVerifier._ungrounded_level_advice
    assert unsafe("De risico-opbrengstverhoudingen lijken aantrekkelijk.")
    assert unsafe("Stel je stop-loss in op 76.000 om verliezen te beperken.")
    assert unsafe("Pas aan zodra een doel wordt bereikt.")
    assert unsafe("The risk-reward ratio looks attractive.")
    assert unsafe("Deze niveaus hebben positieve reward-to-risk ratio's.")
    assert unsafe("De verhouding voor target twee is nog beter.")
    assert unsafe("Houd rekening met de targets om eventuele winstnemingen te plannen.")
    assert unsafe("Set your stop-loss at 76,000.")
    assert not unsafe("Het opgeslagen risico per unit is 4.000; de verhouding is 2:1.")
    assert not unsafe("Controleer of de opgeslagen stop-loss nog passend is.")


def test_runtime_field_names_are_not_user_facing_answer_copy():
    internal = FinnResponsesAnswerVerifier._contains_internal_identifier
    assert internal("De level_geometry is compleet.")
    assert internal("missing_required_inputs: stop_loss")
    assert not internal("De opgeslagen stop-loss en doelen zijn bekend.")


def test_strategy_levels_remain_attributed_to_strategy_not_setup():
    evidence = (
        {"scope": "read_active_setup", "status": "completed", "data": {"name": "BTC Breakout Full"}},
        {"scope": "read_linked_strategy", "status": "completed", "data": {"name": "BTC Breakout Full Strategy"}},
    )
    wrong = FinnResponsesAnswerVerifier._strategy_levels_attributed_to_setup
    assert wrong("De BTC Breakout Full setup heeft een entry op 80000.", evidence)
    assert not wrong("De BTC Breakout Full setup is gekoppeld aan een strategie met entry 80000.", evidence)
    assert not wrong("De BTC Breakout Full Strategy heeft een entry op 80000.", evidence)


def test_static_geometry_fallback_uses_only_owner_scoped_read_facts():
    evidence = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "name": "BTC Breakout Full Strategy",
        "level_geometry": {
            "status": "completed", "risk_per_unit": "4000",
            "targets": [
                {"price": "88000", "reward_per_unit": "8000", "reward_to_risk": "2.00"},
                {"price": "92000", "reward_per_unit": "12000", "reward_to_risk": "3.00"},
            ],
        },
    }},)
    answer = FinnResponsesAnswerVerifier._static_geometry_answer(evidence, "nl")
    assert answer is not None
    assert all(value in answer for value in ("4.000", "88.000", "92.000", "2:1", "3:1"))
    assert "€" not in answer and "aantrekkelijk" not in answer
    assert "geen oordeel over de huidige markt" in answer
    assert FinnResponsesAnswerVerifier._static_geometry_answer((), "nl") is None


def test_static_calculation_terminalizes_without_model_repair_or_invented_currency():
    result = FinnResponsesResult(
        "Dit lijkt een aantrekkelijke setup met €4.000 risico.", "resp-calc",
        ({"name": "get_active_plan_and_strategy", "status": "completed", "result": {
            "results": [{"scope": "read_linked_strategy", "status": "completed", "data": {
                "name": "BTC Breakout Full Strategy", "level_geometry": {
                    "status": "completed", "risk_per_unit": "4000",
                    "targets": [
                        {"price": "88000", "reward_per_unit": "8000", "reward_to_risk": "2.00"},
                        {"price": "92000", "reward_per_unit": "12000", "reward_to_risk": "3.00"},
                    ],
                },
            }}],
        }},), response_focus="calculation",
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Wat is de verhouding zonder actuele koers?", result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.reason == "static_level_geometry"
    assert "4.000" in verified.text and "2:1" in verified.text and "3:1" in verified.text
    assert "€" not in verified.text and "aantrekkelijk" not in verified.text


def test_percentage_claims_require_grounded_percentage_or_explicit_calculation():
    supported = FinnResponsesAnswerVerifier._percentage_claims_supported
    evidence = ({"status": "completed", "data": {"risk_style": "balanced"}},)
    assert not supported(
        answer="Je risicopercentage is 5%.", message="Beoordeel mijn plan.",
        previous_answer="", evidence=evidence, response_focus="review",
    )
    assert supported(
        answer="Je noemde 5% risico.", message="Mijn grens is 5%.",
        previous_answer="", evidence=evidence, response_focus="review",
    )
    assert supported(
        answer="Je ingestelde grens is 5%.", message="Beoordeel mijn plan.",
        previous_answer="", evidence=({"status": "completed", "data": {"risk_percent": 5}},),
        response_focus="review",
    )
    portfolio = ({"status": "completed", "data": {
        "global": {"allocations_pct": {"Cash": 100}},
    }},)
    assert supported(
        answer="Je allocatie is 100% contant.", message="Toon mijn portfolio.",
        previous_answer="", evidence=portfolio, response_focus=None,
    )
    assert not supported(
        answer="Je allocatie is 50% contant.", message="Toon mijn portfolio.",
        previous_answer="", evidence=portfolio, response_focus=None,
    )
    geometry = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "level_geometry": {"status": "completed", "entry_stop_distance_percent": "5.00"},
    }},)
    assert not supported(
        answer="Je ingestelde risicogrens is 5%.", message="Beoordeel mijn plan.",
        previous_answer="", evidence=geometry, response_focus="review",
    )
    assert supported(
        answer="Het prijsverschil tussen entry en stop-loss is 5% van entry.",
        message="Bereken het prijsverschil.", previous_answer="", evidence=geometry,
        response_focus="calculation",
    )
    assert supported(
        answer="De afstand tot de stop is 5% van de entry.",
        message="Beoordeel mijn plan.", previous_answer="", evidence=geometry,
        response_focus="review",
    )


def test_hypothetical_user_amount_is_not_attributed_to_finn():
    check = FinnResponsesAnswerVerifier._proposal_speaker_is_user
    assert not check("Ik denk aan 100 euro per week.")
    assert not check("I am considering 100 euros per week.")
    assert not check("Ich erwäge 100 Euro pro Woche.")
    assert check("Je overweegt 100 euro per week.")
    assert check("FINN kan nog niet beoordelen of 100 euro per week past.")


def test_unsupported_saved_horizon_claim_becomes_localized_typed_clarification():
    result = FinnResponsesResult(
        "Dieses Setup eignet sich eher für langfristigen Vermögensaufbau als für Swingtrading.",
        "resp-horizon", ({"name": "get_active_plan_and_strategy", "status": "completed", "result": {
            "results": [{"scope": "read_active_setup", "status": "completed", "data": {
                "name": "Coach DCA Basis", "timeframe": "4H", "dca_frequency": "daily",
            }}],
        }},),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Ist mein 4H-DCA-Setup langfristig?", result=result, locale="de",
    ))
    assert verified.status == "clarification_required"
    assert verified.reason == "investment_horizon_required"
    assert verified.text.startswith("4H beschreibt")
    assert "investment_horizon_required" not in verified.text
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Dein gespeichertes Setup passt eher zum langfristigen Vermögensaufbau.",
        ({"scope": "read_active_setup", "status": "completed",
          "data": {"name": "Coach DCA Basis", "timeframe": "4H"}},),
    )
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Your saved DCA setup is structured as accumulation, not a swing trade.",
        ({"scope": "read_active_setup", "status": "completed",
          "data": {"name": "Coach DCA Basis", "timeframe": "4H"}},),
    )


def test_ungrounded_positive_fit_detects_plain_alignment_claim():
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Your daily DCA plan aligns with a conservative approach."
    )


def test_model_classified_horizon_question_asks_instead_of_inventing_horizon():
    result = FinnResponsesResult(
        "Je 4H DCA-setup is ontworpen voor langetermijnopbouw.",
        "resp-horizon-classified", ({
            "name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"name": "Coach DCA Basis", "timeframe": "4H"},
            }]},
        },), horizon_classification_question=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Is mijn setup voor lange termijn of swingtrading?", result=result, locale="nl",
    ))
    assert verified.status == "clarification_required"
    assert verified.reason == "investment_horizon_required"
    assert "4H beschrijft" in verified.text


def test_horizon_clarification_answer_stays_conversational_not_saved():
    result = FinnResponsesResult(
        "Your saved setup aims for long-term wealth building and matches your goal.",
        "resp-horizon-reply", ({
            "name": "evaluate_plan", "status": "partial", "result": {"results": []},
        },), resumed_clarification_reason="investment_horizon_required",
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="For the long term, around five years.", result=result, locale="en",
    ))
    assert verified.status == "completed"
    assert verified.reason == "user_detail_acknowledged"
    assert "five years" in verified.text
    assert "saved setup aims" not in verified.text
    assert "saved plan has not changed" in verified.text


def test_model_led_horizon_followup_preserves_verified_coach_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = (
        "With a roughly five-year horizon, your stated aim is long-term accumulation. "
        "The 4H chart timeframe does not establish a saved holding period."
    )
    result = FinnResponsesResult(
        answer, "resp-model-horizon", (), model_led_coach=True,
        resumed_clarification_reason="investment_horizon_required",
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="For the long term, around five years.", result=result, locale="en",
    ))
    assert verified.status == "completed"
    assert verified.text == answer
    semantic.verify_async.assert_awaited()


def test_currency_amounts_normalize_singular_and_plural_user_units():
    amounts = FinnResponsesAnswerVerifier._currency_amounts
    assert amounts("100 euro per week") == {"1E+2"}
    assert amounts("100 euros per week") == amounts("€100 per week")
    assert amounts("250 dollars monthly") == amounts("$250 monthly")


@pytest.mark.parametrize("locale,message,needle", [
    ("nl", "Voor de lange termijn, ongeveer vijf jaar.", "je opgeslagen plan is niet gewijzigd"),
    ("en", "For the long term, around five years.", "your saved plan has not changed"),
    ("de", "Langfristig, ungefähr fünf Jahre.", "dein gespeicherter Plan wurde nicht geändert"),
])
def test_detail_fallback_acknowledges_user_without_claiming_persistence(locale, message, needle):
    answer = FinnResponsesAnswerVerifier._user_detail_acknowledgement(message, locale)
    assert message in answer
    assert needle in answer


def test_current_strategy_is_not_claimed_when_only_setup_was_read():
    evidence = ({"scope": "read_active_setup", "status": "completed", "data": {"name": "Coach DCA Basis"}},)
    assert not FinnResponsesAnswerVerifier._saved_entity_type_supported(
        "Ich kann deine aktuelle Strategie noch nicht bewerten.", evidence,
    )
    assert FinnResponsesAnswerVerifier._saved_entity_type_supported(
        "Ich kann dein gespeichertes Setup noch nicht bewerten.", evidence,
    )


def test_guided_strategy_tool_is_limited_to_pending_registry_operation():
    catalog = FinnResponsesToolCatalog()
    definitions = catalog.definitions(guided_operation_id="create_strategy")
    assert [item["name"] for item in definitions] == ["create_or_update_trade_plan_proposal"]
    variants = definitions[0]["parameters"]["properties"]["payload"]
    assert variants["properties"]["operation_id"]["enum"] == ["create_strategy"]
    assert "base_amount" in variants["properties"]["inputs"]["properties"]
    assert "changed_fields" not in variants["properties"]["inputs"]["properties"]


def test_target_reselection_uses_only_registry_contracts_for_resolved_domain():
    definitions = FinnResponsesToolCatalog().definitions(retry_target_domain="strategy")
    assert all(item["name"].endswith("_proposal") for item in definitions)
    for item in definitions:
        payload = item["parameters"]["properties"]["payload"]
        variants = payload.get("oneOf", [payload])
        assert all(
            FinnV2OperationRegistry().require_supported(variant["properties"]["operation_id"]["enum"][0]).domain == "strategy"
            for variant in variants
        )
    assert any(item["name"] == "create_or_update_trade_plan_proposal" for item in definitions)


@pytest.mark.parametrize("model_value,expected", [
    ("vast", "fixed"), ("vaste uitvoering", "fixed"),
    ("fixed", "fixed"), ("aangepast", "custom"),
    ("fest", "fixed"), ("feste Ausführung", "fixed"),
])
def test_model_strategy_execution_mode_uses_guided_contract_canonicalization(model_value, expected):
    assert FinnV2OperationStateService._canonical_input("execution_mode", model_value) == expected


@pytest.mark.parametrize("field,value,expected", [
    ("dca_frequency", "wekelijks", "weekly"),
    ("dca_frequency", "monthly", "monthly"),
    ("dca_day", "maandag", "monday"),
    ("dca_frequency", "soms", None),
])
def test_model_dca_inputs_share_guided_canonicalization(field, value, expected):
    assert FinnV2OperationStateService._canonical_input(field, value) == expected


def test_catalog_uses_registry_for_required_and_conditional_inputs():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    assert call.missing_inputs == ("timeframe", "name", "dca_frequency", "dca_amount_mode", "base_amount")
    assert call.operation_id == "create_setup"
    assert len(catalog.definitions()) == 2 + len(catalog.read_tools) + len(catalog.proposal_operations) + len(catalog.evaluation_contracts)
    assert "answer_directly" not in {item["name"] for item in catalog.definitions()}
    proposal = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    assert proposal["parameters"]["properties"]["payload"]["properties"]["inputs"]["properties"]["min_investment"]["type"] == "number"


def test_evaluation_tool_uses_registry_scopes_and_cannot_write():
    catalog = FinnResponsesToolCatalog()
    contract = FinnV2OperationRegistry().require_supported("evaluate_plan")
    call = catalog.validate("evaluate_plan", {"asset": "BTC"})
    assert call.operation_id is None
    assert call.evaluation_operation_id == "evaluate_plan"
    assert call.read_tools == contract.tool_names
    assert call.required_inputs == call.missing_inputs == ()
    assert any(item["name"] == "evaluate_plan" for item in catalog.definitions())
    definitions = {item["name"]: item for item in catalog.definitions()}
    assert "static arithmetic" in definitions["get_active_plan_and_strategy"]["description"]
    assert "not this assessment" in definitions["evaluate_plan"]["description"]
    assert "hypothetical_change" in definitions["evaluate_plan"]["parameters"]["properties"]
    scenario = catalog.validate("evaluate_plan", {
        "asset": "BTC", "hypothetical_change": "Change daily DCA to 100 EUR per week",
    })
    assert scenario.inputs["hypothetical_change"] == "Change daily DCA to 100 EUR per week"
    assert scenario.operation_id is None
    with pytest.raises(FinnResponsesToolError):
        catalog.validate("evaluate_plan", {"hypothetical_change": "x" * 501})
    with pytest.raises(FinnResponsesToolError):
        catalog.validate("evaluate_plan", {"user_id": 17})


def test_profile_read_cannot_authorize_personal_fit_claim(monkeypatch):
    seen = []

    async def reject_personal_fit(_self, **kwargs):
        seen.append(kwargs)
        return HardClaimBoundaryResult(True, ("personal_fit",), {
            "personal_fit_quote": "wat past bij je risicoprofiel",
        })

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        reject_personal_fit,
    )
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "100 euro per week past bij je risicoprofiel.", "resp-fit", ({
            "name": "get_my_profile_and_risk_style", "status": "completed",
            "result": {"results": [{
                "scope": "read_profile", "status": "completed",
                "data": {"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
            }]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(
        message="Past 100 euro per week bij mijn plan?", result=result,
    ))
    assert answer.status != "completed"
    assert answer.reason == "personal_fit_not_established"
    assert seen and seen[0]["tool_trace"] == result.tool_trace


def test_rejected_personal_fit_has_typed_previous_turn_limit():
    context = project_verified_turn({
        "run_id": "prior-run", "terminal_status": "unavailable",
        "terminal_reason": "personal_fit_not_established",
        "answer": "Ik kan dat nog niet vaststellen.",
        "user_message": "Past 100 euro per week bij mij?",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_profile", "status": "completed", "source": "owner_profile",
            "data": {"has_profile": True},
        }]}}],
    })
    assert context["evidence_limit"].startswith("Saved profile or plan facts alone")
    assert context["evidence"][0]["scope"] == "read_profile"


def test_why_followup_can_quote_prior_user_amount_without_treating_it_as_saved():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer_text = (
        "Ik kan nog niet bepalen of de door jou voorgestelde 100 euro per week "
        "bij je risicostijl past; daarvoor ontbreekt een beoordeling van je plan."
    )
    result = FinnResponsesResult(
        answer_text, "resp-why", (), uses_previous_response=True,
        model_led_coach=True,
    )
    previous = {
        "answer": "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
        "user_message": "Ik denk aan 100 euro per week. Past dat bij mij?",
        "terminal_status": "unavailable",
        "terminal_reason": "personal_fit_not_established",
        "tool_trace": [{"name": "get_my_profile_and_risk_style", "result": {"results": [{
            "scope": "read_profile", "status": "completed", "source": "owner_profile",
            "data": {"has_profile": True},
        }]}}],
    }
    verified = asyncio.run(FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(),
    ).verify(message="Waarom?", result=result, previous_response=previous))
    assert verified.status == "completed"
    assert verified.text == answer_text
    prior_context = next(item for item in semantic.verify_async.await_args.kwargs["compact_evidence"]
                         if item.get("scope") == "previous_response")
    assert prior_context["availability"] == "unavailable"
    assert prior_context["data"]["terminal_status"] == "unavailable"


def test_clarification_tool_accepts_one_natural_question_not_internal_fields():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("ask_for_clarification", {
        "question": "Welke van je twee BTC-setups bedoel je?", "reason": "choice_required",
    }).inputs["reason"] == "choice_required"
    with pytest.raises(FinnResponsesToolError, match="clarification_question_invalid"):
        catalog.validate("ask_for_clarification", {
            "question": "Wat is je setup_id?", "reason": "choice_required",
        })


def test_read_timeframe_cannot_be_a_selected_object_name():
    catalog = FinnResponsesToolCatalog()
    definition = next(item for item in catalog.definitions() if item["name"] == "get_active_plan_and_strategy")
    assert "setup_name" in definition["parameters"]["properties"]
    assert catalog.validate("get_active_plan_and_strategy", {
        "setup_name": "Matrix Strategy Parent",
    }).inputs["setup_name"] == "Matrix Strategy Parent"
    with pytest.raises(FinnResponsesToolError, match="read_timeframe_invalid"):
        catalog.validate("get_active_plan_and_strategy", {
            "asset": "BTC", "timeframe": "Matrix Strategy Parent",
        })
    assert catalog.validate("get_active_plan_and_strategy", {
        "asset": "BTC", "timeframe": "4h",
    }).inputs["timeframe"] == "4H"


def test_indicator_model_category_is_canonicalized_by_existing_catalog():
    contract = FinnV2OperationRegistry().require_supported("create_indicator_configuration")
    state = FinnV2OperationStateService().resolve(
        contract=contract,
        message="Maak een technische RSI-indicatorconfiguratie voor ADA.",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"asset": "ADA", "indicator": "RSI", "category": "technisch"},
        model_tool_inputs=True,
    )
    assert state.collected_inputs["indicator"] == "rsi"
    assert state.collected_inputs["category"] == "technical"
    assert not state.missing_required_inputs


def test_model_changed_fields_use_canonical_setup_timeframe():
    assert FinnV2OperationStateService._canonical_input(
        "changed_fields", {"timeframe": "1 uur"}
    ) == {"timeframe": "1H"}


def test_catalog_rejects_model_owned_identity_and_undeclared_inputs():
    catalog = FinnResponsesToolCatalog()
    for inputs in ({"user_id": 3}, {"proposal_id": "other"}, {"bogus": True}):
        with pytest.raises(FinnResponsesToolError):
            catalog.validate(
                "create_dca_plan_proposal",
                {"operation_id": "create_setup", "inputs": inputs},
            )
    with pytest.raises(FinnResponsesToolError):
        catalog.validate("confirm_proposal", {})
    echoed_entity = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "update_setup", "inputs": {"setup_id": 99, "changed_fields": {"timeframe": "1H"}}},
    )
    assert echoed_entity.inputs == {"changed_fields": {"timeframe": "1H"}}
    with pytest.raises(FinnResponsesToolError, match="proposal_input_type_invalid"):
        catalog.validate(
            "create_dca_plan_proposal",
            {"operation_id": "create_setup", "inputs": {"min_investment": "100"}},
        )
    nullable = catalog.validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"min_investment": None, "symbol": "BTC"}},
    )
    assert "min_investment" not in nullable.inputs
    assert "min_investment" not in nullable.required_inputs
    placeholders = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {
            "name": "New Strategy", "base_amount": 0, "entry": "", "targets": [],
        }},
    )
    assert placeholders.inputs == {"name": "New Strategy"}
    assert {"base_amount", "entry", "targets"}.issubset(placeholders.missing_inputs)
    strategy_tool = next(item for item in catalog.definitions() if item["name"] == "create_or_update_trade_plan_proposal")
    variants = strategy_tool["parameters"]["properties"]["payload"]["oneOf"]
    assert all("setup_id" not in variant["properties"]["inputs"]["properties"] for variant in variants)
    update_setup_schema = next(
        variant for variant in variants
        if variant["properties"]["operation_id"]["enum"] == ["update_setup"]
    )
    assert "draft_intent" in update_setup_schema["required"]
    assert set(update_setup_schema["properties"]["inputs"]["properties"]) == {"changed_fields"}
    assert "update_setup:" in strategy_tool["description"]
    assert "Target saved object types: setup, strategy" in strategy_tool["description"]
    assert "Model-supplied fields allowed for this operation: changed_fields" in strategy_tool["description"]
    assert "updating an existing saved object is draft_intent=new" in strategy_tool["description"]
    paper_tool = next(item for item in catalog.definitions() if item["name"] == "manage_paper_bot_proposal")
    assert "Target saved object types: bot" in paper_tool["description"]
    assert all(
        "activate_bot" not in variant["properties"]["operation_id"]["enum"]
        for variant in paper_tool["parameters"]["properties"]["payload"]["oneOf"]
    )
    nested = catalog.validate("create_or_update_trade_plan_proposal", {
        "payload": {"operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}}},
    })
    assert nested.operation_id == "update_setup"


def test_responses_provider_call_disables_sdk_retries_and_sets_timeout():
    fake = FakeResponses(response("r1", text="Een algemene uitleg."))
    client = SimpleNamespace(with_options=Mock(return_value=SimpleNamespace(responses=fake)))

    async def execute(_call):
        raise AssertionError("no tool calls expected")

    asyncio.run(FinnResponsesLoop(client=client, executor=execute).run(
        message="Wat is RSI?", instructions="Use FINN contracts.",
    ))
    assert client.with_options.call_args.kwargs["max_retries"] == 0
    assert 0 < client.with_options.call_args.kwargs["timeout"] <= 20


def test_invalid_sibling_operation_field_returns_registry_driven_repair_hint():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"name": "Existing Setup"},
        }),)),
        response("r2", text="Ik kan de setup pas wijzigen na een geldig voorstel."),
    )

    async def execute(_call):
        raise AssertionError("invalid tool arguments must not reach execution")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Wijzig Existing Setup", instructions="Use FINN contracts."
    ))
    rejected = result.tool_trace[0]["result"]
    contract = FinnV2OperationRegistry().require_supported("update_setup")
    assert rejected["reason"] == "proposal_input_not_in_action_contract"
    assert rejected["operation_id"] == "update_setup"
    assert rejected["allowed_inputs"] == [field for field in contract.input_fields if field != "setup_id"]
    assert rejected["required_inputs"] == list(contract.required_inputs)


def test_dca_frequency_tool_enum_is_from_the_existing_action_contract():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    catalog = FinnResponsesToolCatalog(registry=registry)
    tool = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    payload = tool["parameters"]["properties"]["payload"]
    variant = payload["oneOf"][0] if "oneOf" in payload else payload
    frequency = variant["properties"]["inputs"]["properties"]["dca_frequency"]
    assert frequency["enum"] == list(contract.allowed_values_for("dca_frequency"))
    with pytest.raises(FinnResponsesToolError, match="proposal_input_value_invalid:dca_frequency"):
        catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "draft_intent": "new", "inputs": {
                "setup_type": "dca", "dca_frequency": "wekelijk",
            },
        })


def test_incompatible_specialized_proposal_retries_with_registry_sibling():
    payload = {"operation_id": "create_setup", "draft_intent": "new", "inputs": {
        "setup_type": "swing", "name": "SOL Swing", "symbol": "SOL", "timeframe": "4H",
    }}
    catalog = FinnResponsesToolCatalog()
    with pytest.raises(FinnResponsesToolError, match="dca_tool_requires_dca_setup_contract") as exc:
        catalog.validate("create_dca_plan_proposal", payload)
    assert exc.value.details["recommended_tool_name"] == "create_or_update_trade_plan_proposal"

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", payload),)),
        response("r2", calls=(tool_call("c2", "create_or_update_trade_plan_proposal", payload),)),
        response("r3", text="Ik heb een voorstel voor je swing-setup klaarstaan."),
    )
    executed = []

    async def execute(call):
        executed.append(call.name)
        return {"status": "validation_pending", "operation_id": call.operation_id}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Maak een SOL swing-setup op 4H", instructions="Use the action registry."))
    assert executed == ["create_or_update_trade_plan_proposal"]
    assert result.tool_trace[0]["result"]["recommended_tool_name"] == "create_or_update_trade_plan_proposal"
    assert fake.requests[1]["tool_choice"] == {
        "type": "function", "name": "create_or_update_trade_plan_proposal",
    }


def test_model_dca_proposal_uses_existing_guided_input_canonicalization():
    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "new", "inputs": {
            "name": "Build Smoke BTC", "symbol": "BTC", "timeframe": "4H",
            "setup_type": "DCA", "dca_frequency": "wekelijks", "dca_day": "maandag",
            "dca_amount_mode": "fixed", "base_amount": 100,
        },
    })
    assert call.inputs["setup_type"] == "dca"
    assert call.inputs["dca_frequency"] == "weekly"
    assert call.inputs["dca_day"] == "monday"
    assert call.missing_inputs == ()


def test_invalid_proposal_is_retried_once_with_the_same_registry_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"name": "Existing Setup"},
        }),)),
        response("r2", calls=(tool_call("c2", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}},
        }),)),
        response("r3", text="Ik heb het wijzigingsvoorstel voorbereid."),
    )

    async def execute(_call):
        return {"status": "validation_pending", "confirmation_required": True}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wijzig mijn setup", instructions="Gebruik het contract"))
    assert result.tool_trace[0]["result"]["reason"] == "proposal_input_not_in_action_contract"
    assert fake.requests[1]["tool_choice"] == {
        "type": "function", "name": "create_or_update_trade_plan_proposal",
    }
    assert fake.requests[2]["tool_choice"] == "none"


def test_read_then_invalid_update_can_repair_with_the_registry_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", calls=(tool_call("c2", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"timeframe": "1H"},
        }),)),
        response("r3", calls=(tool_call("c3", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}},
        }),)),
        response("r4", text="Ik heb het wijzigingsvoorstel voorbereid."),
    )

    async def execute(call):
        if call.operation_id is None:
            return {"status": "completed", "results": []}
        return {"status": "validation_pending", "confirmation_required": True}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wijzig mijn setup", instructions="Gebruik het contract"))
    assert len(result.tool_trace) == 3
    assert result.tool_trace[1]["result"]["reason"] == "proposal_input_not_in_action_contract"
    assert fake.requests[2]["tool_choice"] == {
        "type": "function", "name": "create_or_update_trade_plan_proposal",
    }
    assert fake.requests[3]["tool_choice"] == "none"


def test_catalog_rejects_non_scalar_read_selectors():
    catalog = FinnResponsesToolCatalog()
    for arguments in ({"asset": {"symbol": "BTC"}}, {"timeframe": ["4H"]}):
        with pytest.raises(FinnResponsesToolError, match="read_arguments_invalid"):
            catalog.validate("get_market_snapshot", arguments)
    assert catalog.validate(
        "get_active_plan_and_strategy", {"asset": " BTC ", "timeframe": ""},
    ).inputs == {"asset": "BTC"}


def test_proposal_candidate_uses_registry_contract_and_existing_guided_state():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een BTC DCA-setup", conversation_context={}, verified_asset="BTC",
    )
    plan = analysis.request_plan
    assert plan.operation_id == "create_setup"
    assert plan.selector_source == "responses_tool_call"
    assert plan.operation_state["collected_inputs"]["symbol"] == "BTC"
    assert plan.missing_information == ["timeframe", "name", "dca_frequency", "dca_amount_mode", "base_amount"]


def test_explicit_setup_name_overrides_truncated_model_candidate():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {
            "setup_type": "dca", "symbol": "BTC", "timeframe": "4H",
            "name": "Responses Build DCA", "dca_frequency": "weekly",
            "min_investment": 150,
        }},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak een BTC DCA setup op 4H met de naam Responses Build DCA 2eb7de2e, 150 euro per week.",
        conversation_context={}, verified_asset="BTC",
    )
    assert result.request_plan.operation_state["collected_inputs"]["name"] == "Responses Build DCA 2eb7de2e"


@pytest.mark.parametrize("model_timeframe", ["1W", "wekelijks"])
def test_weekly_dca_cadence_cannot_satisfy_setup_chart_timeframe(model_timeframe):
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {
            "setup_type": "dca", "symbol": "BTC", "name": "Build Smoke BTC",
            "dca_frequency": "weekly", "timeframe": model_timeframe,
        }},
    )
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=call, message="Maak een wekelijkse BTC DCA-setup met naam Build Smoke BTC",
        conversation_context={}, verified_asset="BTC",
    )
    state = first.request_plan.operation_state
    assert "timeframe" not in state["collected_inputs"]
    assert "timeframe" in state["missing_required_inputs"]


def test_model_cannot_invent_weekday_for_a_weekly_setup():
    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "inputs": {
            "setup_type": "dca", "symbol": "BTC", "name": "Build Smoke BTC",
            "dca_frequency": "wekelijks", "dca_day": "zaterdag", "timeframe": "4H",
        },
    })
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=call, message="Maak een wekelijkse BTC DCA-setup met naam Build Smoke BTC op 4H",
        conversation_context={}, verified_asset="BTC",
    )
    assert "dca_day" not in first.request_plan.operation_state["collected_inputs"]
    assert "dca_day" in first.request_plan.operation_state["missing_required_inputs"]
    explicit = selection.from_call(
        call=call, message="Maak een wekelijkse BTC DCA-setup op zaterdag met naam Build Smoke BTC op 4H",
        conversation_context={}, verified_asset="BTC",
    )
    assert explicit.request_plan.operation_state["collected_inputs"]["dca_day"] == "saturday"


def test_saved_indicator_configuration_does_not_bundle_unavailable_current_values():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("get_indicator_snapshot", {}).read_tools == ("read_indicator_configuration",)
    assert catalog.validate("get_current_technical_snapshot", {}).read_tools == ("read_technical_snapshot",)


def test_indicator_read_options_come_from_existing_macro_catalog():
    evidence = FinnResponsesReadExecutor._macro_catalog_evidence()
    assert evidence["scope"] == "available_macro_indicator_catalog"
    assert evidence["source"] == "macro_indicator_catalog"
    assert any(item["name"] == "dxy" for item in evidence["data"]["supported_options"])
    assert evidence["data"]["proposal_operation_id"] == "create_indicator_configuration"


def test_proposal_candidate_rejects_cross_asset_context():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    with pytest.raises(ValueError, match="proposal_asset_conflicts"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak een BTC DCA-setup", conversation_context={}, verified_asset="AAPL",
        )


def test_proposal_candidate_does_not_trust_an_unmentioned_model_asset():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "AEX"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een DCA-setup", conversation_context={}, verified_asset=None,
    )
    assert analysis.request_plan.operation_state["collected_inputs"].get("symbol") != "AEX"
    with pytest.raises(ValueError, match="proposal_asset_ambiguous"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak een BTC en ETH setup", conversation_context={}, verified_asset=None,
        )


def test_unsupported_pair_is_reported_without_substituting_base_asset():
    from backend.services.asset_catalog_service import (
        corrected_catalog_instrument, requests_unspecified_asset_correction, unsupported_catalog_pair_mention,
    )

    assert unsupported_catalog_pair_mention("ETH, niet ETH/EUR") is None
    assert unsupported_catalog_pair_mention("ETH/EUR, niet ETH") == "ETH/EUR"
    assert corrected_catalog_instrument("Ik bedoel ETH/EUR, niet ETH.") == "ETH/EUR"
    assert corrected_catalog_instrument("I mean AAPL, not ETH.") == "AAPL"
    assert corrected_catalog_instrument("Ik bedoel ETH, niet ETH/EUR.") == "ETH"
    assert corrected_catalog_instrument("Niet ETH maar AAPL (Apple-aandelen).") == "AAPL"
    assert corrected_catalog_instrument("Ik wil toch AAPL als Apple-aandelen in plaats van ETH.") == "AAPL"
    assert corrected_catalog_instrument("Maak dit plan voor AAPL, niet voor ETH.") == "AAPL"
    assert corrected_catalog_instrument(
        "Correctie: gebruik AAPL (Apple) in plaats van ETH voor dit vaste DCA-concept."
    ) == "AAPL"
    assert corrected_catalog_instrument("Wat betekent ETH/EUR?") is None
    assert corrected_catalog_instrument("Wat als ik AAPL gebruik in plaats van ETH?") is None
    assert corrected_catalog_instrument("Ik bedoel, hoe werkt AAPL naast mijn ETH-plan?") is None
    assert requests_unspecified_asset_correction("Ik bedoel een aandeel in plaats van ETH.", "ETH")
    assert requests_unspecified_asset_correction("I mean a stock instead of BTC.", "BTC")
    assert not requests_unspecified_asset_correction("Wat als ik een aandeel gebruik in plaats van ETH?", "ETH")
    assert not requests_unspecified_asset_correction("Ik bedoel een aandeel in plaats van BTC.", "ETH")
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "ETH"}},
    )
    with pytest.raises(FinnResponsesToolError, match="asset_pair_not_in_catalog") as caught:
        FinnResponsesProposalSelection().from_call(
            call=call,
            message="Maak een Smart DCA-plan voor ETH/EUR.",
            conversation_context={}, verified_asset=None,
        )
    assert caught.value.details["requested_instrument"] == "ETH/EUR"
    assert caught.value.details["status"] == "unsupported"


def test_unspecified_asset_correction_collects_ticker_without_reusing_rejected_asset():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {"symbol": "ETH"}},
    )
    correction = {
        "proposal_id": "old-eth-proposal", "status": "cancelled",
        "operation_id": "create_setup", "previous_asset": "ETH",
        "requested_instrument": None, "awaiting_instrument": True,
        "prior_inputs": {
            "name": "ETH Smart DCA", "setup_type": "dca", "timeframe": "1D",
            "dca_frequency": "weekly", "dca_day": "monday", "base_amount": 80,
            "dca_amount_mode": "fixed",
        },
    }
    first = FinnResponsesProposalSelection().from_call(
        call=call, message="Ik bedoel een aandeel in plaats van ETH.",
        conversation_context={"proposal_correction_result": correction}, verified_asset=None,
    )
    state = first.request_plan.operation_state
    assert state["collected_inputs"].get("symbol") is None
    assert state["next_missing_input"] == "symbol"
    assert state["open_proposal_id"] is None
    second = FinnResponsesProposalSelection().from_call(
        call=call, message="AAPL, het Apple-aandeel.",
        conversation_context={
            "proposal_correction_result": correction,
            "active_guided_operation": state,
        }, verified_asset=None,
    )
    continued = second.request_plan.operation_state
    assert continued["collected_inputs"]["symbol"] == "AAPL"
    assert "name" in continued["missing_required_inputs"]
    assert continued["open_proposal_id"] is None


def test_open_dca_name_correction_keeps_fields_without_old_proposal_id():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {"name": "Bevestig niets"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="De naam is alleen ‘Apple DCA Nieuwe QA’. Bevestig niets.",
        conversation_context={"proposal_correction_result": {
            "proposal_id": "old-aapl-proposal", "status": "cancelled",
            "operation_id": "create_setup", "previous_asset": "AAPL",
            "requested_instrument": "AAPL", "corrected_name": "Apple DCA Nieuwe QA",
            "prior_inputs": {
                "name": "Noem de setup Apple DCA Nieuwe QA. Toon de conceptkaart, bevestig niets.",
                "symbol": "AAPL", "setup_type": "dca", "timeframe": "1D",
                "dca_frequency": "weekly", "dca_day": "monday", "base_amount": 80,
                "dca_amount_mode": "fixed",
            },
        }},
        verified_asset=None,
    )
    state = analysis.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "Apple DCA Nieuwe QA"
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["base_amount"] == 80
    assert state["open_proposal_id"] is None
    assert state["missing_required_inputs"] == []


def test_asset_correction_clarification_reuses_prior_dca_fields_without_old_proposal():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {
            "setup_type": "dca", "symbol": "AAPL",
        }},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Ja, AAPL is Apple-aandelen.",
        conversation_context={"proposal_correction_result": {
            "proposal_id": "old-eth-proposal", "status": "cancelled",
            "operation_id": "create_setup", "previous_asset": "ETH",
            "requested_instrument": "AAPL", "prior_inputs": {
                "name": "ETH Smart DCA", "setup_type": "dca", "timeframe": "1D",
                "dca_frequency": "weekly", "dca_day": "monday",
                "dca_amount_mode": "score_bands", "base_amount": 80,
                "score_source": "benchmark_score", "low_threshold": 40,
                "high_threshold": 70, "low_score_percent": 75,
                "mid_score_percent": 100, "high_score_percent": 125,
            },
        }},
        verified_asset=None,
    )
    state = analysis.request_plan.operation_state
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["timeframe"] == "1D"
    assert state["collected_inputs"]["base_amount"] == 80
    assert state["collected_inputs"]["high_score_percent"] == 125
    assert "name" in state["missing_required_inputs"]
    assert state["open_proposal_id"] is None


def test_asset_correction_clarification_keeps_explicit_replacement_name():
    from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
    from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService

    correction = (
        "Correctie: gebruik AAPL (Apple) in plaats van ETH voor dit vaste DCA-concept. "
        "Houd 1D, elke maandag en €80 per aankoop; noem het Apple DCA Correctie QA. "
        "Toon een nieuw voorstel, bevestig niets."
    )
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    explicit = FinnV2OperationStateService().explicit_inputs(
        contract=contract, message=correction, explicit_asset="AAPL",
    )
    assert explicit["name"] == "Apple DCA Correctie QA"
    assert explicit["base_amount"] == 80
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {"symbol": "AAPL"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Ja, ik bedoel Apple-aandelen met ticker AAPL. Maak een nieuw voorstel.",
        conversation_context={"proposal_correction_result": {
            "proposal_id": "old-eth-proposal", "status": "cancelled",
            "operation_id": "create_setup", "previous_asset": "ETH",
            "requested_instrument": "AAPL", "prior_inputs": {
                "name": "ETH DCA Correctie QA", "setup_type": "dca", "timeframe": "1D",
                "dca_frequency": "weekly", "dca_day": "monday", "base_amount": 80,
                **{key: value for key, value in explicit.items() if key not in {"symbol", "asset"}},
            },
        }},
        verified_asset=None,
    )
    state = analysis.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "Apple DCA Correctie QA"
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["base_amount"] == 80
    assert state["missing_required_inputs"] == []
    direct = FinnResponsesProposalSelection().from_call(
        call=call, message=correction,
        conversation_context={"proposal_correction_result": {
            "proposal_id": "old-eth-proposal", "status": "cancelled",
            "operation_id": "create_setup", "previous_asset": "ETH",
            "requested_instrument": "AAPL", "prior_inputs": {
                "name": "Apple DCA Correctie QA", "setup_type": "dca",
                "timeframe": "1D", "dca_frequency": "weekly",
                "dca_day": "monday", "base_amount": 80,
            },
        }}, verified_asset=None,
    )
    assert direct.request_plan.operation_state["collected_inputs"]["symbol"] == "AAPL"


def test_asset_correction_name_slot_accepts_name_containing_correction_word():
    from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
    from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService

    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    states = FinnV2OperationStateService()
    first = states.resolve(
        contract=contract,
        message="Correctie: gebruik AAPL in plaats van ETH.",
        explicit_asset="AAPL",
        conversation_context={},
        derived_inputs={
            "symbol": "AAPL", "setup_type": "dca", "timeframe": "1D",
            "dca_frequency": "weekly", "dca_day": "monday", "base_amount": 80,
            "dca_amount_mode": "fixed",
        },
        model_tool_inputs=True,
    )
    assert first.missing_required_inputs == ["name"]
    second = states.resolve(
        contract=contract,
        message="Ja, ik bedoel AAPL. Noem het Apple DCA Correctie QA.",
        explicit_asset="AAPL",
        conversation_context={
            "conversation_state_version": states.CONTEXT_STATE_VERSION,
            "active_guided_operation": first.dict(),
        },
        model_tool_inputs=True,
    )
    assert second.collected_inputs["name"] == "Apple DCA Correctie QA"
    assert second.missing_required_inputs == []


def test_saved_object_update_is_not_treated_as_draft_revision():
    call = FinnResponsesToolCatalog().validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "update_setup", "draft_intent": "revise", "inputs": {
            "setup_id": 99, "changed_fields": {"timeframe": "1H"},
        }},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Wijzig mijn bestaande setup naar 1H",
        conversation_context={},
        verified_asset=None,
    )
    assert analysis.request_plan.operation_id == "update_setup"
    assert analysis.request_plan.operation_state["collected_inputs"] == {"changed_fields": {"timeframe": "1H"}}
    assert "setup_id" in analysis.request_plan.missing_information


def test_parent_read_name_does_not_become_new_strategy_name():
    call = FinnResponsesToolCatalog().validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {"name": "Parent Setup"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak een strategie voor Parent Setup.",
        conversation_context={},
        verified_asset=None,
        read_context=[{"results": [{"data": {"name": "Parent Setup"}}]}],
    )
    assert "name" not in analysis.request_plan.operation_state["collected_inputs"]
    assert "name" in analysis.request_plan.missing_information


def test_parent_name_without_explicit_new_name_is_not_supplied_even_without_read():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {"name": "Parent Setup"}},
    )
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=call, message="Maak een strategie voor Parent Setup.",
        conversation_context={}, verified_asset=None,
    )
    assert "name" in first.request_plan.missing_information
    named = selection.from_call(
        call=call, message="Maak een strategie met de naam Parent Setup voor mijn plan.",
        conversation_context={}, verified_asset=None,
    )
    assert named.request_plan.operation_state["collected_inputs"]["name"] == "Parent Setup"


def test_revised_dca_draft_retains_prior_fields_and_changes_only_amount():
    catalog = FinnResponsesToolCatalog()
    contract = catalog.registry.require_supported("create_setup")
    prior_state = {
        "operation_id": "create_setup", "contract_version": contract.version,
        "status": "proposed", "open_proposal_id": "proposal-owned-by-conversation",
        "collected_inputs": {
            "setup_type": "dca", "symbol": "BTC", "timeframe": "4H",
            "name": "Responses Revised 0923", "dca_frequency": "wekelijks",
            "dca_day": "maandag", "dca_amount_mode": "fixed", "base_amount": 150,
        },
        "missing_required_inputs": [],
    }
    context = {"proposal_revision": {
        "proposal_id": "proposal-owned-by-conversation",
        "operation_id": "create_setup", "guided_state": prior_state,
    }}
    call = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "revise",
        "inputs": {"base_amount": 100},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC",
    )
    state = analysis.request_plan.operation_state
    assert state["open_proposal_id"] == "proposal-owned-by-conversation"
    assert state["collected_inputs"]["name"] == "Responses Revised 0923"
    assert state["collected_inputs"]["base_amount"] == 100
    assert state["missing_required_inputs"] == []
    omitted_intent = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "inputs": {"base_amount": 100},
    })
    implicit_revision = FinnResponsesProposalSelection().from_call(
        call=omitted_intent, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC",
    ).request_plan.operation_state
    assert implicit_revision["open_proposal_id"] == "proposal-owned-by-conversation"
    assert implicit_revision["collected_inputs"]["name"] == "Responses Revised 0923"
    assert implicit_revision["missing_required_inputs"] == []
    explicitly_new = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "new",
        "inputs": {"setup_type": "dca", "base_amount": 100},
    })
    new_state = FinnResponsesProposalSelection().from_call(
        call=explicitly_new, message="Maak een nieuwe DCA setup.",
        conversation_context=context, verified_asset="BTC",
    ).request_plan.operation_state
    assert new_state["open_proposal_id"] is None
    assert new_state["collected_inputs"].get("name") != "Responses Revised 0923"
    with pytest.raises(ValueError, match="revisable_proposal_not_found"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak er 100 euro per week van.",
            conversation_context={}, verified_asset="BTC",
        )


def test_model_tool_call_fills_only_pending_guided_slot():
    catalog = FinnResponsesToolCatalog()
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"setup_type": "dca", "symbol": "BTC", "timeframe": "4H"},
        }),
        message="Maak een BTC DCA-setup op 4H",
        conversation_context={},
        verified_asset="BTC",
    )
    context = {"active_guided_operation": first.request_plan.operation_state}
    assert first.request_plan.operation_state["next_missing_input"] == "name"
    second = selection.from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"name": "FINN DCA Flow 0914", "timeframe": "1D"},
        }),
        message="FINN DCA Flow 0914",
        conversation_context=context,
        verified_asset="BTC",
    )
    state = second.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "FINN DCA Flow 0914"
    assert state["collected_inputs"]["timeframe"] == "4H"
    assert state["next_missing_input"] == "dca_frequency"


def test_model_generated_name_is_not_user_supplied_input():
    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "operation_id": "create_setup",
        "inputs": {"symbol": "BTC", "timeframe": "4H", "setup_type": "dca", "name": "DCA BTC 4H"},
    })
    first = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een nieuwe DCA-setup voor BTC op 4H.",
        conversation_context={}, verified_asset="BTC",
    )
    assert "name" not in first.request_plan.operation_state["collected_inputs"]
    assert first.request_plan.operation_state["next_missing_input"] == "name"
    second = FinnResponsesProposalSelection().from_call(
        call=FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"name": "DCA BTC 4H", "dca_frequency": "weekly"},
        }),
        message="Responses Guided 0914",
        conversation_context={"active_guided_operation": first.request_plan.operation_state},
        verified_asset="BTC",
    )
    state = second.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "Responses Guided 0914"
    assert "dca_frequency" not in state["collected_inputs"]


def test_pending_guided_operation_is_persisted_without_model_skipping_it():
    catalog = FinnResponsesToolCatalog()
    first = FinnResponsesProposalSelection().from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),
        message="Maak een DCA-setup voor BTC", conversation_context={}, verified_asset="BTC",
    )
    front = object.__new__(FinnResponsesFrontDoor)
    fake = FakeResponses(response("r1", text="Ik ga verder."))
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-guided"
    front.proposals = FinnResponsesProposalSelection()
    context = {"active_guided_operation": first.request_plan.operation_state}
    result = asyncio.run(front.run(
        message="4H", instructions="Vul het gevraagde veld", conversation_context=context,
        verified_asset="BTC",
    ))
    assert not fake.requests
    assert result.proposal_analysis.request_plan.operation_id == "create_setup"
    assert result.proposal_analysis.request_plan.operation_state["collected_inputs"]["timeframe"] == "4H"


class FakeResponses:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(response_id, *, text="", calls=()):
    return SimpleNamespace(id=response_id, status="completed", output_text=text, output=list(calls))


def tool_call(call_id, name, arguments):
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=json.dumps(arguments))


def test_model_led_coach_uses_one_compact_prompt_without_legacy_answer_rules():
    instructions = FinnResponsesFrontDoor._model_led_instructions("nl")
    fake = FakeResponses(response("coach-1", text="Welke bevestiging bedoel je precies?"))
    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=fake),
        executor=AsyncMock(),
    )
    result = asyncio.run(loop.run(
        message="Waarom wachten?", instructions=instructions,
        previous_verified_answer="Je wilt op bevestiging wachten.",
        model_led_coach=True, locale="nl",
    ))
    sent = fake.requests[0]
    assert result.text == "Welke bevestiging bedoel je precies?"
    assert sent["model"] == "gpt-6-luna"
    assert sent["reasoning"] == {"effort": "none"}
    assert sent["tool_choice"] == "auto"
    assert "trading outcomes" in sent["instructions"]
    assert "Keep user-stated entry conditions intact" in sent["instructions"]
    assert "specific safe process step" in sent["instructions"]
    assert "For this process-choice question" not in sent["instructions"]
    assert "FINN already attempted" not in sent["instructions"]
    assert "Write the entire user-facing response in Dutch" in sent["instructions"]


def test_non_reasoning_clarification_model_does_not_receive_reasoning_option():
    fake = FakeResponses(
        response("first", calls=(tool_call("call-1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),)),
        response("second", text="Wat is de naam van je plan?"),
    )

    async def execute(_call):
        return {"status": "needs_input", "missing_inputs": ["name"]}

    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
        clarification_model="gpt-4o",
    )
    asyncio.run(loop.run(message="Maak een DCA-plan.", instructions="FINN"))
    assert fake.requests[0]["reasoning"] == {"effort": "none"}
    assert fake.requests[1]["model"] == "gpt-4o"
    assert "reasoning" not in fake.requests[1]


@pytest.mark.parametrize("locale,language", [
    ("nl", "Dutch"), ("en", "English"), ("de", "German"),
])
def test_model_led_coach_keeps_effective_locale_after_prompt_reset(locale, language):
    fake = FakeResponses(response("coach-locale", text="A short answer."))
    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=AsyncMock(),
    )
    asyncio.run(loop.run(
        message="Assess my active strategy.",
        instructions=FinnResponsesFrontDoor._model_led_instructions(locale),
        model_led_coach=True, locale=locale,
    ))
    assert f"Write the entire user-facing response in {language}" in fake.requests[0]["instructions"]


def test_direct_answer_read_boundary_distinguishes_saved_fact_from_general_coaching():
    fake = FakeResponses(
        response("judge-1", text='{"requires_read": true}'),
        response("judge-2", text='{"requires_read": false}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.direct_answer_requires_read(
        message="Is mijn 4H DCA-setup voor lange termijn?",
        answer="Ik kan dat zonder details niet zeggen.",
    ))
    assert not asyncio.run(guard.direct_answer_requires_read(
        message="Waarom kan geduld helpen bij een plan?",
        answer="Een vooraf gekozen regel kan impulsieve beslissingen beperken.",
    ))
    assert all(request["tool_choice"] == "none" for request in fake.requests)
    assert all(not request.get("tools") for request in fake.requests)
    assert all(request["model"] == "gpt-6-luna" for request in fake.requests)
    assert all(request["reasoning"] == {"effort": "none"} for request in fake.requests)
    assert all("temperature" not in request for request in fake.requests)


def test_tool_relevance_guard_uses_typed_responses_without_exposing_identity():
    fake = FakeResponses(response("judge", text='{"aligned": false}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    aligned = asyncio.run(guard.is_relevant(
        message="Past wekelijkse BTC-DCA bij mijn plan?", previous_answer="",
        tool_name="create_dca_plan_proposal", tool_purpose="Maak een DCA-setup",
        is_proposal=True,
    ))
    assert aligned is False
    request = fake.requests[0]
    assert request["tool_choice"] == "none" and request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"
    assert "user_id" not in request["input"] and "proposal_id" not in request["input"]
    assert "candidate_operation_id" not in request["input"]
    assert request["text"]["format"]["schema"]["required"] == ["aligned"]


def test_proposal_relevance_checks_mutation_intent_without_overruling_object_kind():
    fake = FakeResponses(response("judge", text='{"aligned": true}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    aligned = asyncio.run(guard.is_relevant(
        message="Maak een strategie voor Matrix Strategy Parent.",
        previous_answer="", tool_name="create_strategy",
        tool_purpose="create strategy", is_proposal=True,
        proposal_operations=[
            {"operation_id": "create_setup", "domain": "setup", "polarity": "create"},
            {"operation_id": "create_strategy", "domain": "strategy", "polarity": "create"},
        ],
    ))
    assert aligned is True
    assert guard.recommended_operation_id is None
    assert "Matrix Strategy Parent" in fake.requests[0]["input"]
    assert "registry_action_operations" not in fake.requests[0]["input"]


def test_mutation_domain_guard_uses_registry_domains_without_owner_identity():
    fake = FakeResponses(response("domain", text='{"domain": "strategy"}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    domain = asyncio.run(guard.requested_mutation_domain(
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro",
        domains=[
            {"domain": "setup", "purpose": "Manage a setup"},
            {"domain": "strategy", "purpose": "Manage a strategy"},
            {"domain": "bot", "purpose": "Manage a bot"},
        ],
    ))
    assert domain == "strategy"
    request = fake.requests[0]
    assert request["tool_choice"] == "none" and request["store"] is False
    assert request["text"]["format"]["schema"]["properties"]["domain"]["enum"] == [
        "setup", "strategy", "bot", "unknown",
    ]
    assert "user_id" not in request["input"] and "proposal_id" not in request["input"]


@pytest.mark.parametrize("corrects", [True, False])
def test_guided_target_correction_is_model_classified_without_identity(corrects):
    fake = FakeResponses(response("correction", text=json.dumps({"corrects_target": corrects})))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    actual = asyncio.run(guard.corrects_guided_target(
        message="Ik bedoel geen paper-bot. Ik bedoel alleen de strategie BTC Breakout Full Strategy.",
        original_operation="delete_bot", requested_slot="bot_id", corrected_domain="strategy",
    ))
    assert actual is corrects
    request = fake.requests[0]
    assert request["tool_choice"] == "none" and request["store"] is False
    assert "user_id" not in request["input"] and "strategy_id" not in request["input"]


def test_proposal_relevance_only_checks_mutation_intent():
    fake = FakeResponses(response("judge", text='{"aligned": true}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    operations = [
        {"operation_id": "update_setup", "domain": "setup", "polarity": "WRITE_ACTION",
         "purpose": "Change a saved setup"},
        {"operation_id": "update_strategy", "domain": "strategy", "polarity": "WRITE_ACTION",
         "purpose": "Change a saved strategy"},
    ]
    aligned = asyncio.run(guard.is_relevant(
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering",
        previous_answer="", tool_name="update_setup", tool_purpose="WRITE_ACTION setup",
        is_proposal=True, proposal_operations=operations,
    ))
    assert aligned is True
    payload = json.loads(fake.requests[0]["input"])
    assert payload == {
        "latest_user_message": "Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering",
        "previous_verified_answer": "",
    }
    assert "persistent change" in fake.requests[0]["instructions"]


@pytest.mark.parametrize("message,continues", [
    ("Apple Paper Bot", True),
    ("Ik bedoel geen bot. Verwijder alleen mijn strategie.", False),
    ("Ik bekijk AAPL; zou je nu handelen of wachten?", False),
])
def test_open_clarification_only_resumes_for_an_answer(message, continues):
    fake = FakeResponses(response("judge", text=json.dumps({"continues": continues})))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    result = asyncio.run(guard.continues_clarification(
        message=message, original_request="Verwijder mijn paper-bot",
        question="Welke paper-bot bedoel je?",
    ))
    assert result is continues
    assert fake.requests[0]["tool_choice"] == "none"


@pytest.mark.parametrize("message,operation_id,requested_slot,continues", [
    ("BTC Breakout Bot", "delete_bot", "bot_id", True),
    ("Verwijder mijn strategie BTC Breakout Full Strategy", "delete_bot", "bot_id", False),
    ("Ik bekijk AAPL; moet ik handelen of wachten?", "delete_bot", "bot_id", False),
    ("Stop-loss op 72000", "create_strategy", "stop_loss", True),
])
def test_guided_turn_boundary_separates_slot_answers_from_new_requests(
    message, operation_id, requested_slot, continues,
):
    fake = FakeResponses(response("judge", text=json.dumps({"continues": continues})))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    actual = asyncio.run(guard.continues_guided_operation(
        message=message, operation_id=operation_id,
        operation_purpose="Continue the active action contract",
        requested_slot=requested_slot, question="Which value should be supplied?",
    ))
    assert actual is continues
    assert fake.requests[0]["text"]["format"]["schema"]["required"] == ["continues"]


@pytest.mark.parametrize("message,requested_slot,expected", [
    ("100 euro.", "base_amount", True),
    ("Entry rond 76000 euro.", "entry", True),
    ("Stop-loss op 72000.", "stop_loss", True),
    ("Vaste uitvoering.", "execution_mode", True),
    ("Dat weet ik nog niet.", "execution_mode", False),
    ("Lösche die in diesem Ablauf erstellte Strategie.", "bot_id", False),
    ("Wat vind je van mijn plan?", "base_amount", False),
    ("Verwijder mijn bot.", "name", False),
    ("Noem de nieuwe strategie ETH Extra Variant. Toon de kaart, bevestig niets.", "name", True),
])
def test_persisted_guided_slot_answer_is_bound_before_model_context_switch(
    message, requested_slot, expected,
):
    registry = FinnV2OperationRegistry()
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=message,
        contract=registry.require_supported("create_strategy"),
        registry=registry,
        requested_slot=requested_slot,
    ) is expected


def test_specific_strategy_name_blocks_overlapping_setup_proposal(monkeypatch):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "draft_intent": "new",
            "inputs": {"changed_fields": {"min_investment": 300}},
        }),)),
        response("r2", text="Ik zal de strategie apart behandelen."),
    )

    class Resolver:
        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, *, user_id, entity_type, **_kwargs):
            names = {
                "setup": (1, "BTC Breakout Full"),
                "strategy": (2, "BTC Breakout Full Strategy"),
            }
            if entity_type not in names:
                return CanonicalEntityTarget(
                    entity_type=entity_type, owner_id=user_id,
                    resolution_status="not_found",
                )
            entity_id, name = names[entity_type]
            return CanonicalEntityTarget(
                entity_type=entity_type, entity_id=entity_id, display_name=name,
                owner_id=user_id, source="explicit_name", resolution_status="resolved",
            )

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(commit=AsyncMock())

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2EntityResolutionService",
        Resolver,
    )
    class ProgressRepository:
        def __init__(self, _session):
            pass

        async def record_responses_progress(self, **_kwargs):
            pass

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2RuntimeContractRepository",
        ProgressRepository,
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "wrong-target"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    front.reads = SimpleNamespace(session_factory=session_factory)
    result = asyncio.run(front.run(
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering",
        instructions="Use FINN tools", conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["result"]["reason"] == "owner_scoped_target_type_mismatch"
    assert result.response.tool_trace[0]["result"]["target_domain"] == "strategy"


def test_owner_scoped_named_strategy_survives_inconclusive_domain_check(monkeypatch):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_strategy", "draft_intent": "new",
            "inputs": {"changed_fields": {"base_amount": 120}},
        }),)),
        response("r2", text="Ik heb een wijzigingsvoorstel voorbereid."),
    )
    guard = SimpleNamespace(
        requested_mutation_domain=AsyncMock(return_value="unknown"),
        is_relevant=AsyncMock(return_value=True),
    )

    class Resolver:
        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, *, user_id, entity_type, **_kwargs):
            if entity_type == "strategy":
                return CanonicalEntityTarget(
                    entity_type="strategy", entity_id=7,
                    display_name="Matrix Update Strategie", owner_id=user_id,
                    source="explicit_name", resolution_status="resolved",
                )
            return CanonicalEntityTarget(
                entity_type=entity_type, owner_id=user_id, resolution_status="not_found",
            )

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(commit=AsyncMock())

    class ProgressRepository:
        def __init__(self, _session):
            pass

        async def record_responses_progress(self, **_kwargs):
            pass

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2EntityResolutionService", Resolver,
    )
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2RuntimeContractRepository",
        ProgressRepository,
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "named-strategy-domain-unknown"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = guard
    front.reads = SimpleNamespace(session_factory=session_factory)
    result = asyncio.run(front.run(
        message="Werk Matrix Update Strategie bij en zet de basisinleg naar 120 euro.",
        instructions="Use FINN tools", conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is not None
    assert result.proposal_analysis.request_plan.operation_id == "update_strategy"
    assert result.response.tool_trace[0]["result"]["status"] == "needs_input"


def test_missing_strategy_cannot_turn_prefix_matched_setup_into_write_proposal(monkeypatch):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "draft_intent": "new",
            "inputs": {"changed_fields": {"min_investment": 300}},
        }),)),
        response("r2", text="Ik kan de bedoelde strategie nog niet vinden."),
    )
    guard = SimpleNamespace(
        requested_mutation_domain=AsyncMock(return_value="strategy"),
        is_relevant=AsyncMock(return_value=True),
    )

    class Resolver:
        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, *, user_id, entity_type, **_kwargs):
            if entity_type == "setup":
                return CanonicalEntityTarget(
                    entity_type="setup", entity_id=1, display_name="BTC Breakout Full",
                    owner_id=user_id, source="explicit_name", resolution_status="resolved",
                )
            return CanonicalEntityTarget(
                entity_type=entity_type, owner_id=user_id, resolution_status="not_found",
            )

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(commit=AsyncMock())

    class ProgressRepository:
        def __init__(self, _session):
            pass

        async def record_responses_progress(self, **_kwargs):
            pass

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2EntityResolutionService", Resolver,
    )
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2RuntimeContractRepository",
        ProgressRepository,
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "missing-strategy-target"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = guard
    front.reads = SimpleNamespace(session_factory=session_factory)
    result = asyncio.run(front.run(
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering",
        instructions="Use FINN tools", conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["result"]["reason"] == "requested_object_type_mismatch", result.response.tool_trace[0]["result"]
    assert result.response.tool_trace[0]["result"]["target_domain"] == "strategy"
    assert guard.requested_mutation_domain.await_count == 1


def test_verified_strategy_domain_outweighs_saved_setup_name_prefix(monkeypatch):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_strategy", "draft_intent": "new",
            "inputs": {"changed_fields": {"base_amount": 300}},
        }),)),
        response("r2", text="Ik kan die strategie nog niet vinden. Welke bedoel je?"),
    )
    guard = SimpleNamespace(
        requested_mutation_domain=AsyncMock(return_value="strategy"),
        is_relevant=AsyncMock(return_value=True),
    )

    class Resolver:
        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, *, user_id, entity_type, **_kwargs):
            if entity_type == "setup":
                return CanonicalEntityTarget(
                    entity_type="setup", entity_id=1, display_name="BTC Breakout Full",
                    owner_id=user_id, source="explicit_name", resolution_status="resolved",
                )
            return CanonicalEntityTarget(
                entity_type=entity_type, owner_id=user_id, resolution_status="not_found",
            )

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(commit=AsyncMock())

    class ProgressRepository:
        def __init__(self, _session):
            pass

        async def record_responses_progress(self, **_kwargs):
            pass

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2EntityResolutionService", Resolver,
    )
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnV2RuntimeContractRepository",
        ProgressRepository,
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "verified-strategy-target"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = guard
    front.reads = SimpleNamespace(session_factory=session_factory)
    result = asyncio.run(front.run(
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering",
        instructions="Use FINN tools", conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is not None
    assert result.proposal_analysis.request_plan.operation_id == "update_strategy"
    assert result.response.tool_trace[0]["result"]["status"] == "needs_input"
    assert result.response.tool_trace[0]["result"]["operation_id"] == "update_strategy"
    assert guard.requested_mutation_domain.await_count == 1


def test_limited_evaluation_preserves_conditional_plan_reasoning():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer, limited_evaluation_format

    schema = limited_evaluation_format()["format"]["schema"]
    assert "conditional_observation" in schema["required"]
    answer = limited_evaluation_answer(json.dumps({
        "saved_context": "Je plan bevat een wachtregel.",
        "user_proposal": "",
        "conditional_observation": "Als de bevestiging ontbreekt, is je eigen entryvoorwaarde nog niet voldaan.",
        "assessment_limit": "Zonder verse koers kan ik niet vaststellen of die bevestiging er nu is.",
        "next_safe_step": "Controleer die voorwaarde voordat je een nieuwe trade overweegt.",
    }))
    assert "entryvoorwaarde" in answer
    assert "niet vaststellen" in answer
    assert "Controleer" in answer


def test_limited_evaluation_renders_only_requested_answer_focus():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    payload = {
        "saved_context": "Je BTC-strategie heeft opgeslagen niveaus.",
        "user_proposal": "", "conditional_observation": "Risico per eenheid is 4000.",
        "verified_strength": "De opgeslagen niveaus maken een berekening mogelijk.",
        "verified_constraint": "Een actuele koers ontbreekt.",
        "priority_actions": ["Controleer je niveaus", "Wacht op actuele data", "Bepaal je risicogrens"],
        "avoid_action": "Vermijd een impulsieve trade.",
        "assessment_limit": "Geschiktheid is nog niet beoordeeld.",
        "next_safe_step": "Controleer eerst de marktsnapshot.",
    }
    review = limited_evaluation_answer(json.dumps({**payload, "response_focus": "review"}))
    assert "berekening mogelijk" in review and "Een actuele koers ontbreekt" in review
    assert "1. Controleer" not in review and "Risico per eenheid" not in review
    calculation = limited_evaluation_answer(json.dumps({**payload, "response_focus": "calculation"}))
    assert "Risico per eenheid" in calculation and "berekening mogelijk" not in calculation
    priorities = limited_evaluation_answer(json.dumps({**payload, "response_focus": "priorities"}))
    assert "1. Controleer" in priorities and "3. Bepaal" in priorities
    assert "Vermijd een impulsieve trade" in priorities and "Risico per eenheid" not in priorities


def test_priority_answer_does_not_require_unused_next_step_field():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "response_focus": "priorities", "saved_context": "Je strategie bevat opgeslagen niveaus.",
        "user_proposal": "", "conditional_observation": "",
        "verified_strength": "", "verified_constraint": "",
        "priority_actions": ["Controleer je opgeslagen niveaus", "Bepaal je risicogrens", "Wacht op verse data"],
        "avoid_action": "Vermijd handelen zonder bevestiging.",
        "assessment_limit": "", "next_safe_step": "",
    }))
    assert "1. Controleer" in answer and "3. Wacht" in answer
    assert "Vermijd handelen" in answer


def test_review_constraint_can_carry_evidence_limit_without_duplicate_limit_field():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "response_focus": "review", "saved_context": "Je BTC-strategie heeft entry, stop en targets.",
        "user_proposal": "", "conditional_observation": "",
        "verified_strength": "De opgeslagen niveaus maken het risico per eenheid berekenbaar.",
        "verified_constraint": "Zonder actuele marktdata kan ik de entry nu niet beoordelen.",
        "priority_actions": [], "avoid_action": "", "assessment_limit": "",
        "next_safe_step": "Controleer eerst of er een verse koerssnapshot beschikbaar is.",
    }))
    assert "risico per eenheid berekenbaar" in answer
    assert "Zonder actuele marktdata" in answer
    assert "verse koerssnapshot" in answer
    assert "Sterk in je plan:" in answer
    assert "Waar ik je afrem:" in answer
    assert "Eerst controleren:" in answer


@pytest.mark.parametrize("locale,expected", [
    ("nl", "zelfstandig plan"),
    ("en", "standalone plan"),
    ("de", "eigenständigen Plan"),
])
def test_plan_review_next_step_uses_typed_missing_component(locale, expected):
    from backend.services.finn_v2_responses_loop import (
        limited_evaluation_answer, plan_review_next_step_from_evidence,
    )

    evidence = [
        {"scope": "read_active_setup", "status": "completed", "data": {"setup_type": "dca"}},
        {"scope": "read_linked_strategy", "status": "unavailable", "reason": "strategy_not_resolved"},
        {"scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable"},
    ]
    step = plan_review_next_step_from_evidence(evidence, locale)
    answer = limited_evaluation_answer(json.dumps({
        "response_focus": "review", "saved_context": "Duplicated saved context",
        "user_proposal": "", "conditional_observation": "", "priority_actions": [],
        "avoid_action": "",
        "verified_strength": "The schedule is recorded.",
        "verified_constraint": "Current market evidence is unavailable.",
        "assessment_limit": "Duplicated market limitation",
        "next_safe_step": "Wait for market data.",
    }), locale=locale, review_next_step=step)
    assert expected in answer
    assert "Wait for market data" not in answer
    assert "Duplicated" not in answer
    assert plan_review_next_step_from_evidence(
        [{**evidence[0]}, {"scope": "read_linked_strategy", "status": "completed"}], locale,
    ) is None


def test_personal_advice_audit_rejects_user_rule_claimed_as_saved():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "user_claim_as_saved": True,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "actionable_next_decision": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    accepted = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Je opgeslagen setup vereist bevestiging voor een entry.",
        question="Mijn plan zegt wachten op bevestiging. Moet ik die regel negeren?",
        evidence=[{"scope": "read_active_setup", "status": "completed", "data": {
            "name": "Coach DCA Basis", "timeframe": "4H",
        }}],
        remaining=20,
    ))
    assert accepted is False


def test_personal_advice_audit_rejects_missing_requested_response_structure():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "user_claim_as_saved": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "question_requests_choice": True,
        "actionable_next_decision": True,
        "requested_structure_satisfied": False,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    diagnostics = {}
    accepted = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Hier zijn drie acties: controleer je plan.",
        question="Wat zijn mijn drie prioriteiten en wat moet ik vermijden?",
        evidence=[{"scope": "read_active_setup", "status": "completed", "data": {"name": "BTC Plan"}}],
        remaining=20,
        audit_diagnostics=diagnostics,
    ))
    assert accepted is False
    assert diagnostics["rejected_checks"] == ["requested_structure_missing"]


def test_personal_advice_audit_rejects_invented_confirmation_trigger():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "user_claim_as_saved": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "question_requests_choice": True,
        "actionable_next_decision": True,
        "requested_structure_satisfied": True,
        "invented_rule_detail": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    diagnostics = {}
    accepted = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Wacht op een price-action patroon; dat vergroot je kans op succes.",
        question="Mijn regel zegt te wachten op bevestiging. Moet ik toch handelen?",
        evidence=[{"scope": "read_active_setup", "status": "completed", "data": {"name": "BTC Plan"}}],
        remaining=20, audit_diagnostics=diagnostics,
    ))
    assert accepted is False
    assert diagnostics["rejected_checks"] == ["invented_rule_detail"]


def test_primary_read_choice_uses_existing_evaluation_operation():
    fake = FakeResponses(response("judge", text='{"operation_id":"evaluate_plan","requires_judgment":true,"conditional_process":false}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Past mijn BTC-plan bij mijn risicostijl?", previous_answer="",
        proposed_tool="get_my_profile_and_risk_style", proposed_purpose="Read saved profile",
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate saved plan"}],
    ))
    assert chosen == "evaluate_plan"
    assert fake.requests[0]["text"]["format"]["schema"]["properties"]["operation_id"]["enum"] == [
        "respond_without_tool", "get_my_profile_and_risk_style", "evaluate_plan",
    ]


def test_primary_evaluation_choice_can_downgrade_to_saved_plan_read():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "get_active_plan_and_strategy",
        "requires_judgment": False, "conditional_process": False,
    })))
    chosen = asyncio.run(FinnResponsesToolRelevanceGuard(
        SimpleNamespace(responses=fake),
    ).preferred_read_operation(
        message="Bereken mijn risico per BTC uit entry 80000 en stop 76000.",
        previous_answer="", proposed_tool="evaluate_plan",
        proposed_purpose="Evaluate saved plan",
        read_options=[{"operation_id": "get_active_plan_and_strategy", "purpose": "Read saved levels"}],
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate saved plan"}],
    ))
    assert chosen == "get_active_plan_and_strategy"
    assert fake.requests[0]["text"]["format"]["schema"]["properties"]["operation_id"]["enum"] == [
        "respond_without_tool", "evaluate_plan", "get_active_plan_and_strategy",
    ]


def test_primary_evaluation_choice_preserves_requested_judgment():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "evaluate_plan",
        "requires_judgment": True, "conditional_process": False,
        "response_focus": "review",
    })))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Wat zijn de zwakke punten van mijn plan?", previous_answer="",
        proposed_tool="evaluate_plan", proposed_purpose="Evaluate saved plan",
        read_options=[{"operation_id": "get_active_plan_and_strategy", "purpose": "Read saved plan"}],
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate saved plan"}],
    ))
    assert chosen == "evaluate_plan"
    assert guard.response_focus == "review"


def test_limited_evaluation_schema_keeps_classified_answer_form():
    from backend.services.finn_v2_responses_loop import limited_evaluation_format

    assert limited_evaluation_format("review")["format"]["schema"]["properties"]["response_focus"]["enum"] == ["review"]
    assert limited_evaluation_format("priorities")["format"]["schema"]["properties"]["response_focus"]["enum"] == ["priorities"]
    assert limited_evaluation_format()["format"]["schema"]["properties"]["response_focus"]["enum"] == [
        "general", "review", "calculation", "priorities",
    ]


def test_static_calculation_uses_registry_described_read_even_if_model_proposes_evaluation():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "evaluate_plan", "requires_judgment": True,
        "conditional_process": False, "response_focus": "calculation",
    })))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="What is the numeric reward-to-risk ratio from my saved levels?",
        previous_answer="", proposed_tool="evaluate_plan", proposed_purpose="Evaluate plan",
        read_options=[{
            "operation_id": "get_active_plan_and_strategy",
            "purpose": "Owner-scoped saved plan read with static arithmetic from entry, stop and targets",
        }],
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate suitability"}],
    ))
    assert chosen == "get_active_plan_and_strategy"
    assert guard.response_focus == "calculation"


def test_conditional_plan_priorities_use_saved_plan_read_not_full_evaluation():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "evaluate_plan", "requires_judgment": True,
        "conditional_process": True, "response_focus": "priorities",
        "requested_priority_count": 0,
    })))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Which preparatory steps matter for my saved plan before fresh data is available?",
        previous_answer="", proposed_tool="evaluate_plan", proposed_purpose="Evaluate plan",
        read_options=[{"operation_id": "get_active_plan_and_strategy", "purpose": "Read saved plan"}],
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate suitability"}],
    ))
    assert chosen == "get_active_plan_and_strategy"
    assert guard.conditional_process is True
    assert guard.response_focus == "general"


def test_explicit_three_priority_request_retains_priority_answer_form():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "get_active_plan_and_strategy", "requires_judgment": False,
        "conditional_process": True, "response_focus": "priorities",
        "requested_priority_count": 3,
    })))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Wat zijn mijn drie belangrijkste acties en wat moet ik laten?",
        previous_answer="", proposed_tool="get_active_plan_and_strategy",
        proposed_purpose="Read saved plan",
        read_options=[{"operation_id": "get_active_plan_and_strategy", "purpose": "Read saved plan"}],
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate suitability"}],
    ))
    assert chosen == "get_active_plan_and_strategy"
    assert guard.response_focus == "priorities"


def test_saved_plan_read_uses_typed_priority_process_answer():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", text=json.dumps({
            "priority_actions": ["Controleer je opgeslagen niveaus", "Bepaal je risicogrens", "Wacht op verse data"],
            "avoid_action": "Vermijd een ongefundeerde trade.",
            "data_limit": "De huidige marktcondities zijn niet geverifieerd.",
        })),
    )

    async def execute(_call):
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Geef drie voorbereidingen en wat ik moet vermijden.",
        instructions="Gebruik FINN-tools.", response_focus_check=lambda: "priorities",
    ))
    assert "1. Controleer" in result.text and "3. Wacht" in result.text
    assert "Vermijd" in result.text
    assert fake.requests[1]["tool_choice"] == "none"
    assert fake.requests[1]["text"]["format"]["name"] == "finn_plan_process_priorities"


def test_static_geometry_answer_must_include_absolute_risk_and_each_ratio():
    evidence = ({
        "scope": "read_linked_strategy", "status": "completed",
        "data": {"level_geometry": {
            "status": "completed", "risk_per_unit": "4000",
            "targets": [{"reward_to_risk": "2.00"}, {"reward_to_risk": "3.00"}],
        }},
    },)
    complete = FinnResponsesAnswerVerifier._static_geometry_complete
    assert complete("Risico 4.000 per eenheid; doelen 2,00 en 3,00 keer risico.", evidence, "calculation")
    assert not complete("De doelen zijn 2,00 en 3,00 keer het risico.", evidence, "calculation")
    assert not complete("Risico 4.000 per eenheid; eerste doel 2,00 keer.", evidence, "calculation")
    assert complete("De doelen zijn 2,00 en 3,00 keer het risico.", evidence, "review")


def test_conditional_plan_rule_keeps_factual_read_not_full_suitability_evaluation():
    fake = FakeResponses(response("judge", text=json.dumps({
        "operation_id": "evaluate_plan", "requires_judgment": True,
        "conditional_process": True,
    })))
    chosen = asyncio.run(FinnResponsesToolRelevanceGuard(
        SimpleNamespace(responses=fake),
    ).preferred_read_operation(
        message="Mijn plan zegt wachten op bevestiging. Moet ik die regel negeren uit FOMO?",
        previous_answer="", proposed_tool="get_active_plan_and_strategy",
        proposed_purpose="Read saved setup and strategy",
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Assess full plan"}],
    ))
    assert chosen == "get_active_plan_and_strategy"


def test_capability_question_does_not_promote_profile_read_to_plan_evaluation():
    fake = FakeResponses(response("judge", text='{"operation_id":"evaluate_plan","requires_judgment":false,"conditional_process":false}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Gebaseerd op mijn profiel, waar kan je mij mee helpen?", previous_answer="",
        proposed_tool="get_my_profile_and_risk_style", proposed_purpose="Read saved profile",
        evaluation_options=[{"operation_id": "evaluate_plan", "purpose": "Evaluate saved plan"}],
    ))
    assert chosen == "get_my_profile_and_risk_style"


def test_horizon_classification_keeps_factual_read_instead_of_suitability_evaluation():
    fake = FakeResponses(response("judge", text='{"operation_id":"evaluate_setup","requires_judgment":false,"conditional_process":false}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Ist mein 4H-DCA-Setup langfristiger Vermögensaufbau oder ein Swingtrade?",
        previous_answer="Lass die gespeicherten Einstellungen unverändert.",
        proposed_tool="get_active_plan_and_strategy", proposed_purpose="Read saved setup",
        evaluation_options=[{"operation_id": "evaluate_setup", "purpose": "Evaluate setup"}],
    ))
    assert chosen == "get_active_plan_and_strategy"
    assert "timeframe does not establish" in fake.requests[0]["instructions"]


def test_primary_operation_retry_forces_registry_evaluation_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        response("r2", calls=(tool_call("c2", "evaluate_plan", {}),)),
        response("r3", text="De beoordeling is beperkt door ontbrekende actuele data."),
    )
    executed = []

    async def execute(call):
        executed.append(call.name)
        if call.name == "get_my_profile_and_risk_style":
            return {
                "status": "retry", "reason": "primary_operation_mismatch",
                "recommended_tool_name": "evaluate_plan",
                "instruction": "Use the registry-backed plan evaluation.",
            }
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Past mijn plan?", instructions="Use FINN tools."))
    assert executed == ["get_my_profile_and_risk_style", "evaluate_plan"]
    assert fake.requests[1]["tool_choice"] == {"type": "function", "name": "evaluate_plan"}
    assert result.text == "De beoordeling is beperkt door ontbrekende actuele data."


def test_primary_read_guard_can_choose_general_education_without_a_tool():
    fake = FakeResponses(response(
        "judge", text=json.dumps({
            "operation_id": "respond_without_tool", "requires_judgment": False,
            "conditional_process": False, "horizon_classification_question": False,
            "response_focus": "general", "requested_priority_count": 0,
        }),
    ))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    chosen = asyncio.run(guard.preferred_read_operation(
        message="Wat betekent periodiek beleggen in het algemeen?", previous_answer="",
        proposed_tool="evaluate_setup", proposed_purpose="Evaluate a saved setup",
        evaluation_options=[{"operation_id": "evaluate_setup", "purpose": "Evaluate setup"}],
    ))
    assert chosen == "respond_without_tool"


def test_front_door_rejects_unnecessary_read_then_answers_without_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", text="Bij periodiek beleggen koop je op vaste momenten voor een vast bedrag; het neemt koersrisico niet weg."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-education"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        preferred_read_operation=AsyncMock(return_value="respond_without_tool"),
        is_relevant=AsyncMock(return_value=False),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            raise AssertionError("An educational answer must not read owner data")

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Wat betekent periodiek beleggen in het algemeen?",
        instructions="Use FINN evidence only when needed", conversation_context={}, verified_asset=None,
    ))
    assert result.response.tool_trace[0]["result"]["finalize_now"] is True
    assert fake.requests[1]["tool_choice"] == "none"
    assert "koersrisico niet weg" in result.response.text
    front.relevance_guard.is_relevant.assert_not_awaited()


def test_front_door_executes_its_recommended_registry_evaluation_once():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", calls=(tool_call("c2", "evaluate_setup", {"asset": "BTC"}),)),
        response("r3", text="Ik kan de passendheid nog niet beoordelen zonder actuele gegevens."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-recommended-evaluation"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        preferred_read_operation=AsyncMock(return_value="evaluate_setup"),
        is_relevant=AsyncMock(return_value=False),
    )
    calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            calls.append(call)
            return {"status": "partial", "evaluation_operation_id": "evaluate_setup", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Past een wekelijkse BTC-DCA bij mijn plan?",
        instructions="Gebruik FINN evidence", conversation_context={}, verified_asset="BTC",
    ))

    assert [call.evaluation_operation_id for call in calls] == ["evaluate_setup"]
    front.relevance_guard.is_relevant.assert_not_awaited()
    assert result.response.tool_trace[0]["result"]["recommended_tool_name"] == "evaluate_setup"


def test_front_door_replaces_unneeded_evaluation_with_owner_scoped_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {}),)),
        response("r3", text="Je opgeslagen instap is 80.000 en stop 76.000; het verschil is 4.000."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-static-plan-read"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        preferred_read_operation=AsyncMock(return_value="get_active_plan_and_strategy"),
        is_relevant=AsyncMock(return_value=False),
        conditional_process=False,
    )
    calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            calls.append(call)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Wat is mijn risico per stuk op basis van mijn opgeslagen entry en stop?",
        instructions="Gebruik FINN evidence", conversation_context={}, verified_asset="BTC",
    ))

    assert [call.name for call in calls] == ["get_active_plan_and_strategy"]
    assert result.response.tool_trace[0]["result"]["recommended_tool_name"] == "get_active_plan_and_strategy"
    assert fake.requests[1]["tool_choice"] == {"type": "function", "name": "get_active_plan_and_strategy"}
    front.relevance_guard.is_relevant.assert_not_awaited()


def test_partial_evaluation_tells_coach_not_to_offer_same_run_again():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", text=json.dumps({
            "saved_context": "Mijn opgeslagen setup is bekend.",
            "user_proposal": "",
            "assessment_limit": "Actuele marktdata ontbreken; daarom blijft de beoordeling beperkt.",
            "next_safe_step": "Laat je huidige setup ongewijzigd totdat de ontbrekende gegevens beschikbaar zijn.",
        })),
    )

    async def execute(_call):
        return {
            "status": "partial", "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "missing_required_scopes": ["market_snapshot"], "results": [],
        }

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Beoordeel mijn plan", instructions="Gebruik FINN-tools."))
    assert "already attempted the requested registry evaluation" in fake.requests[1]["instructions"]
    assert "market_snapshot" in fake.requests[1]["instructions"]
    assert "Do not say that no evaluation was performed" in fake.requests[1]["instructions"]
    assert 'Current user question (quoted data): "Beoordeel mijn plan"' in fake.requests[1]["instructions"]
    assert fake.requests[1]["text"]["format"]["name"] == "finn_limited_evaluation"
    assert fake.requests[1]["tool_choice"] == "none"


def test_model_led_partial_evaluation_keeps_natural_answer_without_legacy_json():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", text="Ik kan je plan nog niet beoordelen zonder actuele marktdata."),
    )

    async def execute(_call):
        return {
            "status": "partial", "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "missing_required_scopes": ["market_snapshot"], "results": [],
        }

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Beoordeel mijn plan", instructions="Gebruik FINN-tools.",
          model_led_coach=True))
    assert result.text == "Ik kan je plan nog niet beoordelen zonder actuele marktdata."
    assert "text" not in fake.requests[1]
    assert fake.requests[1]["tool_choice"] == "none"


def test_partial_evaluation_requires_explicit_evidence_limit():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", text=json.dumps({
            "saved_context": "Je setup bestaat.",
            "user_proposal": "",
            "assessment_limit": "",
            "next_safe_step": "Wijzig je DCA-frequentie.",
        })),
    )

    async def execute(_call):
        return {"status": "partial", "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence", "results": []}

    with pytest.raises(FinnResponsesError, match="responses_limited_evaluation_incomplete"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute,
        ).run(message="Past mijn plan?", instructions="Gebruik FINN-tools."))


def test_partial_evaluation_requires_a_safe_next_process_choice():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", text=json.dumps({
            "saved_context": "Je setup bestaat.",
            "user_proposal": "",
            "assessment_limit": "De beoordeling mist actuele bronnen.",
            "next_safe_step": "",
        })),
    )

    async def execute(_call):
        return {"status": "partial", "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence", "results": []}

    with pytest.raises(FinnResponsesError, match="responses_limited_evaluation_incomplete"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute,
        ).run(message="Past mijn plan?", instructions="Gebruik FINN-tools."))


def test_limited_evaluation_keeps_saved_state_separate_from_user_proposal():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "saved_context": "Je opgeslagen BTC-setup gebruikt dagelijkse DCA.",
        "user_proposal": "Je overweegt €100 per week.",
        "assessment_limit": "Zonder actuele gegevens kan ik de passendheid niet beoordelen.",
        "next_safe_step": "Laat de opgeslagen setup voorlopig ongewijzigd.",
    }))
    assert "opgeslagen BTC-setup gebruikt dagelijkse DCA" in answer
    assert "Je overweegt €100 per week" in answer
    assert "Opgeslagen:" not in answer
    assert "Je voorstel:" not in answer
    assert "opgeslagen €100" not in answer


def test_limited_evaluation_uses_owner_locale_not_combined_text_detection():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "saved_context": "BTC DCA",
        "user_proposal": "100 euro per week",
        "assessment_limit": "De actuele marktgegevens ontbreken voor een betrouwbaar oordeel.",
        "next_safe_step": "Laat de huidige setup ongewijzigd tot de gegevens beschikbaar zijn.",
    }), locale="nl")
    assert answer.startswith("BTC DCA. 100 euro per week.")


def test_limited_evaluation_mixed_language_is_sent_to_verifier_for_repair():
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "saved_context": "Your saved BTC setup lacks a linked strategy and current market evidence.",
        "user_proposal": "100 euro per week",
        "assessment_limit": "De actuele marktgegevens ontbreken voor een betrouwbaar oordeel.",
        "next_safe_step": "Laat de huidige setup ongewijzigd tot de gegevens beschikbaar zijn.",
    }), locale="nl")
    assert not FinnResponsesAnswerVerifier._language_matches(answer, "nl")
    assert FinnResponsesAnswerVerifier._language_matches(
        "Je opgeslagen BTC-setup heeft nog geen gekoppelde strategie. Laat hem voorlopig ongewijzigd.", "nl",
    )
    assert not FinnResponsesAnswerVerifier._language_matches(
        "Die Eignung deines Setups bleibt unassessed, weil aktuelle Daten fehlen.", "de",
    )


def test_chat_locale_preserves_short_followup_and_allows_language_switch():
    from backend.services.locale_config import resolve_chat_locale

    assert resolve_chat_locale("nl", "Waarom?") == "nl"
    assert resolve_chat_locale("nl", "Please explain why my saved plan is not ready yet.") == "nl"
    assert resolve_chat_locale("nl", "Bitte erkläre, warum mein gespeicherter Plan noch nicht bereit ist.") == "nl"
    assert resolve_chat_locale("nl", "Antwoord in het Engels.") == "en"
    assert resolve_chat_locale("en", "Antworte auf Deutsch.") == "de"
    assert resolve_chat_locale("de", "Can you check the BTC setup?") == "de"
    assert resolve_chat_locale("nl", "Why?", conversation_locale="en") == "en"
    assert resolve_chat_locale("nl", "Antworte auf Deutsch.", conversation_locale="en") == "de"
    assert resolve_chat_locale("nl", "Waarom?") == "nl"


@pytest.mark.parametrize("preferred,message,expected", [
    ("nl", "Please explain my BTC plan in English.", "English"),
    ("nl", "Please explain my BTC plan.", "Dutch"),
    ("en", "Antworte auf Deutsch.", "German"),
])
def test_responses_uses_backend_effective_language_not_evidence_language(preferred, message, expected):
    from backend.services.locale_config import resolve_chat_locale

    fake = FakeResponses(response("r1", text="A grounded answer."))

    async def execute(_call):
        raise AssertionError("no tool calls expected")

    asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message=message,
        instructions="Earlier tool evidence was written in English.",
        locale=resolve_chat_locale(preferred, message),
    ))
    instructions = fake.requests[0]["instructions"]
    assert f"Write the entire user-facing response in {expected}" in instructions
    assert "effective language selected by the backend" in instructions
    assert "Do not infer a different output language" in instructions


def test_profile_coach_presentation_rejects_field_inventory():
    assert not FinnResponsesAnswerVerifier._evaluation_presentation_is_coaching(
        "Gebaseerd op je profiel:\n- **Risicoprofiel:** conservatief\n- **Asset:** BTC"
    )
    assert FinnResponsesAnswerVerifier._evaluation_presentation_is_coaching(
        "Je bouwt rustig vermogen op met BTC. Ik kan je helpen je DCA-setup tegen je risicoafspraken te houden."
    )
    assert FinnResponsesAnswerVerifier._evaluation_presentation_is_coaching(
        "1. Controleer je regel.\n2. Bepaal je risicogrens.\n3. Wacht op bewijs.",
        requested_list=True,
    )


@pytest.mark.parametrize("context,proposal,expected", [
    ("Your saved BTC setup uses daily purchases.", "You are considering 100 euros per week.",
     "You are considering 100 euros per week."),
    ("Dein gespeichertes BTC-Setup verwendet tägliche Käufe.",
     "Du erwägst 100 Euro pro Woche.", "Du erwägst 100 Euro pro Woche."),
])
def test_limited_evaluation_preserves_full_sentences_in_each_language(context, proposal, expected):
    from backend.services.finn_v2_responses_loop import limited_evaluation_answer

    answer = limited_evaluation_answer(json.dumps({
        "saved_context": context,
        "user_proposal": proposal,
        "assessment_limit": (
            "Current data is missing, so suitability is unverified."
            if expected.startswith("You") else
            "Aktuelle Daten fehlen, daher ist die Eignung nicht belegt."
        ),
        "next_safe_step": (
            "Keep the saved setup unchanged for now."
            if expected.startswith("You") else
            "Lass das gespeicherte Setup vorerst unverändert."
        ),
    }))
    assert expected in answer


def test_previous_answer_sufficiency_is_model_judgment_not_keyword_route():
    fake = FakeResponses(
        response("judge", text='{"kind": "explain_previous"}'),
        response("confirm", text='{"matches_restricted_followup": true}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Waarom?",
        previous_answer="De opgeslagen strategie is niet op actuele markt- en risicodata beoordeeld.",
    )) == "explain_previous"
    assert fake.requests[0]["tool_choice"] == "none"


def test_new_setup_question_is_not_an_explanation_of_previous_answer():
    fake = FakeResponses(
        response("judge", text='{"kind": "explain_previous"}'),
        response("confirm", text='{"matches_restricted_followup": false}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Is mijn 4H DCA-setup langetermijnopbouw of een swingtrade?",
        previous_answer="Houd je huidige setup voorlopig ongewijzigd.",
    )) is False
    assert len(fake.requests) == 2


def test_next_decision_uses_verified_answer_without_new_read():
    fake = FakeResponses(
        response("judge", text='{"kind": "next_decision_from_previous"}'),
        response("confirm", text='{"matches_restricted_followup": true}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Wat moet ik als volgende stap besluiten?",
        previous_answer="De geschiktheid is onbewezen door ontbrekende marktdata; bepaal eerst of je de huidige DCA-inleg wilt aanhouden.",
    )) == "next_decision_from_previous"
    assert "next_decision_from_previous" in fake.requests[0]["text"]["format"]["schema"]["properties"]["kind"]["enum"]
    assert fake.requests[1]["input"] == "Wat moet ik als volgende stap besluiten?"


def test_luna_followup_classifier_uses_none_reasoning():
    fake = FakeResponses(
        response("judge", text='{"kind": "next_decision_from_previous"}'),
        response("confirm", text='{"matches_restricted_followup": true}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Wat moet ik als volgende stap besluiten?",
        previous_answer="Bepaal eerst of je de huidige inleg wilt aanhouden.",
        model="gpt-6-luna", reasoning_effort="none",
    )) == "next_decision_from_previous"
    assert len(fake.requests) == 2
    assert all(request["model"] == "gpt-6-luna" for request in fake.requests)
    assert all(request["reasoning"] == {"effort": "none"} for request in fake.requests)
    assert all("temperature" not in request for request in fake.requests)


def test_answer_to_previous_question_is_typed_and_not_a_new_decision_request():
    fake = FakeResponses(
        response("judge", text='{"kind": "answers_previous_question"}'),
        response("confirm", text='{"matches_restricted_followup": true}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Voor de lange termijn, ongeveer vijf jaar.",
        previous_answer="Wat is je beleggingshorizon?",
    )) == "answers_previous_question"

    direct = FakeResponses(response("answer", text="Je beoogt dus een horizon van vijf jaar."))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "evidence_boundary": "Use the verified prior answer."}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=direct), executor=execute,
    ).run(
        message="Voor de lange termijn, ongeveer vijf jaar.",
        instructions="Use verified prior context.", locale="nl",
        previous_verified_answer="Wat is je beleggingshorizon?",
        previous_answer_only=True, answering_previous_question=True,
    ))
    assert result.answer_kind == "answers_previous_question"
    assert direct.requests[0]["tools"] == []
    assert "Incorporate that supplied preference" in direct.requests[0]["instructions"]


def test_persisted_detail_clarification_answer_does_not_rerun_evaluation():
    fake = FakeResponses(response("answer", text="Je beoogt vijf jaar DCA-opbouw; de 4H-grafiek bepaalt die horizon niet."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-detail-answer"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="answers_previous_question"),
    )

    class Reads:
        session_factory = None

        async def __call__(self, call):
            assert call.name == "answer_directly"
            return {"status": "completed", "evidence_boundary": "Use only the verified prior answer."}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Voor de lange termijn, ongeveer vijf jaar.",
        model_message="Previous unresolved request: Is this long-term? User's new message: five years",
        instructions="Coach using verified context.",
        conversation_context={"responses_clarification": {
            "original_message": "Is mijn DCA-setup langetermijnopbouw of swingtrade?",
            "question": "Wat is je beoogde horizon?",
            "reason": "user_detail_required",
        }},
        verified_asset="BTC",
        previous_response={"answer": "Wat is je beoogde horizon?"},
        resuming_clarification=True,
    ))
    assert result.response.answer_kind == "answers_previous_question"
    assert result.response.tool_trace == ()
    assert result.response.uses_previous_response is True
    assert fake.requests[0]["tools"] == []
    assert fake.requests[0]["input"][-1]["content"] == "Voor de lange termijn, ongeveer vijf jaar."
    assert "Original question awaiting this detail" in fake.requests[0]["instructions"]
    assert "Is mijn DCA-setup langetermijnopbouw of swingtrade?" in fake.requests[0]["instructions"]


def test_model_led_clarification_answer_receives_verified_prior_question():
    fake = FakeResponses(response("answer", text="Je bedoelt dus ongeveer vijf jaar; 4H is alleen het grafiektijdsbestek."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-coach-horizon"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    front.reads = SimpleNamespace(session_factory=None)
    asyncio.run(front.run(
        message="Voor de lange termijn, ongeveer vijf jaar.",
        instructions="Use verified context.",
        conversation_context={"responses_clarification": {
            "original_message": "Is mijn 4H-setup voor opbouw of korte trades?",
            "question": "Hoe lang wil je aanhouden?", "reason": "investment_horizon_required",
        }},
        verified_asset="BTC",
        previous_response={
            "run_id": "previous-run", "answer": "Hoe lang wil je aanhouden?",
            "terminal_status": "clarification_required",
            "terminal_reason": "investment_horizon_required", "tool_trace": [],
        },
        resuming_clarification=True,
    ))
    assert "Hoe lang wil je aanhouden?" in fake.requests[0]["input"][0]["content"]
    assert fake.requests[0]["input"][-1]["content"] == "Voor de lange termijn, ongeveer vijf jaar."
    assert "Do not repeat a clarification already answered" in fake.requests[0]["instructions"]
    assert "Is mijn 4H-setup voor opbouw of korte trades?" in fake.requests[0]["instructions"]


def test_object_choice_clarification_keeps_existing_resolution_route():
    fake = FakeResponses(response("r1", text="Welke setup bedoel je?"))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-object-choice"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(previous_answer_suffices=AsyncMock())
    front.reads = SimpleNamespace(session_factory=None)
    asyncio.run(front.run(
        message="Mijn tweede BTC-setup", instructions="Resolve the selected setup.",
        conversation_context={"responses_clarification": {
            "original_message": "Wijzig mijn BTC-setup", "question": "Welke setup bedoel je?",
            "reason": "choice_required",
        }},
        verified_asset="BTC", previous_response={"answer": "Welke setup bedoel je?"},
        resuming_clarification=True,
    ))
    front.relevance_guard.previous_answer_suffices.assert_not_awaited()


def test_new_object_interpretation_is_not_forced_into_previous_decision_route():
    fake = FakeResponses(
        response("judge", text='{"kind": "next_decision_from_previous"}'),
        response("confirm", text='{"matches_restricted_followup": false}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Is mijn 4H DCA-setup langetermijnopbouw of een swingtrade?",
        previous_answer="Houd je huidige setup voorlopig ongewijzigd.",
    )) is False
    assert "A new question asking how to classify" in fake.requests[0]["instructions"]
    assert "ONLY the current user message" in fake.requests[1]["instructions"]


def test_new_question_cannot_be_taken_as_answer_to_previous_question():
    fake = FakeResponses(
        response("judge", text='{"kind": "answers_previous_question"}'),
    )
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Ist mein 4H-DCA-Setup langfristiger Vermögensaufbau oder ein Swingtrade?",
        previous_answer="Für die Beurteilung fehlen aktuelle Marktdaten.",
    )) is False
    assert len(fake.requests) == 1


def test_user_detail_acknowledgement_never_exposes_internal_choice_wrapper():
    answer = FinnResponsesAnswerVerifier._user_detail_acknowledgement(
        "Original user request: Is dit een swingtrade?\n"
        "User's chosen answer: Langfristig, ungefähr fünf Jahre.", "de",
    )
    assert "fünf Jahre" in answer
    assert "Original user request" not in answer
    assert "User's chosen answer" not in answer
    assert "swingtrade" not in answer.casefold()


def test_horizon_acknowledgement_uses_verified_setup_not_internal_wrapper():
    answer = FinnResponsesAnswerVerifier._horizon_detail_acknowledgement(
        "Original user request: Is dit een swingtrade?\n"
        "User's chosen answer: Langfristig, ungefähr fünf Jahre.",
        ({"scope": "read_active_setup", "status": "completed",
          "data": {"setup_type": "dca", "name": "Coach DCA Basis"}},), "de",
    )
    assert "fünf Jahre" in answer and "DCA-Setup" in answer
    assert "Original user request" not in answer
    assert "gespeichertes Setup wurde nicht geändert" in answer


def test_clarification_answer_duration_must_survive_final_response():
    message = (
        "Original user request: Is this long-term?\n"
        "User's chosen answer: For the long term, around five years."
    )
    preserved = FinnResponsesAnswerVerifier._answered_duration_preserved
    assert not preserved(message, "Keep your saved DCA setup unchanged.")
    assert preserved(message, "You mean about five years for your DCA setup.")
    assert preserved(message, "You mean about 5 years for your DCA setup.")


def test_read_answer_cannot_claim_finn_wants_to_mutate_user_data():
    check = FinnResponsesAnswerVerifier._assistant_does_not_claim_user_mutation
    assert not check("Ik wil een macro-indicator toevoegen voor je strategie.")
    assert not check("I want to add a macro indicator to your plan.")
    assert not check("Ich möchte einen Indikator hinzufügen.")
    assert check("Je kunt overwegen een macro-indicator toe te voegen.")


def test_detail_answer_audit_does_not_require_old_hypothetical_change():
    verdict = {
        "unsupported_personal_advice": False, "unsupported_entity_claim": False,
        "proposed_as_saved": False, "proposed_change_omitted": True,
        "premature_action_invitation": False, "language_mismatch": False,
        "unnatural_language": False, "addresses_request": True,
        "actionable_next_decision": True,
    }
    fake = FakeResponses(response("audit", text=json.dumps(verdict)))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(responses=fake))
    kwargs = dict(
        answer="Je beoogt vijf jaar; dat is nog niet opgeslagen als planwijziging.",
        evidence=[], remaining=20, question="Voor de lange termijn, ongeveer vijf jaar.",
        previous_answer="Wat is je beleggingshorizon?", locale="nl",
    )
    assert asyncio.run(verifier._personal_advice_is_grounded(
        **kwargs, answering_previous_question=True,
    ))
    assert not asyncio.run(verifier._personal_advice_is_grounded(
        **kwargs, answering_previous_question=False,
    ))


@pytest.mark.parametrize("message", [
    "Welke keuze moet ik nu eerst maken?",
    "Wat moet ik dan concreet doen met die FOMO terwijl ik op bevestiging wacht?",
])
def test_next_decision_followup_is_restricted_to_previous_verified_answer(message):
    fake = FakeResponses(response("r1", text=json.dumps({
        "reason": "De geschiktheid van een wijziging is nog onbewezen.",
        "next_decision": "Bepaal eerst of je de huidige inleg wilt aanhouden.",
    })))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-next-decision"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="next_decision_from_previous"),
        is_relevant=AsyncMock(),
    )

    class Reads:
        session_factory = None

        async def __call__(self, call):
            assert call.name == "answer_directly"
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message=message, instructions="Gebruik FINN-tools",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "De huidige DCA-inleg is bekend, maar actuele marktdata ontbreken."},
    ))
    front.relevance_guard.previous_answer_suffices.assert_awaited_once()
    assert fake.requests[0]["tools"] == []
    assert fake.requests[0]["tool_choice"] == "none"
    assert fake.requests[0]["text"]["format"]["name"] == "finn_next_decision"
    assert "one concrete preparatory decision" in fake.requests[0]["instructions"]
    assert "request another market analysis" in fake.requests[0]["instructions"]
    assert result.response.answer_kind == "grounded_next_decision"
    assert result.response.text.endswith("Bepaal eerst of je de huidige inleg wilt aanhouden.")


def test_model_led_next_decision_uses_completed_verified_answer():
    fake = FakeResponses(response("r1", text=(
        "De geschiktheid van een wijziging is nog onbewezen. "
        "Bepaal eerst of je de huidige inleg wilt aanhouden."
    )))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-model-led-next-decision"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="next_decision_from_previous"),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            raise AssertionError("A verified-answer follow-up must not fetch data")

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Welke keuze moet ik nu eerst maken?",
        instructions="Gebruik FINN-tools", conversation_context={}, verified_asset=None,
        previous_response={
            "answer": "De huidige DCA-inleg is bekend, maar actuele marktdata ontbreken.",
            "terminal_status": "completed", "tool_trace": [],
        },
    ))
    front.relevance_guard.previous_answer_suffices.assert_not_awaited()
    assert fake.requests[0]["model"] == "gpt-6-luna"
    assert fake.requests[0]["reasoning"] == {"effort": "none"}
    assert fake.requests[0]["tool_choice"] == "auto"
    assert result.response.answer_kind == "free_text"
    assert "Bepaal eerst" in result.response.text


def test_next_decision_uses_prior_typed_absence_without_inventing_strategy():
    fake = FakeResponses(response("r1", text=json.dumps({
        "reason": "Je beschrijft een wachtregel voor een entry.",
        "next_decision": "Laat de wachtregel staan en noteer welke bevestiging je afwacht.",
    })))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "results": []}

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Wat doe ik met FOMO terwijl ik wacht?", instructions="Gebruik FINN-tools",
        previous_verified_answer="De door jou beschreven wachtregel is nog niet vervuld.",
        previous_tool_availability=({"scope": "read_active_setup", "status": "completed"}, {
            "scope": "read_linked_strategy", "status": "unavailable",
        }),
        previous_answer_only=True, next_decision_from_previous=True,
    ))
    assert "read_linked_strategy" in fake.requests[0]["input"][0]["content"]
    assert "did not find a linked saved strategy" in fake.requests[0]["instructions"]


def test_conditional_next_step_is_structured_around_prior_rule():
    fake = FakeResponses(response("r1", text=json.dumps({
        "condition_from_previous_answer": "You are waiting for entry confirmation.",
        "step_now": "Write down what would count as that confirmation.",
        "avoid_now": "Do not enter before it is observed.",
        "data_limit": "I cannot verify the current market condition here.",
    })))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="What should I do while waiting?", instructions="Use FINN evidence",
        previous_verified_answer="The wait rule you described requires entry confirmation.",
        previous_answer_only=True, next_decision_from_previous=True,
        conditional_next_step_from_previous=True, locale="en",
    ))
    assert result.answer_kind == "conditional_next_step"
    assert fake.requests[0]["text"]["format"]["name"] == "finn_conditional_next_step"
    assert "Write down what would count" in result.text
    assert "Do not enter before" in result.text


@pytest.mark.parametrize("locale,answer", [
    ("nl", "Schrijf precies op wat als bevestiging telt. Ga niet in de markt voordat die is waargenomen."),
    ("en", "Write down what counts as confirmation. Do not enter the market before it arrives."),
    ("de", "Schreibe auf, was als Bestätigung zählt. Betritt keinen Trade, bevor du sie siehst."),
])
def test_coach_gate_requires_action_condition_and_no_entry(locale, answer):
    from backend.scripts.run_finn_responses_personal_coach_regression import actionable_wait_step

    assert actionable_wait_step(answer, locale)
    assert not actionable_wait_step("Focus on discipline and consider other trades.", "en")


def test_next_decision_can_use_earlier_owner_verified_answer_after_why_turn():
    earlier = "Je kunt de huidige DCA-setup ongewijzigd laten terwijl actuele gegevens ontbreken."
    fake = FakeResponses(response("r1", text=json.dumps({
        "reason": "Een geschiktheidsoordeel ontbreekt nog.",
        "next_decision": "Laat daarom de huidige setup voorlopig ongewijzigd.",
    })))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "results": [], "evidence_boundary": "No new facts fetched."}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Welke keuze moet ik nu eerst maken?", instructions="Gebruik FINN-tools.",
        previous_verified_answer="Zonder actuele data kan ik de geschiktheid niet beoordelen.",
        antecedent_verified_answer=earlier,
        previous_answer_only=True, next_decision_from_previous=True,
    ))
    assert earlier in fake.requests[0]["input"][0]["content"]
    assert result.text.endswith("Laat daarom de huidige setup voorlopig ongewijzigd.")


def test_next_decision_cannot_omit_user_action():
    fake = FakeResponses(response("r1", text=json.dumps({
        "reason": "Actuele marktdata ontbreken.", "next_decision": "",
    })))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "results": [], "evidence_boundary": "Previous answer only."}

    with pytest.raises(FinnResponsesError, match="responses_next_decision_incomplete"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute,
        ).run(
            message="Welke keuze nu?", instructions="Gebruik het vorige antwoord",
            previous_verified_answer="De huidige beoordeling is beperkt.",
            previous_answer_only=True, next_decision_from_previous=True,
        ))


def test_next_decision_does_not_require_literal_quote_from_previous_answer():
    fake = FakeResponses(response("r1", text=json.dumps({
        "reason": "Actuele marktdata ontbreken.",
        "next_decision": "Laat de huidige setup voorlopig ongewijzigd.",
    })))

    async def execute(call):
        assert call.name == "answer_directly"
        return {"status": "completed", "results": [], "evidence_boundary": "Previous answer only."}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Welke keuze nu?", instructions="Gebruik het vorige antwoord",
        previous_verified_answer="De huidige beoordeling is beperkt door ontbrekende marktdata.",
        previous_answer_only=True, next_decision_from_previous=True,
    ))
    assert result.answer_kind == "grounded_next_decision"
    assert "grounding_quote" not in fake.requests[0]["text"]["format"]["schema"]["required"]


def test_direct_followup_cannot_introduce_unmentioned_catalog_option():
    evidence = ({"scope": "available_macro_indicator_catalog", "status": "completed",
                 "data": {"supported_options": [
                     {"name": "sp500", "display_name": "S&P 500 Index"},
                     {"name": "vix", "display_name": "CBOE Volatility Index (VIX)"},
                 ]}},)
    verifier = FinnResponsesAnswerVerifier()
    assert verifier._introduces_new_catalog_option(
        "Kies de S&P 500 Index of VIX.", "Actuele marktdata ontbreken.", evidence,
    )
    assert not verifier._introduces_new_catalog_option(
        "Je vroeg naar de S&P 500 Index.", "Wat betekent de S&P 500 Index?", evidence,
    )


@pytest.mark.parametrize("answer", [
    "Setup ID: 7855", "Strategy-ID: 12", "finn-v2-run-123abc",
])
def test_coach_answer_rejects_internal_identifiers(answer):
    assert FinnResponsesAnswerVerifier._contains_internal_identifier(answer)
    assert not FinnResponsesAnswerVerifier._contains_internal_identifier(
        "Je setup BTC 4H heeft een opgeslagen stop-loss van 90."
    )


def test_catalog_focus_audit_rejects_many_options_for_one_choice():
    fake = FakeResponses(response("judge", text=json.dumps({
        "one_candidate_requested": True, "focused": False, "selected_option": "DXY",
        "replacement": "Overweeg DXY als aanvulling; het toont de algemene dollarsterkte.",
    })))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(responses=fake))
    focused, replacement = asyncio.run(verifier._catalog_answer_is_focused(
        question="Welk macro-indicator mis ik nog en waarom?",
        answer="Overweeg DXY, VIX en CPI.",
        options=[
            {"name": "DXY", "display_name": "US Dollar Index (Derived Basket)"},
            {"name": "VIX", "display_name": "CBOE Volatility Index"},
            {"name": "CPI", "display_name": "Consumer Price Index"},
        ], remaining=None,
    ))
    assert focused is False
    assert "DXY" in replacement and "VIX" not in replacement
    assert fake.requests[0]["store"] is False
    assert fake.requests[0]["text"]["format"]["type"] == "json_schema"
    assert "falsely says the user wants" in fake.requests[0]["instructions"]


def test_model_led_indicator_answer_is_not_replaced_by_catalog_copy():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    answer_text = (
        "Voor BTC zijn geen indicatoren opgeslagen. Een mogelijke aanvulling is "
        "BTC-spot-ETF-instroom; zonder actuele waarden kan ik de relevantie niet beoordelen."
    )
    result = FinnResponsesResult(
        answer_text, "resp-indicators", ({
            "name": "evaluate_indicator_configuration", "status": "partial", "result": {
                "results": [
                    {"scope": "read_indicator_configuration", "status": "completed", "data": {
                        "macro": [], "technical": [], "market": [],
                    }},
                    {"scope": "available_macro_indicator_catalog", "status": "completed", "data": {
                        "supported_options": [
                            {"name": "vix", "display_name": "CBOE Volatility Index (VIX)"},
                        ],
                    }},
                ],
            },
        },), model_led_coach=True,
    )
    verified = asyncio.run(verifier.verify(
        message="Welke indicatoren gebruik ik voor BTC en wat ontbreekt mogelijk nog?",
        result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == answer_text


def test_conditional_capability_answer_needs_no_owner_read_but_stays_grounded():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer_text = (
        "Ik kan je helpen instapregels te verduidelijken en risico's te bespreken. "
        "Als je een setup hebt opgeslagen, kan ik die na een read met je doornemen."
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Waarmee kun je me rond mijn handelsplan helpen?",
        result=FinnResponsesResult(answer_text, "resp-capability", (), model_led_coach=True),
        locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == answer_text
    assert verified.evidence == ()
    guidance = semantic.verify_async.await_args.kwargs["verification_guidance"]
    assert "The effective answer language is Dutch" in guidance
    assert "not against the language of the latest user message alone" in guidance
    assert "conditional description" in guidance
    assert "Require evidence for claims about this user's saved objects" in guidance
    assert "not a verified current quote or trend" in guidance
    assert "not a provider outage" in FinnResponsesFrontDoor._model_led_instructions("nl")
    assert len(guidance) < 2500


def test_model_led_fabricated_current_quote_is_blocked_even_if_semantic_model_passes():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="What is BTC trading at now?",
        result=FinnResponsesResult(
            "BTC is trading at $999,999 right now.", "resp-fabricated-price", (),
            model_led_coach=True,
        ),
        locale="en",
    ))
    assert verified.status == "unavailable"
    assert "$999,999" not in verified.text


def test_profile_tool_description_excludes_unrelated_general_explanations():
    definition = next(
        tool for tool in FinnResponsesToolCatalog().definitions()
        if tool["name"] == "get_my_profile_and_risk_style"
    )
    assert "saved profile or risk style" in definition["description"]
    assert "general explanation" in definition["description"]
    assert "not a judgment" in definition["description"]
    assert "evaluate_plan" in definition["description"]


def test_portfolio_tool_description_matches_its_actual_evidence_scope():
    definition = next(
        tool for tool in FinnResponsesToolCatalog().definitions()
        if tool["name"] == "get_portfolio_and_exposure"
    )
    assert "Paper-bot portfolio valuation" in definition["description"]
    assert "does not contain trade transaction history" in definition["description"]
    assert "tax calculations" in definition["description"]


def test_model_led_general_explanation_does_not_invite_invented_example_amounts():
    instructions = FinnResponsesFrontDoor._model_led_instructions("nl")
    assert "answer without account reads" in instructions
    assert "do not invent an example price, currency amount" in instructions


def test_unresolved_owner_object_is_not_presented_as_provider_outage():
    instructions = FinnResponsesFrontDoor._model_led_instructions("nl")
    assert "no unique owner-scoped object" in instructions
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Je setup is opgeslagen, maar ik vond geen gekoppelde strategie. Daarom kan ik geen bot tonen.",
        "resp-unresolved", ({"name": "get_active_plan_and_strategy", "status": "partial", "result": {
            "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {
                    "name": "Atlas", "symbol": "XLM", "timeframe": "4H",
                }},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved"},
            ],
        }},), model_led_coach=True,
    )
    asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Toon mijn complete plan met setup, strategie en bot.",
        result=result, locale="nl",
    ))
    assert "no unique owner-scoped" in semantic.verify_async.await_args.kwargs["verification_guidance"]


def test_catalog_audit_cannot_call_missing_candidate_focused():
    fake = FakeResponses(response("judge", text=json.dumps({
        "one_candidate_requested": True, "focused": True,
        "selected_option": "DXY",
        "replacement": "Overweeg DXY als macro-indicator; die toont de algemene dollarsterkte.",
    })))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(responses=fake))
    focused, replacement = asyncio.run(verifier._catalog_answer_is_focused(
        question="Welk macro-indicator mis ik nog en waarom?",
        answer="Ik heb hiervoor geen actuele marktdata.",
        options=[{"name": "DXY", "display_name": "US Dollar Index (Derived Basket)"}],
        remaining=None,
    ))
    assert focused is False
    assert "DXY" in replacement


def test_catalog_audit_recovers_when_first_judgment_omits_choice():
    fake = FakeResponses(
        response("judge", text=json.dumps({
            "one_candidate_requested": True, "focused": True,
            "selected_option": "", "replacement": "",
        })),
        response("choose", text=json.dumps({
            "selected_option": "dxy",
            "answer": "De US Dollar Index (Derived Basket) toont algemene dollarsterkte.",
        })),
    )
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(responses=fake))
    focused, replacement = asyncio.run(verifier._catalog_answer_is_focused(
        question="Welk macro-indicator mis ik nog en waarom?",
        answer="Actuele marktdata ontbreken.",
        options=[{"name": "dxy", "display_name": "US Dollar Index (Derived Basket)"}],
        remaining=None,
    ))
    assert focused is False
    assert "US Dollar Index" in replacement
    assert fake.requests[1]["text"]["format"]["schema"]["properties"]["selected_option"]["enum"] == ["dxy"]


def test_confirmed_previous_answer_limits_short_followup_to_direct_answer():
    fake = FakeResponses(response("r1", text="Een actuele markt- en risicobeoordeling ontbreekt nog."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-why"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="explain_previous"),
        is_relevant=AsyncMock(),
    )
    called = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            called.append(call.name)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Waarom?", instructions="Gebruik de vorige geverifieerde uitleg",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "Deze strategie heeft nog geen actuele markt- en risicobeoordeling."},
    ))
    assert called == []
    assert fake.requests[0]["tools"] == []
    assert "No new market facts" in fake.requests[0]["instructions"]
    assert fake.requests[0]["tool_choice"] == "none"
    assert result.response.tool_trace == ()
    assert result.response.uses_previous_response is True
    assert result.proposal_analysis is None


def test_undecided_previous_answer_keeps_normal_tool_route_open():
    fake = FakeResponses(response("r1", text="Ik controleer eerst de relevante gegevens."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-undecided"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value=None),
        is_relevant=AsyncMock(),
    )

    class Reads:
        session_factory = None

        async def __call__(self, call):
            raise AssertionError(f"Unexpected server-classified direct call: {call.name}")

    front.reads = Reads()
    asyncio.run(front.run(
        message="Ongeveer vijf jaar.", instructions="Gebruik FINN-tools",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "Welke beleggingshorizon bedoel je?"},
    ))
    assert fake.requests[0]["tools"]
    assert fake.requests[0]["tool_choice"] != "none"


def test_verified_responses_cursor_keeps_user_visible_answer_authoritative():
    fake = FakeResponses(response("r1", text="De risicobeoordeling ontbreekt nog."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-cursor"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="explain_previous"), is_relevant=AsyncMock(),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            return {"status": "completed", "results": []}

    front.reads = Reads()
    asyncio.run(front.run(
        message="Waarom?", instructions="Gebruik het vorige antwoord",
        conversation_context={}, verified_asset="BTC",
        previous_response_id="resp-verified-prior",
        previous_response={"answer": "Voor deze keuze ontbreekt een risicobeoordeling."},
    ))
    assert "previous_response_id" not in fake.requests[0]
    assert fake.requests[0]["input"][0]["content"].startswith(
        "Voor deze keuze ontbreekt een risicobeoordeling."
    )
    assert "Verified preceding-turn context" in fake.requests[0]["input"][0]["content"]
    assert fake.requests[0]["input"][1] == {"role": "user", "content": "Waarom?"}
    assert "unverified draft" in fake.requests[0]["instructions"]


def test_model_led_followup_uses_verified_context_without_a_second_intent_judge():
    fake = FakeResponses(response("r1", text="Je koos nog geen setup; daarom kan ik die niet beoordelen."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-model-led-followup"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(), is_relevant=AsyncMock(),
        preferred_read_operation=AsyncMock(),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            raise AssertionError("A direct answer must not fetch data")

    front.reads = Reads()
    turn = asyncio.run(front.run(
        message="Kun je uitleggen waarom je eerst een keuze nodig hebt?",
        instructions="Gebruik alleen geverifieerde context",
        conversation_context={}, verified_asset="BTC",
        previous_response={
            "run_id": "prior-run", "answer": "Welke van je twee setups bedoel je?",
            "terminal_status": "clarification_required", "terminal_reason": "setup_ambiguous",
            "tool_trace": [],
        },
    ))
    assert turn.response.uses_previous_response is True
    assert turn.response.tool_trace == ()
    assert fake.requests[0]["tool_choice"] == "auto"
    assert "setup_ambiguous" in fake.requests[0]["input"][0]["content"]
    front.relevance_guard.previous_answer_suffices.assert_not_awaited()
    front.relevance_guard.is_relevant.assert_not_awaited()


def test_model_led_explanation_of_verified_answer_does_not_fetch_market_data():
    fake = FakeResponses(response("r1", text="De controle voorkomt dat FOMO je regel vervangt."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-model-led-why"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value="explain_previous"),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            raise AssertionError("Explaining the verified answer needs no new read")

    front.reads = Reads()
    turn = asyncio.run(front.run(
        message="Waarom is die vooraf gekozen controle nuttig?",
        instructions="Gebruik geverifieerde context", conversation_context={},
        verified_asset="BTC", previous_response={
            "run_id": "prior-run", "answer": "Wacht op je vooraf gekozen controle.",
            "terminal_status": "completed", "tool_trace": [],
        },
    ))
    assert turn.response.tool_trace == ()
    front.relevance_guard.previous_answer_suffices.assert_not_awaited()
    assert fake.requests[0]["tool_choice"] == "auto"


def test_model_led_followup_after_open_tool_response_uses_verified_context_only():
    fake = FakeResponses(response("r2", text="Ik vroeg om een keuze omdat er twee setups zijn."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-after-open-tool"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace()

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            raise AssertionError("No read is needed to explain the saved clarification")

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Waarom?", instructions="Use verified context",
        conversation_context={}, verified_asset="BTC",
        previous_response_id=None,
        previous_response={
            "run_id": "prior-run", "response_id": None,
            "answer": "Ik zie meerdere setups. Welke bedoel je?",
            "terminal_status": "clarification_required", "terminal_reason": "setup_ambiguous",
            "tool_trace": [{"name": "evaluate_plan", "status": "partial", "result": {
                "results": [{"scope": "read_active_setup", "status": "unavailable",
                             "reason": "setup_ambiguous"}],
            }}],
        },
    ))
    assert result.response.text.startswith("Ik vroeg om een keuze")
    assert "previous_response_id" not in fake.requests[0]
    assert "setup_ambiguous" in fake.requests[0]["input"][0]["content"]


def test_model_led_read_uses_registry_tool_without_a_second_tool_selector():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        response("r2", text="Je profiel is beschikbaar; laten we je risicostijl bespreken."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-model-led-read"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(), is_relevant=AsyncMock(),
        preferred_read_operation=AsyncMock(),
    )
    seen = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            seen.append(call.name)
            return {"status": "completed", "results": [
                {"scope": "read_profile", "status": "completed", "source": "owner_profile",
                 "as_of": "2026-09-27", "data": {"has_profile": True}},
            ]}

    front.reads = Reads()
    turn = asyncio.run(front.run(
        message="Wat weet je over mijn risicostijl?", instructions="Gebruik FINN-data",
        conversation_context={}, verified_asset="BTC",
    ))
    assert seen == ["get_my_profile_and_risk_style"]
    assert turn.response.tool_trace[0]["call_id"] == "c1"
    assert fake.requests[0]["tool_choice"] == "auto"
    front.relevance_guard.preferred_read_operation.assert_not_awaited()
    front.relevance_guard.is_relevant.assert_not_awaited()


def test_guided_strategy_slot_binds_without_provider_call():
    fake = FakeResponses()
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-guided-stop"
    front.proposals = FinnResponsesProposalSelection()
    contract = front.proposals.registry.require_supported("create_strategy")
    initial = front.proposals.states.resolve(
        contract=contract, message="", explicit_asset="BTC", conversation_context={},
        supplied_inputs={
            "setup_id": 42, "name": "BTC Plan", "execution_mode": "fixed",
            "base_amount": 100, "entry": "76000",
        },
    )
    assert initial.next_missing_input == "stop_loss"
    result = asyncio.run(front.run(
        message="Stop-loss op 72000", instructions="unused",
        conversation_context={"active_guided_operation": initial.dict()},
        verified_asset="BTC", previous_response_id="resp_previous",
    ))
    state = result.proposal_analysis.request_plan.operation_state
    assert not fake.requests
    assert result.proposal_analysis.request_plan.operation_id == "create_strategy"
    assert state["collected_inputs"]["base_amount"] == 100
    assert state["collected_inputs"]["entry"] == 76000
    assert state["collected_inputs"]["stop_loss"] == 72000.0


def test_irrelevant_proposal_is_retried_without_creating_draft():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {}),)),
        response("r3", text="Ik heb eerst je opgeslagen plan nodig om dit te beoordelen."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-fit"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(is_relevant=AsyncMock(return_value=False))

    async def read(_call):
        return {"status": "partial", "results": []}

    class Reads:
        session_factory = None

        async def __call__(self, call):
            return await read(call)

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Past een wekelijkse BTC-DCA bij mijn plan?", instructions="Beoordeel het plan",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["status"] == "retry"
    front.relevance_guard.is_relevant.assert_awaited()
    assert front.relevance_guard.is_relevant.await_args_list[0].kwargs["tool_name"] == "create_setup"


def test_inconclusive_relevance_does_not_veto_confirmation_gated_draft():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "manage_paper_bot_proposal", {
            "operation_id": "deactivate_bot", "draft_intent": "new", "inputs": {},
        }),)),
        response("r2", text="Welke bestaande bot bedoel je?"),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-relevance-timeout"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        is_relevant=AsyncMock(return_value=None),
        requested_mutation_domain=AsyncMock(return_value="bot"),
    )
    front.reads = SimpleNamespace(session_factory=None)
    result = asyncio.run(front.run(
        message="Deactiveer de bot Matrix Deactivate Bot.",
        instructions="Use FINN tools", conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is not None
    assert result.proposal_analysis.request_plan.operation_id == "deactivate_bot"
    assert result.response.tool_trace[0]["result"]["status"] == "needs_input"


def test_model_led_read_question_cannot_start_a_select_asset_proposal():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "manage_asset_watchlist_proposal", {
            "operation_id": "select_asset", "draft_intent": "new", "inputs": {},
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_asset_context", {}),)),
        response("r3", text="Je actieve asset is BTC."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-active-asset-read"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(is_relevant=AsyncMock(return_value=True))

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Welke asset is actief?", instructions="unused",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["status"] == "retry"
    assert result.response.tool_trace[1]["name"] == "get_active_asset_context"
    assert result.response.text == "Je actieve asset is BTC."
    front.relevance_guard.is_relevant.assert_not_awaited()


def test_model_led_completed_read_is_not_reaudited_as_a_missing_action():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_asset_context", {}),)),
        response("r2", text="Je actieve asset is BTC."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-active-asset-read"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        requested_action_contract=AsyncMock(return_value="select_asset"),
    )

    class Reads:
        session_factory = None

        async def __call__(self, _call):
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Welke asset is actief?", instructions="unused",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.text == "Je actieve asset is BTC."
    assert len(result.response.tool_trace) == 1
    front.relevance_guard.requested_action_contract.assert_not_awaited()


@pytest.mark.parametrize("question", [
    "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?",
    "Stel: ik nam deze maand 8 impulsieve trades, 6 verlies en 2 winst, samen -4,2%. Wat is het belangrijkste patroon en welke ene regel zou ik testen?",
])
def test_read_only_coach_questions_cannot_be_reaudited_as_mutations(question):
    fake = FakeResponses(response("coach-direct", text="Laten we dit als reflectie bekijken."))
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-read-only-coach"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        requested_action_contract=AsyncMock(return_value="create_setup"),
    )
    result = asyncio.run(front.run(
        message=question, instructions="unused", conversation_context={},
        verified_asset=None,
    ))
    assert result.proposal_analysis is None
    assert fake.requests[0]["tool_choice"] == "auto"
    assert all(not tool["name"].startswith("propose_") for tool in fake.requests[0]["tools"])
    assert all(tool["name"] != "ask_for_clarification" for tool in fake.requests[0]["tools"])
    front.relevance_guard.requested_action_contract.assert_not_awaited()


def test_irrelevant_followup_read_is_retried_before_data_access():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_current_technical_snapshot", {}),)),
        response("r2", calls=(tool_call("c2", "answer_directly", {"uses_previous_response": True}),)),
        response("r3", text="Omdat de actuele beoordeling nog niet is uitgevoerd."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-followup"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value=False),
        is_relevant=AsyncMock(return_value=False),
    )
    read_calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            read_calls.append(call.name)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Waarom?", instructions="Verklaar het vorige antwoord",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "Een actuele markt- en risicobeoordeling ontbreekt nog."},
    ))
    assert read_calls == ["answer_directly"]
    assert result.response.tool_trace[0]["status"] == "retry"


def test_duplicate_read_is_not_executed_and_model_can_clarify():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {}),)),
        response("r3", calls=(tool_call("c3", "ask_for_clarification", {
            "question": "Wil je eerst je risicostijl of je DCA-frequentie beoordelen?",
            "reason": "choice_required",
        }),)),
        response("r4", text="Wil je eerst je risicostijl of je DCA-frequentie beoordelen?"),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-duplicate-read"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    read_calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            read_calls.append(call.name)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Welke keuze moet ik eerst maken?", instructions="Gebruik de bestaande evidence",
        conversation_context={}, verified_asset="BTC",
    ))
    assert read_calls == ["get_active_plan_and_strategy"]
    assert result.response.tool_trace[1]["status"] == "retry"
    assert result.response.tool_trace[1]["result"]["reason"] == "read_already_completed_this_turn"
    assert fake.requests[2]["tool_choice"] == "required"
    assert result.response.tool_trace[2]["status"] == "needs_input"


def test_unbound_reference_can_clarify_without_irrelevant_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "ask_for_clarification", {
            "question": "Wat wil je dat ik verander?",
            "reason": "user_detail_required",
        }),)),
        response("r2", text="Wat wil je dat ik verander?"),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-unbound-reference"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    front.reads = SimpleNamespace(session_factory=None)

    result = asyncio.run(front.run(
        message="Change that for me. Without any other context.",
        instructions="Ask for the missing target", conversation_context={}, verified_asset=None,
    ))
    assert result.response.tool_trace[0]["status"] == "needs_input"
    assert result.response.tool_trace[0]["result"]["reason"] == "user_detail_required"
    assert fake.requests[0]["tool_choice"] == "auto"


def test_partial_evaluation_can_be_followed_by_missing_profile_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", calls=(tool_call("c2", "get_my_profile_and_risk_style", {}),)),
        response("r3", text=json.dumps({
            "saved_context": "Je opgeslagen setup is bekend.",
            "user_proposal": "",
            "assessment_limit": "Ik kan de passendheid nog niet beoordelen: actuele marktdata ontbreken.",
            "next_safe_step": "Laat je huidige setup ongewijzigd totdat de ontbrekende gegevens beschikbaar zijn.",
        })),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-evaluation-once"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    read_calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            read_calls.append(call.name)
            if call.name == "get_my_profile_and_risk_style":
                return {"status": "completed", "results": [
                    {"scope": "read_user_profile", "status": "completed", "data": {"risk_style": "cautious"}},
                ]}
            return {
                "status": "partial", "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["market_snapshot"], "results": [],
            }

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Past mijn BTC-plan bij mijn risicostijl?", instructions="Gebruik FINN-tools.",
        conversation_context={}, verified_asset="BTC",
    ))
    assert read_calls == ["evaluate_plan", "get_my_profile_and_risk_style"]
    assert fake.requests[2]["tools"] == []
    assert result.response.tool_trace[1]["status"] == "completed"
    assert fake.requests[2]["tool_choice"] == "none"


def test_evaluate_plan_relevance_uses_canonical_contract_meaning():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", text="Ik kan de passendheid nog niet beoordelen zonder actuele evidence."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-evaluate-plan"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(is_relevant=AsyncMock(return_value=True))
    calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            calls.append(call)
            return {"status": "partial", "evaluation_operation_id": "evaluate_plan", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Beoordeel mijn volledige BTC-plan.", instructions="Beoordeel alleen met evidence",
        conversation_context={}, verified_asset="BTC",
    ))
    assert calls[0].evaluation_operation_id == "evaluate_plan"
    assert calls[0].operation_id is None
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["status"] == "partial"
    kwargs = front.relevance_guard.is_relevant.await_args.kwargs
    assert kwargs["tool_name"] == "evaluate_plan"
    assert "overall trading plan" in kwargs["tool_purpose"]
    assert kwargs["is_proposal"] is False


def test_clarification_tool_stops_at_one_choice_and_returns_typed_terminal_question():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        response("r2", calls=(tool_call("c2", "ask_for_clarification", {
            "question": "Welke risicostijl past bij jou?", "reason": "choice_required",
        }),)),
        response("r3", text="Welke risicostijl past bij jou?"),
    )

    async def execute(call):
        if call.name == "ask_for_clarification":
            return {"status": "needs_input", **call.inputs}
        return {"status": "partial", "results": [{
            "scope": "read_profile", "status": "completed", "data": {"has_profile": False},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Beoordeel mijn BTC-plan", instructions="Gebruik FINN-tools"))
    assert fake.requests[2]["tool_choice"] == "none"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Beoordeel mijn BTC-plan", result=result,
    ))
    assert answer.status == "clarification_required"
    assert answer.clarification == {
        "question": "Welke risicostijl past bij jou?", "reason": "choice_required",
    }


def test_recovery_clarification_reuses_completed_read_from_same_run():
    fake = FakeResponses(
        response("r2", calls=(tool_call("c2", "ask_for_clarification", {
            "question": "Wat is je risicostijl?", "reason": "user_detail_required",
        }),)),
        response("r3", text="Wat is je risicostijl?"),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.reads = SimpleNamespace(session_factory=None)
    front.user_id = 21
    front.run_id = "run-recovery"
    result = asyncio.run(front.run(
        message="Maak een plan voor mij", instructions="Vraag gericht door",
        conversation_context={}, verified_asset="BTC",
        prior_tool_trace=({"name": "get_my_profile_and_risk_style", "status": "completed"},),
    ))
    assert result.response.tool_trace[0]["result"]["status"] == "needs_input"


def test_resumed_choice_keeps_evaluation_available_after_identity_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "setup_name": "Matrix Strategy Update Parent",
        }),)),
        response("r2", text="Deze strategy gebruikt je gekozen setup."),
    )

    async def execute(_call):
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed",
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Matrix Strategy Update Parent", instructions="Gebruik FINN-tools",
          resuming_clarification=True))
    assert result.text
    available = {item["name"] for item in fake.requests[1]["tools"]}
    assert {"ask_for_clarification", "evaluate_plan"} <= available
    assert "answer_directly" not in available


def test_resumed_evaluation_requires_registry_tool_after_owner_scoped_choice():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "setup_name": "Chosen Setup",
        }),)),
        response("r2", calls=(tool_call("c2", "evaluate_plan", {}),)),
        response("r3", text=json.dumps({
            "saved_context": "Je hebt Chosen Setup geselecteerd",
            "user_proposal": "",
            "assessment_limit": "Ik kan de geschiktheid niet beoordelen zonder actuele marktdata",
            "next_safe_step": "Laat de opgeslagen instellingen voorlopig ongewijzigd",
        })),
    )

    async def execute(call):
        if call.name == "evaluate_plan":
            return {"status": "partial", "evaluation_operation_id": "evaluate_plan",
                    "assessment_status": "insufficient_evidence", "missing_required_scopes": ["market_snapshot"],
                    "results": [{"scope": "read_profile", "status": "completed"}]}
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed", "data": {"setup_id": 42},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Chosen Setup", instructions="Gebruik FINN-tools",
          resuming_clarification=True, resume_evaluation_operation_id="evaluate_plan"))
    assert [call["name"] for call in result.tool_trace] == [
        "get_active_plan_and_strategy", "evaluate_plan",
    ]
    assert fake.requests[1]["tool_choice"] == {"type": "function", "name": "evaluate_plan"}


def test_indicator_catalog_evaluation_does_not_use_generic_plan_limitation_format():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_indicator_configuration", {}),)),
        response("r2", text="DXY ontbreekt nog in je macroconfiguratie. Het volgt de dollarsterkte, maar ik kan de actuele waarde niet beoordelen."),
    )

    async def execute(_call):
        return {"status": "partial", "evaluation_operation_id": "evaluate_indicator_configuration",
                "assessment_status": "insufficient_evidence", "missing_required_scopes": ["macro_snapshot"],
                "results": [{"scope": "available_macro_indicator_catalog", "status": "completed"}]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Welke macro-indicator ontbreekt?", instructions="Gebruik FINN-tools"))
    assert "DXY" in result.text
    assert "text" not in fake.requests[1]


def test_new_topic_after_clarification_keeps_normal_read_tools():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_market_snapshot", {"asset": "AAPL"}),)),
        response("r2", text="Ik heb nog geen actuele AAPL-snapshot."),
    )

    async def execute(_call):
        return {"status": "partial", "results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat is de actuele AAPL-koers?", instructions="Gebruik FINN-tools",
          resuming_clarification=True))
    assert "get_indicator_snapshot" in {item["name"] for item in fake.requests[1]["tools"]}


def test_unavailable_market_data_is_not_a_user_choice():
    result = FinnResponsesResult("Ik heb geen actuele koers en kan dit nog niet beoordelen.", "r1", ({
        "name": "get_market_snapshot", "status": "partial",
        "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable",
        }]},
    },))
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat is de actuele BTC-koers?", result=result,
    ))
    assert answer.status == "completed"
    assert answer.clarification is None


def test_responses_loop_handles_multiple_calls_then_answer():
    fake = FakeResponses(
        response("r1", calls=(
            tool_call("c1", "get_my_profile_and_risk_style", {}),
            tool_call("c2", "get_active_asset_context", {"asset": "AAPL"}),
        )),
        response("r2", text="Je Apple-plan heeft nog geen koersbewijs."),
    )
    outputs = []

    async def execute(call):
        outputs.append(call)
        return {"status": "completed", "asset": call.inputs.get("asset")}

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Wat betekent dit voor Apple?", instructions="Gebruik FINN-feiten."
    ))
    assert result.response_id == "r2"
    assert len(outputs) == 2
    assert [item["call_id"] for item in fake.requests[1]["input"]] == ["c1", "c2"]
    assert fake.requests[1]["previous_response_id"] == "r1"
    assert all(request.get("parallel_tool_calls", False) is False for request in fake.requests)
    assert all(tool["name"] not in {"confirm_proposal", "execute_confirmed_proposal"} for tool in fake.requests[0]["tools"])


def test_static_calculation_stops_after_owner_scoped_read_without_third_provider_round():
    fake = FakeResponses(response("r1", calls=(
        tool_call("c1", "get_active_plan_and_strategy", {}),
    )))

    async def execute(_call):
        return {"status": "completed", "results": [{
            "scope": "read_linked_strategy", "status": "completed",
            "data": {"name": "BTC Strategy", "level_geometry": {
                "status": "completed", "risk_per_unit": "4000", "targets": [{
                    "price": "88000", "reward_per_unit": "8000", "reward_to_risk": "2.00",
                }],
            }},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Bereken mijn risico en opbrengst uit opgeslagen niveaus.",
        instructions="Gebruik FINN-tools.", response_focus_check=lambda: "calculation",
    ))
    assert result.response_focus == "calculation"
    assert result.text.strip()
    assert len(fake.requests) == 1
    assert result.tool_trace[0]["status"] == "completed"


def test_conflicting_proposal_calls_create_no_draft_before_single_retry():
    fake = FakeResponses(
        response("r1", calls=(
            tool_call("c1", "create_or_update_trade_plan_proposal", {
                "payload": {"operation_id": "update_setup", "draft_intent": "revise",
                            "inputs": {"changed_fields": {"min_investment": 200}}},
            }),
            tool_call("c2", "create_or_update_trade_plan_proposal", {
                "payload": {"operation_id": "create_setup", "draft_intent": "new",
                            "inputs": {"name": "Separate DCA", "symbol": "BTC", "setup_type": "dca"}},
            }),
        )),
        response("r2", calls=(tool_call("c3", "create_or_update_trade_plan_proposal", {
            "payload": {"operation_id": "create_setup", "draft_intent": "new",
                        "inputs": {"name": "Separate DCA", "symbol": "BTC", "setup_type": "dca"}},
        }),)),
        response("r3", text="Ik heb een nieuw concept voorbereid."),
    )
    executed = []

    async def execute(call):
        executed.append(call.operation_id)
        return {"status": "needs_input", "missing_inputs": ["dca_frequency"]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Maak daarnaast een nieuwe setup", instructions="Gebruik FINN-contracten"))
    assert [item["result"]["reason"] for item in result.tool_trace[:2]] == [
        "multiple_action_proposals", "multiple_action_proposals",
    ]
    assert executed == ["create_setup"]
    assert fake.requests[1]["tool_choice"] == "required"
    assert all(request.get("parallel_tool_calls", False) is False for request in fake.requests)


def test_dca_revision_does_not_turn_weekly_frequency_into_chart_timeframe():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "payload": {"operation_id": "create_setup", "draft_intent": "revise", "inputs": {
            "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H", "setup_type": "dca",
            "dca_frequency": "weekly", "dca_day": "monday", "min_investment": 100,
        }},
    })
    context = {"proposal_revision": {
        "operation_id": "create_setup", "proposal_id": "owned-draft",
        "guided_state": {
            "operation_id": "create_setup", "status": "proposed",
            "contract_version": FinnV2OperationRegistry().require_supported("create_setup").version,
            "open_proposal_id": "owned-draft",
            "collected_inputs": {"name": "BTC DCA", "symbol": "BTC", "timeframe": "4H",
                                 "setup_type": "dca", "dca_frequency": "weekly",
                                 "dca_day": "monday", "min_investment": 150},
            "missing_required_inputs": [], "next_missing_input": None,
        },
    }}
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC", read_context=[],
    )
    assert analysis.request_plan.operation_state["collected_inputs"]["timeframe"] == "4H"


def test_dca_proposal_uses_explicit_asset_when_another_asset_is_negated():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "payload": {"operation_id": "create_setup", "draft_intent": "new", "inputs": {
            "name": "ETH Smart Test", "symbol": "ETH", "timeframe": "1D",
            "setup_type": "dca", "dca_frequency": "weekly", "dca_day": "monday",
            "dca_amount_mode": "score_bands", "base_amount": 100,
            "score_source": "benchmark_score", "low_threshold": 40,
            "high_threshold": 70, "low_score_percent": 50,
            "mid_score_percent": 100, "high_score_percent": 150,
        }},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak Smart DCA voor ETH, niet BTC: naam ETH Smart Test, timeframe 1D, "
                "iedere maandag, basisbedrag €100. Onder 40 50%, 40 tot 70 100%, "
                "vanaf 70 150% van de totale benchmarkscore.",
        conversation_context={}, verified_asset=None, read_context=[],
    )
    assert analysis.request_plan.operation_state["collected_inputs"]["symbol"] == "ETH"
    assert analysis.request_plan.operation_state["missing_required_inputs"] == []


def test_read_only_question_about_open_dca_draft_has_no_proposal_tool():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    fake = FakeResponses(response("draft-coach", text="Bij score 50 geldt de middenstaffel."))

    async def execute(_call):
        raise AssertionError("no tool call expected")

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Wat betekent score 50 voor dit open Smart DCA-concept?",
        instructions="Coach over het open concept.", model_led_coach=True,
        read_only_turn=True, open_draft_available=True,
    ))
    names = {tool["name"] for tool in fake.requests[0]["tools"]}
    assert "get_active_plan_and_strategy" in names
    assert "get_open_dca_draft" in names
    assert "create_dca_plan_proposal" not in names
    assert FinnResponsesToolCatalog().validate("get_open_dca_draft", {}).name == "get_open_dca_draft"


def test_new_dca_weekly_cadence_cannot_supply_missing_chart_timeframe():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "payload": {"operation_id": "create_setup", "draft_intent": "new", "inputs": {
            "name": "BTC DCA", "symbol": "BTC", "timeframe": "1W", "setup_type": "dca",
            "dca_frequency": "weekly", "min_investment": 100,
        }},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een BTC DCA setup van 100 euro per week.",
        conversation_context={}, verified_asset="BTC", read_context=[],
    )
    assert "timeframe" in analysis.request_plan.operation_state["missing_required_inputs"]


def test_valid_proposal_call_is_followed_only_by_a_final_answer():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),)),
        response("r2", text="Ik heb een concept klaar; wat is de naam?"),
    )

    async def execute(_call):
        return {"status": "needs_input", "missing_inputs": ["name"]}

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Maak een DCA-setup", instructions="Use FINN contracts."
    ))
    assert result.response_id == "r2"
    assert fake.requests[1]["tool_choice"] == "none"
    assert fake.requests[0]["model"] == "gpt-6-luna"
    assert fake.requests[1]["model"] == "gpt-6-luna"
    assert fake.requests[1]["reasoning"] == {"effort": "none"}
    assert fake.requests[1]["previous_response_id"] == "r1"
    assert len(fake.requests[1]["input"]) == 1
    assert fake.requests[1]["input"][-1]["call_id"] == "c1"
    assert not result.response_id_reusable
    assert fake.requests[0]["tool_choice"] == "auto"


def test_complete_proposal_uses_bounded_final_model_with_call_id_replay():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"name": "BTC DCA", "symbol": "BTC"},
        }),)),
        response("r2", text="Ik heb een concept voor BTC DCA klaar."),
    )

    async def execute(_call):
        return {"status": "validation_pending", "operation_id": "create_setup", "missing_inputs": []}

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Maak een BTC DCA-setup", instructions="Use FINN contracts."
    ))
    assert result.response_id == "r2"
    assert fake.requests[0]["model"] == "gpt-6-luna"
    assert fake.requests[1]["model"] == "gpt-6-luna"
    assert fake.requests[1]["reasoning"] == {"effort": "none"}
    assert fake.requests[1]["tool_choice"] == "none"
    assert fake.requests[1]["previous_response_id"] == "r1"
    assert len(fake.requests[1]["input"]) == 1
    assert fake.requests[1]["input"][-1]["call_id"] == "c1"
    assert not result.response_id_reusable


def test_four_bounded_tool_attempts_still_allow_a_terminal_proposal_reply():
    fake = FakeResponses(*(
        response(f"r{index}", calls=(tool_call(f"c{index}", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"symbol": "BTC"},
        }),))
        for index in range(1, 5)
    ), response("r5", text="Welke naam wil je voor je BTC-setup gebruiken?"))
    attempts = 0

    async def execute(_call):
        nonlocal attempts
        attempts += 1
        return (
            {"status": "retry", "reason": "incompatible_inputs"}
            if attempts < 4 else
            {"status": "needs_input", "operation_id": "create_setup", "missing_inputs": ["name"]}
        )

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Maak een BTC-setup", instructions="Use FINN contracts."))
    assert attempts == 4
    assert len(fake.requests) == 5
    assert result.text == "Welke naam wil je voor je BTC-setup gebruiken?"
    assert result.tool_trace[-1]["status"] == "needs_input"
    assert not result.response_id_reusable


def test_provider_failure_has_no_legacy_fallback():
    fake = FakeResponses(RuntimeError("provider down"))

    async def execute(_call):
        raise AssertionError("not reached")

    with pytest.raises(FinnResponsesError, match="responses_provider_error"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Hallo", instructions="Help"
        ))
    assert len(fake.requests) == 1


def test_provider_quota_failure_is_typed_and_has_no_legacy_fallback():
    error = RuntimeError("provider quota unavailable")
    error.code = "credit_balance_exhausted"
    fake = FakeResponses(error)

    async def execute(_call):
        raise AssertionError("A provider failure must not execute a tool")

    with pytest.raises(FinnResponsesError, match="responses_provider_quota_unavailable"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Denk met me mee", instructions="Use FINN contracts."
        ))
    assert len(fake.requests) == 1


def test_successful_canonical_responses_call_clears_stale_shared_quota_breaker(monkeypatch):
    from backend.utils import openai_client

    fake = FakeResponses(response("r1", text="Ik kan je helpen nadenken zonder iets te wijzigen."))
    client = SimpleNamespace(responses=fake)
    cleared = []
    monkeypatch.setattr(openai_client, "async_client", client)
    monkeypatch.setattr(openai_client, "clear_openai_runtime_breaker", lambda: cleared.append(True))
    monkeypatch.setattr(
        "backend.services.ai_availability_service.get_ai_availability",
        lambda: {"reason": "ai_unavailable_budget", "source": "redis"},
    )

    async def execute(_call):
        raise AssertionError("A direct response must not execute a tool")

    result = asyncio.run(FinnResponsesLoop(client=client, executor=execute).run(
        message="Denk met me mee", instructions="Use FINN contracts.",
    ))
    assert result.text.startswith("Ik kan je helpen")
    assert cleared == [True]


def test_responses_loop_reads_typed_output_when_output_text_is_empty():
    typed_message = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text="Je plan is nog niet compleet.")],
    )
    fake = FakeResponses(response("r1", calls=(typed_message,)))

    async def execute(_call):
        raise AssertionError("no tool was requested")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Is mijn plan compleet?", instructions="Gebruik FINN-feiten."
    ))
    assert result.text == "Je plan is nog niet compleet."
    assert result.tool_trace == ()


def test_model_cannot_call_confirmation_or_execution():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "execute_confirmed_proposal", {}),)),
        response("r2", text="Ik kan dit niet zonder je bevestiging uitvoeren."),
    )

    async def execute(_call):
        raise AssertionError("unauthorized model tool reached executor")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Voer uit", instructions="Safety"
    ))
    assert result.tool_trace[0]["status"] == "unavailable"


def test_read_executor_uses_server_owner_and_does_not_invent_as_of():
    class FakeReads:
        def __init__(self):
            self.calls = []

        async def execute_tool(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="internal", asset="AAPL", result={"name": "Plan"}, error_codes=[],
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-1"
    executor.reads = FakeReads()
    call = FinnResponsesToolCatalog().validate("get_active_plan_and_strategy", {"asset": "AAPL"})
    result = asyncio.run(executor(call))
    assert len(result["results"]) == 2
    assert result["results"][0]["as_of"] is None
    assert "not a current market" in result["evidence_boundary"]
    assert all(kwargs["user_id"] == 44 and kwargs["run_id"] == "run-1" for kwargs in executor.reads.calls)


def test_active_asset_read_preserves_owner_scoped_selection_source():
    class Reads:
        async def execute_tool(self, **kwargs):
            if kwargs["tool_name"] == "read_active_asset":
                kwargs["shared_state"].update({
                    "asset": "BTC", "resolution_source": "selected_asset",
                })
                data = {"symbol": "BTC", "display_name": "Bitcoin"}
            else:
                data = {"symbols": []}
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="asset_catalog" if kwargs["tool_name"] == "read_active_asset" else "internal",
                asset="BTC", result=data, error_codes=[],
            )

    executor = FinnResponsesReadExecutor(session=object(), user_id=44, run_id="run-asset")
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_active_asset_context", {},
    )))
    assert result["results"][0]["resolution_source"] == "selected_asset"
    assert result["results"][0]["data"]["symbol"] == "BTC"
    assert result["results"][1]["data"]["symbols"] == []
    assert "resolution_source" not in result["results"][1]


def test_local_setup_read_experiment_exposes_facts_not_coach_copy(monkeypatch):
    class Reads:
        async def execute_tool(self, **kwargs):
            if kwargs["tool_name"] == "read_active_setup":
                data = {
                    "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H",
                    "setup_type": "dca", "dca_frequency": "daily",
                    "setups": [{"name": "BTC DCA", "symbol": "BTC"}],
                    "setup_id": 123,
                }
            else:
                data = {"status": "unavailable"}
            return SimpleNamespace(
                success=kwargs["tool_name"] == "read_active_setup",
                availability="available", freshness_status="unknown",
                source="owner_database", asset="BTC", result=data, error_codes=[],
            )

    monkeypatch.setenv("APP_ENV", "local_finn")
    monkeypatch.setenv("FINN_SIMPLE_COACH_EXPERIMENT", "1")
    executor = FinnResponsesReadExecutor(session=object(), user_id=44, run_id="run-1")
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_active_plan_and_strategy", {"asset": "BTC"},
    )))
    setup = result["results"][0]["data"]
    assert setup["fields"]["name"] == "BTC DCA"
    assert setup["not_recorded_fields"] == []
    assert "investment_horizon" not in setup["available_setup_fields"]
    assert result["results"][0]["source"] == "owner_database"
    assert "entity_id" not in setup
    assert "evidence_boundary" not in result
    assert result["evidence_kind"] == "saved_plan_configuration"
    assert result["assessment_status"] == "not_assessed"
    monkeypatch.setenv("APP_ENV", "production")
    normal = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_active_plan_and_strategy", {"asset": "BTC"},
    )))
    assert "evidence_boundary" in normal
    assert normal["results"][0]["data"]["setup_id"] == 123


def test_local_facts_only_projection_applies_to_profile_and_evaluation(monkeypatch):
    class Reads:
        async def execute_tool(self, **kwargs):
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="owner_database", asset="BTC",
                result={"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
                error_codes=[],
            )

    monkeypatch.setenv("APP_ENV", "local_finn")
    monkeypatch.setenv("FINN_SIMPLE_COACH_EXPERIMENT", "1")
    executor = FinnResponsesReadExecutor(session=object(), user_id=44, run_id="run-1")
    executor.reads = Reads()
    profile = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_my_profile_and_risk_style", {},
    )))
    assert "evidence_boundary" not in profile
    assert profile["evidence_kind"] == "saved_profile_preferences"
    assert profile["assessment_status"] == "not_assessed"
    assert profile["results"][0]["source"] == "owner_database"
    evaluation = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "evaluate_setup", {"asset": "BTC"},
    )))
    assert evaluation["evaluation_operation_id"] == "evaluate_setup"
    assert evaluation["assessment_status"]
    assert "assessment_boundary" not in evaluation


@pytest.mark.parametrize("has_profile,missing", [(False, ["profile"]), (True, [])])
def test_portfolio_evaluation_requires_usable_profile_not_just_successful_read(has_profile, missing):
    class Reads:
        async def execute_tool(self, **kwargs):
            tool = kwargs["tool_name"]
            data = (
                {"has_profile": has_profile, "trader_profile": {"risk_profiles": ["balanced"] if has_profile else []}}
                if tool == "read_profile" else
                {"global": {"currency": "EUR", "total_equity": 0, "invested_value": 0,
                            "total_budget_limit": 400},
                 "bots": [{"is_active": True, "is_live": False}]}
                if tool == "read_portfolio" else {}
            )
            return SimpleNamespace(
                success=True, availability="available", freshness_status=(
                    "fresh" if tool == "read_portfolio" else "unknown"
                ),
                as_of="2026-09-28T12:00:00Z" if tool == "read_portfolio" else None,
                source="owner_database", asset=None, result=data, error_codes=[],
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-portfolio"
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate("evaluate_portfolio", {})))
    assert result["missing_required_scopes"] == missing
    assert result["assessment_status"] == (
        "insufficient_evidence" if missing else "evidence_collected_not_yet_judged"
    )
    assert "budget limit is not available cash" in result["assessment_boundary"]
    assert "Paper bot is configuration" in result["assessment_boundary"]


def test_portfolio_readback_identifies_each_bot_budget_separately():
    class Reads:
        async def execute_tool(self, **_kwargs):
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="bot_portfolios", asset=None, as_of=None, error_codes=[],
                result={
                    "global": {"total_budget_limit": 725.0},
                    "bots": [
                        {"bot_id": 1, "name": "BTC Paper", "budget_total_eur": 600.0},
                        {"bot_id": 2, "name": "ETH Paper", "budget_total_eur": 125.0},
                    ],
                },
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-portfolio-budget"
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_portfolio_and_exposure", {},
    )))

    assert result["results"][0]["data"]["bots"][0]["budget_total_eur"] == 600.0
    assert "bots[].budget_total_eur" in result["evidence_boundary"]
    assert "sum across the selected bots" in result["evidence_boundary"]


def test_plan_evidence_coverage_distinguishes_saved_facts_from_full_assessment():
    class Reads:
        async def execute_tool(self, **kwargs):
            tool = kwargs["tool_name"]
            available = tool in {"read_active_setup", "read_profile", "read_user_preferences"}
            return SimpleNamespace(
                success=available, availability="available" if available else "unavailable",
                freshness_status="fresh" if available else "unknown",
                source="owner_database", asset="BTC",
                result={"has_profile": True} if tool == "read_profile" else {"name": "Saved setup"},
                error_codes=[] if available else ["source_unavailable"],
            )

    executor = FinnResponsesReadExecutor(session=object(), user_id=44, run_id="run-coverage")
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "evaluate_plan", {"asset": "BTC"},
    )))
    assert result["assessment_status"] == "insufficient_evidence"
    assert result["evidence_coverage"]["saved_setup"] == {
        "status": "available", "missing_scopes": [],
    }
    assert result["evidence_coverage"]["saved_strategy"]["status"] == "incomplete"
    assert result["evidence_coverage"]["full_assessment"]["status"] == "incomplete"
    assert result["evidence_coverage"]["current_market"]["status"] == "incomplete"

    scenario = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "evaluate_plan", {"asset": "BTC", "hypothetical_change": "100 EUR weekly DCA"},
    )))
    assert scenario["hypothetical_scenario"] == {
        "change": "100 EUR weekly DCA",
        "status": "user_proposed_not_saved",
        "assessment": "not_established_by_scenario_alone",
    }


def test_evaluation_requires_fresh_dated_sources_and_projects_their_as_of():
    class Reads:
        def __init__(self):
            self.market_freshness = "stale"

        async def execute_tool(self, **kwargs):
            tool = kwargs["tool_name"]
            from backend.domain.finn_v2_tools import TOOL_FRESHNESS_MAX_AGE_SECONDS
            dated = TOOL_FRESHNESS_MAX_AGE_SECONDS.get(tool) is not None
            return SimpleNamespace(
                success=True, availability="available",
                freshness_status=(self.market_freshness if tool == "read_market_snapshot"
                                  else "fresh" if dated else "not_applicable"),
                as_of="2026-09-28T12:00:00Z" if dated else None,
                source="owner_database", asset="BTC",
                result={"has_profile": True} if tool == "read_profile" else {"name": "Saved"},
                error_codes=[],
            )

    reads = Reads()
    executor = FinnResponsesReadExecutor(session=object(), user_id=44, run_id="run-freshness")
    executor.reads = reads
    call = FinnResponsesToolCatalog().validate("evaluate_plan", {"asset": "BTC"})
    stale = asyncio.run(executor(call))
    assert stale["missing_required_scopes"] == ["market_snapshot"]
    assert stale["evidence_coverage"]["current_market"] == {
        "status": "incomplete", "missing_scopes": ["market_snapshot"],
    }
    assert next(item for item in stale["results"] if item["scope"] == "read_market_snapshot")["as_of"]
    reads.market_freshness = "fresh"
    fresh = asyncio.run(executor(call))
    assert fresh["missing_required_scopes"] == []
    assert fresh["evidence_coverage"]["full_assessment"]["status"] == "available"


def test_portfolio_evaluation_repair_uses_portfolio_evidence_not_plan_template():
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=[
        SimpleNamespace(available=True, passes=False, reason_codes=["insufficient_evidence"]),
        SimpleNamespace(available=True, passes=True, reason_codes=[]),
    ]))
    revised = (
        "Je portefeuille toont nu geen belegde positie. De ingestelde paper-bot is geen "
        "live belegging; zonder ingevuld profiel kan ik niet beoordelen wat bij je past."
    )
    create = AsyncMock(return_value=SimpleNamespace(output_text=revised))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    result = FinnResponsesResult("Investeer nu je budget.", "resp-portfolio", ({
        "name": "evaluate_portfolio", "status": "completed", "result": {
            "evaluation_operation_id": "evaluate_portfolio",
            "assessment_status": "insufficient_evidence",
            "missing_required_scopes": ["profile"],
            "results": [
                {"scope": "read_profile", "status": "completed", "data": {"has_profile": False}},
                {"scope": "read_portfolio", "status": "completed", "data": {
                    "global": {"currency": "EUR", "invested_value": 0},
                    "bots": [{"is_live": False, "is_active": True}],
                }},
            ],
        },
    },))
    answer = asyncio.run(verifier.verify(
        message="Beoordeel mijn portefeuille.", result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == revised
    assert "text" not in create.await_args.kwargs
    assert any(
        item["scope"] == "read_portfolio"
        for item in semantic.verify_async.await_args.kwargs["compact_evidence"]
    )


def test_read_executor_uses_explicit_current_source_timestamp_only():
    assert FinnResponsesReadExecutor._as_of({
        "as_of": "2026-10-09", "reported_scores": {"macro_score": None},
    }) == "2026-10-09"
    assert FinnResponsesReadExecutor._as_of({"daily_scores": {"report_date": "2026-09-26"}}) is None


def test_score_tool_exposes_current_missing_component_boundary_to_model():
    class Reads:
        async def execute_tool(self, **kwargs):
            if kwargs["tool_name"] == "read_asset_scores":
                return SimpleNamespace(
                    success=True, availability="available", freshness_status="fresh",
                    source="daily_scores_and_source_indicators", asset="BTC",
                    result={"symbol": "BTC", "as_of": "2026-10-09",
                            "reported_scores": {"macro_score": None, "market_score": 30},
                            "component_source_status": {"macro_score": "stale_source", "market_score": "fresh"},
                            "benchmark_score": None}, error_codes=[],
                )
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="asset_catalog", asset="BTC", result={"symbol": "BTC"}, error_codes=[],
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-scores"
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate("explain_score", {})))
    scores = next(item for item in result["results"] if item["scope"] == "read_asset_scores")
    assert scores["as_of"] == "2026-10-09"
    assert scores["data"]["reported_scores"]["macro_score"] is None
    assert "source-verified" in result["evidence_boundary"]


def test_factual_score_list_exception_does_not_apply_to_score_advice():
    evidence = ({"scope": "read_asset_scores", "status": "completed"},)
    allow = FinnResponsesAnswerVerifier._factual_score_list_requested
    assert allow("Toon mijn BTC-scores en zeg of ze actueel zijn.", evidence)
    assert not allow("Beoordeel mijn BTC-scores en geef advies.", evidence)
    assert not allow("Toon mijn BTC-scores.", ())


def test_responses_loop_guides_current_score_answer_without_replacing_model_text():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "explain_score", {}),)),
        response("r2", text="Macro is onbekend; daarom is er geen totale benchmarkscore."),
    )

    async def execute(_call):
        return {"status": "completed", "results": [{
            "scope": "read_asset_scores", "status": "completed", "freshness": "fresh",
            "as_of": "2026-10-09", "data": {"reported_scores": {"macro_score": None},
                                          "component_source_status": {"macro_score": "stale_source"},
                                          "benchmark_score": None},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Toon mijn scores.", instructions="Use FINN evidence."))
    assert "For current score evidence" in fake.requests[1]["instructions"]
    assert result.text == "Macro is onbekend; daarom is er geen totale benchmarkscore."


def test_profile_tool_result_exposes_capability_not_suitability_boundary():
    class Reads:
        async def execute_tool(self, **_kwargs):
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="users.ai_preferences", asset=None,
                result={"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
                error_codes=[],
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-profile"
    executor.reads = Reads()
    result = asyncio.run(executor(FinnResponsesToolCatalog().validate(
        "get_my_profile_and_risk_style", {},
    )))

    assert "not a suitability assessment" in result["evidence_boundary"]
    assert "Do not infer" in result["evidence_boundary"]


def test_read_executor_closes_each_database_session_before_provider_resumes(monkeypatch):
    opened = []

    class Session:
        async def __aenter__(self):
            opened.append(self)
            return self

        async def __aexit__(self, *_args):
            opened.remove(self)

    class ToolService:
        def __init__(self, session):
            assert session in opened

        async def execute_tool(self, **_kwargs):
            return SimpleNamespace(
                success=True, availability="available", freshness_status="fresh",
                source="owned_database", asset="BTC", result={"as_of": "2026-09-23T10:00:00Z"},
                error_codes=[],
            )

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_read_executor.FinnV2ToolExecutionService", ToolService,
    )
    executor = FinnResponsesReadExecutor(session_factory=Session, user_id=44, run_id="run-1")
    call = FinnResponsesToolCatalog().validate("get_active_plan_and_strategy", {"asset": "BTC"})
    result = asyncio.run(executor(call))
    assert opened == []
    assert len(result["results"]) == 2
    assert all(item["as_of"] == "2026-09-23T10:00:00Z" for item in result["results"])


def test_responses_exchange_is_owner_bound_and_single_write():
    row = SimpleNamespace(user_id=7, run_id="run-7", conversation_id="conv-7", state_json={})
    repo = object.__new__(FinnV2RuntimeContractRepository)
    repo._required_for_update = AsyncMock(return_value=row)

    async def write_revision(*, row, state):
        row.state_json = state
        return row

    repo._write_revision = write_revision
    with pytest.raises(RuntimeContractConflictError, match="owner_mismatch"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=8, response_id="resp-7", tool_trace=[], answer="Antwoord",
        ))
    result = asyncio.run(repo.record_responses_exchange(
        run_id="run-7", user_id=7, response_id="resp-7",
        tool_trace=[{"call_id": "c1", "status": "completed"}], answer="Antwoord",
        turn_contract={"question": "Vergelijk twee setups", "answer_type": "compare",
                       "targets": [{"setup_id": 1}, {"setup_id": 2}]},
    ))
    assert result.state_json["responses_exchange"]["conversation_id"] == "conv-7"
    assert result.state_json["responses_exchange"]["response_id_reusable"] is True
    assert [item["setup_id"] for item in result.state_json["responses_exchange"]["turn_contract"]["targets"]] == [1, 2]
    assert project_verified_turn({
        "turn_contract": result.state_json["responses_exchange"]["turn_contract"],
    })["turn_contract"]["answer_type"] == "compare"
    with pytest.raises(RuntimeContractConflictError, match="already_recorded"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=7, response_id="resp-8", tool_trace=[], answer="Anders",
        ))
    with pytest.raises(RuntimeContractConflictError, match="already_recorded"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=7, response_id="resp-8", tool_trace=[], answer="Anders",
            supersedes_response_id="wrong-response",
        ))
    recovered = asyncio.run(repo.record_responses_exchange(
        run_id="run-7", user_id=7, response_id="resp-8",
        tool_trace=[{"call_id": "c1"}, {"call_id": "c2"}], answer="Hersteld antwoord",
        supersedes_response_id="resp-7",
        response_id_reusable=False,
    ))
    assert recovered.state_json["responses_exchange"]["supersedes_response_id"] == "resp-7"
    assert recovered.state_json["responses_exchange"]["response_id_reusable"] is False
    assert [item["call_id"] for item in recovered.state_json["responses_exchange"]["tool_trace"]] == ["c1", "c2"]


def test_verified_setup_subject_is_owner_bound_and_can_be_cleared():
    row = SimpleNamespace(user_id=7, run_id="run-7", state_json={})
    repo = object.__new__(FinnV2RuntimeContractRepository)
    repo._required_for_update = AsyncMock(return_value=row)

    async def write_revision(*, row, state):
        row.state_json = state
        return row

    repo._write_revision = write_revision
    subject = {"owner_id": 7, "setup_id": 42, "name": "BTC Full Base", "symbol": "BTC"}
    with pytest.raises(RuntimeContractConflictError, match="owner_mismatch"):
        asyncio.run(repo.record_verified_setup_subject(
            run_id="run-7", user_id=8, subject=subject,
        ))
    with pytest.raises(RuntimeContractConflictError, match="invalid"):
        asyncio.run(repo.record_verified_setup_subject(
            run_id="run-7", user_id=7, subject={**subject, "owner_id": 8},
        ))
    asyncio.run(repo.record_verified_setup_subject(
        run_id="run-7", user_id=7, subject=subject,
    ))
    assert row.state_json["verified_setup_subject"] == subject
    assert verified_selected_setup({
        "terminal_status": "completed", "terminal_kind": "free_text",
        "owner_user_id": 7, "verified_setup_subject": row.state_json["verified_setup_subject"],
    }) == (42, "BTC Full Base")
    asyncio.run(repo.record_verified_setup_subject(
        run_id="run-7", user_id=7, subject=None,
    ))
    assert row.state_json["verified_setup_subject"] is None


def test_pending_clarification_is_persisted_on_the_owner_conversation_contract():
    row = SimpleNamespace(user_id=7, run_id="run-7", conversation_id="conv-7", state_json={})
    repo = object.__new__(FinnV2RuntimeContractRepository)
    repo._required_for_update = AsyncMock(return_value=row)

    async def write_revision(*, row, state):
        row.state_json = state
        return row

    repo._write_revision = write_revision
    with pytest.raises(RuntimeContractConflictError, match="owner_or_conversation_missing"):
        asyncio.run(repo.record_responses_clarification(
            run_id="run-7", user_id=8, original_message="Beoordeel mijn plan",
            question="Welke setup bedoel je?", reason="choice_required",
        ))
    result = asyncio.run(repo.record_responses_clarification(
        run_id="run-7", user_id=7, original_message="Beoordeel mijn plan",
        question="Welke setup bedoel je?", reason="choice_required",
    ))
    assert result.state_json["responses_clarification"] == {
        "original_message": "Beoordeel mijn plan",
        "question": "Welke setup bedoel je?",
        "reason": "choice_required",
        "conversation_id": "conv-7",
        "run_id": "run-7",
    }


def test_responses_cursor_rejects_stale_conversation_turn():
    row = SimpleNamespace(last_run_id="new-run", context_json={})
    repo = object.__new__(FinnV2ConversationRepository)
    repo.get_by_id_for_user = AsyncMock(return_value=row)
    repo._flush_with_rollback = AsyncMock()
    with pytest.raises(RuntimeContractConflictError, match="stale_or_unowned"):
        asyncio.run(repo.set_responses_cursor(
            conversation_id="conv-1", user_id=7, run_id="old-run", response_id="resp-old",
        ))
    asyncio.run(repo.set_responses_cursor(
        conversation_id="conv-1", user_id=7, run_id="new-run", response_id="resp-new",
    ))
    assert row.context_json["responses_cursor"] == {"run_id": "new-run", "response_id": "resp-new"}
    asyncio.run(repo.set_responses_cursor(
        conversation_id="conv-1", user_id=7, run_id="new-run", response_id="resp-next",
        locale="en",
    ))
    assert row.context_json["responses_cursor"] == {
        "run_id": "new-run", "response_id": "resp-next", "locale": "en",
    }


def test_read_answer_requires_independent_evidence_verification():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=False, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "De koers is zeker gestegen.", "resp-1", ({
            "status": "completed", "result": {"results": [{
                "scope": "read_market_snapshot", "status": "unavailable", "source": "provider",
                "asset": "AAPL", "as_of": None, "freshness": "unknown", "availability": "unavailable",
                "data": None, "reason": "market_snapshot_missing",
            }]},
        },),
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat doet AAPL nu?", result=result,
    ))
    assert answer.status == "unavailable"
    assert "gestegen" not in answer.text
    assert answer.evidence[0]["asset"] == "AAPL"
    semantic.verify_async.return_value = SimpleNamespace(available=True, passes=True, reason_codes=[])
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat doet AAPL nu?", result=result,
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["compact_evidence"][0]["reason"] == "market_snapshot_missing"


def test_partial_evaluation_survives_semantic_timeout_only_with_independent_audit():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=False, passes=False, reason_codes=["timeout"],
    )))
    verifier = FinnResponsesAnswerVerifier(
        semantic, client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock())),
    )
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "Je DCA-setup staat klaar, maar zonder actuele marktgegevens kan ik niet beoordelen "
        "of die bij je risicoprofiel past. Wil je eerst de marktgegevens controleren?",
        "resp-partial", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["read_market_snapshot"],
                "results": [
                    {"scope": "read_profile", "status": "completed", "data": {"has_profile": True}},
                    {"scope": "read_active_setup", "status": "completed",
                     "data": {"name": "DCA Basis", "setup_type": "dca"}},
                    {"scope": "read_market_snapshot", "status": "unavailable",
                     "reason": "source_unavailable"},
                ],
            },
        },),
    )
    answer = asyncio.run(verifier.verify(message="Past mijn plan bij mijn profiel?", result=result))
    assert answer.status == "completed"
    verifier._personal_advice_is_grounded.return_value = False
    rejected = asyncio.run(verifier.verify(message="Past mijn plan bij mijn profiel?", result=result))
    assert rejected.status == "completed"
    assert rejected.reason == "insufficient_evidence"
    assert "niet beoordelen" in rejected.text
    assert "niets gewijzigd" in rejected.text


def test_model_led_answer_uses_semantic_boundary_without_optional_advice_audit():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(
        semantic, client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock())),
    )

    async def unavailable_audit(**kwargs):
        kwargs["audit_diagnostics"]["audit_unavailable"] = "TimeoutError"
        return False

    verifier._personal_advice_is_grounded = AsyncMock(side_effect=unavailable_audit)
    answer_text = (
        "I cannot assess your saved plan yet because current market data are unavailable. "
        "Which setup would you like to review?"
    )
    result = FinnResponsesResult(
        answer_text, "resp-safe-partial", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["market_snapshot"],
                "results": [
                    {"scope": "read_active_setup", "status": "completed",
                     "data": {"name": "Saved Plan", "setup_type": "trade"}},
                    {"scope": "read_market_snapshot", "status": "unavailable",
                     "reason": "source_unavailable"},
                ],
            },
        },), model_led_coach=True,
    )
    verified = asyncio.run(verifier.verify(
        message="Can you assess my saved plan?", result=result, locale="en",
    ))
    assert verified.status == "completed"
    assert verified.text == answer_text
    semantic.verify_async.assert_awaited()
    verifier._personal_advice_is_grounded.assert_not_awaited()

    semantic.verify_async.return_value = SimpleNamespace(
        available=True, passes=False, reason_codes=["unverified_personal_claim"],
    )
    rejected = asyncio.run(verifier.verify(
        message="Can you assess my saved plan?", result=result, locale="en",
    ))
    assert rejected.text != answer_text
    verifier._personal_advice_is_grounded.assert_not_awaited()


def test_limited_plan_review_uses_saved_strategy_facts_even_if_model_verifier_accepts():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=None)
    result = FinnResponsesResult(
        "Sterk in je plan: de setup heeft entry en targets. Waar ik je afrem: geen marktdata. "
        "Controleer eerst de actuele gegevens. 4H betekent langetermijnopbouw.",
        "resp-review", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["read_market_snapshot"],
                "results": [
                    {"scope": "read_linked_strategy", "status": "completed", "data": {
                        "name": "BTC Plan", "entry": "80000", "stop_loss": "76000",
                        "targets": [{"target": "88000"}],
                    }},
                    {"scope": "read_market_snapshot", "status": "unavailable",
                     "reason": "source_unavailable"},
                ],
            },
        },), response_focus="review",
    )
    for passes in (True, False):
        semantic.verify_async.return_value.passes = passes
        answer = asyncio.run(verifier.verify(
            message="Wat is sterk, waar rem je me af en wat controleer ik eerst?", result=result,
        ))
        assert answer.status == "completed"
        assert answer.reason == "insufficient_evidence"
        assert "opgeslagen strategie" in answer.text
        assert "Controleer eerst" in answer.text
        assert "setup heeft entry" not in answer.text
        assert "4H beschrijft" not in answer.text
        assert "sterk als vastgelegd controlepunt" in answer.text.casefold()


def test_limited_evaluation_cannot_claim_completion_after_requested_form_fails():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=False, passes=False, reason_codes=["timeout"],
    )))
    verifier = FinnResponsesAnswerVerifier(
        semantic, client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock())),
    )

    async def reject_structure(**kwargs):
        kwargs["audit_diagnostics"]["rejected_checks"] = ["requested_structure_missing"]
        return False

    verifier._personal_advice_is_grounded = AsyncMock(side_effect=reject_structure)
    result = FinnResponsesResult("Actuele marktdata ontbreken.", "resp-partial", ({
        "name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_profile", "status": "completed", "data": {"has_profile": False}},
                {"scope": "read_active_setup", "status": "completed", "data": {"name": "BTC Plan"}},
            ],
        },
    },))
    answer = asyncio.run(verifier.verify(
        message="Noem drie prioriteiten voor mijn plan.", result=result,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "responses_requested_structure_unverified"


def test_second_followup_audits_prior_evaluation_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(
        semantic, client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
            return_value=SimpleNamespace(output_text=""),
        ))),
    )
    verifier._personal_advice_is_grounded = AsyncMock(return_value=False)
    prior_trace = ({
        "name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_profile", "status": "completed", "data": {"has_profile": True}},
                {"scope": "read_active_setup", "status": "completed",
                 "data": {"name": "DCA Basis", "setup_type": "dca"}},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable"},
            ],
        },
    },)
    answer = asyncio.run(verifier.verify(
        message="Welke keuze moet ik nu eerst maken?",
        result=FinnResponsesResult(
            "Ik kan niet beoordelen welke keuze het beste is.", "resp-followup", ({
                "name": "answer_directly", "status": "completed",
                "arguments": {"uses_previous_response": True}, "result": {"results": []},
            },),
        ),
        previous_response={"answer": "Zonder actuele marktdata blijft de geschiktheid onbekend.",
                           "tool_trace": prior_trace},
    ))
    verifier._personal_advice_is_grounded.assert_awaited()
    assert answer.status == "unavailable"


def test_partial_evaluation_rejects_hedged_positive_fit():
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Aangezien je voorzichtig bent, kan deze wijziging acceptabel zijn."
    )
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "This change might be suitable for your risk profile."
    )
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Deze wijziging lijkt goed te passen bij jouw voorzichtige risicostijl."
    )
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Dit is een solide aanpak voor een conservatieve risicostijl."
    )
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Met die horizon past dit goed bij je doel."
    )
    assert not FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Ik kan niet beoordelen of deze wijziging voor jou acceptabel is."
    )


def test_general_education_is_verified_without_personal_read_scope():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat betekent RSI in algemene zin?",
        result=FinnResponsesResult("RSI is een technische indicator.", "resp-1", ({
            "name": "answer_directly", "status": "completed", "result": {"results": []},
        },)),
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["mode"] == "EXPLAIN"
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"]["general_education_no_personal_claims"]


def test_confirmed_action_result_is_grounding_for_saved_object_readback():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Welke setup heb ik net opgeslagen?",
        result=FinnResponsesResult("Je hebt Build Smoke BTC opgeslagen.", "resp-1", ({
            "name": "get_decision_history", "status": "partial",
            "result": {"results": [{"scope": "read_latest_report", "status": "unavailable"}]},
        },)),
        recent_action_result={
            "owner_user_id": 7, "result_status": "succeeded", "operation_id": "create_setup",
            "entity_type": "setup", "canonical_name": "Build Smoke BTC", "entity_id": 42,
        },
    ))
    assert answer.status == "completed"
    evidence = semantic.verify_async.await_args.kwargs["compact_evidence"]
    confirmed = next(item for item in evidence if item["scope"] == "confirmed_action_result")
    assert confirmed["data"]["canonical_name"] == "Build Smoke BTC"
    assert "entity_id" not in confirmed["data"]
    assert "confirmed_action_result" in semantic.verify_async.await_args.kwargs["deterministic_summary"]["available_scopes"]


def test_rejected_read_is_rewritten_once_via_responses_and_reverified():
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=[
        SimpleNamespace(available=True, passes=False, reason_codes=["unsupported_market_claim"]),
        SimpleNamespace(available=True, passes=True, reason_codes=[]),
    ]))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="Ik heb geen actuele AAPL-koers om dit te beoordelen."),
    )))
    result = FinnResponsesResult("AAPL stijgt zeker.", "resp-1", ({
        "status": "partial", "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "asset": "AAPL",
            "source": "provider", "as_of": None, "reason": "market_snapshot_missing",
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Wat doet AAPL?", result=result,
    ))
    assert answer.status == "completed"
    assert answer.text == "Ik heb geen actuele AAPL-koers om dit te beoordelen."
    assert semantic.verify_async.await_count == 2
    assert client.responses.create.await_args.kwargs["tool_choice"] == "none"


def test_rewrite_cannot_override_second_verifier_rejection():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_market_claim"],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="AAPL stijgt zeker."),
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Wat doet AAPL?", result=FinnResponsesResult("AAPL stijgt.", "resp-1", ()),
    ))
    assert answer.status == "unavailable"
    assert semantic.verify_async.await_count == 2


def test_unsupported_asset_quantity_is_rewritten_without_repeating_rejected_draft():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="De strategie heeft een basisbedrag van 100, zonder opgegeven valuta."),
    )))
    result = FinnResponsesResult("Zet 100 BTC in.", "resp-1", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_linked_strategy", "status": "completed", "asset": "BTC",
            "data": {"base_amount": 100},
        }]},
    },))
    verifier = FinnResponsesAnswerVerifier(semantic, client)
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    answer = asyncio.run(verifier.verify(
        message="Waarom past dit plan?", result=result,
    ))
    assert answer.status == "completed"
    assert "100 BTC" not in answer.text
    assert "rejected_draft" not in client.responses.create.await_args.kwargs["input"]


def test_previous_unavailable_source_cannot_be_explained_with_invented_outage():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_cause"],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text='{"unsupported_cause": true}'),
    )))
    previous = {
        "run_id": "prior-run", "answer": "Ik heb geen actuele koers.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Waarom?",
            result=FinnResponsesResult("Door een technische storing.", "resp-2", (), uses_previous_response=True),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "storing" not in answer.text


def test_rejected_follow_up_uses_persisted_previous_evidence_limitation():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_cause"],
    )))
    previous = {
        "run_id": "prior-run", "answer": "Actuele koersen ontbreken.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?", result=FinnResponsesResult("Door een storing.", "resp-2", (), uses_previous_response=True),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "oorzaak" in answer.text


def test_clarification_followup_ignores_unrelated_prior_market_outage():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "run_id": "prior-run",
        "terminal_status": "clarification_required",
        "terminal_reason": "setup_ambiguous",
        "answer": "Ik zie meerdere setups. Welke wil je gebruiken?",
        "tool_trace": [{"result": {"results": [
            {"scope": "read_active_setup", "status": "unavailable", "reason": "setup_ambiguous"},
            {"scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable"},
        ]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?",
        result=FinnResponsesResult(
            "Omdat je meerdere setups hebt en ik niet zomaar een van die setups mag kiezen.",
            "resp-2", (), uses_previous_response=True,
        ),
        previous_response=previous,
    ))
    assert answer.status == "completed"
    assert answer.used_previous_response
    evidence = semantic.verify_async.await_args.kwargs["compact_evidence"]
    assert any(item["scope"] == "previous_response" for item in evidence)
    assert not any(item.get("reason") == "source_unavailable" for item in evidence)
    guidance = semantic.verify_async.await_args.kwargs["verification_guidance"]
    assert "not for the original financial assessment" in guidance
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"][
        "previous_clarification_reason"
    ] == "setup_ambiguous"


def test_rejected_followup_does_not_mislabel_scope_failure_as_unknown_cause():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["response_scope_incomplete"],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Welke keuze moet ik nu eerst maken?",
        result=FinnResponsesResult("Ik weet het niet.", "resp-2", ()),
        previous_response={
            "answer": "Actuele marktdata ontbreken.",
            "tool_trace": [{"result": {"results": [{
                "scope": "read_market_snapshot", "status": "unavailable",
                "reason": "source_unavailable",
            }]}}],
        },
    ))
    assert answer.status == "unavailable"
    assert "oorzaak" not in answer.text


def test_unrelated_previous_market_failure_does_not_override_setup_ambiguity():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    previous = {
        "answer": "Ik heb geen actuele AAPL-koers.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    current = FinnResponsesResult("Ik kan je setup beoordelen.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "partial",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "unavailable",
            "reason": "setup_ambiguous", "asset": "BTC",
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Tell me about my BTC setup", result=current, previous_response=previous,
    ))
    assert answer.status == "clarification_required"
    assert answer.reason == "setup_ambiguous"
    assert answer.text.startswith("I found several setups")


def test_resolved_setup_replaces_prior_ambiguous_evidence_in_follow_up():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_claim"],
    )))
    previous = {
        "answer": "Welke BTC-setup bedoel je?",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "unavailable", "reason": "setup_ambiguous",
        }]}}],
    }
    current = FinnResponsesResult("Matrix Strategy Parent is je DCA-setup.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "partial",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed", "reason": None,
            "data": {"name": "Matrix Strategy Parent"},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Matrix Strategy Parent", result=current, previous_response=previous,
    ))
    assert answer.reason != "setup_ambiguous"
    previous_evidence = semantic.verify_async.await_args.kwargs["compact_evidence"][-1]
    assert previous_evidence["data"]["source_evidence"] == []


def test_follow_up_keeps_prior_completed_setup_when_current_read_is_profile():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "answer": "Matrix Update Strategie gebruikt setup Matrix Strategy Update Parent.",
        "tool_trace": [{"result": {"results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"name": "Matrix Strategy Update Parent"}},
            {"scope": "read_linked_strategy", "status": "completed",
             "data": {"name": "Matrix Update Strategie"}},
            {"scope": "read_market_snapshot", "status": "unavailable",
             "reason": "source_unavailable"},
        ]}}],
    }
    current = FinnResponsesResult("Je risicoprofiel ontbreekt nog.", "resp-2", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed",
            "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?", result=current, previous_response=previous,
    ))
    assert answer.status == "completed"
    previous_evidence = semantic.verify_async.await_args.kwargs["compact_evidence"][-1]
    assert {item["scope"] for item in previous_evidence["data"]["source_evidence"]} == {
        "read_active_setup", "read_linked_strategy",
    }


def test_absent_profile_is_verifiable_limitation_not_missing_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("Je risicoprofiel ontbreekt nog; wat past bij jou?", "resp-1", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed",
            "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Gebaseerd op mijn profiel, waar kan je mij mee helpen?", result=result,
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["mode"] == "UNAVAILABLE"
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"]["missing_profile_established"]


def test_prior_completed_profile_is_flattened_for_setup_followup_verification():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "answer": "Welke setup bedoel je?",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_profile", "status": "completed", "source": "users.ai_preferences",
            "data": {"has_profile": True, "trader_profile": {
                "risk_profiles": ["balanced"], "investment_goals": ["wealth_building"],
            }},
        }]}}],
    }
    current = FinnResponsesResult("Je profiel is balanced; de setup is BTC 4H.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed", "source": "setups",
            "data": {"name": "BTC Plan", "symbol": "BTC", "timeframe": "4H"},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="BTC Plan", result=current, previous_response=previous,
    ))
    assert answer.status == "completed"
    compact = semantic.verify_async.await_args.kwargs["compact_evidence"]
    assert any(item.get("scope") == "read_profile" and item.get("lineage") == "previous_verified_run"
               for item in compact)


def test_new_direct_topic_does_not_inherit_previous_unavailable_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("RSI vergelijkt koersbewegingen.", "resp-2", ({
        "name": "answer_directly", "arguments": {"uses_previous_response": False},
        "status": "completed", "result": {"results": []},
    },))
    previous = {
        "answer": "De actuele marktdata ontbreekt.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat betekent RSI in algemene zin?", result=result, previous_response=previous,
    ))
    assert answer.status == "completed"
    assert answer.used_previous_response is False
    assert all(
        item.get("scope") != "previous_response"
        for item in semantic.verify_async.await_args.kwargs["compact_evidence"]
    )


def test_saved_amount_does_not_ground_asset_quantity():
    evidence = ({
        "scope": "read_linked_strategy", "status": "completed", "asset": "BTC",
        "data": {"base_amount": 100, "entry": "100"},
    },)
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._asset_quantities_supported(
        answer="Zet 100 BTC in.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert verifier._asset_quantities_supported(
        answer="Je basisbedrag is 100.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert not verifier._currency_units_supported(
        answer="Je inzet is $100.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert verifier._currency_units_supported(
        answer="Je inzet is €100.", message="Wat is mijn plan?",
        evidence=({**evidence[0], "data": {"base_amount": 100, "currency": "EUR"}},),
    )


def test_verified_previous_answer_grounds_currency_in_short_followup():
    verifier = FinnResponsesAnswerVerifier()
    assert verifier._currency_units_supported(
        answer="Compare your proposed €100 per week with your limit.",
        message="What should I decide first?",
        previous_answer="You are considering 100 euros per week.",
        evidence=(),
    )
    assert verifier._currency_units_supported(
        answer="€100 per week is nog niet op geschiktheid beoordeeld.",
        message="Waarom?",
        previous_answer="Je overweegt €100 per week; de geschiktheid is nog niet beoordeeld.",
        evidence=(),
    )
    assert not verifier._currency_units_supported(
        answer="$100 per week is geschikt.",
        message="Waarom?",
        previous_answer="Je overweegt €100 per week; de geschiktheid is nog niet beoordeeld.",
        evidence=(),
    )


def test_short_why_must_advance_beyond_verified_previous_answer():
    previous = "Je DCA-setup is dagelijks. Zonder risico-evaluatie is geschiktheid onbekend."
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._followup_advances_conversation("Waarom?", previous, previous)
    assert verifier._followup_advances_conversation(
        "Waarom?", previous,
        "Omdat de opgeslagen frequentie niets zegt over de actuele markt of je verliesruimte.",
    )
    assert verifier._followup_advances_conversation("Wat nu?", previous, previous)


def test_previous_clarification_is_presented_as_choice_not_missing_profile():
    fake = FakeResponses(response("r-choice", text="Omdat ik niet willekeurig een setup kies."))

    async def execute(_call):
        raise AssertionError("previous verified clarification needs no tool")

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Waarom?", instructions="Antwoord in het Nederlands.",
        previous_verified_answer="Ik zie meerdere setups. Welke wil je gebruiken?",
        previous_terminal_status="clarification_required",
        previous_terminal_reason="setup_ambiguous", previous_answer_only=True,
        previous_tool_availability=({"scope": "read_active_setup", "status": "unavailable",
                                     "reason": "setup_ambiguous"},),
    ))
    context = fake.requests[0]["input"][0]["content"]
    assert "setup_ambiguous" in context
    assert "do not infer missing profile" in context
    assert fake.requests[0]["tool_choice"] == "none"


def test_responses_loop_accepts_direct_answer_without_tools():
    fake = FakeResponses(response("r1", text="Ik kan je plan uitleggen."))

    async def execute(_call):
        raise AssertionError("no tool requested")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Hallo", instructions="Antwoord helder"
    ))
    assert result.tool_trace == ()
    assert result.text == "Ik kan je plan uitleggen."
    assert fake.requests[0]["tool_choice"] == "auto"
    assert "answer_directly" not in {tool["name"] for tool in fake.requests[0]["tools"]}


def test_incomplete_responses_output_has_one_bounded_retry_before_any_tool_runs():
    incomplete = SimpleNamespace(
        id="incomplete-1", status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"), output=[], output_text="",
    )
    fake = FakeResponses(incomplete, response("r2", text="DCA spreidt aankopen over tijd."))

    async def execute(_call):
        raise AssertionError("an incomplete response must never execute a tool")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Wat is DCA?", instructions="Antwoord helder",
    ))
    assert result.text == "DCA spreidt aankopen over tijd."
    assert [request["max_output_tokens"] for request in fake.requests] == [700, 1400]
    assert result.tool_trace == ()


def test_incomplete_responses_non_token_failure_is_not_retried():
    incomplete = SimpleNamespace(
        id="incomplete-1", status="incomplete",
        incomplete_details=SimpleNamespace(reason="content_filter"), output=[], output_text="",
    )
    fake = FakeResponses(incomplete)

    async def execute(_call):
        raise AssertionError("no tool should run")

    with pytest.raises(FinnResponsesError, match="responses_incomplete"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Wat is DCA?", instructions="Antwoord helder",
        ))
    assert len(fake.requests) == 1


def test_unverified_direct_answer_repair_can_only_call_read_tools():
    fake = FakeResponses(
        response("repair-1", calls=(tool_call("read-1", "get_active_asset_context", {}),)),
        response("repair-2", text="Ik kan de huidige koers niet bevestigen."),
    )
    calls = []

    async def execute(call):
        calls.append(call)
        return {"status": "unavailable", "reason": "source_unavailable", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Wat is nu de BTC-koers?", instructions="Gebruik geverifieerde gegevens.",
        force_read_repair=True,
    ))
    assert fake.requests[0]["tool_choice"] == "required"
    assert fake.requests[0].get("previous_response_id") is None
    assert all(tool["name"].startswith(("get_", "evaluate_")) for tool in fake.requests[0]["tools"])
    assert len(calls) == 1
    assert [item["name"] for item in result.tool_trace] == ["get_active_asset_context"]
    assert result.text == "Ik kan de huidige koers niet bevestigen."


def test_rejected_claim_feedback_returns_to_model_without_action_tools():
    fake = FakeResponses(response(
        "repair-safe", text="Je profiel is voorzichtig; of €100 per week past, kan ik nog niet beoordelen.",
    ))

    async def execute(_call):
        raise AssertionError("No tool is required for an honest limitation")

    feedback = {
        "status": "answer_rejected", "reason": "personal_fit_not_established",
        "evidence": [{"scope": "read_profile", "status": "completed", "source": "owner_profile"}],
    }
    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Past €100 per week bij mij?", instructions="Gebruik geverifieerde gegevens.",
        previous_response_id="rejected-response", rejection_feedback=feedback,
    ))
    request = fake.requests[0]
    assert request["previous_response_id"] == "rejected-response"
    assert request["tool_choice"] == "auto"
    assert all(
        tool["name"].startswith(("get_", "evaluate_"))
        for tool in request["tools"]
    )
    assert any(
        item["role"] == "developer" and "personal_fit_not_established" in item["content"]
        for item in request["input"]
    )
    assert len(fake.requests) == 1
    assert result.tool_trace == ()


@pytest.mark.parametrize("reason", [
    "personal_fit_not_established", "saved_entity_type_unverified",
    "trading_outcome_claim_unverified", "user_condition_bypass_blocked",
])
def test_hard_boundary_feedback_requires_honest_answer_without_more_tools(reason):
    fake = FakeResponses(response(
        "repair-limit", text="Of €100 per week bij je past kan ik met de beschikbare gegevens niet vaststellen.",
    ))

    async def execute(_call):
        raise AssertionError("The assessment already identified missing evidence")

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Past €100 per week bij mij?", instructions="Gebruik geverifieerde gegevens.",
        previous_response_id="rejected-assessment",
        rejection_feedback={
            "status": "answer_rejected", "reason": reason,
            "repair_mode": "explain_limit",
        },
    ))
    assert fake.requests[0]["previous_response_id"] == "rejected-assessment"
    assert fake.requests[0]["tool_choice"] == "none"
    assert fake.requests[0]["tools"] == []
    assert result.text.startswith("Of €100")


def test_read_only_repair_accepts_evaluation_but_never_proposal_trace():
    assert FinnV2RunService._read_only_repair_eligible(())
    assert FinnV2RunService._read_only_repair_eligible((
        {"name": "get_my_profile_and_risk_style"},
        {"name": "evaluate_plan", "status": "partial"},
    ))
    assert not FinnV2RunService._read_only_repair_eligible((
        {"name": "evaluate_plan"}, {"name": "propose_strategy"},
    ))


def test_previous_verified_answer_is_an_assistant_turn_not_user_instructions():
    fake = FakeResponses(response("r1", text="Omdat de huidige beoordeling ontbreekt."))

    async def execute(_call):
        raise AssertionError("no tool needed")

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Waarom?", instructions="Explain the verified answer.",
        previous_verified_answer="Je strategie is opgeslagen, maar nog niet beoordeeld.",
    ))
    assert fake.requests[0]["input"] == [
        {"role": "assistant", "content": "Je strategie is opgeslagen, maar nog niet beoordeeld."},
        {"role": "user", "content": "Waarom?"},
    ]


def test_unavailable_coach_turn_is_not_presented_as_a_verified_prior_answer():
    fake = FakeResponses(response("r1", text="Een ruimere stop vergt een kleinere positie."))

    async def execute(_call):
        raise AssertionError("no tool needed")

    previous = project_verified_turn({
        "answer": "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
        "user_message": "Zou een kleinere positie met meer ruimte voor de stop verstandig zijn?",
        "terminal_status": "unavailable",
        "terminal_reason": "responses_evidence_not_verified",
    })
    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Hoe houd ik hetzelfde maximale euroverlies?",
        instructions="Answer the latest question.",
        verified_turn_context=previous,
        previous_terminal_status="unavailable",
        model_led_coach=True,
    ))
    context = fake.requests[0]["input"][0]["content"]
    assert "user saw only this fallback" in context
    assert "none was shown" in context
    assert "Immediately preceding verified FINN answer" not in context
    assert "before a condition that user said must be met" not in context


@pytest.mark.parametrize(("message", "draft"), [
    (
        "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. "
        "Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?",
        "Een stop-loss uit frustratie weghalen vergroot het mogelijke verlies. "
        "Onderzoek eerst of de stop bij je handelsidee past; ik wijzig niets.",
    ),
    (
        "Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor de stop "
        "niet verstandiger kunnen zijn? Denk kritisch mee zonder een nieuw niveau te verzinnen.",
        "Een ruimere stop en een kleinere positie kunnen hetzelfde maximale verlies begrenzen. "
        "De stop hoort bij het handelsidee; bepaal vooraf hoeveel verlies je accepteert.",
    ),
])
def test_source_independent_coaching_does_not_need_second_opinion(message, draft):
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("no second judge")))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=message,
        result=FinnResponsesResult(
            draft, "coach-response", (), model_led_coach=True, model_owned_repair=True,
            answer_kind="free_text", turn_contract={
                "answer_type": "weigh", "targets": [], "saved_subject_reference": False,
            },
        ),
        locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == draft
    assert verified.reason == "source_independent_coaching"
    semantic.verify_async.assert_not_awaited()


def test_general_coaching_after_unavailable_read_keeps_model_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=AssertionError("no second judge")))
    draft = (
        "Een ruimere stop vergroot je verlies per eenheid. "
        "Een kleinere positie kan dat begrenzen, zolang je vooraf dezelfde verliesgrens kiest."
    )
    previous = {
        "answer": "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
        "user_message": "Ik wil mijn stop-loss weghalen.",
        "terminal_status": "unavailable",
        "tool_trace": [{"name": "get_my_profile_and_risk_style", "result": {"results": [{
            "scope": "read_profile", "status": "completed", "source": "owner_profile",
            "data": {"has_profile": True},
        }]}}],
    }
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Zou een kleinere positie met een ruimere stop verstandiger kunnen zijn?",
        result=FinnResponsesResult(
            draft, "coach-followup", (), model_led_coach=True,
            model_owned_repair=True, uses_previous_response=True,
            answer_kind="free_text", turn_contract={
                "answer_type": "weigh", "targets": [], "saved_subject_reference": False,
            },
        ), previous_response=previous, locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == draft
    semantic.verify_async.assert_not_awaited()


def test_general_coaching_with_current_profile_read_keeps_source_review():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    draft = "Een stop-loss impulsief weghalen kan je verlies vergroten. Onderzoek eerst de reden voor je uitstapgrens."
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Wat vind je van het weghalen van mijn stop-loss? Geef coaching, verander niets.",
        result=FinnResponsesResult(
            draft, "coach-with-read", ({
                "name": "get_my_profile_and_risk_style", "result": {"results": [{
                    "scope": "read_profile", "status": "completed", "source": "owner_profile",
                    "data": {"has_profile": True},
                }]},
            },), model_led_coach=True, model_owned_repair=True,
            answer_kind="free_text", turn_contract={
                "answer_type": "weigh", "targets": [], "saved_subject_reference": False,
            },
        ), locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.text == draft
    semantic.verify_async.assert_awaited()


@pytest.mark.parametrize("draft", [
    "In jouw opgeslagen strategie staat een stop-loss op 72.000.",
    "BTC stijgt vandaag, dus die stop is nu te krap.",
    "BTC stijgt sterk, dus je kunt instappen.",
])
def test_source_dependent_coaching_still_requires_source_review(draft):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_saved_fact"],
    )))
    asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Hoe kijk je naar mijn stop-loss?",
        result=FinnResponsesResult(
            draft,
            "coach-response", (), model_led_coach=True, answer_kind="free_text",
        ), locale="nl",
    ))
    semantic.verify_async.assert_awaited()


def test_source_independent_coaching_cannot_claim_a_write():
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Hoe kijk je naar mijn stop-loss?",
        result=FinnResponsesResult(
            "Ik heb je stop-loss gewijzigd.", "coach-response", (),
            model_led_coach=True, answer_kind="free_text",
        ), locale="nl",
    ))
    assert answer.status != "completed"
    assert answer.reason != "source_independent_coaching"


def test_invalid_read_arguments_get_one_schema_bound_repair_call():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "symbol": "BTC", "timeframe": "4H",
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {
            "asset": "BTC", "timeframe": "4H",
        }),)),
        response("r3", text="Je opgeslagen BTC-plan gebruikt 4H."),
    )

    async def execute(call):
        assert call.inputs == {"asset": "BTC", "timeframe": "4H"}
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "timeframe": "4H"},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat is mijn BTC-plan?", instructions="Gebruik FINN-tools"))
    assert result.tool_trace[0]["result"]["reason"] == "read_arguments_invalid"
    assert "declared argument names" in result.tool_trace[0]["result"]["instruction"]
    assert result.tool_trace[1]["status"] == "completed"
    assert fake.requests[1]["tool_choice"] == {
        "type": "function", "name": "get_active_plan_and_strategy",
    }


def test_repeated_invalid_read_cannot_consume_lifecycle_in_repair_loop():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_indicator_snapshot", {
            "asset": "BTC", "category": "technical",
        }),)),
        response("r2", calls=(tool_call("c2", "get_indicator_snapshot", {
            "asset": "BTC", "category": "RSI",
        }),)),
        response("r3", text="Ik heb geen geverifieerde actuele indicatorwaarden."),
    )

    async def execute(_call):
        raise AssertionError("invalid arguments must not reach execution")

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat zeggen RSI en MA200 nu?", instructions="Gebruik FINN-tools"))
    assert len(result.tool_trace) == 2
    assert all(item["result"]["reason"] == "read_arguments_invalid"
               for item in result.tool_trace)
    assert fake.requests[2]["tool_choice"] == "none"


def test_ambiguous_setup_read_terminalizes_without_second_provider_round():
    fake = FakeResponses(response("r1", calls=(
        tool_call("c1", "get_active_plan_and_strategy", {}),
    )))

    async def execute(_call):
        return {"status": "partial", "results": [{
            "scope": "read_active_setup", "status": "unavailable",
            "reason": "setup_ambiguous",
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Welk plan past bij mij?", instructions="Gebruik FINN-feiten"))
    assert len(fake.requests) == 1
    assert result.tool_trace[0]["result"]["results"][0]["reason"] == "setup_ambiguous"
    assert result.text == "A setup choice is required."
    assert result.response_id_reusable is False


def test_model_led_ambiguous_setup_read_reaches_coach_for_partial_answer():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", text="Ik kan de koersvraag beantwoorden, maar welke setup bedoel je?"),
    )

    async def execute(_call):
        return {"status": "partial", "results": [{
            "scope": "read_active_setup", "status": "unavailable",
            "reason": "setup_ambiguous",
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat is de koers en wat betekent dit voor mijn setup?",
          instructions="Gebruik FINN-feiten", model_led_coach=True))
    assert len(fake.requests) == 2
    assert result.text.startswith("Ik kan de koersvraag")
    assert result.tool_trace[0]["result"]["results"][0]["reason"] == "setup_ambiguous"


def test_model_led_ambiguous_setup_does_not_replace_grounded_partial_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Een koerssnapshot is niet beschikbaar. Welke setup bedoel je voor de planbeoordeling?",
        "resp-partial", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "unavailable",
                                   "reason": "setup_ambiguous"}]},
        },), model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat is de koers en wat betekent dit voor mijn setup?", result=result,
    ))
    assert verified.status == "completed"
    assert verified.text == result.text
    assert semantic.verify_async.await_count == 1
    assert "do not claim a number of matches" in (
        semantic.verify_async.await_args.kwargs["verification_guidance"]
    )


def test_model_led_rejected_ambiguous_setup_asks_for_the_saved_target():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    result = FinnResponsesResult(
        "Ik kan je setup beoordelen.", "resp-ambiguous", ({
            "name": "evaluate_setup", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "unavailable",
                                   "reason": "setup_ambiguous"}]},
        },), model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Beoordeel mijn actieve setup.", result=result, locale="nl",
    ))
    assert verified.status == "clarification_required"
    assert verified.reason == "setup_ambiguous"
    assert verified.clarification["question"] == verified.text


def test_model_led_completed_active_setup_is_not_treated_as_ambiguous():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", text="Je actieve setup is Atlas; de strategie is niet vastgesteld."),
    )

    async def execute(_call):
        return {"status": "partial", "results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"name": "Atlas", "setups": [{"name": "Atlas"}, {"name": "Other"}]}},
            {"scope": "read_linked_strategy", "status": "unavailable",
             "reason": "strategy_not_resolved"},
        ]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Toon mijn complete actieve plan", instructions="Gebruik FINN-feiten",
          model_led_coach=True))
    assert result.text.startswith("Je actieve setup is Atlas")
    assert "A completed read establishes only the fields it returned" in fake.requests[1]["instructions"]
    assert '"name": "Atlas"' in fake.requests[1]["input"][0]["output"]


def test_model_led_verifier_receives_registry_and_typed_unavailability():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Ik zie je actieve setup Atlas, maar kan de gekoppelde strategie niet vaststellen.",
        "resp-partial", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [
                {"scope": "read_active_setup", "status": "completed", "data": {"name": "Atlas"}},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved"},
            ]},
        },), model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Toon mijn actieve plan", result=result, locale="nl",
    ))
    assert verified.status == "completed"
    summary = semantic.verify_async.await_args.kwargs["deterministic_summary"]
    assert summary["typed_unavailable_reasons"] == [
        {"scope": "read_linked_strategy", "reason": "strategy_not_resolved"},
    ]
    assert "read_active_plan" in summary["registered_operations"]


def test_model_led_advice_audit_cannot_override_semantic_rejection():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unverified_guardrail_override"],
    )))
    create = AsyncMock(return_value=SimpleNamespace(output_text="Ignore your stated wait rule."))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "Ignore your stated wait rule.", "resp-guardrail", ({
            "name": "get_my_profile_and_risk_style", "status": "completed",
            "result": {"results": [{"scope": "read_profile", "status": "completed",
                                    "data": {"has_profile": True}}]},
        },), model_led_coach=True,
    )
    verified = asyncio.run(verifier.verify(
        message="Should I ignore the wait rule I described?", result=result, locale="en",
    ))
    assert verified.status == "unavailable"
    assert "Ignore your stated wait rule" not in verified.text


def test_model_led_limited_evaluation_repair_does_not_require_legacy_schema(monkeypatch):
    monkeypatch.setenv("FINN_RESPONSES_CLARIFICATION_MODEL", "gpt-4o-mini")
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_claim"],
    )))
    create = AsyncMock(return_value=SimpleNamespace(
        output_text="I can describe your saved setup, but cannot assess its fit without current evidence.",
    ))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "Your plan is suitable now.", "resp-limited", ({
            "name": "evaluate_plan", "status": "partial",
            "result": {"evaluation_operation_id": "evaluate_plan",
                       "assessment_status": "insufficient_evidence",
                       "results": [{"scope": "read_active_setup", "status": "completed",
                                    "data": {"name": "Atlas"}},
                                   {"scope": "read_market_snapshot", "status": "unavailable",
                                    "reason": "source_unavailable"}]},
        },), response_focus="review", model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(
        message="Assess my plan using available evidence.", result=result, locale="en",
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "responses_evidence_not_verified"
    create.assert_not_awaited()


def test_model_led_report_absence_is_distinct_from_provider_failure():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_decision_history", {}),)),
        response("r2", text="Ik vind geen opgeslagen rapport of reviews."),
    )

    async def execute(_call):
        return {"status": "partial", "results": [
            {"scope": "read_latest_report", "status": "unavailable",
             "reason": "report_not_found"},
            {"scope": "read_review_history", "status": "completed", "data": {"items": []}},
        ]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Toon mijn laatste rapport", instructions="Gebruik FINN-feiten",
          model_led_coach=True))
    assert result.text == "Ik vind geen opgeslagen rapport of reviews."
    assert "never invent a cause or a match" in fake.requests[1]["instructions"]
    assert '"reason": "report_not_found"' in fake.requests[1]["input"][0]["output"]


def test_direct_answer_is_an_explicit_model_choice_with_no_finn_reads():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("answer_directly", {}).read_tools == ()
    with pytest.raises(FinnResponsesToolError, match="direct_answer_arguments_invalid"):
        catalog.validate("answer_directly", {"asset": "BTC"})
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "answer_directly", {}),)),
        response("r2", text="RSI vergelijkt recente stijgingen en dalingen."),
    )

    async def execute(call):
        assert call.read_tools == ()
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat betekent RSI?", instructions="Antwoord algemeen"))
    assert [call["name"] for call in result.tool_trace] == ["answer_directly"]
    assert fake.requests[0]["tool_choice"] == "auto"
    assert "tool_choice" not in fake.requests[1]


def test_direct_answer_boundary_does_not_claim_personal_evidence():
    catalog = FinnResponsesToolCatalog()
    executor = object.__new__(FinnResponsesReadExecutor)
    result = asyncio.run(executor(catalog.validate("answer_directly", {})))
    assert result["results"] == []
    assert "call relevant FINN read tools" in result["evidence_boundary"]
    followup = asyncio.run(executor(catalog.validate(
        "answer_directly", {"uses_previous_response": True},
    )))
    assert "preceding verified answer" in followup["evidence_boundary"]
    assert "No owner-scoped or market facts" not in followup["evidence_boundary"]
    proposal = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    assert "question about whether an action fits a plan" in proposal["description"]


def test_two_read_rounds_force_a_final_answer_before_the_lifecycle_budget():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "answer_directly", {}),)),
        response("r2", calls=(tool_call("c2", "get_my_profile_and_risk_style", {}),)),
        response("r3", text="Ik kan dit alleen op basis van je profiel beoordelen."),
    )

    async def execute(call):
        return {"status": "completed", "results": [], "tool": call.name}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Past dit bij mij?", instructions="Gebruik bewijs"))
    assert len(result.tool_trace) == 2
    assert fake.requests[2]["tool_choice"] == "none"
    assert fake.requests[2]["max_output_tokens"] == 350


def test_model_led_tool_continuation_has_room_for_one_complete_answer():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        response("r2", text="Ik kan je profiel toelichten."),
    )

    async def execute(call):
        return {"status": "completed", "results": [], "tool": call.name}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat zegt mijn profiel?", instructions="Gebruik bewijs", model_led_coach=True))
    assert result.text == "Ik kan je profiel toelichten."
    assert fake.requests[1]["max_output_tokens"] == 1000


def test_tool_trace_is_checkpointed_before_a_later_provider_failure():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        RuntimeError("provider down"),
    )
    checkpoints = []

    async def execute(_call):
        return {"status": "completed", "results": []}

    async def checkpoint(response_id, trace):
        checkpoints.append((response_id, trace))

    with pytest.raises(FinnResponsesError, match="responses_provider_error"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute,
            on_tool_result=checkpoint,
        ).run(message="Wat weet je over mijn profiel?", instructions="Gebruik bewijs"))
    assert checkpoints[0][0] == "r1"
    assert checkpoints[0][1][0]["name"] == "get_my_profile_and_risk_style"


def test_verifier_failure_codes_come_from_typed_tool_evidence_not_model_prose():
    classify = FinnResponsesAnswerVerifier._typed_failure_reason
    assert classify(({"status": "unavailable", "reason": "setup_ambiguous"},)) == "setup_ambiguous"
    assert classify(({"status": "unavailable", "reason": "provider_unavailable"},)) == "source_unavailable"
    assert classify(()) == "no_evidence_available"
    assert classify((
        {"status": "completed"}, {"status": "unavailable", "reason": "source_unavailable"},
    )) == "responses_evidence_not_verified"


def test_responses_provider_timeout_leaves_terminal_persistence_reserve(monkeypatch):
    from backend.services import finn_v2_responses_loop as module

    async def stalled_provider(**_kwargs):
        await asyncio.Event().wait()

    fake = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=stalled_provider)))
    monkeypatch.setattr(module, "remaining_lifecycle_seconds", lambda: 3.55)

    async def run_case():
        started = asyncio.get_running_loop().time()
        with pytest.raises(FinnResponsesError, match="responses_provider_timeout"):
            await FinnResponsesLoop(client=fake, executor=AsyncMock()).run(
                message="Wat weet je?", instructions="Gebruik bewijs",
            )
        return asyncio.get_running_loop().time() - started

    assert asyncio.run(run_case()) < 0.5
    fake.responses.create.assert_awaited_once()


def test_provider_timeout_after_typed_evaluation_retains_trace_and_terminalizes():
    calls = 0

    async def provider(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return response("resp-plan", calls=(tool_call("c1", "evaluate_plan", {}),))
        await asyncio.Event().wait()

    async def execute(call):
        assert call.name == "evaluate_plan"
        return {
            "status": "partial", "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence", "results": [],
        }

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=SimpleNamespace(create=provider)),
        executor=execute, provider_timeout_seconds=0.05,
    ).run(message="Beoordeel mijn plan", instructions="Gebruik bewijs"))
    assert calls == 2
    assert result.answer_kind == "provider_unavailable"
    assert result.tool_trace[0]["result"]["assessment_status"] == "insufficient_evidence"
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Beoordeel mijn plan", result=result, locale="nl",
    ))
    assert verified.status == "unavailable"
    assert verified.reason == "responses_provider_timeout"
    assert "Er is niets gewijzigd" in verified.text


def test_responses_loop_bounds_tool_rounds_without_silent_answer():
    fake = FakeResponses(response("r1", calls=(tool_call("c1", "get_active_asset_context", {}),)))

    async def execute(_call):
        return {"status": "completed"}

    with pytest.raises(FinnResponsesError, match="responses_tool_round_limit"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute, max_rounds=1,
        ).run(message="Welke asset?", instructions="Check feiten"))


def test_responses_loop_rejects_duplicate_call_ids():
    fake = FakeResponses(response("r1", calls=(
        tool_call("c1", "get_active_asset_context", {}),
        tool_call("c1", "get_indicator_snapshot", {}),
    )))

    async def execute(_call):
        return {"status": "completed"}

    with pytest.raises(FinnResponsesError, match="responses_duplicate_call_id"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Hoe ziet mijn plan eruit?", instructions="Check feiten"
        ))


def test_front_door_prepares_existing_action_pipeline_without_writing():
    fake = FakeResponses(
        response("r1", calls=(tool_call("p1", "create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"setup_type": "dca", "symbol": "BTC", "timeframe": "4H", "name": "DCA test", "dca_frequency": "weekly", "dca_day": "monday", "dca_amount_mode": "fixed", "base_amount": 100},
        }),)),
        response("r2", text="Ik heb je DCA-concept voorbereid; bevestig nog niets."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()

    async def no_reads(_call):
        raise AssertionError("proposal selection is not a database write")

    front.reads = no_reads
    result = asyncio.run(front.run(
        message="Maak een BTC DCA-setup op 4H met de naam DCA test, wekelijks op maandag voor 100 euro.", instructions="Gebruik tools",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis.request_plan.operation_id == "create_setup"
    assert result.proposal_analysis.request_plan.operation_state["status"] == "complete"
    assert result.response.tool_trace[0]["result"]["status"] == "validation_pending"


def test_model_read_asset_must_be_explicitly_mentioned_by_user():
    from backend.services.asset_catalog_service import mentioned_catalog_symbols

    assert mentioned_catalog_symbols("Apple en MSFT") == {"AAPL", "MSFT"}
    assert mentioned_catalog_symbols("Wat zeggen RSI en MA200?") == set()
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_indicator_snapshot", {"asset": "AEX"}),)),
        response("r2", text="Ik heb nog geen actuele indicatorwaarden."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    async def read(call):
        received.append(call.inputs)
        return {"status": "completed", "results": []}

    front.reads = read
    asyncio.run(front.run(
        message="Wat zeggen RSI en MA200 samen?", instructions="Gebruik bewijs",
        conversation_context={}, verified_asset=None,
    ))
    assert received == [{}]


def test_plan_read_reference_is_a_typed_model_choice():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate(
        "get_active_plan_and_strategy", {"reference": "previous_response"},
    ).inputs == {"reference": "previous_response"}
    with pytest.raises(FinnResponsesToolError, match="read_reference_invalid"):
        catalog.validate("get_active_plan_and_strategy", {"reference": "another_user"})


@pytest.mark.parametrize(
    ("asset_name", "message", "symbol"),
    [
        ("Bitcoin", "Beoordeel mijn BTC-handelsplan.", "BTC"),
        ("Apple", "Lees mijn AAPL-plan.", "AAPL"),
        ("Microsoft", "Lees mijn MSFT-plan.", "MSFT"),
    ],
)
def test_model_read_asset_uses_catalog_symbol_after_explicit_mention(asset_name, message, symbol):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {"asset": asset_name}),)),
        response("r2", text="Ik lees je plan."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    async def read(call):
        received.append(call.inputs)
        return {"status": "completed", "results": []}

    front.reads = read
    asyncio.run(front.run(
        message=message, instructions="Gebruik bewijs",
        conversation_context={}, verified_asset=symbol,
    ))
    assert received == [{"asset": symbol}]


def test_recent_confirmed_setup_is_bound_server_side_before_read(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {"asset": "BTC"}),)),
        response("r2", text="Je setup gebruikt 100 euro per week."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: True)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["conversation_context"]["previous_action_result"]["entity_id"] == "326"
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Wat zijn frequentie en bedrag van de setup die je net hebt opgeslagen?",
        instructions="Gebruik bewijs", verified_asset="BTC",
        conversation_context={"previous_action_result": {
            "owner_user_id": 21, "result_status": "succeeded", "entity_type": "setup", "entity_id": "326",
        }},
    ))
    assert received == [{"setup_id": 326}]


def test_named_setup_coaching_binds_evaluation_to_its_owner_scoped_strategy(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {"asset": "BTC"}),)),
        response("r2", text="Controleer eerst de voorwaarde van BTC Full Base."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "named-setup-coaching"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert "BTC Full Base" in kwargs["message"]
            return SimpleNamespace(resolution_status="resolved", entity_id=42,
                                   source="explicit_name")

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository,
                        "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Ik heb FOMO bij BTC Full Base. Hoe kijk je naar mijn risico?",
        instructions="coach", verified_asset="BTC", conversation_context={},
    ))
    assert received == [{"asset": "BTC", "setup_id": 42}]


def test_saved_level_claims_cannot_borrow_prices_from_another_btc_strategy():
    evidence = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "name": "BTC Full Base Strategy", "setup_id": 42,
        "entry": 76000, "stop_loss": 72000, "targets": [84000],
    }},)
    supports = FinnResponsesAnswerVerifier._saved_strategy_levels_supported
    message = "Ik heb FOMO bij BTC Full Base. Hoe kijk je naar mijn risico?"
    assert supports("Je opgeslagen entry is 76.000 en de stop-loss 72.000.", evidence, message)
    assert supports("De entry-stopafstand is 5,26%; wacht 24 uur als je FOMO voelt.",
                    evidence, message)
    assert not supports("Je opgeslagen entry is 80.000 en de stop-loss 76.000.", evidence, message)
    assert not supports("De niveaus 80.000/76.000 horen bij dit plan.", evidence, message)
    both_strategies = (*evidence, {"scope": "read_linked_strategy", "status": "completed",
                                  "data": {"setup_id": 43, "name": "BTC Breakout Full Strategy",
                                           "entry": 80000, "stop_loss": 76000,
                                           "targets": [88000]}})
    assert not supports("Je opgeslagen entry is 80.000 en de stop-loss 76.000.",
                        both_strategies, "Wat staat bij dat plan?", selected_setup_id=42)
    assert not supports("Voor dit plan staan 80.000/76.000 opgeslagen.",
                        both_strategies, "Wat staat bij dat plan?", selected_setup_id=42)
    assert supports("Je opgeslagen entry is 76.000 en de stop-loss 72.000.",
                    both_strategies, "Wat staat bij dat plan?", selected_setup_id=42)


def test_rejected_coaching_retains_only_the_named_setups_linked_strategy():
    evidence = (
        {"scope": "read_active_setup", "status": "completed", "data": {
            "setup_id": 42, "name": "BTC Full Base", "symbol": "BTC",
        }},
        {"scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": 42, "name": "BTC Full Base Strategy",
            "entry": 76000, "stop_loss": 72000,
        }},
    )
    question = "Ik heb FOMO bij BTC Full Base. Welke entry en stop horen hierbij?"
    answer = FinnResponsesAnswerVerifier._grounded_named_setup_coach_fallback(
        question, evidence, "nl",
    )
    assert "76.000" in answer and "72.000" in answer
    assert "80.000" not in answer
    mismatched = (evidence[0], {**evidence[1], "data": {**evidence[1]["data"], "setup_id": 43}})
    assert FinnResponsesAnswerVerifier._grounded_named_setup_coach_fallback(
        question, mismatched, "nl",
    ) is None
    fractional = (evidence[0], {**evidence[1], "data": {
        **evidence[1]["data"], "entry": "0.75", "stop_loss": "0.65",
    }})
    fractional_answer = FinnResponsesAnswerVerifier._grounded_named_setup_coach_fallback(
        question, fractional, "nl",
    )
    assert "0,75" in fractional_answer and "0,65" in fractional_answer


@pytest.mark.parametrize("read_arguments", [
    {"reference": "previous_response"},
    {"setup_name": "Mijn BTC-setup"},
])
def test_previous_setup_read_reference_is_owner_scoped_and_server_resolved(monkeypatch, read_arguments):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            **read_arguments,
        }),)),
        response("r2", text="Omdat je gekozen setup op 4H werkt."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["conversation_context"]["canonical_entity_target"] == {
                "entity_type": "setup", "entity_id": 326,
            }
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    observed = asyncio.run(front.run(
        message="Waarom?", instructions="Gebruik bewijs", verified_asset="BTC",
        previous_response_id="resp-previous",
        conversation_context={}, previous_response={
            "answer": "Je gekozen setup gebruikt 4H.",
            "tool_trace": [{"result": {"results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 326, "name": "Mijn BTC-setup"},
            }]}}],
        },
    ))
    assert observed.response.uses_previous_response is True
    assert received == [{"setup_id": 326}]
    assert fake.requests[0]["previous_response_id"] == "resp-previous"
    assert fake.requests[0]["input"][0]["role"] == "assistant"
    assert fake.requests[0]["input"][0]["content"].startswith("Je gekozen setup gebruikt 4H.")
    assert '"scope": "read_active_setup"' in fake.requests[0]["input"][0]["content"]


def test_missing_previous_setup_identity_finishes_from_verified_answer_without_repeating_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response", "asset": "BTC",
        }),)),
        response("r2", text="You said you wanted a clear signal first. "
                 "Waiting follows that stated rule, but it does not guarantee a better trade."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-process-followup"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.reads = SimpleNamespace(session_factory=None)
    front.relevance_guard = None
    result = asyncio.run(front.run(
        message="Why use that prior check if I might miss the move?",
        instructions="coach", verified_asset="BTC", locale="en",
        conversation_context={}, previous_response={
            "answer": "You said you intended to wait for a clear signal before acting.",
            "tool_trace": [], "terminal_status": "completed",
        },
    ))
    assert result.response.text.startswith("You said you wanted a clear signal")
    assert fake.requests[1]["tool_choice"] == "none"
    assert len(fake.requests) == 2


def test_model_previous_reference_reuses_verified_list_selection_not_model_name(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response", "setup_name": "BTC Breakout Full",
        }),)),
        response("r2", text="Ik heb BTC Full Base gelezen."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "selected-list-context"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["conversation_context"]["canonical_entity_target"] == {
                "entity_type": "setup", "entity_id": 42,
            }
            assert "setup_name" not in kwargs["selector"]
            return SimpleNamespace(resolution_status="resolved", entity_id=42)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository,
                        "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Kun je het risico daarvan toelichten?", instructions="coach",
        verified_asset="BTC", conversation_context={}, previous_response={
            "answer": "Nummer 2 is BTC Full Base.", "terminal_kind": "listed_setup_reference",
            "terminal_status": "completed", "tool_trace": [{
                "name": "get_saved_setup_inventory", "status": "completed",
                "arguments": {"listed_ordinal": 2, "setup_ids": [42]},
                "result": {"results": [{"scope": "read_saved_setup_inventory",
                                       "status": "completed", "data": {"setups": [
                                           {"setup_id": 42, "name": "BTC Full Base"},
                                       ]}}]},
            }],
        },
    ))
    assert received == [{"setup_id": 42}]


@pytest.mark.parametrize("message", [
    "Beoordeel het risico van dat plan.",
    "Beoordeel het risico van dat BTC-plan.",
])
def test_evaluation_followup_uses_verified_selected_setup_id(monkeypatch, message):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {
            "asset": "BTC",
        }),)),
        response("r2", text="Controleer eerst de voorwaarden van BTC Full Base."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "selected-evaluation-context"
    front.model_led_coach = True
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["conversation_context"]["canonical_entity_target"] == {
                "entity_type": "setup", "entity_id": 42,
            }
            assert "setup_name" not in kwargs["selector"]
            return SimpleNamespace(resolution_status="resolved", entity_id=42,
                                   source="active_runtime_context")

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository,
                        "record_responses_progress", AsyncMock())
    front.reads = Reads()
    observed = asyncio.run(front.run(
        message=message, instructions="coach",
        verified_asset="BTC", conversation_context={}, previous_response={
            "answer": "Nummer 2 is BTC Full Base.", "terminal_kind": "listed_setup_reference",
            "terminal_status": "completed", "tool_trace": [{
                "name": "get_saved_setup_inventory", "status": "completed",
                "arguments": {"listed_ordinal": 2, "setup_ids": [42]},
                "result": {"results": [{"scope": "read_saved_setup_inventory",
                                       "status": "completed", "data": {"setups": [
                                           {"setup_id": 42, "name": "BTC Full Base", "symbol": "BTC"},
                                       ]}}]},
            }],
        },
    ))
    assert len(received) == 1, repr(observed.response.tool_trace)
    assert received[0]["setup_id"] == 42
    assert received[0].get("asset") in {None, "BTC"}


def test_duplicate_setup_read_uses_canonical_owner_scoped_target(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "setup_name": "Older setup name",
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {
            "reference": "previous_response", "setup_name": "Another old name",
        }),)),
        response("r3", text="De laatst opgeslagen setup heet Nieuwe DCA."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-canonical-dedup"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = None
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            calls.append(call.inputs)
            return {"status": "partial", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 326, "name": "Nieuwe DCA"},
            }]}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: True)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Welke setup heb je net opgeslagen?", instructions="Gebruik bewijs",
        verified_asset="BTC", conversation_context={"previous_action_result": {
            "owner_user_id": 21, "result_status": "succeeded", "entity_type": "setup", "entity_id": 326,
        }},
    ))

    assert calls == [{"setup_id": 326}]
    assert result.response.tool_trace[1]["result"]["reason"] == "read_already_completed_this_turn"


def test_setup_choice_resolves_user_name_when_model_points_at_clarification(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response", "setup_name": "Matrix Strategy",
        }),)),
        response("r2", text="Je gekozen setup heet Matrix Strategy Update Parent."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-choice"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 326, "name": "Matrix Strategy Update Parent"},
            }]}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["message"] == "Matrix Strategy Update Parent"
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Matrix Strategy Update Parent", instructions="Gebruik bewijs",
        verified_asset="BTC", conversation_context={}, resuming_clarification=True,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert received == [{"setup_id": 326}]


def test_previous_response_reference_uses_confirmed_owner_scoped_setup_result(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response",
        }),)),
        response("r2", text="De laatst opgeslagen setup gebruikt 200 per week."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-latest"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 327, "name": "Latest", "min_investment": 200},
            }]}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: True)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["conversation_context"]["canonical_entity_target"]["entity_id"] == "327"
            return SimpleNamespace(resolution_status="resolved", entity_id=327)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Wat is het bedrag van de setup die ik net heb opgeslagen?",
        instructions="Gebruik bewijs", verified_asset="BTC", conversation_context={
            "previous_action_result": {
                "owner_user_id": 21, "result_status": "succeeded",
                "entity_type": "setup", "entity_id": "327",
            },
        },
    ))
    assert received == [{"setup_id": 327}]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Wat zijn frequentie en bedrag van de setup die je net hebt opgeslagen?", True),
        ("What did you just save in this setup?", True),
        ("Was hast du in diesem Setup gerade gespeichert?", True),
        ("Was kann ich über meinen BTC-Plan sagen?", False),
        ("Welke BTC setups heb ik?", False),
    ],
)
def test_recent_setup_reference_does_not_capture_general_plan_reads(message, expected):
    from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService

    assert FinnV2EntityResolutionService.references_recent_action(message, "setup") is expected


def test_responses_money_claims_require_current_or_immediate_verified_evidence():
    verifier = FinnResponsesAnswerVerifier()
    evidence = ({"scope": "read_market_snapshot", "status": "unavailable"},)
    assert not verifier._amounts_supported(
        answer="Du investierst 150 Euro pro Woche.", message="Was ist mein BTC-Plan?",
        previous_answer="Für die Bewertung fehlen aktuelle Daten.", evidence=evidence,
    )
    assert verifier._amounts_supported(
        answer="Du investierst 100 Euro pro Woche.", message="Was ist mein BTC-Plan?",
        previous_answer="De opgeslagen setup gebruikt €100 per week.", evidence=evidence,
    )
    assert verifier._amounts_supported(
        answer="Het budget is €1.000,00.", message="Wat is het botbudget?",
        previous_answer="", evidence=({
            "scope": "read_bot_status", "status": "completed", "data": {"budget": 1000},
        },),
    )
    portfolio = ({"scope": "read_portfolio", "status": "completed", "data": {
        "global": {"total_equity": 1250, "cash_balance": 250, "realized_pnl": 10},
    }},)
    assert verifier._amounts_supported(
        answer="Je vermogen is €1.250 en je contante saldo is €250.",
        message="Toon mijn portfolio.", previous_answer="", evidence=portfolio,
    )
    assert not verifier._amounts_supported(
        answer="Je vermogen is €1.500.",
        message="Toon mijn portfolio.", previous_answer="", evidence=portfolio,
    )


def test_portfolio_terminal_verifier_accepts_nested_allocation_but_not_invented_amount():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    evidence = {
        "scope": "read_portfolio", "status": "completed", "source": "portfolio",
        "data": {"global": {"currency": "EUR", "total_equity": 1250,
                            "allocations_pct": {"Cash": 100}}},
    }
    def result(answer):
        return FinnResponsesResult(answer, "resp-portfolio", ({
            "name": "get_portfolio_and_exposure", "status": "completed",
            "result": {"status": "completed", "results": [evidence]},
        },))

    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Toon mijn portfolio.",
        result=result("Je vermogen is €1.250 en je portefeuille is 100% contant."), locale="nl",
    ))
    assert verified.status == "completed", (verified.reason, verified.text)
    invalid = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Toon mijn portfolio.",
        result=result("Je vermogen is €1.500 en je portefeuille is 100% contant."), locale="nl",
    ))
    assert invalid.status == "unavailable"


def test_unknown_saved_setup_amount_cannot_gain_an_invented_change_direction():
    verifier = FinnResponsesAnswerVerifier()
    evidence = ({
        "scope": "read_active_setup", "status": "completed",
        "data": {"name": "Coach DCA Basis", "min_investment": None},
    },)
    message = "Ik denk aan 100 euro per week. Past dat bij mijn plan?"
    assert not verifier._amounts_supported(
        answer="Je overweegt je DCA-hoeveelheid te verhogen naar 100 euro per week.",
        message=message, previous_answer="", evidence=evidence,
    )
    assert verifier._amounts_supported(
        answer="Je overweegt 100 euro per week voor je DCA-setup.",
        message=message, previous_answer="", evidence=evidence,
    )


def test_responses_verifier_blocks_stale_saved_amount_even_if_semantic_model_passes():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("De setup gebruikt €150 per week.", "resp-amount", ({
        "name": "get_market_snapshot", "status": "partial",
        "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable",
        }]},
    },))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat kan ik veilig zeggen over mijn BTC-plan?",
        result=result, previous_response={"answer": "Er ontbreekt actuele marktdata."},
    ))
    assert verified.status == "unavailable"
    assert verified.reason == "responses_evidence_not_verified"
    assert "150" not in verified.text
    semantic.verify_async.assert_awaited_once()


def test_recent_action_result_query_orders_by_execution_not_contract_revision():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: [SimpleNamespace(state_json={"action_result": {
            "owner_user_id": 21, "entity_id": "327", "result_status": "succeeded",
            "created_at": "2026-09-24T10:05:00+00:00",
        }}), SimpleNamespace(state_json={"action_result": {
            "owner_user_id": 21, "entity_id": "326", "result_status": "succeeded",
            "created_at": "2026-09-24T10:00:00+00:00",
        }})],
    )))
    repository = FinnV2RuntimeContractRepository(session)
    latest = asyncio.run(repository.get_latest_action_result_for_conversation(
        conversation_id="conv-1", user_id=21,
    ))
    assert latest.state_json["action_result"]["entity_id"] == "327"
    ordering = str(session.execute.await_args.args[0].compile(
        compile_kwargs={"literal_binds": True},
    )).split("ORDER BY", 1)[1]
    assert "action_result" in ordering and "created_at" in ordering
    assert ordering.index("created_at") < ordering.index("updated_at")


@pytest.mark.parametrize(
    ("answer", "unsupported", "expected"),
    [
        ("Je stop-loss is 90 en je target is 120.", False, True),
        ("Deze aanpassing is cruciaal om jouw investeringsdoel te bereiken.", True, False),
    ],
)
def test_personal_advice_audit_uses_typed_evidence(answer, unsupported, expected):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": unsupported,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
    }))
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    verifier = FinnResponsesAnswerVerifier(client=client)
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer=answer,
        evidence=[{"scope": "read_active_strategy", "status": "completed", "data": {
            "stop_loss": 90, "targets": [120],
        }}],
        remaining=20,
    ))
    assert actual is expected
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["tool_choice"] == "none"
    assert "read_active_strategy" in kwargs["input"]


def test_personal_advice_audit_checks_repeated_supplied_input():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": False,
    }))
    create = AsyncMock(return_value=response)
    verifier = FinnResponsesAnswerVerifier(
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    grounded = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Kies eerst een bedrag per week.",
        evidence=[{"scope": "read_profile", "status": "completed",
                   "data": {"has_profile": True}}],
        remaining=20,
        question="Past 100 euro per week bij mijn voorzichtige profiel?",
    ))
    assert grounded is False
    assert "already explicit" in create.await_args.kwargs["instructions"]


def test_personal_advice_audit_rejects_broken_coach_copy():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "language_mismatch": False,
        "unnatural_language": True,
        "addresses_request": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert not asyncio.run(verifier._personal_advice_is_grounded(
        answer="Je risicopro profiel toont een geschiktheidsof.",
        evidence=[{"scope": "read_profile", "status": "completed",
                   "data": {"has_profile": True}}],
        remaining=20, question="Wat betekent dit voor mijn plan?",
    ))


@pytest.mark.parametrize(
    ("entity_claim", "language_mismatch", "expected"),
    [(True, False, False), (False, True, True), (False, False, True)],
)
def test_personal_advice_audit_checks_saved_object_type_and_answer_language(
    entity_claim, language_mismatch, expected,
):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": entity_claim,
        "unsupported_entity_quote": "Coach DCA Basis is je strategie." if entity_claim else "",
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": language_mismatch,
        "unnatural_language": False,
        "addresses_request": True,
    }))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response)))
    verifier = FinnResponsesAnswerVerifier(client=client)
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Coach DCA Basis is je strategie.",
        evidence=[{"scope": "read_active_setup", "status": "completed", "data": {
            "name": "Coach DCA Basis", "setup_type": "dca",
        }}, {"scope": "read_linked_strategy", "status": "unavailable", "data": None}],
        remaining=20, question="Wat vind je van mijn setup?", locale="nl",
    ))
    assert actual is expected
    schema = client.responses.create.await_args.kwargs["text"]["format"]["schema"]
    assert "unsupported_entity_claim" in schema["required"]
    assert "unsupported_entity_quote" in schema["required"]
    assert "language_mismatch" in schema["required"]
    assert "unnatural_language" in schema["required"]


@pytest.mark.parametrize("quote", [
    "De gekoppelde strategie kon ik niet vaststellen.",
    "De gekoppelde strategie",
    "Ik kan niet betrouwbaar aangeven welke bot bij dit actieve plan hoort.",
])
def test_personal_advice_audit_preserves_honest_partial_entity_read(quote):
    answer = (
        "Je actieve setup is Confirmation prerequisite voor XLM op 4H. "
        "De gekoppelde strategie kon ik niet vaststellen. "
        "Ik kan niet betrouwbaar aangeven welke bot bij dit actieve plan hoort."
    )
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": True,
        "unsupported_entity_quote": quote,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "actionable_next_decision": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert asyncio.run(verifier._personal_advice_is_grounded(
        answer=answer,
        evidence=[
            {"scope": "read_active_setup", "status": "completed", "data": {
                "name": "Confirmation prerequisite", "symbol": "XLM", "timeframe": "4H",
            }},
            {"scope": "read_linked_strategy", "status": "unavailable", "data": None},
        ],
        remaining=20, question="Toon mijn complete actieve plan.", locale="nl",
    ))


def test_personal_advice_audit_rejects_actual_language_switch():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False, "unsupported_entity_claim": False,
        "proposed_as_saved": False, "proposed_change_omitted": False,
        "premature_action_invitation": False, "language_mismatch": True,
        "unnatural_language": False, "addresses_request": True,
        "actionable_next_decision": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert not asyncio.run(verifier._personal_advice_is_grounded(
        answer="Your saved setup is configured for weekly purchases, but I cannot assess whether it suits your risk profile.",
        evidence=[{"scope": "read_active_setup", "status": "completed", "data": {"name": "BTC DCA"}}],
        remaining=20, question="Wat weet je over mijn setup?", locale="nl",
    ))


def test_response_language_check_catches_short_foreign_sentence_without_rejecting_names():
    assert not FinnResponsesAnswerVerifier._language_matches(
        "Je plan staat klaar. I cannot assess your plan yet.", "nl",
    )
    assert FinnResponsesAnswerVerifier._language_matches(
        "Je setup heet Apple Swing. Wat betekent dit voor mijn plan?", "nl",
    )
    assert not FinnResponsesAnswerVerifier._language_matches(
        "Ne saute pas la règle de confirmation par peur de rater le mouvement. "
        "Je ne peux pas évaluer le signal actuel car les données de marché sont indisponibles.",
        "nl",
    )
    assert FinnResponsesAnswerVerifier._language_matches(
        "Zonder die koppeling kan ik niet vaststellen hoe de bot je huidige plan beïnvloedt. "
        "Welke bot of strategie bedoel je?", "nl",
    )
    assert FinnResponsesAnswerVerifier._language_matches(
        "Ik kan je actieve setup nog niet beoordelen: het systeem kan niet bepalen welke "
        "opgeslagen setup je bedoelt. Welke setup wil je laten beoordelen?", "nl",
    )


def test_personal_advice_audit_excludes_superseded_chat_and_draft_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult("De nieuwe setup heet Nieuw en gebruikt 200.", "resp-new", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "Nieuw", "min_investment": 200},
        }]},
    },))
    previous = {
        "answer": "De oude draft heet Oud en gebruikt 100.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "Oud", "min_investment": 100},
        }]}}],
    }
    verified = asyncio.run(verifier.verify(
        message="Wat heb je net opgeslagen?", result=result, previous_response=previous,
    ))
    assert verified.status == "completed"
    audit_evidence = verifier._personal_advice_is_grounded.await_args.kwargs["evidence"]
    assert [item["data"]["name"] for item in audit_evidence] == ["Nieuw"]


def test_short_explanation_verifies_only_immediately_previous_verified_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    verifier._cause_claim_is_grounded = AsyncMock(return_value=False)
    previous = {
        "answer": "BTC Plan bewaart instap 100; passendheid is nog niet beoordeeld.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "entry": 100},
        }, {
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}}],
    }
    result = FinnResponsesResult("Omdat die instap slechts een opgeslagen instelling is.",
                                 "resp-followup", ({
                                     "name": "answer_directly", "status": "completed",
                                     "arguments": {"uses_previous_response": True},
                                     "result": {"results": []},
                                 },))
    answer = asyncio.run(verifier.verify(
        message="Waarom?", result=result, previous_response=previous,
    ))
    assert answer.status == "completed"
    verifier._personal_advice_is_grounded.assert_not_awaited()
    verifier._cause_claim_is_grounded.assert_not_awaited()
    semantic_evidence = semantic.verify_async.await_args.kwargs["compact_evidence"]
    assert semantic.verify_async.await_args.kwargs["user_message"] == "Waarom?"
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"]["previous_verified_answer"] == previous["answer"]
    assert len(semantic_evidence) == 1
    assert semantic_evidence[0]["scope"] == "previous_response"
    assert semantic_evidence[0]["data"]["answer"] == previous["answer"]
    assert semantic_evidence[0]["data"]["source_evidence"] == []


def test_unavailable_optional_read_does_not_erase_supported_process_followup():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "The check separates your planned entry reason from the fear of missing a move; "
        "it does not guarantee a better trade.", "resp-optional-read", ({
            "name": "get_active_plan_and_strategy", "status": "unavailable",
            "result": {"status": "unavailable", "reason": "previous_response_reference_unavailable"},
        },), uses_previous_response=True,
    )
    previous = {
        "answer": "You said you intended to wait for a clear signal before acting. "
        "BTC moving alone does not prove that signal is present.",
        "tool_trace": [], "terminal_status": "completed",
    }
    answer = asyncio.run(verifier.verify(
        message="Why use that prior check if I might miss the move?",
        result=result, previous_response=previous, locale="en",
    ))
    assert answer.status == "completed"
    compact = semantic.verify_async.await_args.kwargs["compact_evidence"]
    assert any(item["scope"] == "previous_response" for item in compact)
    assert not any(item.get("scope") == "read_active_setup" for item in compact)


def test_next_decision_verifier_receives_earlier_verified_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult(
        "Laat de opgeslagen setup voorlopig ongewijzigd.", "resp-next", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True},
            "result": {"results": []},
        },),
    )
    answer = asyncio.run(verifier.verify(
        message="Welke keuze maak ik eerst?", result=result,
        previous_response={
            "answer": "Zonder marktdata is geschiktheid nog niet vastgesteld.",
            "antecedent_verified_answer": "Je kunt je opgeslagen setup ongewijzigd laten.",
            "tool_trace": [],
        },
    ))
    assert answer.status == "completed"
    scopes = {item["scope"]: item for item in semantic.verify_async.await_args.kwargs["compact_evidence"]}
    assert scopes["antecedent_verified_response"]["data"]["answer"] == (
        "Je kunt je opgeslagen setup ongewijzigd laten."
    )


def test_followup_amount_uses_verified_antecedent_not_unrelated_context():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult(
        "Vergelijk je huidige inleg met de €100 per week die je overweegt; wijzig nog niets.",
        "resp-next", (), uses_previous_response=True, model_led_coach=True,
    )
    previous = {
        "answer": "Zonder actuele data kan ik geschiktheid nog niet beoordelen.",
        "antecedent_verified_answer": "Je overweegt €100 per week; je opgeslagen setup blijft ongewijzigd.",
        "tool_trace": [],
    }
    verified = asyncio.run(verifier.verify(
        message="Welke keuze moet ik eerst maken?", result=result,
        previous_response=previous, locale="nl",
    ))
    assert verified.status == "completed"

    unrelated = asyncio.run(verifier.verify(
        message="Welke keuze moet ik eerst maken?", result=result,
        previous_response={"answer": previous["answer"], "tool_trace": []}, locale="nl",
    ))
    assert unrelated.status != "completed"


@pytest.mark.parametrize("advice_ok, expected_status", [
    (True, "completed"), (False, "unavailable"),
])
def test_next_decision_uses_independent_advice_audit_without_redundant_cause_veto(
    advice_ok, expected_status,
):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=advice_ok)
    verifier._cause_claim_is_grounded = AsyncMock(return_value=False)
    previous = {
        "answer": "Zonder actuele data kan ik dit nog niet beoordelen.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan"},
        }, {
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}}],
    }
    result = FinnResponsesResult(
        "Laat je opgeslagen setup voorlopig ongewijzigd.", "resp-decision", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True}, "result": {"results": []},
        },), "grounded_next_decision",
    )
    answer = asyncio.run(verifier.verify(
        message="Welke keuze moet ik nu eerst maken?", result=result,
        previous_response=previous,
    ))
    assert answer.status == expected_status
    assert verifier._personal_advice_is_grounded.await_args.kwargs["question"] == (
        "Welke keuze moet ik nu eerst maken?"
    )
    verifier._cause_claim_is_grounded.assert_not_awaited()


def test_short_explanation_cannot_override_unsupported_positive_fit_claim():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    previous = {
        "answer": "Je hebt een DCA-setup; geschiktheid is niet beoordeeld.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed", "data": {"name": "BTC Plan"},
        }]}}],
    }
    result = FinnResponsesResult(
        "Want jouw DCA-setup past goed bij je risicostijl.", "resp-unsafe", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True}, "result": {"results": []},
        },),
    )
    answer = asyncio.run(verifier.verify(
        message="Waarom?", result=result, previous_response=previous,
    ))
    assert answer.status == "unavailable"


def test_missing_profile_asks_for_goal_and_risk_style_without_personal_advice():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["missing_profile"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=False)
    result = FinnResponsesResult("Je profiel is nog niet ingevuld.", "resp-profile", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed", "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(verifier.verify(message="Wat past bij mijn profiel?", result=result))
    assert answer.status == "clarification_required"
    assert answer.reason == "user_detail_required"
    assert "doel" in answer.text and "risicostijl" in answer.text
    verifier._personal_advice_is_grounded.assert_not_awaited()


def test_unsupported_personal_advice_rewrite_gets_typed_rejection_reason():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "De opgeslagen setup heet BTC Plan. Ik kan de passendheid nog niet beoordelen."
    create = AsyncMock(return_value=SimpleNamespace(output_text=rewrite))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(side_effect=[False, True])
    result = FinnResponsesResult("Deze setup past bij jouw risicoprofiel.", "resp", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan"},
        }]},
    },))
    answer = asyncio.run(verifier.verify(message="Past dit?", result=result))
    assert answer.status == "completed"
    assert answer.text == rewrite
    assert "personal_advice_not_grounded" in create.await_args.kwargs["input"]
    assert "Preserve the answer form requested by the user" in create.await_args.kwargs["instructions"]


def test_grounded_personal_limitation_survives_generic_read_verifier_rejection():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["risk_assessment_missing"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    message = "Past 100 euro per week bij mijn voorzichtige BTC-plan?"
    answer_text = (
        "Je opgeslagen BTC-setup gebruikt dagelijkse DCA en je risicoprofiel is "
        "voorzichtig. Of 100 euro per week past, kan ik zonder risicobeoordeling "
        "nog niet vaststellen. Wil je die beoordeling laten uitvoeren?"
    )
    result = FinnResponsesResult(answer_text, "resp-limited", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed",
            "data": {"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
        }]},
    }, {
        "name": "get_active_plan_and_strategy", "status": "partial",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC-plan", "setup_type": "dca", "dca_frequency": "daily"},
        }, {
            "scope": "read_linked_strategy", "status": "unavailable",
            "reason": "strategy_not_resolved", "data": None,
        }]},
    }))
    verified = asyncio.run(verifier.verify(message=message, result=result))
    assert verified.status == "completed"
    assert verified.text == answer_text
    verifier._personal_advice_is_grounded.assert_awaited_once()
    assert verifier._personal_advice_is_grounded.await_args.kwargs["question"] == message


def test_direct_followup_keeps_previous_unavailable_strategy_for_grounding():
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    previous_response = {
        "answer": "Je setup bestaat, maar er is geen gekoppelde strategie gevonden.",
        "tool_trace": ({
            "name": "get_active_plan_and_strategy",
            "result": {"results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"name": "Coach DCA Basis"},
            }, {
                "scope": "read_linked_strategy", "status": "unavailable",
                "reason": "strategy_not_resolved", "data": None,
            }]},
        },),
    }
    result = FinnResponsesResult(
        "Analyseer je strategie terwijl je wacht.", "resp-followup", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True},
            "result": {"results": []},
        },),
    )
    asyncio.run(verifier.verify(
        message="Wat doe ik met de FOMO terwijl ik wacht?",
        result=result, previous_response=previous_response,
    ))
    evidence = verifier._personal_advice_is_grounded.await_args.kwargs["evidence"]
    assert any(
        item.get("scope") == "read_linked_strategy"
        and item.get("status") == "unavailable"
        for item in evidence
    )


def test_plan_evaluation_does_not_trigger_single_indicator_catalog_check():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["limited_evidence"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    verifier._catalog_answer_is_focused = AsyncMock(return_value=(False, ""))
    result = FinnResponsesResult(
        "Mijn BTC-setup is opgeslagen, maar de actuele geschiktheid is nog niet beoordeeld.",
        "resp-evaluate", ({"name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "results": [
                {"scope": "read_active_setup", "status": "completed",
                 "data": {"name": "Coach DCA Basis", "setup_type": "dca"}},
                {"scope": "available_macro_indicator_catalog", "status": "completed",
                 "data": {"supported_options": [{"name": "DXY", "display_name": "DXY"}]}},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable"},
            ],
        }},),
    )
    answer = asyncio.run(verifier.verify(
        message="Beoordeel mijn BTC-plan.", result=result,
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["mode"] == "EVALUATE"
    verifier._catalog_answer_is_focused.assert_not_awaited()


def test_plan_review_audit_receives_typed_missing_strategy_and_market_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "Je DCA-setup is opgeslagen. Wacht op marktdata en blijf je plan volgen.",
        "resp-plan-gap", ({"name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_active_setup", "status": "completed",
                 "data": {"name": "Coach DCA", "setup_type": "dca"}},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved", "data": None},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable", "data": None},
            ],
        }},), "free_text", "review",
    )
    asyncio.run(verifier.verify(message="Beoordeel mijn plan en geef mijn volgende stap.", result=result))
    audited = verifier._personal_advice_is_grounded.await_args.kwargs["evidence"]
    assert {item["scope"]: item["status"] for item in audited if item["scope"].startswith("read_")} == {
        "read_active_setup": "completed",
        "read_linked_strategy": "unavailable",
        "read_market_snapshot": "unavailable",
    }
    assert next(item for item in audited if item["scope"] == "read_linked_strategy")["reason"] == "strategy_not_resolved"
    assert verifier._personal_advice_is_grounded.await_args.kwargs["require_actionable_next_decision"] is True


@pytest.mark.parametrize("locale,expected", [
    ("nl", "geen gekoppelde strategie"),
    ("en", "No linked strategy"),
    ("de", "keine verknüpfte Strategie"),
])
def test_rejected_limited_plan_review_keeps_typed_plan_gap_and_user_choice(locale, expected):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult(
        "Wait for market data.", "resp-plan-gap", ({"name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {"name": "Coach DCA"}},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved", "data": None},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable", "data": None},
            ],
        }},), "free_text", "review",
    )
    verified = asyncio.run(verifier.verify(message="Review my plan", result=result, locale=locale))
    assert verified.status == "completed"
    assert expected in verified.text
    assert "Coach DCA" in verified.text
    assert "Wait for market data" not in verified.text


def test_rejected_plan_review_preserves_proposed_amount_without_calling_it_saved():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    result = FinnResponsesResult("Generic market warning", "resp-proposal-review", ({
        "name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_active_setup", "status": "completed", "data": {"name": "Coach DCA"}},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved"},
            ],
        },
    },), "free_text", "review")
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Ik denk aan 100 euro per week. Past dat bij mijn plan?",
        result=result, locale="nl",
    ))
    assert "Je overweegt 100 euro per week" in verified.text
    assert "voorgestelde inleg" in verified.text
    assert "opgeslagen bedrag" not in verified.text


def test_horizon_guard_rejects_cross_sentence_inference_from_setup_type_and_timeframe():
    evidence = ({"scope": "read_active_setup", "status": "completed",
                 "data": {"setup_type": "dca", "timeframe": "4H"}},)
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Je DCA-setup heeft een 4H-grafiek. Hierdoor wordt het doorgaans beschouwd "
        "als een langetermijnopbouwstrategie.", evidence,
    )
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Your DCA setup uses a 4H chart. Therefore it is considered a long-term strategy.", evidence,
    )
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Je opgeslagen BTC-setup lijkt bedoeld voor langetermijnopbouw, niet voor swingtrades.", evidence,
    )
    assert not FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Your saved setup appears intended for long-term accumulation.", evidence,
    )
    assert FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Je DCA-setup heeft een 4H-grafiek. Welke beleggingshorizon bedoel je?", evidence,
    )
    assert FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
        "Je opgeslagen setup is dagelijkse DCA; die frequentie maakt het op zichzelf geen swingtrade. "
        "Op basis van deze gegevens kan ik niet kiezen tussen langetermijnopbouw en swingtrade.",
        evidence,
    )


def test_level_advice_guard_rejects_speculative_saved_level_changes():
    assert FinnResponsesAnswerVerifier._ungrounded_level_advice(
        "Dit geeft een goede reward-to-risk verhouding van 2:1."
    )
    assert FinnResponsesAnswerVerifier._ungrounded_level_advice(
        "Sterk in je plan: Het plan heeft een duidelijke risico-beloningsverhouding "
        "met ratio's van 2:1 en 3:1."
    )
    assert FinnResponsesAnswerVerifier._ungrounded_level_advice(
        "Bepaal of je de instap- en targetniveaus wilt bevestigen of aanpassen "
        "op basis van recente marktbewegingen."
    )
    assert FinnResponsesAnswerVerifier._ungrounded_level_advice(
        "Consider whether to adjust the entry and target levels based on recent market moves."
    )
    assert not FinnResponsesAnswerVerifier._ungrounded_level_advice(
        "Controleer welke entry, stop-loss en targets je hebt opgeslagen; wijzig nog niets."
    )


def test_absolute_risk_per_unit_cannot_be_described_as_percentage():
    evidence = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "level_geometry": {"status": "completed", "risk_per_unit": "4000"},
    }},)
    assert not FinnResponsesAnswerVerifier._static_risk_units_supported(
        "Het risicopercentage per eenheid is 4000.", evidence,
    )
    assert FinnResponsesAnswerVerifier._static_risk_units_supported(
        "Het absolute risico per eenheid is 4.000; dit is geen risicopercentage.", evidence,
    )


def test_unavailable_live_source_cannot_be_an_immediate_priority():
    assert FinnResponsesAnswerVerifier._asks_user_to_supply_unavailable_source(
        "Zorg voor het updaten van de ontbrekende markt- en technische gegevens."
    )
    assert FinnResponsesAnswerVerifier._uses_unavailable_live_source_as_current_action(
        "Controleer de huidige prijs van BTC en vergelijk die met je entry."
    )
    assert FinnResponsesAnswerVerifier._uses_unavailable_live_source_as_current_action(
        "Controleer of de prijs van BTC bij de instapprijs ligt voordat je een positie opent."
    )
    assert FinnResponsesAnswerVerifier._uses_unavailable_live_source_as_current_action(
        "Houd de prijsontwikkeling in de gaten en anticipeer op een stijging."
    )
    assert not FinnResponsesAnswerVerifier._uses_unavailable_live_source_as_current_action(
        "Zodra actuele marktdata beschikbaar zijn, controleer dan of je entryvoorwaarde geldt."
    )


def test_rejected_priority_list_uses_saved_levels_without_pretending_live_data():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    result = FinnResponsesResult("Controleer de huidige koers.", "resp-priorities", ({
        "name": "evaluate_plan", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_linked_strategy", "status": "completed",
                 "data": {"entry": 80000, "stop_loss": 76000, "targets": [88000]}},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable"},
            ],
        },
    },), "free_text", "priorities")
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Wat zijn mijn drie prioriteiten?", result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert "1. Controleer of de opgeslagen entry" in verified.text
    assert "3. Laat een nieuwe entrybeslissing open" in verified.text
    assert "Controleer de huidige koers" not in verified.text


def test_plan_read_without_market_snapshot_cannot_ground_live_price_priorities():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "1. Controleer de huidige marktprijs van BTC.\n"
        "2. Volg de prijsontwikkeling en pas je entry aan.\n"
        "3. Bevestig de actuele markttrend.",
        "resp-read-priorities", ({"name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": [{"scope": "read_linked_strategy", "status": "completed",
                                  "data": {"entry": 80000, "stop_loss": 76000,
                                           "targets": [88000, 92000]}}]}},),
        "free_text", "priorities",
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Wat zijn mijn drie prioriteiten?", result=result, locale="nl",
    ))
    assert verified.status == "completed"
    assert "1. Controleer of de opgeslagen entry" in verified.text
    assert "huidige marktprijs" not in verified.text
    assert "plaats geen order" in verified.text


def test_plan_evaluation_inventory_is_rewritten_as_coaching():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "Je BTC-setup gebruikt dagelijkse DCA. Actuele marktdata ontbreken, dus ik kan de passendheid nog niet beoordelen. Laat je huidige setup voorlopig ongewijzigd."
    create = AsyncMock(return_value=SimpleNamespace(output_text=json.dumps({
        "saved_context": "Je BTC-setup gebruikt dagelijkse DCA.",
        "user_proposal": "",
        "assessment_limit": "Actuele marktdata ontbreken, dus ik kan de passendheid nog niet beoordelen.",
        "next_safe_step": "Laat je huidige setup voorlopig ongewijzigd.",
    })))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult(
        "### Mijn profiel\n- Voorzichtig\n- BTC\n- Dagelijkse DCA", "resp-evaluate", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["market_snapshot"],
                "results": [{"scope": "read_active_setup", "status": "completed",
                             "data": {"name": "Coach DCA Basis", "setup_type": "dca"}},
                            {"scope": "read_linked_strategy", "status": "unavailable",
                             "reason": "strategy_not_resolved", "data": None}],
            },
        },),
    )
    answer = asyncio.run(verifier.verify(message="Beoordeel mijn BTC-plan.", result=result))
    assert answer.status == "completed" and answer.text == rewrite
    assert "assessment_presentation_not_coaching" in create.await_args.kwargs["input"]
    repair_input = json.loads(create.await_args.kwargs["input"])
    assert repair_input["grounded_plan"] == {
        "source": "owner_scoped_persisted_read",
        "setup": {"name": "Coach DCA Basis", "setup_type": "dca"},
        "strategy": {}, "profile_saved": False,
        "component_statuses": {
            "read_active_setup": {"status": "completed", "reason": None},
            "read_linked_strategy": {"status": "unavailable", "reason": "strategy_not_resolved"},
        },
    }
    assert repair_input["typed_scope_statuses"]["read_linked_strategy"] == {
        "status": "unavailable", "reason": "strategy_not_resolved",
    }
    assert repair_input["proposed_change_is_not_saved"] is True
    assert not verifier._evaluation_presentation_is_coaching(result.text)
    assert verifier._evaluation_presentation_is_coaching(rewrite)


def test_partial_evaluation_rejects_offer_to_repeat_same_assessment():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "Actuele marktdata ontbreken, dus de geschiktheid blijft onbewezen. Laat je huidige setup voorlopig ongewijzigd."
    create = AsyncMock(return_value=SimpleNamespace(output_text=json.dumps({
        "saved_context": "",
        "user_proposal": "",
        "assessment_limit": "Actuele marktdata ontbreken, dus de geschiktheid blijft onbewezen.",
        "next_safe_step": "Laat je huidige setup voorlopig ongewijzigd.",
    })))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(
        side_effect=lambda **kwargs: kwargs["answer"] == rewrite,
    )
    result = FinnResponsesResult(
        "Wil je dat ik een marktevaluatie uitvoer?", "resp-evaluation-repeat", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "missing_required_scopes": ["market_snapshot"],
                "results": [{"scope": "read_active_setup", "status": "completed",
                             "data": {"name": "Coach DCA Basis", "setup_type": "dca"}}],
            },
        },),
    )
    answer = asyncio.run(verifier.verify(message="Past mijn plan bij mijn risicostijl?", result=result))
    assert answer.status == "completed" and answer.text == rewrite
    assert "FINN already attempted this evaluation" in create.await_args.kwargs["instructions"]
    assert "no current market/risk assessment has been performed" not in create.await_args.kwargs["instructions"]
    assert verifier._reoffers_attempted_evaluation(result.text)
    assert not verifier._reoffers_attempted_evaluation(rewrite)


def test_ambiguous_evaluation_can_ask_which_object_to_assess():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    text = (
        "Ik kan je actieve strategie nog niet beoordelen omdat de setup onduidelijk is. "
        "Welke setup wil je laten beoordelen?"
    )
    result = FinnResponsesResult(text, "resp-ambiguous-strategy", ({
        "name": "evaluate_strategy", "status": "partial", "result": {
            "evaluation_operation_id": "evaluate_strategy",
            "assessment_status": "insufficient_evidence",
            "missing_required_scopes": ["active_setup", "linked_strategy"],
            "results": [
                {"scope": "read_active_setup", "status": "unavailable",
                 "reason": "setup_ambiguous", "availability": "ambiguous"},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "setup_ambiguous", "availability": "ambiguous"},
            ],
        },
    },), model_led_coach=True)
    answer = asyncio.run(verifier.verify(message="Beoordeel mijn actieve strategie.", result=result))
    assert answer.status == "completed"
    assert answer.text == text


def test_model_led_read_uses_one_semantic_boundary_not_second_coach_audit():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(side_effect=AssertionError("second coach audit"))
    result = FinnResponsesResult(
        "Je opgeslagen setup heet BTC Basis. Of die bij je past, is nog niet beoordeeld.",
        "resp-read", ({"name": "get_active_plan_and_strategy", "status": "completed",
                       "result": {"results": [{"scope": "read_active_setup",
                                              "status": "completed",
                                              "data": {"name": "BTC Basis", "symbol": "BTC"}}]}},),
        model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(message="Welke setup heb ik?", result=result, locale="nl"))
    assert answer.status == "completed"
    verifier._personal_advice_is_grounded.assert_not_awaited()
    semantic.verify_async.assert_awaited_once()


def test_model_led_verified_read_rewrites_wrong_language_with_typed_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    create = AsyncMock(return_value=SimpleNamespace(
        output_text="De opgeslagen setup heet Atlas en gebruikt BTC op 4H.",
    ))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    result = FinnResponsesResult(
        "Das gespeicherte Setup heißt Atlas und verwendet BTC auf 4H.",
        "resp-german-draft", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "Atlas", "symbol": "BTC", "timeframe": "4H"}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(
        message="Zeige mir das aktuell gespeicherte Setup.", result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == "De opgeslagen setup heet Atlas en gebruikt BTC op 4H."
    create.assert_awaited_once()
    assert create.await_args.kwargs["model"] == "gpt-6-luna"


def test_model_led_hard_semantic_rejection_still_blocks_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unverified_personal_claim"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult(
        "Deze setup garandeert winst.", "resp-unsafe", (), model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(message="Wat vind je van mijn setup?", result=result, locale="nl"))
    assert answer.status != "completed" or answer.text != result.text


def test_general_stop_size_tradeoff_survives_setup_ambiguity():
    question = (
        "Kun je stopafstand en positieomvang afwegen zonder mijn plan te wijzigen?"
    )
    draft = (
        "Een ruimere stop vergroot het verlies per eenheid. Een kleinere "
        "positieomvang kan dezelfde vooraf gekozen risicogrens bewaken; "
        "ik kan geen specifieke opgeslagen BTC-setup aanwijzen."
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    result = FinnResponsesResult(
        draft, "resp-risk", (), model_led_coach=True,
        turn_contract={
            "question": question, "answer_type": "weigh", "targets": [],
            "requested_fields": ["stop_distance", "position_size"],
        },
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft


def test_source_independent_risk_lesson_uses_model_answer_without_setup_clarification():
    question = (
        "Puur als algemene risicoles: hoe kan een kleinere positie bij een "
        "ruimere stop hetzelfde maximale verlies begrenzen?"
    )
    draft = (
        "Je hebt gelijk: je vroeg naar stopafstand en positieomvang. "
        "Mijn vorige antwoord week daarvan af. Een ruimere stop vergroot "
        "het verlies per eenheid; een kleinere positie kan het berekende "
        "risico beperken als je haar evenredig verkleint. Kosten en "
        "slippage kunnen het werkelijke verlies beïnvloeden."
    )
    semantic = SimpleNamespace(verify_async=AsyncMock())
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message=question,
        result=FinnResponsesResult(
            draft, "resp-risk-lesson", (), model_led_coach=True,
            turn_contract={
                "question": question, "answer_type": "explain", "targets": [],
                "requested_fields": ["stop_distance", "position_size"],
            },
        ), locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text == draft
    semantic.verify_async.assert_not_called()


def test_model_led_fomo_rejection_returns_safe_coaching_instead_of_generic_fallback(monkeypatch):
    async def assess(_self, **_kwargs):
        return HardClaimBoundaryResult(True, (), {})

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        assess,
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    result = FinnResponsesResult(
        "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
        "resp-fomo", (), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Ik ben bang de beweging te missen en voel FOMO. Denk met me mee.",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "safe_emotional_coaching"
    assert "angst om een koersbeweging te missen" in answer.text
    assert "Welke concrete voorwaarde" in answer.text
    assert "betrouwbare gegevens" not in answer.text


def test_fomo_bypass_rejection_uses_safe_process_copy(monkeypatch):
    async def assess(_self, **_kwargs):
        return HardClaimBoundaryResult(True, ("condition_bypass",), {
            "condition_bypass_quote": "Neem alvast een kleine positie.",
        })

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        assess,
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Neem alvast een kleine positie.", "resp-unsafe-fomo", ({
            "name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "BTC DCA"}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(),
    ).verify(
        message="Ik ben bang de beweging te missen. Moet ik de wachtregel negeren?",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "safe_emotional_coaching"
    assert "kleine positie" not in answer.text
    assert "wachtregel die je beschrijft" in answer.text
    assert "Welke concrete voorwaarde" in answer.text


def test_model_led_coach_does_not_claim_an_unsaved_confirmation_condition():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Wacht op jouw bevestigingsvoorwaarde voordat je handelt.",
        "resp-condition", ({"name": "get_active_plan_and_strategy", "status": "completed",
                            "result": {"results": [{"scope": "read_active_setup",
                                                   "status": "completed",
                                                   "data": {"name": "BTC DCA"}}]}},),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Welke voorwaarde bedoel je?", result=result, locale="nl",
    ))
    assert answer.status == "clarification_required"
    assert answer.reason == "confirmation_condition_unverified"
    assert "Welke voorwaarde bedoel je" in answer.text
    semantic.verify_async.assert_not_awaited()


def test_unsaved_confirmation_in_fomo_followup_keeps_a_coach_answer():
    result = FinnResponsesResult(
        "Controleer jouw bevestigingsvoorwaarde.", "resp-fomo-condition", ({
            "name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "BTC DCA"}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Wat moet ik met FOMO doen terwijl ik op bevestiging wacht?",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "safe_emotional_coaching"
    assert "Schrijf" in answer.text and "voorwaarde" in answer.text
    assert "jouw bevestigingsvoorwaarde" not in answer.text


def test_frustration_fallback_stays_a_process_question():
    answer = FinnResponsesAnswerVerifier._emotional_coach_fallback(
        "Ik ben gefrustreerd omdat mijn plan me steeds tegenhoudt.", "nl",
    )
    assert "Dat klinkt frustrerend" in answer
    assert "Welke beslissing" in answer
    assert "trade" not in answer


def test_saved_confirmation_condition_is_allowed_by_source_guard():
    assert not FinnResponsesAnswerVerifier._unsupported_personal_confirmation(
        "Controleer jouw bevestigingsvoorwaarde.",
        ({"scope": "read_active_setup", "status": "completed",
          "data": {"confirmation_condition": "dagcandle sluit boven weerstand"}},),
    )


def test_saved_confirmation_question_requires_a_read_and_uses_verified_absence():
    question = "Welke bevestigingsregel staat in mijn opgeslagen BTC 4H-setup?"
    assert _saved_confirmation_readback(question)
    assert _saved_confirmation_readback(question.rstrip("?"))
    assert not _saved_confirmation_readback("Waarom kan een bevestigingsregel helpen?")
    fake = FakeResponses(
        response("read-rule", calls=(tool_call("rule-call", "get_active_plan_and_strategy", {
            "asset": "BTC", "timeframe": "4H",
        }),)),
        response("rule-answer", text="Ik kan dit nog niet onderbouwen met betrouwbare gegevens."),
    )
    read = {"status": "partial", "results": [
        {"scope": "read_active_setup", "status": "completed",
         "data": {"setup_id": 7, "name": "BTC 4H", "timeframe": "4H"}},
        {"scope": "read_linked_strategy", "status": "unavailable",
         "reason": "strategy_not_resolved", "data": None},
    ]}
    loop = FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=AsyncMock(return_value=read))
    result = asyncio.run(loop.run(
        message=question, instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
        model_led_coach=True, locale="nl",
    ))
    assert fake.requests[0]["tool_choice"] == "auto"
    assert result.tool_trace[0]["name"] == "get_active_plan_and_strategy"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "saved_confirmation_readback"
    assert "geen concrete bevestigings- of entryregel" in answer.text
    assert "BTC 4H" in answer.text
    assert "betrouwbare gegevens" not in answer.text


def test_model_owned_verifier_returns_rejection_instead_of_replacement_copy():
    question = "Welke bevestigingsregel staat in mijn opgeslagen BTC 4H-setup?"
    draft = "Ik kan dit nog niet onderbouwen met betrouwbare gegevens."
    result = FinnResponsesResult(
        draft, "model-draft", ({"result": {"results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"setup_id": 7, "name": "BTC 4H", "timeframe": "4H"}},
            {"scope": "read_linked_strategy", "status": "unavailable",
             "reason": "strategy_not_resolved", "data": None},
        ]}},), model_led_coach=True, model_owned_repair=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "responses_evidence_not_verified"
    assert answer.rejection_details["replacement_reason"] == "saved_confirmation_readback"
    assert "geen concrete bevestigings- of entryregel" not in answer.text


def test_saved_confirmation_question_names_ambiguous_matching_setups():
    question = (
        "Welke bevestigingsvoorwaarde staat concreet in mijn opgeslagen 4H-setup? "
        "En welke van mijn BTC-setups bedoel je eigenlijk?"
    )
    setups = [
        {"setup_id": 7, "name": "BTC 4H Voorzichtig", "symbol": "BTC", "timeframe": "4H"},
        {"setup_id": 8, "name": "BTC 4H Alternatief", "symbol": "BTC", "timeframe": "4H"},
        {"setup_id": 9, "name": "BTC DCA", "symbol": "BTC", "timeframe": "1D"},
    ]
    result = FinnResponsesResult(
        "Er staat geen regel in je setup.", "saved-rule-multi",
        ({"result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                "data": {**setups[0], "setups": setups}}]}},),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.reason == "saved_confirmation_readback"
    assert "BTC 4H Voorzichtig" in answer.text
    assert "BTC 4H Alternatief" in answer.text
    assert "BTC DCA" not in answer.text
    assert "Welke bedoel je?" in answer.text
    assert "geen concrete bevestigings" not in answer.text


def test_hypothetical_trade_reflection_uses_no_action_tools():
    question = (
        "Stel: ik nam deze maand 8 impulsieve trades, 6 verlies en 2 winst, "
        "samen -4,2%. Wat is volgens jou het belangrijkste patroon en welke "
        "ene regel zou ik volgende week testen?"
    )
    assert _hypothetical_trade_reflection(question)
    assert not _hypothetical_trade_reflection("Maak een setup om mijn trades te evalueren.")
    assert not FinnResponsesAnswerVerifier._unsupported_personal_confirmation(
        "Noteer je bevestigingsvoorwaarde voordat je een trade overweegt.", (), question,
    )
    assert not FinnResponsesAnswerVerifier._unsupported_personal_confirmation(
        "Gebruik alleen een bevestigingsvoorwaarde die je vooraf formuleert.", (), question,
    )
    assert FinnResponsesAnswerVerifier._unsupported_personal_confirmation(
        "Je bevestigingsvoorwaarde is opgeslagen en geldt voor deze trade.", (), question,
    )
    assert FinnResponsesAnswerVerifier._unsupported_personal_confirmation(
        "Volg je bevestigingsvoorwaarde.", (),
        "Welke voorwaarde staat in mijn opgeslagen setup?",
    )
    fake = FakeResponses(response("reflection", text="Het patroon is impulsiviteit. Test eerst een vaste pauze."))
    loop = FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=AsyncMock())
    result = asyncio.run(loop.run(
        message=question, instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
        model_led_coach=True, locale="nl",
    ))
    assert fake.requests[0]["tool_choice"] == "auto"
    assert all(not tool["name"].startswith("propose_") for tool in fake.requests[0]["tools"])
    assert result.tool_trace == ()


@pytest.mark.parametrize("question", [
    "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?",
    "Stel: ik nam 8 impulsieve trades, 6 verlies en 2 winst. Wat is het patroon en welke regel zou ik testen?",
])
def test_standalone_coach_questions_do_not_inherit_unrelated_setup_read(question):
    fake = FakeResponses(response("coach", text="Ik beoordeel alleen je huidige vraag."))
    loop = FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=AsyncMock())
    result = asyncio.run(loop.run(
        message=question, instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
        previous_response_id="previous-setup-response",
        previous_verified_answer="Je BTC 4H-setup heeft geen opgeslagen bevestigingsregel.",
        verified_turn_context={"answer": "BTC 4H-setup", "evidence": [{"scope": "read_active_setup"}]},
        model_led_coach=True, locale="nl",
    ))
    assert fake.requests[0]["previous_response_id"] == "previous-setup-response"
    assert fake.requests[0]["input"][-1]["role"] == "user"
    assert result.tool_trace == ()


def test_hypothetical_trade_reflection_timeout_does_not_forge_coaching():
    question = (
        "Stel: ik nam deze maand 8 impulsieve trades, 6 verlies en 2 winst, "
        "samen -4,2%. Wat is het belangrijkste patroon en welke ene regel zou ik testen?"
    )

    async def slow_response(**_kwargs):
        await asyncio.sleep(0.05)

    provider = SimpleNamespace(create=AsyncMock(side_effect=slow_response))
    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=provider), executor=AsyncMock(),
        provider_timeout_seconds=0.01,
    )
    with pytest.raises(FinnResponsesError, match="responses_provider_timeout"):
        asyncio.run(loop.run(
            message=question, instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
            model_led_coach=True, locale="nl",
        ))
    request = provider.create.await_args.kwargs
    assert request["tool_choice"] == "auto"
    assert all(not tool["name"].startswith("propose_") for tool in request["tools"])


def test_first_provider_call_retries_one_transient_server_failure():
    class TransientProviderError(Exception):
        status_code = 503

    fake = FakeResponses(
        TransientProviderError("temporary provider failure"),
        response("after-retry", text="BTC Full Base staat op 4H."),
    )
    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=AsyncMock(),
    )
    result = asyncio.run(loop.run(
        message="Wat is mijn BTC-setup?", instructions="Gebruik alleen bevestigde gegevens.",
        model_led_coach=True, locale="nl",
    ))
    assert result.text == "BTC Full Base staat op 4H."
    assert len(fake.requests) == 2


def test_read_only_answer_retries_one_transient_failure_after_evidence_read():
    class TransientProviderError(Exception):
        status_code = 503

    fake = FakeResponses(
        response("profile-read", calls=(tool_call("profile-call", "get_my_profile_and_risk_style", {}),)),
        TransientProviderError("temporary provider failure"),
        response("answer", text="Je opgeslagen profiel helpt als context, niet als handelssignaal."),
    )
    executions = []

    async def execute(call):
        executions.append(call.name)
        return {"status": "completed", "results": [{"scope": "read_profile", "status": "completed"}]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat weet je van mijn profiel?", instructions="Gebruik bewijs", model_led_coach=True))

    assert result.text.startswith("Je opgeslagen profiel")
    assert executions == ["get_my_profile_and_risk_style"]
    assert len(fake.requests) == 3
    assert fake.requests[1]["previous_response_id"] == fake.requests[2]["previous_response_id"]
    assert result.tool_trace[0]["status"] == "completed"


def test_read_only_answer_retries_one_timeout_after_evidence_read():
    fake = FakeResponses(
        response("profile-read", calls=(tool_call("profile-call", "get_my_profile_and_risk_style", {}),)),
        TimeoutError("temporary timeout"),
        response("answer", text="Ik heb je profiel gelezen."),
    )

    async def execute(_call):
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wanneer is mijn profiel gelezen?", instructions="Gebruik bewijs", model_led_coach=True))

    assert result.text == "Ik heb je profiel gelezen."
    assert len(fake.requests) == 3


def test_rule_objection_does_not_replace_stop_size_question_with_waiting_copy():
    draft = "Een ruimere stop vergroot het verlies per eenheid; een kleinere positie kan hetzelfde maximale verlies begrenzen."
    fake = FakeResponses(response("objection-draft", text=draft))
    loop = FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=AsyncMock())
    asyncio.run(loop.run(
        message="Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor de stop niet verstandiger kunnen zijn? Denk kritisch mee zonder een nieuw niveau te verzinnen.",
        instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
        previous_verified_answer="Weghalen van je stop-loss is geen veilige regel.",
        model_led_coach=True, locale="nl",
    ))
    assert fake.requests[0]["tool_choice"] == "auto"
    result = FinnResponsesResult(
        draft, "rule-objection", (),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor de stop niet verstandiger kunnen zijn?",
        result=result, previous_response={"answer": "Weghalen van je stop-loss is geen veilige regel."},
        locale="nl",
    ))
    assert answer.reason != "rule_objection_coaching"
    assert "wachttijd" not in answer.text


def test_read_only_stop_loss_timeout_does_not_forge_coaching():
    question = (
        "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. "
        "Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?"
    )
    assert _read_only_stop_loss_coaching(question)
    assert not _read_only_stop_loss_coaching("Verwijder mijn stop-loss nu.")

    async def slow_response(**_kwargs):
        await asyncio.sleep(0.05)

    provider = SimpleNamespace(create=AsyncMock(side_effect=slow_response))
    loop = FinnResponsesLoop(
        client=SimpleNamespace(responses=provider), executor=AsyncMock(),
        provider_timeout_seconds=0.01,
    )
    with pytest.raises(FinnResponsesError, match="responses_provider_timeout"):
        asyncio.run(loop.run(
            message=question, instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
            model_led_coach=True, locale="nl",
        ))
    request = provider.create.await_args.kwargs
    assert request["tool_choice"] == "auto"
    assert all(not tool["name"].startswith("propose_") for tool in request["tools"])


def test_stop_loss_coach_does_not_offer_a_mental_exit_as_order_substitute():
    question = (
        "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. "
        "Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?"
    )
    result = FinnResponsesResult(
        "Een grens hoeft niet per se een order te zijn.", "mental-stop-draft", (),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.reason == "safe_stop_loss_coaching"
    assert "stop-loss niet uit angst" in answer.text


def test_priority_coaching_keeps_three_safe_steps_when_live_sources_are_missing():
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._ungrounded_level_advice(
        "Wat is de voorwaarde waarop jouw plan pas een entry toestaat?"
    )
    assert verifier._ungrounded_level_advice("Pas je stop-loss aan.")
    result = FinnResponsesResult(
        "Ik kan vandaag geen drie acties geven.", "priority-draft",
        ({"name": "evaluate_plan", "result": {
            "evaluation_operation_id": "evaluate_plan",
            "assessment_status": "insufficient_evidence",
            "results": [
                {"scope": "read_linked_strategy", "status": "completed", "data": {
                    "name": "BTC Strategie", "entry": "80000", "stop_loss": "76000",
                    "targets": ["88000", "92000"],
                }},
                {"scope": "read_market_snapshot", "status": "unavailable",
                 "reason": "source_unavailable", "data": None},
            ],
        }},), model_led_coach=True,
    )
    answer = asyncio.run(verifier.verify(
        message="Wat zijn vandaag mijn drie belangrijkste acties voor mijn bestaande BTC-plan, en wat moet ik juist laten liggen?",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "insufficient_evidence"
    assert all(f"{number}." in answer.text for number in (1, 2, 3))
    assert "Laat liggen:" in answer.text


def test_stop_loss_coach_does_not_deny_saved_level_without_a_read():
    question = (
        "Ik wil mijn stop-loss weghalen omdat ik bang ben uitgestopt te worden. "
        "Spreek me tegen; wijzig niets."
    )
    result = FinnResponsesResult(
        "Ik heb geen opgeslagen stopniveau om te beoordelen.", "stop-draft", (),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "safe_stop_loss_coaching"
    assert "geen opgeslagen stopniveau" not in answer.text


def test_stop_loss_coach_uses_safe_reply_before_terminal_deadline(monkeypatch):
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.remaining_lifecycle_seconds",
        lambda: 4.5,
    )
    result = FinnResponsesResult(
        "Ik wil jouw situatie eerst grondig bekijken.", "late-stop", (),
        model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Ik wil mijn stop-loss weghalen. Spreek me tegen; wijzig niets.",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "safe_stop_loss_coaching"
    assert "Ik wijzig niets" in answer.text


def test_outcome_guard_allows_negated_probability_assessment_but_blocks_positive_claim():
    guard = FinnResponsesAnswerVerifier._promises_unverified_trading_outcome
    assert not guard("Dit is alleen niveau-rekenwerk, geen beoordeling van de kans op succes.")
    assert not guard("This is not an assessment of the chance of success.")
    assert guard("Deze strategie heeft een hoge kans op succes.")
    assert guard("Geen beoordeling van de koers, maar de kans op winst is hoog.")
    quoted = FinnV2HardClaimBoundary._negated_outcome_assessment
    assert quoted("Dat is geen bewijs dat de trade kansrijk is.", "de trade kansrijk is")
    assert quoted("Dat is geen bewijs dat de trade kansrijk is.", "geen bewijs dat de trade kansrijk is")
    assert not quoted("Geen bewijs voor vandaag, maar de trade is kansrijk.", "de trade is kansrijk")
    assert not quoted("De trade heeft een hoge kans op winst.", "hoge kans op winst")


def test_rejected_plan_review_uses_only_verified_strategy_structure():
    question = "Beoordeel mijn BTC-plan als coach. Wat is sterk, waar rem je me af en wat is mijn check?"
    evidence = (
        {"scope": "read_linked_strategy", "status": "completed",
         "data": {"entry": 80000, "stop_loss": 76000, "targets": [88000]}},
    )
    fallback = FinnResponsesAnswerVerifier._grounded_plan_review_fallback(question, evidence, "nl")
    assert fallback is not None
    assert all(phrase in fallback for phrase in ("Sterk:", "Waar ik je afrem:", "Eerstvolgende check:"))
    assert "80000" not in fallback and "geen actuele" not in fallback
    assert FinnResponsesAnswerVerifier._grounded_plan_review_fallback(question, (), "nl") is None
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    result = FinnResponsesResult(
        "Deze strategie heeft een hoge kans op winst.", "review-rejected", ({
            "name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": list(evidence)},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "grounded_plan_review"
    assert "hoge kans op winst" not in answer.text


def test_limited_personal_plan_answer_preserves_proposal_and_stays_read_only():
    evidence = (
        {"scope": "read_profile", "status": "completed",
         "data": {"trader_profile": {"risk_profiles": ["conservative"]}}},
        {"scope": "read_active_setup", "status": "completed",
         "data": {"symbol": "BTC", "setup_type": "dca", "dca_frequency": "daily"}},
    )
    trace = ({"name": "evaluate_plan", "result": {"assessment_status": "insufficient_evidence"}},)
    fallback = FinnResponsesAnswerVerifier._limited_personal_plan_fallback
    proposal = fallback(
        "Mijn BTC-plan is dagelijkse DCA, maar ik denk aan 100 euro per week. Past dat bij mijn risicostijl?",
        evidence, trace, "nl",
    )
    assert proposal is not None
    assert "€100 per week" in proposal and "jouw voorstel" in proposal
    assert "niet beoordelen" in proposal and "Welke van die twee" in proposal
    review = fallback(
        "Beoordeel nu mijn volledige BTC-plan en mijn risicostijl.", evidence, trace, "nl",
    )
    assert review is not None and "nog niet" in review and "geen instapsignaal" in review
    assert fallback("Beoordeel mijn plan", evidence, (), "nl") is None
    assert fallback("Beoordeel mijn plan", evidence[:1], trace, "nl") is None


def test_rejected_personal_dca_assessment_finishes_without_a_repair_round():
    question = (
        "Mijn huidige BTC-plan is dagelijkse DCA, maar ik denk aan 100 euro per week. "
        "Past dat bij mijn voorzichtige risicostijl?"
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    result = FinnResponsesResult(
        "Een onjuiste persoonlijke beoordeling.", "limited-dca", ({
            "name": "evaluate_plan", "status": "partial",
            "result": {"assessment_status": "insufficient_evidence", "results": [
                {"scope": "read_profile", "status": "completed",
                 "data": {"trader_profile": {"risk_profiles": ["conservative"]}}},
                {"scope": "read_active_setup", "status": "completed",
                 "data": {"symbol": "BTC", "setup_type": "dca", "dca_frequency": "daily"}},
            ]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=question, result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "limited_personal_plan"
    assert "€100 per week" in answer.text
    assert "niet beoordelen" in answer.text


def test_risk_distance_percentage_is_grounded_in_saved_strategy_geometry():
    assert FinnResponsesAnswerVerifier._percentage_claims_supported(
        answer="De risicoafstand is 5% van de entry.", message="Beoordeel mijn plan.",
        previous_answer="", response_focus=None,
        evidence=({"scope": "read_linked_strategy", "status": "completed",
                   "data": {"level_geometry": {
                       "status": "completed", "entry_stop_distance_percent": "5.00",
                   }}},),
    )


def test_model_led_ratio_question_uses_typed_static_geometry_when_draft_is_rejected():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unverified_personal_claim"],
    )))
    geometry = {
        "status": "completed", "risk_per_unit": "4000", "entry_stop_distance_percent": "5.00",
        "targets": [
            {"price": "88000", "reward_per_unit": "8000", "reward_to_risk": "2.00"},
            {"price": "92000", "reward_per_unit": "12000", "reward_to_risk": "3.00"},
        ],
    }
    result = FinnResponsesResult(
        "Deze strategie levert gegarandeerd winst op.", "resp-ratio", ({
            "name": "get_active_plan_and_strategy", "status": "completed",
            "result": {"results": [{"scope": "read_linked_strategy", "status": "completed",
                                   "data": {"name": "BTC Breakout", "level_geometry": geometry}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Wat zegt de verhouding tussen risico en potentiële opbrengst?",
        result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.reason == "static_level_geometry"
    assert "2:1" in answer.text and "3:1" in answer.text
    assert "geen oordeel over de huidige markt" in answer.text
    semantic.verify_async.assert_not_awaited()


def test_model_led_horizon_question_asks_for_missing_holding_period():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Dat kan ik niet classificeren.", "resp-horizon", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "BTC DCA", "timeframe": "4H"}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Is mijn 4H DCA-setup langetermijnopbouw of een swingtrade?",
        result=result, locale="nl",
    ))
    assert answer.status == "clarification_required"
    assert answer.reason == "investment_horizon_required"
    assert "lange termijn" in answer.text
    semantic.verify_async.assert_not_awaited()


def test_static_geometry_does_not_replace_a_different_hypothetical_trade():
    evidence = ({"scope": "read_linked_strategy", "status": "completed", "data": {
        "entry": "80000", "stop_loss": "76000", "targets": ["88000", "92000"],
    }},)
    assert FinnResponsesAnswerVerifier._question_matches_saved_geometry(
        "Wat is de verhouding bij entry 80000 en stop 76000?", evidence,
    )
    assert not FinnResponsesAnswerVerifier._question_matches_saved_geometry(
        "Wat is de verhouding bij entry 90000 en stop 76000?", evidence,
    )


def test_model_led_horizon_reply_does_not_repeat_the_clarification_question():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Beoog je lange termijn of een swingtrade?", "resp-repeat", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "BTC DCA", "setup_type": "dca", "timeframe": "4H"}}]},
        },), model_led_coach=True, uses_previous_response=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Voor de lange termijn, ongeveer vijf jaar.", result=result, locale="nl",
        previous_response={
            "terminal_status": "clarification_required",
            "terminal_reason": "investment_horizon_required",
            "answer": "Beoog je opbouw voor de lange termijn of kortere trades?",
            "tool_trace": [{"result": {"results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"name": "BTC DCA", "setup_type": "dca", "timeframe": "4H"},
            }]}}],
        },
    ))
    assert answer.status == "completed"
    assert "vijf jaar" in answer.text
    assert "DCA-setup" in answer.text
    assert "?" not in answer.text
    semantic.verify_async.assert_not_awaited()


def test_unrelated_followup_after_horizon_question_is_not_treated_as_horizon_answer():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Dat is een andere vraag; welke gegevens bedoel je?", "resp-new-question", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True}, "result": {"results": []},
        },), model_led_coach=True, uses_previous_response=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Hoeveel BTC heb ik nu?", result=result, locale="nl",
        previous_response={
            "terminal_status": "clarification_required",
            "terminal_reason": "investment_horizon_required",
            "answer": "Beoog je opbouw voor de lange termijn of kortere trades?",
        },
    ))
    assert answer.reason != "user_detail_acknowledged"


def test_rejected_horizon_fit_claim_keeps_safe_user_detail_acknowledgement(monkeypatch):
    async def assess(_self, **_kwargs):
        return HardClaimBoundaryResult(True, ("personal_fit",), {
            "personal_fit_quote": "past deze opzet qua bedoeling bij langetermijnopbouw",
        })

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        assess,
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Met jouw horizon van vijf jaar past deze opzet qua bedoeling bij langetermijnopbouw.",
        "resp-fit-horizon", ({
            "name": "get_active_plan_and_strategy", "status": "partial",
            "result": {"results": [{"scope": "read_active_setup", "status": "completed",
                                   "data": {"name": "BTC DCA", "setup_type": "dca", "timeframe": "4H"}}]},
        },), model_led_coach=True, uses_previous_response=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(),
    ).verify(
        message="Voor de lange termijn, ongeveer vijf jaar.", result=result, locale="nl",
        previous_response={
            "terminal_status": "clarification_required",
            "terminal_reason": "investment_horizon_required",
            "answer": "Beoog je opbouw voor de lange termijn of kortere trades?",
        },
    ))
    assert answer.status == "completed"
    assert answer.reason == "user_detail_acknowledged"
    assert "DCA-setup" in answer.text and "vijf jaar" in answer.text
    assert "past deze opzet" not in answer.text


def test_model_led_suitability_answer_attributes_user_proposed_amount():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Ik kan niet beoordelen of €100 per week bij je past; dat bedrag staat niet in je setup.",
        "resp-proposal", (), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Ik denk aan 100 euro per week. Past dat bij mij?", result=result, locale="nl",
    ))
    assert answer.status == "completed"
    assert answer.text.startswith("Je overweegt 100 euro per week.")
    assert "staat niet in je setup" in answer.text


def test_model_led_setup_called_strategy_returns_typed_fact_boundary():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "Je hebt een DCA-strategie voor Bitcoin, maar actuele marktdata ontbreken.",
        "resp-setup-not-strategy", ({
            "name": "evaluate_plan", "status": "partial", "result": {
                "evaluation_operation_id": "evaluate_plan",
                "assessment_status": "insufficient_evidence",
                "results": [
                    {"scope": "read_active_setup", "status": "completed",
                     "data": {"name": "BTC Basis", "setup_type": "dca"}},
                    {"scope": "read_linked_strategy", "status": "unavailable",
                     "reason": "strategy_not_resolved"},
                ],
            },
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(),
    ).verify(message="Beoordeel mijn BTC-plan", result=result, locale="nl"))
    assert answer.status == "unavailable"
    assert answer.reason == "saved_entity_type_unverified"
    assert answer.rejection_details == {"verified_entity_types": ["setup"]}


def test_model_led_rejected_fit_exposes_exact_span_for_one_model_repair(monkeypatch):
    async def assess(_self, **_kwargs):
        return HardClaimBoundaryResult(True, ("personal_fit",), {
            "personal_fit_quote": "100 euro per week past bij je risicostijl",
        })

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_answer_verifier.FinnV2HardClaimBoundary.assess",
        assess,
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "100 euro per week past bij je risicostijl.", "resp-fit", ({
            "name": "get_my_profile_and_risk_style", "status": "completed",
            "result": {"results": [{"scope": "read_profile", "status": "completed",
                                   "data": {"has_profile": True, "trader_profile": {
                                       "risk_profiles": ["conservative"],
                                   }}}]},
        },), model_led_coach=True,
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(),
    ).verify(message="Past €100 per week bij mij?", result=result, locale="nl"))
    assert answer.status == "unavailable"
    assert answer.reason == "personal_fit_not_established"
    assert answer.rejection_details == {"unsupported_claims": {
        "personal_fit_quote": "100 euro per week past bij je risicostijl",
    }}


def test_saved_dca_setup_cannot_be_reported_as_saved_strategy():
    evidence = ({"scope": "read_active_setup", "status": "completed",
                 "data": {"name": "Coach DCA Basis", "setup_type": "dca"}},
                {"scope": "read_linked_strategy", "status": "unavailable",
                 "reason": "strategy_not_resolved"})
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._saved_entity_type_supported(
        "Je hebt een dagelijkse DCA-strategie voor BTC.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Je BTC-plan is gebaseerd op een DCA-strategie met dagelijkse frequentie.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Je huidige plan is een dagelijkse DCA-strategie.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Your current setup involves a daily Dollar-Cost Averaging (DCA) strategy for Bitcoin.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Wacht voordat u uw strategie aanpast.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Ik kan die regel niet uit je opgeslagen strategie halen.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Ihre Strategie ist noch nicht geprüft.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Bis frische Marktdaten verfügbar sind, bleibt deine Strategie unverändert.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Aktuelle Marktdaten fehlen für eine Beurteilung deiner DCA-Strategie.", evidence,
    )
    assert verifier._saved_entity_type_supported(
        "Je opgeslagen DCA-setup gebruikt dagelijkse aankopen; een strategie is niet gevonden.", evidence,
    )
    assert verifier._saved_entity_type_supported(
        "Er is nog geen gekoppelde strategie. Wil je een strategie ontwerpen?", evidence,
    )
    assert verifier._saved_entity_type_supported(
        "Je hebt een dagelijks DCA-setup voor BTC, maar er is geen gekoppelde strategie.", evidence,
    )
    assert not verifier._saved_entity_type_supported(
        "Consider revisiting your strategy.", (), user_message="My BTC plan says to wait.",
    )
    assert verifier._saved_entity_type_supported(
        "Let's discuss your strategy as you describe it.", (),
        user_message="I want to discuss my strategy.",
    )


def test_followup_reuses_prior_owner_scoped_setup_evidence_for_entity_guard():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "run_id": "prior-run", "answer": "Dein DCA-Setup ist gespeichert.",
        "tool_trace": [{"result": {"results": [
            {"scope": "read_active_setup", "status": "completed", "data": {"name": "Coach DCA Basis"}},
            {"scope": "read_linked_strategy", "status": "unavailable", "reason": "strategy_not_resolved"},
        ]}}],
    }
    current = FinnResponsesResult(
        "Bis frische Marktdaten verfügbar sind, bleibt deine Strategie unverändert.",
        "resp-2", ({"name": "answer_directly", "status": "completed",
                    "arguments": {"uses_previous_response": True},
                    "result": {"status": "completed", "results": []}},),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Warum?", result=current, previous_response=previous, locale="de",
    ))
    assert verified.status != "completed"
    assert "deine Strategie unverändert" not in verified.text


def test_followup_verifier_distinguishes_user_stated_rule_from_saved_fact():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "run_id": "prior-run",
        "answer": "Je noemde wachten op bevestiging als je eigen regel; ik heb niet vastgesteld of het signaal er nu is.",
        "tool_trace": [],
    }
    current = FinnResponsesResult(
        "Omdat je bevestiging zelf als voorwaarde noemde. Wachten garandeert geen betere uitkomst.",
        "resp-2", (),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?", result=current, previous_response=previous, locale="nl",
    ))
    guidance = semantic.verify_async.await_args.kwargs["verification_guidance"]
    assert "user-stated" in guidance
    assert verified.status == "completed"


def test_german_coach_answer_is_not_blocked_by_a_formal_register_regex():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "run_id": "prior-run",
        "answer": "Du wolltest erst nach einem klaren Signal handeln.",
        "tool_trace": [],
    }
    current = FinnResponsesResult(
        "Ihr Zweck ist, deine Entscheidung an deinen eigenen Kriterien zu messen. "
        "Das garantiert weder einen besseren Einstieg noch schützt es vor Verlusten.",
        "resp-2", (),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Warum ist diese Prüfung sinnvoll?", result=current,
        previous_response=previous, locale="de",
    ))
    assert verified.status == "completed"


def test_rejected_why_answer_uses_typed_prior_evaluation_limit_instead_of_generic_error():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "run_id": "prior-run", "answer": "Die Eignung kann ich ohne aktuelle Marktdaten nicht beurteilen.",
        "tool_trace": [{"name": "evaluate_plan", "result": {
            "assessment_status": "insufficient_evidence",
            "missing_required_scopes": ["market_snapshot"],
            "results": [
                {"scope": "read_profile", "status": "completed",
                 "data": {"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}}},
                {"scope": "read_active_setup", "status": "completed", "data": {"name": "Coach DCA"}},
                {"scope": "read_linked_strategy", "status": "unavailable"},
                {"scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable"},
            ],
        }}],
    }
    current = FinnResponsesResult(
        "Aktuelle Marktdaten fehlen für eine Beurteilung deiner DCA-Strategie.",
        "resp-2", ({"name": "answer_directly", "status": "completed",
                    "arguments": {"uses_previous_response": True},
                    "result": {"status": "completed", "results": []}},),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Warum?", result=current, previous_response=previous, locale="de",
    ))
    assert verified.status == "completed"
    assert "Marktdaten" in verified.text
    assert "Risikoprofil ist vorhanden" in verified.text
    assert "Strategie" not in verified.text


@pytest.mark.parametrize("claim", [
    "100 euro per week past goed bij jouw conservatieve aanpak.",
    "Weekly DCA fits well with your conservative risk style.",
    "Wöchentliche DCA passt gut zu deinem vorsichtigen Risikostil.",
])
def test_preliminary_positive_personal_fit_claim_is_not_safe_evidence(claim):
    assert FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(claim)
    assert not FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(
        "Ik kan nog niet zeggen of dit bij je risicostijl past."
    )


def test_resolved_setup_choice_verifies_original_request_not_prior_question():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult("De gekozen setup is BTC 4H.", "resp-choice", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "symbol": "BTC", "timeframe": "4H"},
        }]},
    },))
    message = "Original user request: Wat is mijn plan?\nUser's chosen answer: BTC Plan"
    answer = asyncio.run(verifier.verify(
        message=message, result=result,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert answer.status == "completed"
    kwargs = semantic.verify_async.await_args.kwargs
    assert kwargs["mode"] == "READ"
    assert kwargs["user_message"] == message
    assert all(item["scope"] != "previous_response" for item in kwargs["compact_evidence"])
    assert "permitted_limited_answer" in kwargs["deterministic_summary"]
    assert "missing_profile_established" not in kwargs["deterministic_summary"]
    assert "IS a complete, safe answer" in kwargs["verification_guidance"]


@pytest.mark.parametrize(
    ("unsupported", "addresses", "expected"),
    [(False, True, True), (False, False, False), (True, True, False)],
)
def test_personal_advice_audit_checks_safety_and_original_question(
    unsupported, addresses, expected,
):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": unsupported,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": addresses,
    }))
    create = AsyncMock(return_value=response)
    verifier = FinnResponsesAnswerVerifier(
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer="De opgeslagen setup is bekend; passendheid is nog niet beoordeeld.",
        evidence=[{"scope": "read_active_setup", "status": "completed",
                   "data": {"name": "BTC Plan"}}],
        question="Wat is een logisch plan voor mij? BTC Plan",
        remaining=20,
    ))
    assert actual is expected
    assert "Wat is een logisch plan" in create.await_args.kwargs["input"]


def test_personal_advice_audit_rejects_premature_change_after_limited_evaluation():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": True,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
    }))
    create = AsyncMock(return_value=response)
    verifier = FinnResponsesAnswerVerifier(
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer="Ik kan passendheid niet vaststellen. Wil je de setup nu aanpassen?",
        evidence=[{"scope": "evaluation_boundary", "status": "completed", "data": {
            "assessment_status": "insufficient_evidence",
        }}],
        question="Past 100 euro per week bij mijn risicostijl?",
        remaining=20,
    ))
    assert actual is False
    assert "premature_action_invitation" in create.await_args.kwargs["instructions"]


@pytest.mark.parametrize("omitted,expected", [(True, False), (False, True)])
def test_personal_advice_audit_requires_proposed_change_to_survive_answer(omitted, expected):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": omitted,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "actionable_next_decision": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert asyncio.run(verifier._personal_advice_is_grounded(
        answer="Ik kan dit zonder actuele data niet beoordelen.",
        evidence=[{"scope": "read_active_setup", "status": "completed",
                   "data": {"name": "BTC Plan", "min_investment": None}}],
        question="Past mijn voorstel van 100 euro per week bij mijn risicostijl?",
        remaining=20,
    )) is expected


@pytest.mark.parametrize("unsupported,expected", [(False, True), (True, False)])
def test_grounded_next_decision_keeps_safety_audit_without_second_address_vote(unsupported, expected):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": unsupported,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": False,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert asyncio.run(verifier._personal_advice_is_grounded(
        answer="Laat je huidige setup voorlopig ongewijzigd.",
        evidence=[{"scope": "antecedent_verified_response", "status": "completed",
                   "data": {"answer": "Je kunt de setup ongewijzigd laten."}}],
        question="Welke keuze maak ik eerst?", remaining=20,
        require_address_judgment=False,
    )) is expected


@pytest.mark.parametrize("actionable,expected", [(True, True), (False, False)])
def test_grounded_next_decision_requires_independent_actionability_vote(actionable, expected):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": False,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "actionable_next_decision": actionable,
    }))
    create = AsyncMock(return_value=response)
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=create),
    ))
    assert asyncio.run(verifier._personal_advice_is_grounded(
        answer=("Laat de opgeslagen setup voorlopig ongewijzigd." if actionable else
                "Kies welke ontbrekende marktgegevens je wilt onderzoeken."),
        evidence=[{"scope": "previous_response", "status": "completed",
                   "data": {"answer": "Passendheid is zonder marktdata onbekend."}}],
        question="Welke keuze moet ik nu eerst maken?", remaining=20,
        require_address_judgment=False, require_actionable_next_decision=True,
    )) is expected
    assert "actionable_next_decision" in create.await_args.kwargs["text"]["format"]["schema"]["required"]


def test_next_decision_need_not_repeat_proposal_from_prior_question():
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": False,
        "unsupported_entity_claim": False,
        "proposed_as_saved": False,
        "proposed_change_omitted": True,
        "premature_action_invitation": False,
        "language_mismatch": False,
        "unnatural_language": False,
        "addresses_request": True,
        "actionable_next_decision": True,
    }))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
    ))
    assert asyncio.run(verifier._personal_advice_is_grounded(
        answer="Je kunt de huidige setup voorlopig ongewijzigd laten.",
        evidence=[{"scope": "previous_response", "status": "completed",
                   "data": {"answer": "De geschiktheid van je voorstel is nog onbekend."}}],
        question="Welke keuze moet ik nu eerst maken?", remaining=20,
        require_address_judgment=False, require_actionable_next_decision=True,
    )) is True


def test_failed_next_decision_uses_verified_typed_evaluation_boundary():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(side_effect=[False, True])
    result = FinnResponsesResult(
        "Wacht op marktinformatie.", "resp-next", ({
            "name": "answer_directly", "status": "completed",
            "arguments": {"uses_previous_response": True}, "result": {"results": []},
        },), "grounded_next_decision",
    )
    previous = {
        "answer": "Ik kan de geschiktheid niet beoordelen zonder actuele gegevens.",
        "tool_trace": [{"name": "evaluate_plan", "status": "partial", "result": {
            "assessment_status": "insufficient_evidence", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"name": "BTC Plan"},
            }],
        }}],
    }
    answer = asyncio.run(verifier.verify(
        message="Welke keuze moet ik nu eerst maken?", result=result,
        previous_response=previous,
    ))
    assert answer.status == "completed"
    assert "ongewijzigd te laten" in answer.text
    assert verifier._personal_advice_is_grounded.await_count == 1


def test_rejected_next_decision_repair_reaches_verified_typed_fallback():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = SimpleNamespace(output_text="Wacht eerst op marktgegevens.")
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic,
        client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=rewrite))),
    )
    verifier._personal_advice_is_grounded = AsyncMock(side_effect=[False, False, True])
    result = FinnResponsesResult("Wacht op marktgegevens.", "resp-next", ({
        "name": "answer_directly", "status": "completed",
        "arguments": {"uses_previous_response": True}, "result": {"results": []},
    },), "grounded_next_decision")
    previous = {
        "answer": "De geschiktheid is zonder actuele gegevens nog onbekend.",
        "tool_trace": [{"name": "evaluate_plan", "status": "partial", "result": {
            "assessment_status": "insufficient_evidence", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"name": "BTC Plan"},
            }],
        }}],
    }
    answer = asyncio.run(verifier.verify(
        message="Welke keuze moet ik eerst maken?", result=result,
        previous_response=previous,
    ))
    assert answer.status == "completed"
    assert "ongewijzigd te laten" in answer.text
    assert verifier._personal_advice_is_grounded.await_count == 2


def test_unavailable_market_source_is_not_reassigned_to_the_user():
    guard = FinnResponsesAnswerVerifier._asks_user_to_supply_unavailable_source
    assert guard("Vraag actuele marktdata aan om verder te kunnen beoordelen.")
    assert guard("Request current market data before deciding.")
    assert guard("Besorge aktuelle Marktdaten, bevor du entscheidest.")
    assert guard("Als je meer feiten hebt over de huidige marktomstandigheden, kan ik je helpen.")
    assert not guard("Actuele marktdata ontbreken; laat je opgeslagen setup voorlopig staan.")


def test_saved_risk_profile_cannot_be_called_unavailable_in_followup():
    evidence = ({
        "scope": "read_profile", "status": "completed",
        "data": {"has_profile": True, "trader_profile": {"risk_profiles": ["conservative"]}},
    },)
    guard = FinnResponsesAnswerVerifier._profile_presence_claim_supported
    assert not guard(
        "Informationen über deine Risikoeinstellung sind momentan nicht verfügbar.", evidence,
    )
    assert guard("Aktuelle Marktdaten sind momentan nicht verfügbar.", evidence)


def test_unavailable_technical_read_rewrites_unverified_cause_and_wrong_rsi_fact():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "Ik heb geen actuele RSI- of MA200-waarden, dus ik kan ze nu niet samen duiden."
    create = AsyncMock(return_value=SimpleNamespace(output_text=rewrite))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._technical_limitation_is_grounded = AsyncMock(side_effect=[False, True])
    result = FinnResponsesResult("Door een tijdelijke storing ontbreekt RSI; onder 30 is overbought.",
                                 "resp", ({"name": "get_current_technical_snapshot",
                                           "status": "partial", "result": {"results": [{
                                               "scope": "read_technical_snapshot", "status": "unavailable",
                                               "reason": "source_unavailable",
                                           }]}},))
    answer = asyncio.run(verifier.verify(message="Wat zeggen RSI en MA200 samen?", result=result))
    assert answer.status == "completed"
    assert answer.text == rewrite
    assert verifier._technical_limitation_is_grounded.await_count == 2
    assert "technical_claim_not_grounded" in create.await_args.kwargs["input"]


@pytest.mark.parametrize(("audit_passes", "expected_status"), [
    (True, "completed"), (False, "unavailable"),
])
def test_resolved_choice_requires_strong_grounding_even_when_semantic_rejects(
    audit_passes, expected_status,
):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["response_scope_incomplete"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=audit_passes)
    result = FinnResponsesResult(
        "De opgeslagen setup heet BTC Plan. Of deze bij je past is nog niet beoordeeld.",
        "resp-choice", ({"name": "get_active_plan_and_strategy", "status": "completed",
                         "result": {"results": [{"scope": "read_active_setup",
                                                "status": "completed",
                                                "data": {"name": "BTC Plan"}}]}},),
    )
    message = "Original user request: Wat is een logisch plan voor mij?\nUser's chosen answer: BTC Plan"
    answer = asyncio.run(verifier.verify(
        message=message, result=result,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert answer.status == expected_status
    assert verifier._personal_advice_is_grounded.await_args.kwargs["question"] == message


def test_resolved_choice_does_not_publish_a_schema_field_inventory():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult(
        "De gekozen setup is BTC Plan.\n- Naam: BTC Plan\n- Timeframe: 4H",
        "resp-choice", ({"name": "get_active_plan_and_strategy", "status": "completed",
                         "result": {"results": [{"scope": "read_active_setup",
                                                "status": "completed",
                                                "data": {"name": "BTC Plan", "timeframe": "4H"}}]}},),
    )
    answer = asyncio.run(verifier.verify(
        message="Original user request: Wat is een logisch plan voor mij?\nUser's chosen answer: BTC Plan",
        result=result,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert answer.status != "completed"
def test_explicit_next_choice_uses_verified_answer_without_another_model_classifier():
    create = AsyncMock(side_effect=AssertionError("classifier should not be called"))
    guard = FinnResponsesToolRelevanceGuard(
        SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    result = asyncio.run(guard.previous_answer_suffices(
        message="Welke keuze moet ik nu eerst maken?",
        previous_answer="Je huidige BTC-setup staat op dagelijkse DCA; beoordeel eerst je budget.",
        model="gpt-6-luna", reasoning_effort="none",
    ))
    assert result == "next_decision_from_previous"
    create.assert_not_awaited()


def test_setup_choice_followup_uses_preceding_verified_read():
    create = AsyncMock(side_effect=AssertionError("classifier should not be called"))
    guard = FinnResponsesToolRelevanceGuard(
        SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    result = asyncio.run(guard.previous_answer_suffices(
        message="Wat zegt die setup over mijn keuze van daarnet, zonder actuele koers aan te nemen?",
        previous_answer="Je opgeslagen BTC-setup is een trade-setup op 4H.",
        model="gpt-6-luna", reasoning_effort="none",
    ))
    assert result == "explain_previous"
    create.assert_not_awaited()
