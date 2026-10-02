from __future__ import annotations

import asyncio
from types import SimpleNamespace
import pytest

from backend.services import finn_v2_hard_claim_boundary as boundary_module
from backend.services.finn_v2_hard_claim_boundary import FinnV2HardClaimBoundary
from backend.services.finn_v2_hard_claim_boundary import HardClaimBoundaryResult
from backend.services import finn_v2_run_service as run_service
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoorResult
from backend.services.finn_v2_responses_loop import FinnResponsesResult


def _safe_condition_result(kwargs):
    if kwargs["output_spec"].name == "finn_v2_condition_bypass_check":
        return {"parsed": {
            "recommends_entry_before_condition": False,
            "violating_quote": "",
        }}
    if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
        return {"parsed": {"asserts_personal_fit": False, "violating_quote": ""}}
    return None


def test_personal_fit_requires_typed_assessment_not_just_setup_and_profile(monkeypatch):
    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {
                "asserts_personal_fit": True,
                "violating_quote": "je DCA-setup past bij jouw voorzichtige risicostijl",
            }}
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        if kwargs["output_spec"].name == "finn_v2_personal_fit_check":
            return {"parsed": {"explicit_positive_fit": True}}
        return {"parsed": {
            "personal_fit_quote": "je DCA-setup past bij jouw voorzichtige risicostijl",
            "current_market_quote": "", "claimed_saved_action_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="De basis van je DCA-setup past bij jouw voorzichtige risicostijl.",
        tool_trace=({"result": {"results": [
            {"scope": "read_active_setup", "status": "completed"},
            {"scope": "read_profile", "status": "completed"},
        ]}},),
    ))
    assert result.available
    assert result.violations == ("personal_fit",)


def test_whole_answer_fit_check_catches_claim_missed_by_general_extractor(monkeypatch):
    quote = "100 euro per week is goed te doen"

    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {"asserts_personal_fit": True, "violating_quote": quote}}
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        if kwargs["output_spec"].name == "finn_v2_personal_fit_check":
            return {"parsed": {"explicit_positive_fit": True}}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer=f"Voor jouw risicostijl: {quote}.", tool_trace=(),
    ))
    assert result.available
    assert result.violations == ("personal_fit",)
    assert result.quotes["personal_fit_quote"] == quote


def test_whole_answer_fit_detection_cannot_be_vetoed_by_quote_classifier(monkeypatch):
    quote = "Je risicostijl past in grote lijnen bij deze DCA-aanpak"
    calls = []

    async def extract(**kwargs):
        calls.append(kwargs)
        name = kwargs["output_spec"].name
        if name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {"asserts_personal_fit": True, "violating_quote": quote}}
        if name == "finn_v2_condition_bypass_check":
            return {"parsed": {
                "recommends_entry_before_condition": False, "violating_quote": "",
            }}
        if name == "finn_v2_personal_fit_check":
            return {"parsed": {"explicit_positive_fit": False}}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer=f"{quote}, maar ik kan geen volledig oordeel geven.", tool_trace=(),
    ))
    assert result.available
    assert result.violations == ("personal_fit",)
    assert not any(call["output_spec"].name == "finn_v2_personal_fit_check" for call in calls)
    assert next(
        call for call in calls
        if call["output_spec"].name == "finn_v2_whole_answer_personal_fit_check"
    )["model_override"] == boundary_module._WHOLE_ANSWER_FIT_MODEL
    assert next(
        call for call in calls
        if call["output_spec"].name == "finn_v2_whole_answer_personal_fit_check"
    )["reasoning_effort"] == "none"


def test_invalid_whole_answer_fit_quote_remains_a_repairable_safety_violation(monkeypatch):
    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {
                "asserts_personal_fit": True,
                "violating_quote": "This paraphrase is not in the answer",
            }}
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Deze DCA-aanpak past goed bij jouw risicostijl.", tool_trace=(),
    ))
    assert result.available
    assert result.violations == ("personal_fit",)
    assert not result.quotes["personal_fit_quote"]


def test_personal_fit_quote_without_suitability_judgment_is_not_blocked(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        if kwargs["output_spec"].name == "finn_v2_personal_fit_check":
            return {"parsed": {"explicit_positive_fit": False}}
        return {"parsed": {
            "personal_fit_quote": "Je hebt een voorzichtige risicostijl en volgt DCA.",
            "current_market_quote": "", "claimed_saved_action_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Je hebt een voorzichtige risicostijl en volgt DCA. Of €100 past, kan ik niet vaststellen.",
        tool_trace=(),
    ))
    assert result.available and not result.violations


def test_complete_registry_evaluation_supplies_evidence_for_model_judgment():
    completed = ({"result": {
        "evaluation_operation_id": "evaluate_plan",
        "assessment_status": "evidence_collected_not_yet_judged",
        "missing_required_scopes": [],
        "evidence_coverage": {"full_assessment": {"status": "available", "missing_scopes": []}},
    }},)
    assert FinnV2HardClaimBoundary._supported_claims(completed, None)["personal_fit_quote"]
    incomplete = ({"result": {
        "evaluation_operation_id": "evaluate_plan",
        "assessment_status": "insufficient_evidence",
        "missing_required_scopes": ["market_snapshot"],
        "evidence_coverage": {"full_assessment": {"status": "incomplete", "missing_scopes": ["market_snapshot"]}},
    }},)
    assert not FinnV2HardClaimBoundary._supported_claims(incomplete, None)["personal_fit_quote"]


def test_explanation_and_uncertainty_do_not_require_assessment(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="DCA spreidt aankopen; of het bij jou past kan ik niet vaststellen.",
        tool_trace=(),
    ))
    assert result.available and not result.violations


def test_current_market_and_saved_action_need_separate_typed_proof(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        return {"parsed": {
            "personal_fit_quote": "",
            "current_market_quote": "BTC staat nu op 76000",
            "claimed_saved_action_quote": "Ik heb je setup zojuist opgeslagen",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    answer = "BTC staat nu op 76000. Ik heb je setup zojuist opgeslagen."
    boundary = FinnV2HardClaimBoundary()
    unproven = asyncio.run(boundary.assess(answer=answer, tool_trace=()))
    assert unproven.violations == ("current_market", "claimed_saved_action")
    proven = asyncio.run(boundary.assess(
        answer=answer,
        tool_trace=({"result": {"results": [{
            "scope": "read_market_snapshot", "status": "completed",
            "freshness": "fresh", "as_of": "2026-09-28T12:00:00Z",
        }]}},),
        recent_action_result={"result_status": "succeeded", "execution_id": "execution-1"},
    ))
    assert proven.available and not proven.violations


def test_invalid_model_quote_is_repairable_but_not_accepted(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        return {"parsed": {
            "personal_fit_quote": "not in the answer",
            "current_market_quote": "", "claimed_saved_action_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Ik kan dit nog niet beoordelen.", tool_trace=(),
    ))
    assert result.available
    assert result.violations == ("claim_quote_invalid",)


def test_invalid_quote_is_rechecked_before_rejecting_a_safe_answer(monkeypatch):
    calls = []

    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        calls.append(kwargs)
        return {"parsed": {
            "personal_fit_quote": "not in the answer" if len(calls) == 1 else "",
            "current_market_quote": "", "claimed_saved_action_quote": "",
            "outcome_claim_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Of dit past, kan ik nog niet vaststellen.", tool_trace=(),
    ))
    assert result.available and not result.violations
    assert len(calls) == 2


def test_trading_outcome_claim_is_not_authorized_by_a_saved_setup(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        if kwargs["output_spec"].name == "finn_v2_outcome_check":
            return {"parsed": {"predicts_user_outcome": True}}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "",
            "outcome_claim_quote": "mogelijk meer winst kunt maken",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Met deze strategie zou je mogelijk meer winst kunt maken.",
        tool_trace=({"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
        }]}},),
    ))
    assert result.violations == ("outcome_claim",)


def test_saved_setup_readback_in_dutch_perfect_tense_is_not_a_new_write():
    trace = ({"result": {"results": [{"scope": "read_active_setup", "status": "completed"}]}},)
    assert FinnV2HardClaimBoundary._saved_state_readback(
        "je een dagelijkse DCA-setup voor BTC hebt opgeslagen", trace,
    )
    assert FinnV2HardClaimBoundary._saved_state_readback(
        "Je opgeslagen BTC-instelling is dagelijkse DCA", trace,
    )
    assert not FinnV2HardClaimBoundary._saved_state_readback(
        "je zojuist een dagelijkse DCA-setup hebt opgeslagen", trace,
    )


def test_general_purchase_frequency_tradeoff_is_not_a_predicted_user_outcome(monkeypatch):
    quote = "wisselen van dagelijkse naar wekelijkse aankopen vergroot de timingimpact per aankoop"

    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        if kwargs["output_spec"].name == "finn_v2_outcome_check":
            return {"parsed": {"predicts_user_outcome": False}}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": quote,
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer=f"Het {quote}.", tool_trace=(),
    ))
    assert result.available and not result.violations
    assert result.quotes["outcome_claim_quote"] == ""


def test_repair_evidence_keeps_typed_limits_and_selected_saved_facts():
    trace = ({"result": {
        "evaluation_operation_id": "evaluate_plan",
        "assessment_status": "insufficient_evidence",
        "missing_required_scopes": ["market_snapshot"],
        "results": [
            {"scope": "read_profile", "status": "completed", "source": "owner_profile",
             "data": {"has_profile": True, "trader_profile": {
                 "risk_profiles": ["conservative"], "investment_goals": ["wealth_building"],
                 "private_note": "not needed for this repair",
             }}},
            {"scope": "read_market_snapshot", "status": "unavailable",
             "reason": "source_unavailable"},
        ],
    }},)
    evidence = FinnV2HardClaimBoundary.repair_evidence(trace, None)
    assert evidence["claim_support"]["personal_fit_quote"] is False
    assert evidence["assessments"][0]["assessment_status"] == "insufficient_evidence"
    assert evidence["source_facts"][0]["data"]["risk_profiles"] == ["conservative"]
    assert "private_note" not in str(evidence)
    assert evidence["source_facts"][1]["status"] == "unavailable"


def test_user_stated_entry_condition_cannot_be_bypassed_by_smaller_position(monkeypatch):
    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {"asserts_personal_fit": False, "violating_quote": ""}}
        assert "wachten op bevestiging" in kwargs["prompt"]
        if kwargs["output_spec"].name == "finn_v2_condition_bypass_check":
            return {"parsed": {
                "recommends_entry_before_condition": True,
                "violating_quote": "overweeg een kleinere positie in te nemen",
            }}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "overweeg een kleinere positie in te nemen",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Terwijl je wacht, overweeg een kleinere positie in te nemen.",
        user_message="Mijn regel is wachten op bevestiging voor een entry.",
        tool_trace=(),
    ))
    assert result.violations == ("condition_bypass",)


def test_negated_wait_rule_is_not_mistaken_for_entry_advice(monkeypatch):
    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {"asserts_personal_fit": False, "violating_quote": ""}}
        if kwargs["output_spec"].name == "finn_v2_condition_bypass_check":
            return {"parsed": {
                "recommends_entry_before_condition": False,
                "violating_quote": "",
            }}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "Je hoeft die wachtregel niet te negeren.",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer="Je hoeft die wachtregel niet te negeren. Wacht op bevestiging.",
        user_message="Mijn regel is wachten op bevestiging voor entry.", tool_trace=(),
    ))
    assert result.available and not result.violations


def test_executable_order_during_wait_is_blocked_even_if_general_extractor_misses_it(monkeypatch):
    quote = "Overweeg het gebruik van limietorders terwijl je op bevestiging wacht."

    async def extract(**kwargs):
        if kwargs["output_spec"].name == "finn_v2_whole_answer_personal_fit_check":
            return {"parsed": {"asserts_personal_fit": False, "violating_quote": ""}}
        if kwargs["output_spec"].name == "finn_v2_condition_bypass_check":
            return {"parsed": {
                "recommends_entry_before_condition": True,
                "violating_quote": quote,
            }}
        return {"parsed": {
            "personal_fit_quote": "", "current_market_quote": "",
            "claimed_saved_action_quote": "", "outcome_claim_quote": "",
            "condition_bypass_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    result = asyncio.run(FinnV2HardClaimBoundary().assess(
        answer=quote, user_message="Mijn regel is wachten op bevestiging voor entry.",
        tool_trace=(),
    ))
    assert result.available
    assert result.violations == ("condition_bypass",)
    assert result.quotes["condition_bypass_quote"] == quote


def test_local_coach_reuses_typed_entity_horizon_and_profile_checks():
    trace = ({"result": {"results": [
        {"scope": "read_active_setup", "status": "completed", "data": {
            "name": "Coach DCA Basis", "setup_type": "dca", "timeframe": "4H",
        }},
        {"scope": "read_linked_strategy", "status": "unavailable"},
        {"scope": "read_profile", "status": "completed", "data": {
            "trader_profile": {"risk_profiles": ["conservative"]},
        }},
    ]}},)
    violations = run_service._simple_coach_structural_violations(
        text=("Je setup is een DCA-strategie en wijst op langetermijnopbouw. "
              "Er is geen opgeslagen risicoprofiel."),
        tool_trace=trace,
        message="Is mijn 4H DCA-setup langetermijnopbouw of een swingtrade?",
        horizon_classification_question=False,
    )
    assert violations == ("saved_entity_type", "saved_horizon", "saved_profile")
    user_horizon = run_service._simple_coach_structural_violations(
        text="Met jouw horizon van vijf jaar is je bedoeling langetermijnopbouw; de setup is niet gewijzigd.",
        tool_trace=trace, message="Voor de lange termijn, ongeveer vijf jaar.",
        horizon_classification_question=False,
    )
    assert "saved_horizon" not in user_horizon


@pytest.mark.parametrize("repair_model", ("gpt-4o-mini", "gpt-6-luna"))
def test_local_coach_repair_uses_one_typed_boundary_result(monkeypatch, repair_model):
    monkeypatch.setenv("FINN_RESPONSES_REPAIR_MODEL", repair_model)
    verdicts = iter((
        HardClaimBoundaryResult(True, ("personal_fit",), {
            "personal_fit_quote": "Mijn setup past bij mijn risicostijl",
        }),
        HardClaimBoundaryResult(True, (), {}),
    ))

    class Boundary:
        async def assess(self, **_kwargs):
            return next(verdicts)

        @staticmethod
        def repair_evidence(*_args):
            return {"claim_support": {"personal_fit_quote": False}, "source_facts": []}

    class Responses:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id="response-revised",
                output_text="Ik kan uit de opgeslagen setup nog niet bepalen of hij bij mijn risicostijl past.",
            )

    responses = Responses()
    monkeypatch.setattr(run_service, "FinnV2HardClaimBoundary", Boundary)
    monkeypatch.setattr(run_service.openai_client, "async_client", SimpleNamespace(responses=responses))
    prepared = FinnResponsesFrontDoorResult(
        response=FinnResponsesResult(
            "Mijn setup past bij mijn risicostijl", "response-original",
            ({"name": "get_active_plan_and_strategy", "result": {"results": []}},),
        ),
        proposal_analysis=None,
    )
    answer, response_id, revised_text = asyncio.run(run_service._simple_coach_experiment_answer(
        message="Past deze setup bij mij?", prepared=prepared,
    ))
    assert answer.status == "completed"
    assert response_id == "response-revised"
    assert revised_text == answer.text
    assert len(responses.calls) == 1
    assert responses.calls[0]["tool_choice"] == "none"
    if repair_model == "gpt-6-luna":
        assert responses.calls[0]["reasoning"] == {"effort": "none"}
        assert "temperature" not in responses.calls[0]
    else:
        assert responses.calls[0]["temperature"] == 0
    assert "previous_response_id" not in responses.calls[0]
    assert "Past deze setup bij mij?" in responses.calls[0]["input"]


def test_unsupported_claim_without_reads_requests_bounded_read_repair(monkeypatch):
    class Boundary:
        async def assess(self, **_kwargs):
            return HardClaimBoundaryResult(True, ("personal_fit",), {
                "personal_fit_quote": "Deze setup past bij je.",
            })

    monkeypatch.setattr(run_service, "FinnV2HardClaimBoundary", Boundary)
    prepared = FinnResponsesFrontDoorResult(
        response=FinnResponsesResult("Deze setup past bij je.", "response-original", ()),
        proposal_analysis=None,
    )
    answer, response_id, revised_text = asyncio.run(run_service._simple_coach_experiment_answer(
        message="Past deze setup bij mij?", prepared=prepared,
    ))
    assert answer.reason == "no_evidence_available"
    assert response_id == "response-original"
    assert revised_text is None


def test_unproven_outcome_claim_requests_retraction_not_irrelevant_read(monkeypatch):
    verdicts = iter((
        HardClaimBoundaryResult(True, ("outcome_claim",), {
            "outcome_claim_quote": "wachten verbetert je rendement",
        }),
        HardClaimBoundaryResult(True, (), {}),
    ))

    class Boundary:
        async def assess(self, **_kwargs):
            return next(verdicts)

        @staticmethod
        def repair_evidence(*_args):
            return {"claim_support": {"outcome_claim_quote": False}}

    class Responses:
        async def create(self, **_kwargs):
            return SimpleNamespace(id="response-revised", output_text="Volg de regel die je zelf noemt.")

    monkeypatch.setattr(run_service, "FinnV2HardClaimBoundary", Boundary)
    monkeypatch.setattr(run_service.openai_client, "async_client", SimpleNamespace(responses=Responses()))
    prepared = FinnResponsesFrontDoorResult(
        response=FinnResponsesResult("Wachten verbetert je rendement", "response-original", ()),
        proposal_analysis=None,
    )
    answer, response_id, revised_text = asyncio.run(run_service._simple_coach_experiment_answer(
        message="Moet ik op bevestiging wachten?", prepared=prepared,
    ))
    assert answer.status == "completed"
    assert response_id == "response-revised"
    assert revised_text == answer.text
def test_existing_saved_setup_readback_is_not_a_new_write_claim():
    trace = ({"result": {"results": [{
        "scope": "read_active_setup", "status": "completed", "data": {"name": "Atlas"},
    }]}},)
    assert FinnV2HardClaimBoundary._saved_state_readback(
        "Het opgeslagen setup is Atlas.", trace,
    )
    assert FinnV2HardClaimBoundary._saved_state_readback(
        "De opgeslagen BTC-setup heet Atlas.", trace,
    )
    assert FinnV2HardClaimBoundary._saved_state_readback(
        "Er is een dagelijkse DCA-opzet voor BTC op 4H opgeslagen.", trace,
    )
    assert not FinnV2HardClaimBoundary._saved_state_readback(
        "Ik heb je setup zojuist opgeslagen.", trace,
    )
    assert not FinnV2HardClaimBoundary._saved_state_readback(
        "Het opgeslagen setup is nu aangepast.", trace,
    )
    assert not FinnV2HardClaimBoundary._saved_state_readback(
        "Het opgeslagen setup is Atlas.", (),
    )


def test_saved_strategy_levels_are_not_live_market_quotes():
    trace = ({"result": {"results": [{
        "scope": "read_linked_strategy", "status": "completed",
        "data": {"name": "Example Strategy", "entry": "210", "stop_loss": "190", "targets": ["230"]},
    }]}},)
    answer = "In Example Strategy staat een entry van 210 en een stop-loss van 190."
    check = FinnV2HardClaimBoundary._saved_strategy_levels_not_market
    assert check("een entry van 210 en een stop-loss van 190", answer, trace)
    assert not check("de actuele koers is 210", answer, trace)
    assert not check("een entry van 215", answer, trace)
    assert not check("een entry van 210", answer, ())


def test_claim_extractor_cannot_turn_saved_strategy_entry_into_market_quote(monkeypatch):
    async def extract(**kwargs):
        if (condition := _safe_condition_result(kwargs)) is not None:
            return condition
        return {"parsed": {
            "personal_fit_quote": "",
            "current_market_quote": "een entry van 210 en een stop-loss van 190",
            "claimed_saved_action_quote": "",
            "outcome_claim_quote": "", "condition_bypass_quote": "",
        }}

    monkeypatch.setattr(boundary_module, "ask_gpt_structured_response_async", extract)
    trace = ({"result": {"results": [{
        "scope": "read_linked_strategy", "status": "completed",
        "data": {"name": "Example Strategy", "entry": "210", "stop_loss": "190"},
    }]}},)
    answer = "In Example Strategy staat een entry van 210 en een stop-loss van 190."
    verdict = asyncio.run(FinnV2HardClaimBoundary().assess(answer=answer, tool_trace=trace))
    assert verdict.available and not verdict.violations
