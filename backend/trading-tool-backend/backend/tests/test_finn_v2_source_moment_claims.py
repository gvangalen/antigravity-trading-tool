from backend.services.finn_v2_source_moment_claims import (
    complete_requested_bot_status_read_time, current_source_moments_supported,
    source_moment_repair_facts,
)


def test_requested_bot_status_read_time_uses_its_own_owner_bound_read():
    question = "Lees de actuele botstatus en noem de bronmomenten."
    evidence = ({"scope": "read_bot_status", "status": "completed", "data": {
        "bot_id": 130, "read_at": "2026-11-24T13:39:06+00:00",
        "latest_decision": {"decision_at": "2026-11-24T13:33:29+00:00"},
    }}, {"scope": "read_portfolio", "status": "completed", "data": {
        "read_at": "2026-11-24T13:39:06+00:00",
    }})
    first = ("- Laatste botbesluit: 24 november 2026 om 14:33:29 CET.\n"
             "- Actuele botstatus is opnieuw gelezen; de bot stond daarbij actief.\n"
             "- Paper-portefeuille en waardering: 24 november 2026 om 14:39:06 CET.")
    completed = complete_requested_bot_status_read_time(
        first, evidence, question=question, user_time_zone="Europe/Amsterdam",
    )
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in completed
    reread = ({**evidence[0], "data": {**evidence[0]["data"],
               "read_at": "2026-11-24T13:40:07+00:00"}},)
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:40:07 CET" in (
        complete_requested_bot_status_read_time(
            first, evidence + reread, question=question,
            user_time_zone="Europe/Amsterdam",
        )
    )
    assert complete_requested_bot_status_read_time(
        first, evidence + ({**evidence[0], "data": {**evidence[0]["data"],
                         "bot_id": 57}},), question=question,
        user_time_zone="Europe/Amsterdam",
    ) == first
    changed_status = {**reread[0], "data": {**reread[0]["data"], "is_active": False}}
    assert complete_requested_bot_status_read_time(
        first, evidence + (changed_status,), question=question,
        user_time_zone="Europe/Amsterdam",
    ) == first
    shared = (
        "De beslissing is vastgelegd op 24 november 2026 om 14:33:29 CET. "
        "De botstatus en Paper-portefeuille zijn opnieuw uitgelezen op "
        "24 november 2026 om 14:39:06 CET."
    )
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in (
        complete_requested_bot_status_read_time(
            shared, evidence, question=question,
            user_time_zone="Europe/Amsterdam",
        )
    )
    unequal = (evidence[0], {**evidence[1], "data": {
        "read_at": "2026-11-24T13:39:07+00:00",
    }})
    wrong_shared = shared.replace("14:39:06 CET", "14:39:07 CET")
    assert not current_source_moments_supported(wrong_shared, unequal, question=question)
    assert not current_source_moments_supported(
        wrong_shared.replace("botstatus en Paper-portefeuille",
                             "botstatus en de Paper-portefeuille"),
        unequal, question=question,
    )
    bare_shared = (
        "De botstatus en de Paper-portefeuille zijn opnieuw uitgelezen om "
        "14:39:07 CET."
    )
    assert not current_source_moments_supported(bare_shared, unequal, question=question)
    assert current_source_moments_supported(
        bare_shared.replace("14:39:07 CET", "14:39 CET"), unequal,
        question=question,
    )
    assert not current_source_moments_supported(
        "De botstatus en Paper-portefeuille zijn opnieuw uitgelezen om "
        "14:39:06 CET en 14:38:06 CET.", evidence, question=question,
    )
    assert not current_source_moments_supported(
        complete_requested_bot_status_read_time(
            wrong_shared, unequal, question=question,
            user_time_zone="Europe/Amsterdam",
        ), unequal, question=question,
    )
    assert current_source_moments_supported(completed, evidence, question=question)
    assert complete_requested_bot_status_read_time(
        completed, evidence, question=question, user_time_zone="Europe/Amsterdam",
    ) == completed
    assert complete_requested_bot_status_read_time(
        first, (), question=question, user_time_zone="Europe/Amsterdam",
    ) == first
    assert "America/New_York" in complete_requested_bot_status_read_time(
        first, evidence, question=question, user_time_zone="America/New_York",
    )
    mixed = "De botstatus is gelezen en het botbesluit was 24 november 2026 om 14:33:29 CET."
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in (
        complete_requested_bot_status_read_time(
            mixed, evidence, question=question, user_time_zone="Europe/Amsterdam",
        )
    )
    hold_first = "Laatste Hold was 14:33:29 CET en de botstatus is opnieuw gelezen."
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in (
        complete_requested_bot_status_read_time(
            hold_first, evidence, question=question, user_time_zone="Europe/Amsterdam",
        )
    )
    other_bot = ({"scope": "read_bot_status", "status": "completed", "data": {
        "bot_id": 57, "read_at": "2026-11-24T13:39:06+00:00",
    }},)
    named_question = "Lees de actuele botstatus van bot #56 en noem de bronmomenten."
    named_answer = "Bot #56: de actuele botstatus is opnieuw gelezen."
    assert complete_requested_bot_status_read_time(
        named_answer, other_bot, question=named_question, user_time_zone="Europe/Amsterdam",
    ) == named_answer
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in (
        complete_requested_bot_status_read_time(
            named_answer, ({**other_bot[0], "data": {**other_bot[0]["data"], "bot_id": 56}},),
            question=named_question, user_time_zone="Europe/Amsterdam",
        )
    )


def test_model_owned_coach_accepts_only_typed_status_clock_completion():
    import asyncio
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
    from backend.services.finn_v2_responses_loop import FinnResponsesResult

    message = "Lees de actuele botstatus en noem de bronmomenten."
    evidence = ({"scope": "read_bot_status", "status": "completed", "data": {
        "bot_id": 130, "read_at": "2026-11-24T13:39:06+00:00",
        "latest_decision": {"decision_at": "2026-11-24T13:33:29+00:00"},
    }},)
    result = FinnResponsesResult(
        text="De actuele botstatus is opnieuw gelezen. Het laatste botbesluit was 24 november 2026 om 14:33:29 CET.",
        response_id="test-status-clock", answer_kind="free_text", model_owned_repair=True,
        tool_trace=({"name": "get_active_plan_and_strategy", "result": {"results": list(evidence)}},),
    )
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=message, result=result, locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert verified.status == "completed", verified.reason
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in verified.text
    wrong_bot = replace(result,
        text="Bot #56: de actuele botstatus is opnieuw gelezen.",
        tool_trace=({"name": "get_active_plan_and_strategy", "result": {"results": [
            {**evidence[0], "data": {**evidence[0]["data"], "bot_id": 57}},
        ]}},),
    )
    rejected_completion = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message="Lees de actuele botstatus van bot #56 en noem de bronmomenten.",
        result=wrong_bot, locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert "14:39:06 CET" not in rejected_completion.text
    wrong_asset = replace(result,
        text="De actuele AAPL-botstatus is opnieuw gelezen.",
        tool_trace=({"name": "get_active_plan_and_strategy", "result": {"results": [
            {**evidence[0], "asset": "BTC"},
        ]}},),
    )
    asset_question = "Lees de actuele AAPL-botstatus en noem de bronmomenten."
    wrong_asset_answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=asset_question, result=wrong_asset, locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert wrong_asset_answer.status == "unavailable"
    assert wrong_asset_answer.reason == "bot_status_subject_conflicts_with_source"
    assert "14:39:06 CET" not in wrong_asset_answer.text
    matching_asset = replace(wrong_asset, tool_trace=({"name": "get_active_plan_and_strategy",
        "result": {"results": [{**evidence[0], "asset": "AAPL"}]}},))
    matching_asset_answer = asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=asset_question, result=matching_asset, locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert matching_asset_answer.status == "completed", matching_asset_answer.reason
    assert "Botstatus opnieuw gelezen: 24 november 2026 om 14:39:06 CET" in matching_asset_answer.text


def test_future_paper_portfolio_measurement_is_not_verified_as_current():
    evidence = ({"scope": "read_portfolio", "status": "completed",
                 "data": {"read_at": "2026-11-16T09:00:40+00:00"}},)
    diagnostics = []
    assert not current_source_moments_supported(
        "De actuele Paper-portefeuillemeting is van 16 november 2026 om 20:00:40 CET.",
        evidence, diagnostics=diagnostics,
    )
    assert diagnostics == ["portfolio_read_clock_mismatch"]
    assert current_source_moments_supported(
        "De actuele Paper-portefeuillemeting is van 16 november 2026 om 10:00:40 CET.",
        evidence,
    )


def test_portfolio_read_clock_without_repeated_date_matches_only_this_turns_source():
    evidence = ({"scope": "read_portfolio", "status": "completed",
                 "data": {"read_at": "2026-11-24T11:08:16.948510+00:00"}},)
    answer = "De Paper-portefeuille is opnieuw gelezen om **12:08:16 CET**."
    assert current_source_moments_supported(answer, evidence)
    for unsupported in (
        "De Paper-portefeuille is opnieuw gelezen om 12:09:16 CET.",
        "De Paper-portefeuille is opnieuw gelezen om 12:08:16 UTC.",
        "De Paper-portefeuille is opnieuw gelezen om 24 november 2025 12:08:16 CET.",
        "De Paper-portefeuille is opnieuw gelezen om 12:08:16 CET op 23 november 2025.",
        "Op 23 november 2025 is de Paper-portefeuille om 12:08:16 CET opnieuw gelezen.",
        "In 2025 is de Paper-portefeuille om 12:08:16 CET opnieuw gelezen.",
        "De Paper-portefeuille is opnieuw gelezen om 12:08:16 CET en 12:09:16 CET.",
    ):
        diagnostics = []
        assert not current_source_moments_supported(
            unsupported, evidence, diagnostics=diagnostics,
        )
        assert diagnostics == ["portfolio_read_clock_mismatch"]
    assert not current_source_moments_supported(answer, ())
    assert current_source_moments_supported(
        "Op 24 november 2026 is de Paper-portefeuille om 12:08:16 CET opnieuw gelezen.",
        evidence,
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 12:08:16 CET gelezen; de botcheck was om 12:03:29 CET.",
        evidence,
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 12:08:16 CET gelezen, de botcheck was om 12:03:29 CET.",
        evidence,
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 12:08:16 CET gelezen en de botcheck was om 12:03:29 CET.",
        evidence,
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 12:08:16 CET gelezen; de benchmarkscore is uit 2026.",
        evidence,
    )
    assert not current_source_moments_supported(
        "De Paper-portefeuille is om 12:08:16 CET gelezen; "
        "de Paper-portefeuille is opnieuw gelezen om 12:09:16 CET.",
        evidence,
    )


def test_bot_decision_clocks_match_saved_report_or_latest_owner_read():
    evidence = (
        {"scope": "read_latest_report", "status": "completed", "data": {
            "score_source_snapshot": {"report_v2": {"automation": {"bots": [{
                "bot_id": 129, "symbol": "BTC",
                "latest_decision": {"at": "2026-11-16T04:15:18"},
            }]}}},
        }},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"bot_id": 129, "symbol": "BTC",
                                     "decision_at": "2026-11-16T08:45:18+00:00"}],
        }},
    )
    diagnostics = []
    assert not current_source_moments_supported(
        "De BTC-botbeoordeling was op 16 november 2026 om 04:15:18 CET.",
        evidence, diagnostics=diagnostics,
    )
    assert diagnostics == ["bot_decision_clock_mismatch"]
    assert current_source_moments_supported(
        "De BTC-botbeoordeling in het rapport was op 16 november 2026 om 05:15:18 CET. "
        "De huidige BTC-botcheck was op 16 november 2026 om 09:45:18 CET.",
        evidence,
    )
    assert current_source_moments_supported(
        "De BTC-bot gaf geen order; de oudste indicatorbron was 15 november 2026 om 23:59 UTC.",
        evidence,
    )
    assert not current_source_moments_supported(
        "In het gelezen bewijs staat geen BTC-botbesluit om 05:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "Er is geen BTC-botbesluit op 16 november 2026 om 05:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "04:15 is UTC, niet CET. De gelezen BTC-botbesluiten zijn nu om 09:45:18 CET. "
        "In het gelezen bewijs staat geen BTC-botbesluit om 05:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "In het gelezen bewijs staat geen BTC- of AAPL-besluit om 05:15 CET.", evidence,
    )
    assert current_source_moments_supported(
        "Er is geen nieuw BTC-botbesluit om 05:15 CET; het rapport bewaart het oude besluit.", evidence,
    )
    facts = source_moment_repair_facts(evidence)
    assert {fact["kind"]: fact["amsterdam"] for fact in facts if "bot_decision" in fact["kind"]} == {
        "report_bot_decision": "2026-11-16T05:15:18+01:00",
        "current_bot_decision": "2026-11-16T09:45:18+01:00",
    }


def test_bot_status_read_clock_is_not_another_saved_decision_clock():
    evidence = (
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"bot_id": 56, "symbol": "BTC",
                                      "decision_at": "2026-11-24T12:03:29.343838+00:00"}],
        }},
        {"scope": "read_bot_status", "status": "completed", "data": {
            "bot_id": 56, "read_at": "2026-11-24T12:17:09+00:00",
        }},
    )
    answer = (
        "De beslissing is vastgelegd op 24 november 2026 om 13:03:29 CET; "
        "de botstatus en Paper-bedragen zijn opnieuw gelezen op "
        "24 november 2026 om 13:17:09 CET."
    )
    assert current_source_moments_supported(answer, evidence)
    assert current_source_moments_supported(
        answer.replace("botstatus", "bot status"), evidence,
    )
    assert not current_source_moments_supported(
        answer.replace("13:03:29 CET", "13:04:29 CET"), evidence,
    )
    assert not current_source_moments_supported(
        answer.replace("13:17:09 CET", "13:59:59 CET"), evidence,
    )
    assert not current_source_moments_supported(answer, evidence[:1])
    assert current_source_moments_supported(
        "De botstatus is opnieuw gelezen op 24 november 2026 om 13:17:09 CET.",
        evidence[1:],
    )
    assert not current_source_moments_supported(
        "De botstatus is opnieuw gelezen op 24 november 2026 om 13:59:59 CET.",
        evidence[1:],
    )
    assert not current_source_moments_supported(
        "De botstatus is opnieuw gelezen op 24 november 2026 om 13:17:09 CET.",
        ({**evidence[1], "data": {"bot_id": 56}},),
    )
    other_bot = {"scope": "read_bot_status", "status": "completed", "data": {
        "bot_id": 57, "read_at": "2026-11-24T12:18:09+00:00",
    }}
    assert not current_source_moments_supported(
        "De botstatus van bot #56 is opnieuw gelezen op "
        "24 november 2026 om 13:18:09 CET.",
        evidence + (other_bot,),
    )
    assert not current_source_moments_supported(
        "Het BTC-botbesluit was op 24 november 2026 om 13:17:09 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "De botstatus toont de laatste Hold van 24 november 2026 om 13:17:09 CET.", evidence,
    )
    mixed = (
        "De botstatus is om 13:17:09 CET opnieuw gelezen en toont de laatste Hold "
        "van 13:03:29 CET."
    )
    assert current_source_moments_supported(mixed, evidence)
    assert not current_source_moments_supported(
        mixed.replace("om 13:17:09 CET", "om 13:03:29 CET"), evidence,
    )
    reverse = (
        "De botstatus toont de laatste Hold van 13:03:29 CET "
        "en is opnieuw gelezen op 13:17:09 CET."
    )
    assert current_source_moments_supported(reverse, evidence)
    assert not current_source_moments_supported(
        reverse.replace("op 13:17:09 CET", "op 13:03:29 CET"), evidence,
    )
    assert current_source_moments_supported(
        mixed.replace("en toont", "en meldt"), evidence,
    )
    status_only = ({**evidence[1], "data": {
        **evidence[1]["data"],
        "latest_decision": {"decision_at": "2026-11-24T12:03:29+00:00"},
    }},)
    assert current_source_moments_supported(
        "De botstatus is om 13:17:09 CET opnieuw gelezen; "
        "het laatste Hold-besluit was om 13:03:29 CET.", status_only,
    )
    assert not current_source_moments_supported(
        "De botstatus is om 13:17:09 CET opnieuw gelezen; "
        "het laatste Hold-besluit was om 13:59:59 CET.", status_only,
    )
    mixed_dates = (
        "De botstatus is om 13:17:09 CET gelezen en vermeldt de laatste Hold "
        "van 24 november 2026 om 13:03:29 CET."
    )
    assert current_source_moments_supported(mixed_dates, status_only)
    assert not current_source_moments_supported(
        mixed_dates.replace("om 13:17:09 CET gelezen", "om 13:03:29 CET gelezen")
        .replace("om 13:03:29 CET.", "om 13:17:09 CET."), status_only,
    )
    assert current_source_moments_supported(
        "De botstatus is opnieuw gelezen en toont de laatste Hold van "
        "24 november 2026 om 13:03:29 CET.", status_only,
    )
    assert current_source_moments_supported(
        "De botstatus toont de laatste Hold van 13:03:29 CET "
        "en is opnieuw gelezen.", status_only,
    )
    assert not current_source_moments_supported(
        "De botstatus is om 13:03:29 CET en om 13:17:09 CET opnieuw gelezen "
        "en toont de laatste Hold van 13:03:29 CET.", status_only,
    )
    assert not current_source_moments_supported(
        "De botstatus is opnieuw gelezen om 13:17:09 CET en 13:03:29 CET; "
        "de laatste Hold was om 13:03:29 CET.", status_only,
    )
    assert current_source_moments_supported(
        "De botstatus is om 13:17:09 CET gelezen en toont Hold van 13:03:29 CET.",
        status_only,
    )
    portfolio = {"scope": "read_portfolio", "status": "completed", "data": {
        "read_at": "2026-11-24T12:18:07+00:00",
    }}
    assert current_source_moments_supported(
        "De botstatus is om 13:17:09 CET gelezen en de Paper-portefeuille "
        "om 13:18:07 CET uitgelezen.", status_only + (portfolio,),
    )
    assert not current_source_moments_supported(
        "De botstatus is om 13:17:09 CET gelezen en de Paper-portefeuille "
        "om 13:19:07 CET uitgelezen.", status_only + (portfolio,),
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 13:18:07 CET uitgelezen en de botstatus "
        "is om 13:17:09 CET gelezen.", status_only + (portfolio,),
    )
    assert not current_source_moments_supported(
        "De Paper-portefeuille is om 13:19:07 CET uitgelezen en de botstatus "
        "is om 13:17:09 CET gelezen.", status_only + (portfolio,),
    )
    assert current_source_moments_supported(
        "De Paper-portefeuille is om 13:18:07 CET uitgelezen en de bot status "
        "is om 13:17:09 CET gelezen.", status_only + (portfolio,),
    )


def test_report_decision_cannot_be_called_latest_when_later_bot_checks_were_read():
    evidence = (
        {"scope": "read_latest_report", "status": "completed", "data": {
            "score_source_snapshot": {"report_v2": {"automation": {"bots": [
                {"bot_id": 129, "symbol": "BTC", "latest_decision": {"at": "2026-11-20T04:15:18"}},
                {"bot_id": 130, "symbol": "AAPL", "latest_decision": {"at": "2026-11-20T04:15:17"}},
            ]}}},
        }},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [
                {"bot_id": 129, "symbol": "BTC", "decision_at": "2026-11-20T19:15:17+00:00"},
                {"bot_id": 130, "symbol": "AAPL", "decision_at": "2026-11-20T19:15:17+00:00"},
            ],
        }},
    )
    assert current_source_moments_supported(
        "De AAPL-botbeslissing in de rapportmomentopname was om 05:15 CET. "
        "De nieuwste AAPL-botbeslissing was om 20:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "De nieuwste AAPL-botbeslissing was om 05:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "De laatste BTC-botcheck was om 05:15 CET.", evidence,
    )
    assert not current_source_moments_supported(
        "Het dagrapport toont de AAPL-bot om 05:15 CET, maar de laatste AAPL-botcheck was om 05:15 CET.",
        evidence,
    )
    assert not current_source_moments_supported(
        "De AAPL-botbeslissing was om 05:15 CET.", evidence,
        question="Vergelijk mijn actuele AAPL- en BTC-botchecks met het nachtrapport.",
    )
    assert current_source_moments_supported(
        "De AAPL-botbeslissing in de rapportmomentopname was om 05:15 CET. "
        "De latere AAPL-botcheck was om 20:15 CET.", evidence,
        question="Vergelijk mijn actuele AAPL- en BTC-botchecks met het nachtrapport.",
    )
    assert not current_source_moments_supported(
        "De laatste AAPL-botbeslissing was om 05:15 CET.", evidence[:1],
    )

from backend.services.finn_v2_run_service import _minimal_read_answer
from types import SimpleNamespace


def _evidence():
    return (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "quote_currency": "USD", "price": 356.17,
            "source_observed_at_utc": "2026-11-13T20:59:00+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "USDT", "price": 74968,
            "source_observed_at_utc": "2026-11-13T20:55:01+00:00",
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-13T21:03:00+00:00",
        }},
    )


def test_source_moment_retry_facts_keep_pairs_and_clocks_separate():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "EUR", "price": 3000,
            "source_observed_at": "2026-11-15T09:02:06+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "USDT", "price": 3500,
            "source_observed_at": "2026-11-15T08:59:30+00:00",
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-15T09:04:00+00:00", "cash_balance": 10000,
        }},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "generated_at": "2026-11-15T05:00:00+00:00",
            "score_source_snapshot": {"assets": [{
                "pair": "ETH/EUR", "market_snapshot": {
                    "as_of": "2026-11-15T04:59:00+00:00",
                },
            }]},
        }},
        {"scope": "read_market_snapshot", "status": "unavailable", "data": {
            "symbol": "SOL", "quote_currency": "EUR", "price": 100,
            "source_observed_at": "2026-11-15T09:00:00+00:00",
        }},
    )
    facts = source_moment_repair_facts(evidence)
    assert [(fact["kind"], fact["source"]) for fact in facts] == [
        ("quote_source", "ETH/EUR"), ("quote_source", "ETH/USDT"),
        ("read_time", "portfolio"), ("report_quote_source", "ETH/EUR"),
        ("generation_time", "report"),
    ]
    assert facts[0]["amsterdam"] == "2026-11-15T10:02:06+01:00"
    assert facts[1]["utc"] == "2026-11-15T08:59:30+00:00"
    assert "cash_balance" not in str(facts)


def test_multi_asset_quote_table_requires_the_current_source_for_each_row():
    answer = (
        "| Instrument | Benchmark | Koersbronmoment |\n"
        "| AAPL | 52,7 | 13 november 2026, 20:59 UTC |\n"
        "| BTC/USDT | 35,0 | 13 november 2026, 21:55:01 CET |"
    )
    assert current_source_moments_supported(answer, _evidence())
    assert not current_source_moments_supported(
        answer.replace("20:59 UTC", "20:44 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(answer, _evidence()[1:])


def test_live_four_column_comparison_cannot_use_an_old_aapl_source():
    answer = (
        "| Instrument | Markt / macro / techniek | Benchmark | Koersbronmoment | "
        "| BTC/USDT | 50 / 20 / 35 | 35,0 | 13 november 2026, 20:55:01 UTC | "
        "| AAPL | 80 / 20 / 58 | 52,7 | 13 november 2026, 20:44 UTC |"
    )
    assert not current_source_moments_supported(answer, _evidence())
    assert current_source_moments_supported(
        answer.replace("20:44 UTC", "21:59 CET"), _evidence(),
    )


def test_portfolio_read_time_must_convert_cet_and_utc_from_one_instant():
    correct = "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 CET toont €10.005,45."
    assert current_source_moments_supported(correct, _evidence())
    assert current_source_moments_supported(
        correct.replace("22:03 CET", "21:03 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(
        correct.replace("22:03 CET", "22:03 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(
        correct.replace("van 13 november", "op 13 november").replace("22:03 CET", "22:03 UTC"),
        _evidence(),
    )
    assert not current_source_moments_supported(
        "De actuele portefeuille is opgehaald op 13 nov 2026, 22:03 UTC.", _evidence(),
    )
    assert current_source_moments_supported(
        "De actuele portefeuille is opgehaald op 13 nov 2026, 22:03 CET.", _evidence(),
    )


def test_summer_and_winter_labels_are_checked_against_amsterdam_zone():
    summer = ({"scope": "read_portfolio", "status": "completed",
               "data": {"read_at": "2026-07-01T12:00:00+00:00"}},)
    assert current_source_moments_supported(
        "De actuele Paper-portefeuille-snapshot van 1 juli 2026 om 14:00 CEST is geladen.",
        summer,
    )
    assert not current_source_moments_supported(
        "De actuele Paper-portefeuille-snapshot van 1 juli 2026 om 14:00 CET is geladen.",
        summer,
    )


def test_historical_report_moment_remains_separate_from_current_read():
    answer = (
        "Het oude dagrapport noemt 9 november 2026 om 19:03 UTC. "
        "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 CET toont geen posities."
    )
    assert current_source_moments_supported(answer, _evidence())
    assert not current_source_moments_supported(
        "Vergeleken met het oude dagrapport toont de verse Paper-portefeuille-uitlezing "
        "van 13 november 2026 om 22:03 UTC geen posities.", _evidence(),
    )


def test_live_report_generation_utc_and_cet_must_be_the_same_instant():
    report = ({"scope": "read_latest_report", "status": "completed", "data": {
        "report_date": "2026-11-14", "generated_at": "2026-11-14T04:33:08+00:00",
    }},)
    wrong = ("Het dagrapport werd gegenereerd om 04:33:08 UTC "
             "(04:33:08 in Europe/Amsterdam, CET).")
    assert not current_source_moments_supported(wrong, report)
    assert current_source_moments_supported(
        wrong.replace("(04:33:08 in", "(05:33:08 in"), report,
    )
    assert not current_source_moments_supported(
        "Rapport opgesteld: 14 november 2026, 04:33 CET.", report,
    )
    assert current_source_moments_supported(
        "Rapport opgesteld: 14 november 2026, 05:33 CET.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport is gegenereerd om 05:33:08 CET en de BTC/EUR-koersbron "
        "daarin was 04:29:59 UTC.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport is gegenereerd om 04:33:08 UTC en de BTC/EUR-koersbron "
        "daarin was 05:29:59 CET.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport werd gegenereerd met de koersbron van 04:29:59 UTC.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport werd gegenereerd om 05:33:08 CET "
        "(koersbron BTC/EUR 04:29:59 UTC).", report,
    )


def test_report_generation_uses_ce_st_in_summer():
    report = ({"scope": "read_latest_report", "status": "completed", "data": {
        "generated_at": "2026-07-14T04:33:08+00:00",
    }},)
    assert current_source_moments_supported(
        "Rapport opgesteld om 06:33:08 CEST.", report,
    )
    assert not current_source_moments_supported(
        "Rapport opgesteld om 05:33:08 CET.", report,
    )


def test_explicit_cet_report_comparison_requires_local_saved_quote_source():
    evidence = ({"scope": "read_latest_report", "status": "completed", "data": {
        "generated_at": "2026-11-14T04:33:08+00:00",
        "score_source_snapshot": {"assets": [{
            "pair": "BTC/EUR", "market_snapshot": {"as_of": "2026-11-14T04:29:59+00:00"},
        }]},
    }},)
    question = ("Vergelijk mijn dagrapport van 14 november voor BTC/EUR met de "
                "nieuwste BTC/EUR-koers. Noem apart rapportmoment, koersbron in "
                "het rapport en huidige koersbronmoment in CET.")
    utc_only = ("Het dagrapport is gegenereerd om 05:33:08 CET. De historische "
                "koersbron is 14 november 2026 om 04:29:59 UTC.")
    assert not current_source_moments_supported(utc_only, evidence, question=question)
    assert current_source_moments_supported(
        utc_only.replace("04:29:59 UTC", "05:29:59 CET"), evidence, question=question,
    )


def test_current_market_source_in_prose_requires_the_matching_quote_read():
    wrong = "Het nieuwste AAPL-koersbronmoment is 13 november 2026 om 20:44 UTC."
    assert not current_source_moments_supported(wrong, _evidence())
    assert current_source_moments_supported(
        wrong.replace("20:44 UTC", "21:59 CET"), _evidence(),
    )
    assert not current_source_moments_supported(
        wrong.replace("20:44 UTC", "20:59 UTC"), _evidence()[1:],
    )
    historical = "Het laatste AAPL-koersbronmoment in het oude dagrapport was 9 november 2026 om 19:03 UTC."
    assert current_source_moments_supported(historical, _evidence())
    assert current_source_moments_supported(
        "In het oude dagrapport was het laatste AAPL-koersbronmoment 9 november 2026 om 19:03 UTC.",
        _evidence(),
    )
    assert current_source_moments_supported(
        "Het nieuwste koersbronmoment is 13 november 2026 om 20:59 UTC.",
        _evidence()[:1],
    )


def test_live_latest_aapl_quote_rejects_wrong_parenthesized_source_day():
    evidence = ({"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "quote_currency": "USD", "price": 356.4,
        "source_observed_at_utc": "2026-11-13T21:00:00+00:00",
    }},)
    question = (
        "Wat is de nieuwste beschikbare AAPL-koers? Noem uitsluitend prijs, "
        "databron, exact bronmoment in Europe/Amsterdam en of de beurs nu open is."
    )
    wrong = "$356,40 USD · Twelve Data · 14 november 2026, 22:00:00 CET " \
            "(Europe/Amsterdam) · Beurs nu: gesloten."
    assert not current_source_moments_supported(wrong, evidence, question=question)
    assert not current_source_moments_supported(
        "$356,40 USD. Twelve Data · 14 november 2026, 22:00:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "AAPL: $356,40 USD. Bron: Twelve Data. Gemeten: 14 november 2026, 22:00:00 CET.",
        evidence, question=question,
    )
    assert current_source_moments_supported(
        wrong.replace("14 november", "13 november"), evidence, question=question,
    )
    assert current_source_moments_supported(
        "In het oude dagrapport was de laatste AAPL-koers $356,40 USD "
        "op 9 november 2026 om 22:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "De laatste AAPL-koers in het dagrapport was $350 USD "
        "op 9 november 2026 om 22:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "Het dagrapport bevatte een oudere AAPL-koers van $350 USD op "
        "9 november 2026 om 22:00 CET. Het plan is bijgewerkt op "
        "14 november 2026 om 08:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "Het dagrapport bevatte een oudere AAPL-koers van $350 USD op "
        "9 november 2026 om 22:00 CET. De analyse is aangemaakt op "
        "14 november 2026 om 08:00 CET.", evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch, maar de nieuwste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "In het rapport staat een oudere koers; de actuele AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch en de nieuwste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch en de laatste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "De nieuwste AAPL-koers is $356,40 USD op 14 november 2026 om "
        "22:00 CET en het oude rapport toont een andere koers.",
        evidence, question=question,
    )
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text=wrong,
            tool_trace=({"name": "get_market_snapshot", "result": {"results": list(evidence)}},),
            uses_previous_response=False,
        ),
        previous_response=None,
    )
    rejected = _minimal_read_answer(message=question, prepared=prepared)
    assert rejected.status == "unavailable"
    assert rejected.reason == "source_moment_conflicts_with_source"


def test_current_market_source_in_prose_keeps_exact_quote_pair():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "EUR", "price": 66732,
            "source_observed_at_utc": "2026-11-13T20:59:00+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "USDT", "price": 74968,
            "source_observed_at_utc": "2026-11-13T20:44:00+00:00",
        }},
    )
    assert current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:44 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:59 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste bronmoment van BTC/USDT is 13 november 2026 om 20:59 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:59 UTC.",
        evidence[:1],
    )


def test_source_moment_claim_uses_its_own_pair_in_multi_plan_sentence():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "EUR", "price": 3000,
            "source_observed_at_utc": "2026-11-15T09:02:06+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "USDT", "price": 3500,
            "source_observed_at_utc": "2026-11-15T08:59:00+00:00",
        }},
    )
    prefix = "De ETH/EUR-setup en ETH/USDT-bot zijn apart en het actuele ETH/EUR-koersbronmoment is "
    assert current_source_moments_supported(
        prefix + "15 november 2026 om 10:02:06 CET.", evidence,
    )
    assert not current_source_moments_supported(
        prefix + "15 november 2026 om 09:59 CET.", evidence,
    )

    diagnostics = []
    assert not current_source_moments_supported(
        prefix + "15 november 2026 om 09:59 CET.", evidence,
        diagnostics=diagnostics,
    )
    assert diagnostics == ["current_quote_source_prose_mismatch"]


def test_unrelated_second_table_is_not_treated_as_a_quote_source_table():
    answer = (
        "| Instrument | Benchmark | Koersbronmoment |\n"
        "| AAPL | 52,7 | 13 nov 2026, 21:59 CET |\n\n"
        "| Asset | Type | Status |\n"
        "| AAPL | aandeel | actief |"
    )
    assert current_source_moments_supported(answer, _evidence())
    assert current_source_moments_supported(answer.replace("\n\n", " "), _evidence())


def test_live_read_answer_rejects_wrong_zone_before_delivery():
    text = "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 UTC toont €10.005,45."
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text=text,
            tool_trace=({"name": "get_portfolio", "result": {"results": list(_evidence())}},),
            uses_previous_response=False,
        ),
        previous_response=None,
    )
    rejected = _minimal_read_answer(message="Hoe staat mijn Paper-kas?", prepared=prepared)
    assert rejected.status == "unavailable"
    assert rejected.reason == "source_moment_conflicts_with_source"
    assert rejected.rejection_details["source_moment_facts"][-1] == {
        "kind": "read_time", "source": "portfolio",
        "utc": "2026-11-13T21:03:00+00:00",
        "amsterdam": "2026-11-13T22:03:00+01:00",
    }


def test_multi_source_coach_recovers_from_wrong_model_time_with_current_reads():
    question = "Beoordeel mijn AAPL-setup, score, bot, rapport, koers en Paper-kas. Wijzig niets."
    evidence = [
        {"scope": "read_active_setup", "status": "completed", "data": {
            "symbol": "AAPL", "name": "AAPL setup", "min_benchmark_score": 61, "max_benchmark_score": 75}},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                                      "decision_at": "2026-11-19T20:30:00+00:00",
                                      "safety_reason": "Reguliere sessie gesloten"}]}},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "price": 349.34, "quote_currency": "USD",
            "source_observed_at_utc": "2026-11-19T20:29:00+00:00"}},
    ]
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text="De actuele AAPL-koers is $349,34 van 19 november 2026 om 18:00 CET.",
            tool_trace=({"name": "get_market_snapshot", "result": {"results": evidence}},),
            uses_previous_response=False,
            turn_contract={"coach_evidence_plan": {"topics": (
                "setup", "score", "bot", "report", "quote", "portfolio")}},
        ), previous_response=None,
    )
    recovered = _minimal_read_answer(
        message=question, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert recovered.status == "completed"
    assert "Reguliere sessie gesloten" in recovered.text
    assert "21:29:00 CET" in recovered.text
    assert "18:00 CET" not in recovered.text
    assert "geen verifieerbare actuele score" in recovered.text


def test_live_read_answer_rejects_denial_of_saved_historical_bot_decision():
    evidence = (
        {"scope": "read_latest_report", "status": "completed", "data": {
            "generated_at": "2026-11-16T04:21:39+00:00",
            "score_source_snapshot": {"report_v2": {"automation": {"bots": [{
                "bot_id": 129, "symbol": "BTC",
                "latest_decision": {"at": "2026-11-16T04:15:18"},
            }]}}},
        }},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"bot_id": 129, "symbol": "BTC",
                                     "decision_at": "2026-11-16T14:30:17+00:00"}],
        }},
    )
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text="De nieuwste BTC-botbeoordeling is van 15:30 CET. "
                 "In het gelezen bewijs staat geen BTC-botbesluit om 05:15 CET.",
            tool_trace=({"name": "get_decision_history", "result": {"results": list(evidence)}},),
            uses_previous_response=False,
        ),
        previous_response=None,
    )
    rejected = _minimal_read_answer(
        message="Vergelijk mijn dagrapport met de BTC-botbesluiten.", prepared=prepared,
    )
    assert rejected.status == "unavailable"
    assert rejected.reason == "source_moment_conflicts_with_source"
    assert rejected.rejection_details["source_moment_rule"] == "bot_decision_clock_mismatch"
    assert any(fact["kind"] == "report_bot_decision" for fact in
               rejected.rejection_details["source_moment_facts"])


def test_latest_quote_check_keeps_indicator_source_moment_separate():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "EUR", "price": 3000,
            "source_observed_at_utc": "2026-11-15T14:19:59+00:00",
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-15T14:24:51+00:00",
        }},
    )
    question = "Wat is de actuele ETH/EUR-koers en wat zijn de indicatorbronmomenten?"
    answer = (
        "De koersbron voor ETH/EUR registreerde €3.000 op 15 november 2026 om 14:19:59 UTC. "
        "De technische metingen zijn van 14 november 2026 om 23:59:59 UTC: "
        "RSI 26,81 en MACD-histogram −1,4673%. "
        "De Paper-portefeuillelezing van 15 november 2026 om 15:24:51 CET "
        "vermeldt €9.599,97 kas en geen positie."
    )
    assert current_source_moments_supported(answer, evidence, question=question)
    assert not current_source_moments_supported(
        answer.replace("15 november 2026 om 14:19:59 UTC", "14 november 2026 om 14:19:59 UTC"),
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        answer.replace("15 november 2026 om 15:24:51 CET", "15 november 2026 om 16:24:51 CET"),
        evidence, question=question,
    )


def test_broad_current_score_question_does_not_turn_bot_clock_into_quote_clock():
    evidence = ({"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "ETH", "quote_currency": "EUR", "price": 3000,
        "source_observed_at_utc": "2026-11-15T09:02:06+00:00",
    }},)
    question = (
        "Beoordeel mijn ETH/EUR-conceptsetup en actieve Paper-bot apart: actuele "
        "score versus 61–75, koers- en indicatorbronmoment, laatste botbeslissing."
    )
    answer = (
        "Het actuele ETH/EUR-koersbronmoment is 15 november 2026 om 10:02:06 CET. "
        "De botstatus is hold. Beslismoment: 15 november 2026 om 10:00 CET."
    )
    diagnostics = []
    assert current_source_moments_supported(
        answer, evidence, question=question, diagnostics=diagnostics,
    )
    assert diagnostics == []
    assert not current_source_moments_supported(
        answer.replace("10:02:06 CET", "10:03:06 CET"), evidence, question=question,
    )


def test_broad_coach_keeps_paper_valuation_clock_separate_from_quote_source():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "quote_currency": "EUR", "price": 3000,
            "source_observed_at_utc": "2026-11-15T09:02:06+00:00",
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-15T21:31:53+00:00",
        }},
    )
    question = (
        "Beoordeel mijn ETH/EUR-conceptsetup: actuele score, koers- en "
        "indicatorbronmoment, botbeslissing en Paper-kas. Wijzig niets."
    )
    answer = (
        "De ETH/EUR-koersbron gaf €3.000, waargenomen op 15 november 2026 om "
        "10:02:06 CET. De bot besliste op 15 november 2026 om 22:31:41 CET "
        "om te wachten. De Paper-waardering van 15 november 2026 om 22:31:53 CET "
        "toont €9.599,97 kas en geen positie."
    )
    assert current_source_moments_supported(answer, evidence, question=question)
    assert not current_source_moments_supported(
        answer.replace("22:31:53 CET", "22:31:53 UTC"), evidence, question=question,
    )
