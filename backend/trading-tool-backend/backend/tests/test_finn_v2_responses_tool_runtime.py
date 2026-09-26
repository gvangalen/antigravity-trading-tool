import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_responses_loop import FinnResponsesError, FinnResponsesLoop
from backend.services.finn_v2_responses_tool_catalog import (
    FinnResponsesToolCatalog,
    FinnResponsesToolError,
)
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_entity_resolution_service import CanonicalEntityTarget


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
    geometry = ({"status": "completed", "data": {
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
    ("vast", "fixed"), ("fixed", "fixed"), ("aangepast", "custom"),
    ("fest", "fixed"),
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
    assert call.missing_inputs == ("timeframe", "name", "dca_frequency")
    assert call.operation_id == "create_setup"
    assert len(catalog.definitions()) == 15 + len(catalog.evaluation_contracts)
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
    with pytest.raises(FinnResponsesToolError):
        catalog.validate("evaluate_plan", {"user_id": 17})


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
    assert 0 < client.with_options.call_args.kwargs["timeout"] <= 12


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
            "min_investment": 100,
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
    assert plan.missing_information == ["timeframe", "name", "dca_frequency"]


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
            "dca_day": "maandag", "min_investment": 150,
        },
        "missing_required_inputs": [],
    }
    context = {"proposal_revision": {
        "proposal_id": "proposal-owned-by-conversation",
        "operation_id": "create_setup", "guided_state": prior_state,
    }}
    call = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "revise",
        "inputs": {"min_investment": 100},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC",
    )
    state = analysis.request_plan.operation_state
    assert state["open_proposal_id"] == "proposal-owned-by-conversation"
    assert state["collected_inputs"]["name"] == "Responses Revised 0923"
    assert state["collected_inputs"]["min_investment"] == 100
    assert state["missing_required_inputs"] == []
    omitted_intent = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "inputs": {"min_investment": 100},
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
        "inputs": {"setup_type": "dca", "min_investment": 100},
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


def test_proposal_relevance_compares_registry_operation_domain_and_polarity():
    fake = FakeResponses(response("judge", text='{"aligned": false}'))
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
    assert aligned is False
    payload = json.loads(fake.requests[0]["input"])
    assert payload["candidate_operation_id"] == "update_setup"
    assert payload["registry_action_operations"] == operations
    assert "target object type" in fake.requests[0]["instructions"]


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
    ("Wat vind je van mijn plan?", "base_amount", False),
    ("Verwijder mijn bot.", "name", False),
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
        "get_my_profile_and_risk_style", "evaluate_plan",
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
        "evaluate_plan", "get_active_plan_and_strategy",
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
        message="Welke keuze moet ik nu eerst maken?",
        previous_answer="De geschiktheid is onbewezen door ontbrekende marktdata; bepaal eerst of je de huidige DCA-inleg wilt aanhouden.",
    )) == "next_decision_from_previous"
    assert "next_decision_from_previous" in fake.requests[0]["text"]["format"]["schema"]["properties"]["kind"]["enum"]
    assert fake.requests[1]["input"] == "Welke keuze moet ik nu eerst maken?"


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
    assert result.response.tool_trace[0]["name"] == "answer_directly"
    assert fake.requests[0]["tools"] == []
    assert fake.requests[0]["input"][-1]["content"] == "Voor de lange termijn, ongeveer vijf jaar."
    assert "Original question awaiting this detail" in fake.requests[0]["instructions"]
    assert "Is mijn DCA-setup langetermijnopbouw of swingtrade?" in fake.requests[0]["instructions"]


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


def test_next_decision_followup_is_restricted_to_previous_verified_answer():
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
        message="Welke keuze moet ik nu eerst maken?", instructions="Gebruik FINN-tools",
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
    assert called == ["answer_directly"]
    assert fake.requests[0]["tools"] == []
    assert "No new market facts" in fake.requests[0]["instructions"]
    assert fake.requests[0]["tool_choice"] == "none"
    assert [item["name"] for item in result.response.tool_trace] == ["answer_directly"]
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
    assert fake.requests[0]["input"] == [
        {"role": "assistant", "content": "Voor deze keuze ontbreekt een risicobeoordeling."},
        {"role": "user", "content": "Waarom?"},
    ]
    assert "unverified draft" in fake.requests[0]["instructions"]


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
    assert state["collected_inputs"]["entry"] == "76000"
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


def test_partial_evaluation_is_not_repeated_or_followed_by_subset_read():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "evaluate_plan", {}),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {}),)),
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
    assert read_calls == ["evaluate_plan"]
    assert fake.requests[2]["tools"] == []
    assert result.response.tool_trace[1]["result"]["reason"] == "evaluation_already_attempted_this_turn"
    assert fake.requests[2]["tool_choice"] == "none"
    assert result.response.tool_trace[1]["status"] == "retry"


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
    assert {"ask_for_clarification", "answer_directly", "evaluate_plan"} <= available


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
    assert fake.requests[0]["tool_choice"] == "required"


def test_provider_failure_has_no_legacy_fallback():
    fake = FakeResponses(RuntimeError("provider down"))

    async def execute(_call):
        raise AssertionError("not reached")

    with pytest.raises(FinnResponsesError, match="responses_provider_error"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Hallo", instructions="Help"
        ))
    assert len(fake.requests) == 1


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
    ))
    assert result.state_json["responses_exchange"]["conversation_id"] == "conv-7"
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
    ))
    assert recovered.state_json["responses_exchange"]["supersedes_response_id"] == "resp-7"
    assert [item["call_id"] for item in recovered.state_json["responses_exchange"]["tool_trace"]] == ["c1", "c2"]


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
    assert "nog niet wijzigen" in rejected.text


def test_rejected_plan_review_uses_saved_strategy_facts_without_suitability_claim():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["insufficient_evidence"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=None)
    result = FinnResponsesResult(
        "Sterk in je plan: de setup heeft entry en targets. Waar ik je afrem: geen marktdata. "
        "Controleer eerst de actuele gegevens.",
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
        },),
    )
    answer = asyncio.run(verifier.verify(
        message="Wat is sterk, waar rem je me af en wat controleer ik eerst?", result=result,
    ))
    assert answer.status == "completed"
    assert answer.reason == "insufficient_evidence"
    assert "opgeslagen strategie" in answer.text
    assert "Controleer eerst" in answer.text
    assert "setup heeft entry" not in answer.text


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
        available=True, passes=True, reason_codes=[],
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
        result=FinnResponsesResult("Door een technische storing.", "resp-2", ()),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "storing" not in answer.text
    assert client.responses.create.await_args.kwargs["tool_choice"] == "none"


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
        message="Waarom?", result=FinnResponsesResult("Door een storing.", "resp-2", ()),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "oorzaak" in answer.text


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


def test_responses_loop_accepts_direct_answer_without_tools():
    fake = FakeResponses(response("r1", text="Ik kan je plan uitleggen."))

    async def execute(_call):
        raise AssertionError("no tool requested")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Hallo", instructions="Antwoord helder"
    ))
    assert result.tool_trace == ()
    assert result.text == "Ik kan je plan uitleggen."
    assert fake.requests[0]["tool_choice"] == "required"


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
    assert fake.requests[0]["tool_choice"] == "required"
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
            "inputs": {"setup_type": "dca", "symbol": "BTC", "timeframe": "4H", "name": "DCA test", "dca_frequency": "weekly", "dca_day": "monday"},
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
        message="Maak een BTC DCA-setup op 4H met de naam DCA test, wekelijks op maandag.", instructions="Gebruik tools",
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
    asyncio.run(front.run(
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
    assert received == [{"setup_id": 326}]
    assert fake.requests[0]["previous_response_id"] == "resp-previous"
    assert fake.requests[0]["input"][0] == {
        "role": "assistant", "content": "Je gekozen setup gebruikt 4H.",
    }


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
    assert kwargs["model"] == "gpt-4o"
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
    assert "language_mismatch" in schema["required"]
    assert "unnatural_language" in schema["required"]


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
    assert len(semantic_evidence) == 1
    assert semantic_evidence[0]["scope"] == "previous_response"
    assert semantic_evidence[0]["data"]["answer"] == previous["answer"]
    assert semantic_evidence[0]["data"]["source_evidence"] == []


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
                             "data": {"name": "Coach DCA Basis", "setup_type": "dca"}}],
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


def test_german_coach_register_stays_informal():
    guard = FinnResponsesAnswerVerifier._german_register_matches
    assert not guard("Ihr aktueller Plan ist gespeichert. Du kannst ihn prüfen.", "de")
    assert not guard("Sie können Ihren Plan prüfen.", "de")
    assert guard("Dein aktueller Plan ist gespeichert. Du kannst ihn prüfen.", "de")
    assert guard("Ihr aktueller Plan ist gespeichert.", "nl")


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
