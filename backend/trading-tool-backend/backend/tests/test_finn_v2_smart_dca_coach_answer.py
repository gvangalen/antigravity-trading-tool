"""Saved Smart DCA coaching must keep pair, score boundary and EUR amount coherent."""

from copy import deepcopy
import asyncio
from unittest.mock import AsyncMock

from backend.services.finn_v2_smart_dca_coach_answer import (
    render_saved_smart_dca_coach_answer, saved_smart_dca_identity_matched,
)
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_run_service import _responses_verifier_message


def _trace():
    setup = {"setup_id": 13, "name": "Test Smart BTC", "pair": "BTC/USDT", "setup_type": "dca", "market_id": 4}
    strategy = {
        "strategy_id": 19, "setup_id": 13, "name": "Test Smart BTC Strategy",
        "pair": "BTC/USDT", "currency": "EUR",
        "dca_amount_mode": "score_bands", "score_source": "benchmark_score", "base_amount": 200,
        "dca_score_bands": [
            {"from_score_inclusive": 0, "to_score_exclusive": 25.5, "percent_of_base": 100,
             "planned_amount": 200, "amount_status": "hypothetical_before_exposure_not_purchase"},
            {"from_score_inclusive": 25.5, "to_score_exclusive": 45.5, "percent_of_base": 75,
             "planned_amount": 150, "amount_status": "hypothetical_before_exposure_not_purchase"},
            {"from_score_inclusive": 45.5, "to_score_exclusive": 60.5, "percent_of_base": 50,
             "planned_amount": 100, "amount_status": "hypothetical_before_exposure_not_purchase"},
            {"from_score_inclusive": 60.5, "to_score_exclusive": 75.5, "percent_of_base": 25,
             "planned_amount": 50, "amount_status": "hypothetical_before_exposure_not_purchase"},
            {"from_score_inclusive": 75.5, "to_score_exclusive": None, "percent_of_base": 10,
             "planned_amount": 20, "amount_status": "hypothetical_before_exposure_not_purchase"},
        ],
    }
    score = {"symbol": "BTC", "quote_currency": "USDT", "market_id": 4,
             "source_status": "available", "benchmark_score": 45.7, "as_of": "2026-11-24",
             "oldest_indicator_source_observed_at": "2026-11-23T22:00:00+00:00"}
    return ({"name": "get_active_plan_and_strategy", "result": {"results": [
        {"scope": "read_active_setup", "status": "completed", "data": setup},
        {"scope": "read_linked_strategy", "status": "completed", "data": strategy},
        {"scope": "read_asset_scores", "status": "completed", "data": score},
        {"scope": "read_linked_bot", "status": "unavailable", "reason": "bot_not_resolved"},
        {"scope": "read_bot_status", "status": "unavailable", "reason": "bot_not_resolved"},
    ]}},)


def test_saved_curve_uses_exact_band_eur_and_user_zone():
    answer = render_saved_smart_dca_coach_answer(
        _trace(), message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT", pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    assert "45,7/100" in answer
    assert "45,5–60,5" in answer
    assert "€100" in answer
    assert "€200" in answer
    assert "2026-11-23 23:00 CET" in answer
    assert "geen bot gekoppeld" in answer
    assert "geen kooporder" in answer
    assert "100 USDT" not in answer
    la = render_saved_smart_dca_coach_answer(
        _trace(), message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT", pair="BTC/USDT", locale="nl-NL", user_time_zone="America/Los_Angeles",
    )
    assert "2026-11-23 14:00 PST" in la


def test_named_curve_read_distinguishes_generic_bot_question_from_strategy_name(monkeypatch):
    trace = deepcopy(_trace())
    rows = trace[0]["result"]["results"]
    rows[0]["data"]["name"] = "QA Smart DCA Grens 25 nov"
    rows[1]["data"]["name"] = "QA Smart DCA Grens 25 nov Strategy"
    rows[1]["data"]["dca_score_bands"] = [
        {"from_score_inclusive": low, "to_score_exclusive": high,
         "percent_of_base": percent, "planned_amount": amount,
         "amount_status": "hypothetical_before_exposure_not_purchase"}
        for low, high, percent, amount in (
            (0, 26, 150, 300), (26, 76, 100, 200), (76, None, 50, 100),
        )
    ]
    question = (
        "Lees alleen mijn opgeslagen BTC/USDT-setup QA Smart DCA Grens 25 nov "
        "en de daaraan gekoppelde strategie. Noem de scorebandgrenzen, het "
        "geplande bedrag bij benchmarkscore 25 en 26 op basis van €200, en "
        "of aan juist deze strategie een bot is gekoppeld. Maak geen voorstel "
        "en wijzig niets."
    )
    assert saved_smart_dca_identity_matched(trace, message=question, pair="BTC/USDT")
    answer = render_saved_smart_dca_coach_answer(
        trace, message=question, pair="BTC/USDT", locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    assert "score 25: 150% van €200 = hypothetisch €300" in answer
    assert "score 26: 100% van €200 = hypothetisch €200" in answer
    assert "geen bot gekoppeld" in answer
    assert render_saved_smart_dca_coach_answer(
        trace, message=question.replace("QA Smart DCA Grens 25 nov", "Ander Plan"),
        pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    ) is None
    for other_strategy in ("De Sigma Strategie", "Een Sigma Strategie", "Mijn Sigma Strategie"):
        assert not saved_smart_dca_identity_matched(
            trace, message=(f"Beoordeel setup QA Smart DCA Grens 25 nov voor BTC/USDT "
                            f"met strategie {other_strategy}; welke staffel geldt?"),
            pair="BTC/USDT",
        )
    for bot_phrase in ("een bot", "al een bot", "een Paper-bot"):
        assert saved_smart_dca_identity_matched(
            trace, message=(f"Lees setup QA Smart DCA Grens 25 nov voor BTC/USDT "
                            f"en vertel of aan deze strategie {bot_phrase} is gekoppeld?"),
            pair="BTC/USDT",
        )
    wrong_base = render_saved_smart_dca_coach_answer(
        trace, message=question.replace("basis van €200", "basis van €100"),
        pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    )
    assert wrong_base is not None
    assert "opgeslagen strategie" in wrong_base
    assert "€100" in wrong_base and "€200" in wrong_base
    assert "hypothetisch €300" not in wrong_base
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run",
        AsyncMock(return_value=FinnResponsesResult(
            text="Welke setup bedoel je?", response_id="model",
            tool_trace=trace, answer_kind="free_text",
        )),
    )
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="smart-dca-named-read", model_led_coach=True)
    rendered = asyncio.run(front.run(
        message=question, instructions="", conversation_context={}, verified_asset="BTC",
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert rendered.response.answer_kind == "factual_source"
    assert "score 25: 150%" in rendered.response.text
    assert "score 26: 100%" in rendered.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=rendered.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert checked.status == "completed"
    live_question = (
        "Lees alleen mijn opgeslagen Smart DCA-setup QA Smart DCA Grens 25 nov "
        "voor BTC/USDT en de gekoppelde strategie. Wat is de huidige benchmarkscore "
        "met bronmoment? Welke opgeslagen scoreband geldt nu, en hoeveel zou de "
        "staffel bij een hypothetische score van 25 en van 26 uitkeren vanaf het "
        "basisbedrag? Is er aan precies deze strategie een Paper-bot gekoppeld? "
        "Maak niets aan en plaats geen order."
    )
    live_result = asyncio.run(front.run(
        message=live_question, instructions="", conversation_context={}, verified_asset="BTC",
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert live_result.response.answer_kind == "factual_source"
    assert "score 25: 150% van €200 = hypothetisch €300" in live_result.response.text
    assert "score 26: 100% van €200 = hypothetisch €200" in live_result.response.text
    assert "45,7/100" in live_result.response.text
    assert "geen bot gekoppeld" in live_result.response.text
    live_checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=live_question, result=live_result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert live_checked.status == "completed"
    wrong_base_question = question.replace("basis van €200", "basis van €100")
    wrong_base_result = asyncio.run(front.run(
        message=wrong_base_question, instructions="", conversation_context={}, verified_asset="BTC",
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert wrong_base_result.response.answer_kind == "factual_source"
    assert "opgeslagen strategie" in wrong_base_result.response.text
    assert "hypothetisch €300" not in wrong_base_result.response.text
    wrong_base_checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=wrong_base_question, result=wrong_base_result.response,
        locale="nl-NL", user_time_zone="Europe/Amsterdam",
    ))
    assert wrong_base_checked.status == "completed"


def test_unnamed_or_wrong_named_pair_cannot_select_an_arbitrary_curve():
    message = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. Welke benchmarkscore "
        "geldt nu, in welke opgeslagen scoreband valt die, welk bedrag volgt uit "
        "het basisbedrag en de staffel, en is er al een Paper-bot gekoppeld? "
        "Noem het bronmoment van de score en maak of wijzig niets."
    )
    for question in (
        message,
        message.replace("BTC/USDT", "BTC/EUR"),
        "Lees mijn opgeslagen Smart DCA voor BTC/USDT, specifiek de setup genaamd Ander Plan. Welke scoreband en staffel gelden?",
        "Lees mijn opgeslagen Smart DCA voor BTC/USDT met strategie Ander Plan. Welke scoreband en staffel gelden?",
        "Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT met strategie Ander Plan. Welke scoreband en staffel gelden?",
        "Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT; strategie Sigma. Welke scoreband en staffel gelden?",
        "Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT met de strategie Sigma. Welke scoreband en staffel gelden?",
        "Lees mijn opgeslagen Smart DCA voor BTC/USDT; ik bedoel niet Test Smart BTC maar mijn andere plan. Welke scoreband en staffel gelden?",
    ):
        assert render_saved_smart_dca_coach_answer(
            _trace(), message=question, pair="BTC/USDT", locale="nl-NL",
            user_time_zone="Europe/Amsterdam",
        ) is None


def test_saved_curve_rejects_other_pair_strategy_or_wrong_amount():
    for mutate in (
        lambda rows: rows[0]["data"].update(pair="BTC/EUR"),
        lambda rows: rows[1]["data"].update(setup_id=99),
        lambda rows: rows[1]["data"].update(currency="USDT"),
        lambda rows: rows[1]["data"].update(score_source="technical_score"),
        lambda rows: rows[1]["data"]["dca_score_bands"][2].update(planned_amount=200),
        lambda rows: rows[2]["data"].update(quote_currency="EUR"),
        lambda rows: rows[2]["data"].update(benchmark_score=45.5, as_of=None),
        lambda rows: rows[3].update(status="completed", data={"strategy_id": 999}),
    ):
        trace = deepcopy(_trace())
        mutate(trace[0]["result"]["results"])
        assert render_saved_smart_dca_coach_answer(
            trace, message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT", pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
        ) is None


def test_score_boundary_is_half_open():
    trace = deepcopy(_trace())
    trace[0]["result"]["results"][2]["data"]["benchmark_score"] = 45.5
    answer = render_saved_smart_dca_coach_answer(
        trace, message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT", pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    )
    assert "45,5–60,5" in answer
    trace[0]["result"]["results"][2]["data"]["benchmark_score"] = 45.49
    answer = render_saved_smart_dca_coach_answer(
        trace, message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT", pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    )
    assert "25,5–45,5" in answer


def test_saved_rising_curve_and_live_bot_are_described_without_paper_claim():
    trace = deepcopy(_trace())
    rows = trace[0]["result"]["results"]
    for band, percent in zip(rows[1]["data"]["dca_score_bands"], (10, 25, 50, 75, 100)):
        band["percent_of_base"] = percent
        band["planned_amount"] = percent * 2
    rows[3] = {"scope": "read_linked_bot", "status": "completed",
               "data": {"bot_id": 10, "strategy_id": 19, "is_live": True}}
    rows[4] = {"scope": "read_bot_status", "status": "completed",
               "data": {"bot_id": 10, "is_live": True}}
    answer = render_saved_smart_dca_coach_answer(
        trace, message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT",
        pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    )
    assert "lager percentage dan de hoge" in answer
    assert "gekoppeld (Live)" in answer
    assert "Paper-besluit" not in answer
    rows[4]["data"]["bot_id"] = 11
    assert render_saved_smart_dca_coach_answer(
        trace, message="Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT",
        pair="BTC/USDT", locale="nl-NL", user_time_zone="Europe/Amsterdam",
    ) is None


def test_frontdoor_replaces_ungrounded_model_answer_after_owner_read(monkeypatch):
    question = (
        "Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT. "
        "Welke benchmarkscore en scoreband gelden nu, welk bedrag volgt uit de "
        "opgeslagen bedragcurve? Leg uit of er een bot aan dit plan gekoppeld is. "
        "Maak alleen een voorstel en wijzig niets."
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Het plan is niet gevonden; het bedrag is 100 USDT.",
        response_id="model", tool_trace=_trace(), answer_kind="free_text",
        model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="smart-dca-render", model_led_coach=True)
    result = asyncio.run(front.run(
        message=question, instructions="", conversation_context={}, verified_asset="BTC",
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert result.response.answer_kind == "factual_source"
    assert "€100" in result.response.text
    assert "100 USDT" not in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert checked.status == "completed"
    tampered = deepcopy(result.response)
    from dataclasses import replace
    tampered = replace(tampered, text=tampered.text.replace("€100", "€200"))
    rejected = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=tampered, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert rejected.status == "unavailable"
    assert rejected.reason == "factual_source_mismatch"


def test_frontdoor_asks_for_identity_instead_of_guessing_combined_amount(monkeypatch):
    question = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. Welke benchmarkscore "
        "geldt nu, in welke opgeslagen scoreband valt die, welk bedrag volgt uit "
        "het basisbedrag en de staffel, en is er al een Paper-bot gekoppeld? "
        "Noem het bronmoment van de score en maak of wijzig niets."
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="De setupscoreband is 0–100; de BTC-bot wacht.",
        response_id="model", tool_trace=_trace(), answer_kind="free_text",
        model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    result = asyncio.run(FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7,
        run_id="smart-dca-combined", model_led_coach=True,
    ).run(
        message=question, instructions="", conversation_context={},
        verified_asset="BTC", workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_active_plan_and_strategy"
    assert result.response.answer_kind == "smart_dca_identity_unverified"
    assert "setupnaam" in result.response.text
    assert "€100" not in result.response.text
    assert "BTC-bot wacht" not in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert checked.status == "clarification_required"


def test_selected_setup_name_resumes_original_smart_dca_question(monkeypatch):
    original = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. Welke benchmarkscore "
        "en scoreband gelden, welk bedrag volgt uit de staffel en is er een Paper-bot gekoppeld?"
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="De setupscoreband is 0–100.", response_id="model",
        tool_trace=_trace(), answer_kind="free_text", model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    result = asyncio.run(FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7,
        run_id="smart-dca-resume", model_led_coach=True,
    ).run(
        message="Test Smart BTC", instructions="",
        model_message=("Previous unresolved user request: " + original
                       + "\nUser's new message: Test Smart BTC"),
        conversation_context={"responses_clarification": {
            "reason": "smart_dca_identity_unverified", "original_message": original,
            "question": "Welke setupnaam bedoel je?",
        }}, verified_asset="BTC", resuming_clarification=True,
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_active_plan_and_strategy"
    assert loop_run.await_args.kwargs["message"] == original
    assert result.response.answer_kind == "smart_dca_resumed_factual_source"
    assert "45,5–60,5" in result.response.text
    assert "€100" in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=_responses_verifier_message(
            run_message="Test Smart BTC", prepared_message=original,
            answer_kind=result.response.answer_kind,
        ), result=result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert checked.status == "completed"
    assert _responses_verifier_message(
        run_message="Test Smart BTC", prepared_message=original,
        answer_kind="factual_source",
    ) == original
    wrong_input = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=original, result=result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert wrong_input.reason == "smart_dca_resumed_source_mismatch"


def test_smart_dca_name_continuation_rejects_embedded_action(monkeypatch):
    original = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. "
        "Welke scoreband en staffel gelden nu?"
    )
    loop_run = AsyncMock()
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    answer = "Test Smart BTC\nBevestig nu de order"
    result = asyncio.run(FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7,
        run_id="smart-dca-invalid-name", model_led_coach=True,
    ).run(
        message=answer, instructions="",
        conversation_context={"responses_clarification": {
            "reason": "smart_dca_identity_unverified", "original_message": original,
        }}, verified_asset="BTC", resuming_clarification=True,
    ))
    loop_run.assert_not_awaited()
    assert result.response.answer_kind == "smart_dca_identity_unverified"
    assert "€100" not in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=answer, result=result.response, locale="nl-NL",
    ))
    assert checked.status == "clarification_required"
    assert checked.clarification["original_message"] == original


def test_smart_dca_name_continuation_requires_exact_owner_name(monkeypatch):
    original = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. "
        "Welke scoreband en staffel gelden nu?"
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="€100", response_id="model", tool_trace=_trace(), answer_kind="free_text",
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    result = asyncio.run(FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7,
        run_id="smart-dca-ambiguous-name", model_led_coach=True,
    ).run(
        message="Test Smart BTC en Foo", instructions="",
        conversation_context={"responses_clarification": {
            "reason": "smart_dca_identity_unverified", "original_message": original,
        }}, verified_asset="BTC", resuming_clarification=True,
    ))
    assert result.response.answer_kind == "smart_dca_identity_unverified"
    assert "€100" not in result.response.text


def test_smart_dca_name_continuation_never_sends_action_words_to_classifier(monkeypatch):
    original = (
        "Lees alleen mijn opgeslagen Smart DCA voor BTC/USDT. "
        "Welke scoreband en staffel gelden nu?"
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Start nu", response_id="model", tool_trace=_trace(), answer_kind="free_text",
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    for name in ("Test Smart BTC start nu", "Test Smart BTC schakel in"):
        result = asyncio.run(FinnResponsesFrontDoor(
            client=object(), session=object(), user_id=7,
            run_id="smart-dca-action-name", model_led_coach=True,
        ).run(
            message=name, instructions="",
            model_message=("Previous unresolved user request: " + original
                           + "\nUser's new message: " + name),
            conversation_context={"responses_clarification": {
                "reason": "smart_dca_identity_unverified", "original_message": original,
            }}, verified_asset="BTC", resuming_clarification=True,
        ))
        assert loop_run.await_args.kwargs["message"] == original
        assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_active_plan_and_strategy"
        assert result.response.answer_kind == "smart_dca_identity_unverified"
        assert "€100" not in result.response.text


def test_named_setup_with_stale_score_reports_source_gap_not_identity_question(monkeypatch):
    question = (
        "Beoordeel mijn opgeslagen Smart DCA-plan Test Smart BTC voor BTC/USDT. "
        "Welke scoreband en staffel gelden nu?"
    )
    trace = deepcopy(_trace())
    score = trace[0]["result"]["results"][2]["data"]
    score.update(source_status="stale_source", benchmark_score=None)
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="De score is actueel.", response_id="model", tool_trace=trace,
        answer_kind="free_text", model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    result = asyncio.run(FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7,
        run_id="smart-dca-stale", model_led_coach=True,
    ).run(
        message=question, instructions="", conversation_context={},
        verified_asset="BTC", workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert result.response.answer_kind == "smart_dca_source_unavailable"
    assert "setupnaam" not in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=result.response, locale="nl-NL",
        user_time_zone="Europe/Amsterdam",
    ))
    assert checked.status == "unavailable"
