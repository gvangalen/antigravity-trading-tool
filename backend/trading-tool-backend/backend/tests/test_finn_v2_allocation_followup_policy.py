"""Keep allocation follow-ups anchored to the trader's focus and current question."""

import asyncio
from unittest.mock import AsyncMock

from backend.services.finn_v2_responses_front_door import (
    FinnResponsesFrontDoor, _personal_allocation_coaching, _standalone_read_subject,
)
from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall


def test_model_led_allocation_followup_avoids_stale_balance_recap_and_goal_drift():
    instructions = FinnResponsesFrontDoor._model_led_instructions("nl")

    assert "without recapping unchanged account facts" in instructions
    assert "Do not repeat the Paper cash, invested balance, or bot budget" in instructions
    assert "A bot budget remains a limit" in instructions
    assert "carry forward the trader's stated investment focus" in instructions
    assert "do not present an ETF-majority example" in instructions
    assert "Do not infer that BTC focus means all-in BTC" in instructions


def test_short_example_followup_requires_current_profile_read(monkeypatch):
    prior = {
        "terminal_status": "completed",
        "answer": "Wil je dat ik een voorbeeldverdeling voor jouw BTC-portefeuille maak?",
    }
    assert _personal_allocation_coaching("ja laat maar een voorbeeld zien.", prior)
    assert _personal_allocation_coaching("Hoe zou mijn portefeuille eruit moeten zien?", None)
    assert _personal_allocation_coaching(
        "Wat is een goede verdeling, hoeveel cash en hoeveel belegd?",
        {"terminal_status": "completed", "answer": "Jouw Paper-portefeuille bevat €10.000 cash."},
    )
    assert not _personal_allocation_coaching(
        "Hoe past dat bij mijn vrijdagplan, de scores en mijn portefeuille?", None,
    )
    assert not _personal_allocation_coaching("Wat is een ETF?", prior)

    front = FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7, run_id="allocation-followup",
        model_led_coach=True,
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Een BTC-gericht voorbeeld vraagt eerst om jouw risicogrens.",
        response_id="profile-read", tool_trace=(), answer_kind="free_text",
        model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    asyncio.run(front.run(
        message="ja laat maar een voorbeeld zien.", instructions="",
        conversation_context={}, verified_asset="BTC", previous_response=prior,
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_profile_portfolio_and_bots"


def test_live_qa_profile_allocation_question_is_not_reduced_to_readback():
    question = (
        "Mijn opgeslagen profiel heeft een BTC-focus. Geef een illustratief voorbeeld "
        "van hoe ik mijn aandacht tussen BTC, aandelen en kas zou kunnen verdelen, "
        "zonder dit als doelverdeling of koopadvies te presenteren. Behandel Paper-kas "
        "en botlimieten niet als belegde posities. Lees alleen."
    )
    facts = FinnV2RequestPreprocessorService().preprocess(message=question)
    assert _personal_allocation_coaching(question, None)
    assert _standalone_read_subject(question, facts) is None


def test_live_qa_bot_profile_portfolio_comparison_reads_both_sources(monkeypatch):
    question = (
        "Past mijn bestaande BTC Paper-bot bij mijn opgeslagen traderstijl en mijn "
        "huidige totale Paper-portefeuille? Vergelijk het botbudget met de echte "
        "belegde positie en totale kas; noem één controlepunt. Lees alleen, maak "
        "niets en wijzig niets."
    )
    front = FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7, run_id="bot-profile-review",
        model_led_coach=True,
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Ik vergelijk de gelezen bronnen.", response_id="review-read",
        tool_trace=(), answer_kind="free_text", model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    asyncio.run(front.run(
        message=question, instructions="", conversation_context={},
        verified_asset="BTC", previous_response=None,
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_profile_portfolio_and_bots"


def test_plan_review_reads_account_wide_portfolio_beside_selected_asset():
    selectors = {}

    class Reads:
        async def execute_tool(self, **kwargs):
            selectors[kwargs["tool_name"]] = kwargs["selector"]
            return type("Result", (), {
                "success": True, "availability": "available", "freshness_status": "unknown",
                "source": "owner_database", "asset": "BTC", "result": {}, "error_codes": [],
            })()

    reader = FinnResponsesReadExecutor(session=object(), user_id=7, run_id="plan-review")
    reader.reads = Reads()
    call = FinnResponsesToolCall(
        name="evaluate_plan", operation_id=None, inputs={"asset": "BTC"},
        read_tools=("read_profile", "read_portfolio"), required_inputs=(), missing_inputs=(),
        evaluation_operation_id="evaluate_plan",
    )
    asyncio.run(reader(call))
    assert selectors["read_profile"] == {"asset": "BTC"}
    assert selectors["read_portfolio"] == {}


def test_profile_portfolio_bundle_does_not_filter_total_paper_cash():
    selectors = {}

    class Reads:
        async def execute_tool(self, **kwargs):
            selectors[kwargs["tool_name"]] = kwargs["selector"]
            return type("Result", (), {
                "success": True, "availability": "available", "freshness_status": "unknown",
                "source": "owner_database", "asset": None, "result": {}, "error_codes": [],
            })()

    reader = FinnResponsesReadExecutor(session=object(), user_id=7, run_id="profile-portfolio")
    reader.reads = Reads()
    call = FinnResponsesToolCall(
        name="get_profile_portfolio_and_bots", operation_id=None,
        inputs={"asset": "BTC", "environment": "paper"},
        read_tools=("read_profile", "read_portfolio"),
        required_inputs=(), missing_inputs=(),
    )
    output = asyncio.run(reader(call))
    assert selectors["read_profile"] == {"asset": "BTC", "environment": "paper"}
    assert selectors["read_portfolio"] == {"environment": "paper"}
    assert next(row for row in output["results"] if row["scope"] == "read_portfolio")["asset"] is None


def test_live_qa_budget_cash_question_requires_portfolio_read(monkeypatch):
    question = ("Wat is de ingestelde budgetlimiet van mijn BTC Paper-bot, hoeveel is "
                "werkelijk belegd en hoeveel kas is er? Noem die drie afzonderlijk; "
                "lees alleen en verander niets.")
    front = FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7, run_id="budget-cash",
        model_led_coach=True,
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Ik lees de portefeuille.", response_id="portfolio-read", tool_trace=(),
        answer_kind="free_text", model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    asyncio.run(front.run(
        message=question, instructions="", conversation_context={},
        verified_asset="BTC", previous_response=None,
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_portfolio_and_exposure"
