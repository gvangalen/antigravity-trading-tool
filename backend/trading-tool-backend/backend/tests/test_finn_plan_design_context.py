import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domain.finn_dca_plan_contract import dca_automation_capabilities, split_confirmed_dca_plan
from backend.services.finn_v2_plan_design_context import (
    advance_plan_design_focus, remember_unsaved_design,
    requests_execution_capability_question, is_new_separate_setup_request,
    is_explicit_saved_plan_read,
)


def test_separate_setup_focus_survives_followups_and_expires():
    context = {"active_guided_operation": {"operation_id": "create_strategy"}}
    assert advance_plan_design_focus(context, "Maar dit moet een nieuwe setup worden, los van de oude")
    assert context["plan_design_focus"]["kind"] == "new_separate_setup"
    for message in ("Ja, hoe werkt dit op dit platform?", "En welke opties heb ik?", "Geef een naamidee"):
        assert advance_plan_design_focus(context, message)
        assert context["plan_design_focus"]["kind"] == "new_separate_setup"
    assert advance_plan_design_focus(context, "Lees mijn opgeslagen BTC-plan terug")
    assert "plan_design_focus" not in context


def test_explicit_new_parent_is_distinct_from_a_new_strategy_on_saved_parent():
    assert is_new_separate_setup_request("Nee, ik bedoel een nieuwe aparte setup voor AAPL")
    assert is_new_separate_setup_request("We bespreken een nieuwe opzet los van BTC")
    assert not is_new_separate_setup_request("Voeg een nieuwe strategie aan mijn BTC-setup toe")
    assert is_new_separate_setup_request(
        "Ik wil een NIEUW, APART BTC/EUR-DCA-plan ontwerpen; het oude plan is achtergrond."
    )
    assert is_new_separate_setup_request(
        "For this new, separate BTC/EUR DCA idea, let's explore a trendline rule."
    )


def test_plan_design_focus_does_not_bind_an_ordinary_saved_plan_read():
    context = {}
    assert not advance_plan_design_focus(context, "Wat staat in mijn bestaande BTC-setup?")
    assert "plan_design_focus" not in context
    assert is_explicit_saved_plan_read("Wat waren ritme en bedrag van mijn opgeslagen QA BTC EUR-plan?")
    assert not is_explicit_saved_plan_read("Het oude plan is alleen achtergrond voor een nieuw plan")


def test_unsaved_design_remains_separate_from_saved_plan_until_scope_is_chosen():
    context = {}
    assert remember_unsaved_design(context)
    assert context["plan_design_focus"]["kind"] == "unsaved_capability_design"
    assert advance_plan_design_focus(context, "Smart BTC test 200ma")
    assert context["plan_design_focus"]["kind"] == "unsaved_capability_design"
    assert advance_plan_design_focus(context, "Ik bedoel een nieuwe, aparte setup")
    assert context["plan_design_focus"]["kind"] == "new_separate_setup"
    assert not remember_unsaved_design(context)


def test_model_capabilities_match_confirmed_dca_amount_contract():
    facts = dca_automation_capabilities()
    assert facts["supported_amount_modes"] == ("fixed", "score_bands")
    assert facts["minimum_score_band_percent"] > 0
    assert facts["score_band_percent_order"] == "nondecreasing_as_benchmark_score_rises"
    assert facts["score_band_amount_count"] == 3
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC test", "dca_amount_mode": "score_bands",
        "base_amount": 100, "score_source": "benchmark_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100,
        "high_score_percent": 150,
    })
    assert strategy["decision_curve"]["input"] in facts["score_band_input"]
    assert strategy["decision_curve"]["interpolation"] == facts["score_band_interpolation"]
    assert facts["score_band_input"] == ("benchmark_score",)
    assert facts["score_band_interpolation"] == "step"


def test_generic_capability_questions_include_ma_and_trendline_designs():
    assert requests_execution_capability_question(
        "Kan Smart DCA met een percentage aan de hand van de 200ma?"
    )
    assert requests_execution_capability_question(
        "BTC/EUR. Voor dit nieuwe plan: koop juist méér naarmate de koers verder onder de MA200 ligt, vloeiend oplopend. Kan dat?",
        {"plan_design_focus": {"kind": "new_separate_setup"}},
    )
    assert requests_execution_capability_question(
        "Kan een trendline-breakout automatisch een koop en een stop activeren?",
    )
    assert not requests_execution_capability_question("Wat is de MA200-waarde vandaag?")
    assert not requests_execution_capability_question("Kan je mijn opgeslagen plan toelichten?")
    assert requests_execution_capability_question(
        "Kan mijn opgeslagen BTC-plan automatisch verkopen boven een trendlijn?"
    )
    assert not requests_execution_capability_question("Maak een vaste DCA voor ETH op maandag")
    assert not requests_execution_capability_question("Kan je mijn BTC-plan aanpassen?")
    assert not requests_execution_capability_question("Can you update my DCA strategy?")
    assert requests_execution_capability_question("Can this execute automatically?", {
        "plan_design_focus": {"kind": "new_separate_setup"},
    })
    assert requests_execution_capability_question(
        "Koop juist méér naarmate BTC/EUR verder onder de MA200 ligt, met een vloeiend "
        "oplopend bedrag. Kan FINN die regel echt als uitvoerbare DCA instellen?",
        {"plan_design_focus": {"kind": "new_separate_setup"}},
    )
    assert requests_execution_capability_question(
        "For this new, separate BTC/EUR DCA idea, can the purchase amount vary "
        "continuously with distance below MA200, with zero at the line and an "
        "automatic sale above it? Answer only what can actually be executed."
    )
    assert requests_execution_capability_question(
        "Kann der Kaufbetrag stufenlos mit dem Abstand unter einer Trendlinie steigen?"
    )


def test_capability_answer_uses_responses_with_typed_contract(monkeypatch):
    from backend.services import finn_v2_run_service as service

    create = AsyncMock(return_value=SimpleNamespace(
        output_text="De afstand tot MA200 kan hier nog geen DCA-bedrag sturen.", id="resp-test",
    ))
    monkeypatch.setattr(service.openai_client, "async_client", SimpleNamespace(
        responses=SimpleNamespace(create=create),
    ))
    answer, response_id = asyncio.run(service._explain_execution_capability(
        message="Ik wil meer kopen onder MA200", locale="nl", separate_setup=False,
    ))
    assert response_id == "resp-test"
    assert "MA200" in answer
    kwargs = create.await_args.kwargs
    assert kwargs["tool_choice"] == "none"
    assert '"score_band_input": ["benchmark_score"]' in kwargs["input"]
    assert "do not ask again whether the plan is separate" in kwargs["instructions"]


def test_capability_read_does_not_claim_an_answer_verifier_passed():
    from backend.services.finn_v2_responses_answer_verifier import FinnResponsesVerifiedAnswer
    from backend.services.finn_v2_run_service import FinnV2RunService

    run = SimpleNamespace(
        id="capability-run", conversation_id="capability-conversation",
        trace_id="capability-trace", user_id=7, status="planned",
        message="Kan mijn DCA-bedrag lineair van MA200-afstand afhangen?",
        client_context_json={},
    )
    service = FinnV2RunService.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=run), update_status=AsyncMock(),
    )
    service.runtime_contracts = SimpleNamespace(
        get_for_run=AsyncMock(return_value=SimpleNamespace(state_json={
            "responses_exchange": {"answer_kind": "free_text", "tool_trace": [], "turn_contract": {}},
        })),
        record_verified_setup_subject=AsyncMock(),
        materialize_terminal=AsyncMock(return_value=SimpleNamespace(terminal_projection_json={})),
    )
    service.traces = SimpleNamespace(append_event=AsyncMock())
    service.conversations = SimpleNamespace(set_responses_cursor=AsyncMock())
    service._trace_payload = lambda *_args, **_kwargs: {}
    service._commit_session_if_possible = AsyncMock()
    asyncio.run(service.complete_responses_read(
        run_id=run.id, user_id=7, response_id="resp-capability",
        answer=FinnResponsesVerifiedAnswer(
            "completed", "De formule is niet uitvoerbaar in het huidige DCA-contract.", None, (),
        ),
        verifier_ran=False, reasoning_source="responses_typed_capability_facts",
    ))
    response = service.runtime_contracts.materialize_terminal.call_args.kwargs["response"]
    assert response["verifier_status"] == "not_run"
    assert response["reasoning_provenance"]["reasoning_source"] == "responses_typed_capability_facts"
