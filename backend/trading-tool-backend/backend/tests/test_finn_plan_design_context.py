import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domain.finn_dca_plan_contract import dca_automation_capabilities, split_confirmed_dca_plan
from backend.services.finn_v2_plan_design_context import (
    advance_plan_design_focus, remember_unsupported_ma_design,
    requests_unsupported_ma_dca_amount, is_new_separate_setup_request,
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


def test_plan_design_focus_does_not_bind_an_ordinary_saved_plan_read():
    context = {}
    assert not advance_plan_design_focus(context, "Wat staat in mijn bestaande BTC-setup?")
    assert "plan_design_focus" not in context


def test_unsaved_ma_design_remains_separate_from_saved_plan_until_scope_is_chosen():
    context = {}
    assert remember_unsupported_ma_design(context)
    assert context["plan_design_focus"]["kind"] == "unsaved_ma_dca_design"
    assert advance_plan_design_focus(context, "Smart BTC test 200ma")
    assert context["plan_design_focus"]["kind"] == "unsaved_ma_dca_design"
    assert advance_plan_design_focus(context, "Ik bedoel een nieuwe, aparte setup")
    assert context["plan_design_focus"]["kind"] == "new_separate_setup"
    assert not remember_unsupported_ma_design(context)


def test_model_capabilities_match_confirmed_dca_amount_contract():
    facts = dca_automation_capabilities()
    assert facts["supported_amount_modes"] == ("fixed", "score_bands")
    assert facts["score_band_input"] == ("benchmark_score",)
    assert facts["score_band_interpolation"] == "step"
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
    assert not facts["direct_ma_distance_input"]
    assert not facts["linear_ma_distance_sizing"]


def test_ma_distance_amount_request_uses_capability_route_without_swallowing_generic_ma_question():
    assert requests_unsupported_ma_dca_amount(
        "Smart DCA met een percentage aan de hand van de 200ma"
    )
    assert requests_unsupported_ma_dca_amount(
        "Onder MA200 wil ik meer kopen, verder erboven steeds minder"
    )
    assert requests_unsupported_ma_dca_amount(
        "Laat het DCA-bedrag afhangen van de afstand tot het 200-daags gemiddelde"
    )
    assert not requests_unsupported_ma_dca_amount("Wat is de MA200-waarde vandaag?")
    assert not requests_unsupported_ma_dca_amount("Maak een vaste DCA voor ETH op maandag")


def test_capability_answer_uses_responses_with_typed_contract(monkeypatch):
    from backend.services import finn_v2_run_service as service

    create = AsyncMock(return_value=SimpleNamespace(
        output_text="De afstand tot MA200 kan hier nog geen DCA-bedrag sturen.", id="resp-test",
    ))
    monkeypatch.setattr(service.openai_client, "async_client", SimpleNamespace(
        responses=SimpleNamespace(create=create),
    ))
    answer, response_id = asyncio.run(service._explain_unsupported_ma_dca_amount(
        message="Ik wil meer kopen onder MA200", locale="nl", separate_setup=False,
    ))
    assert response_id == "resp-test"
    assert "MA200" in answer
    kwargs = create.await_args.kwargs
    assert kwargs["tool_choice"] == "none"
    assert '"linear_ma_distance_sizing": false' in kwargs["input"]
    assert "before asking for a name" in kwargs["instructions"]


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
