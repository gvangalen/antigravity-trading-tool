import asyncio
from unittest.mock import AsyncMock

from backend.services.finn_v2_profile_paper_fit_answer import render_profile_paper_fit_answer
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier


QUESTION = (
    "Past mijn bestaande BTC Paper-bot bij mijn opgeslagen traderstijl en mijn huidige "
    "totale Paper-portefeuille? Vergelijk expliciet de ingestelde botbudgetlimiet, "
    "het werkelijk belegde bedrag, de botkas en de totale Paper-kas. Behandel kas "
    "en budgetlimiet niet als belegde posities. Noem één concreet controlepunt "
    "dat bij mijn profiel past. Lees alleen; maak geen voorstel en wijzig niets."
)


def _trace():
    return ({"name": "get_profile_portfolio_and_bots", "result": {"results": [
        {"scope": "read_profile", "status": "completed", "asset": "BTC", "data": {
            "has_profile": True, "trader_profile": {
                "trader_types": ["dca_investor"], "asset_focus": ["bitcoin"],
                "risk_profiles": ["balanced"], "behavior_flags": ["fomo", "overtrades"],
            },
        }},
        {"scope": "read_portfolio", "status": "completed", "asset": None, "data": {
            "environment": "paper", "read_at": "2026-11-26T09:00:00+00:00",
            "global": {"cash_balance": 10000, "invested_value": 0},
            "bots": [{"bot_id": 56, "name": "BTC Paper Bot", "symbol": "BTC", "is_live": False,
                      "setup_id": 11, "setup_name": "Long term DCA BTC",
                      "strategy_id": 22, "strategy_name": "Strategie long term dca btc",
                      "budget_total_eur": 1000, "invested_eur": 0,
                      "paper_cash_eur": 10000}],
        }},
    ]}},)


def test_broad_fit_uses_bot_parent_not_unrelated_latest_setup():
    trace = _trace() + ({"name": "evaluate_bot", "result": {"results": [
        *(_trace()[0]["result"]["results"]),
        {"scope": "read_active_setup", "status": "completed", "asset": "BTC",
         "data": {"setup_id": 99, "name": "QA Smart DCA Grens 25 nov"}},
    ]}},)
    answer = render_profile_paper_fit_answer(
        QUESTION, trace, asset="BTC", locale="nl", user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    assert "Long term DCA BTC" in answer
    assert "Strategie long term dca btc" in answer
    assert "QA Smart DCA Grens" not in answer
    assert "botbudgetlimiet is €1000" in answer
    assert "€0 werkelijk belegd" in answer
    assert "€10000 botkas" in answer
    assert "€10000 totale Paper-kas" in answer
    assert "2026-11-26 10:00:00 CET" in answer
    assert "Controlepunt:" in answer


def test_broad_fit_refuses_ambiguous_or_incomplete_bot_source():
    trace = _trace()
    for broken in (
        {"bots": trace[0]["result"]["results"][1]["data"]["bots"] * 2},
        {"bots": [{**trace[0]["result"]["results"][1]["data"]["bots"][0],
                   "strategy_name": None}]},
        {"environment": "live"},
    ):
        rows = [dict(item) for item in trace[0]["result"]["results"]]
        rows[1] = {**rows[1], "data": {**rows[1]["data"], **broken}}
        answer = render_profile_paper_fit_answer(
            QUESTION, ({"name": "get_profile_portfolio_and_bots", "result": {"results": rows}},),
            asset="BTC", locale="nl",
        )
        if "bots" in broken and len(broken["bots"]) == 2:
            assert "niet eenduidig bepalen" in answer
        else:
            assert answer is None


def test_explicit_pair_or_other_bot_name_fails_closed():
    for pair in ("BTC/USDT", "BTC / USDT", "BTC/USDC", "BTC/EUR"):
        pair_question = QUESTION.replace("BTC Paper-bot", f"{pair} Paper-bot")
        pair_answer = render_profile_paper_fit_answer(
            pair_question, _trace(), asset="BTC", locale="nl",
        )
        assert "handelspaar niet" in pair_answer
        assert "Long term DCA BTC" not in pair_answer

    other_name = QUESTION.replace("BTC Paper-bot", "BTC Paper-bot Alpha")
    name_answer = render_profile_paper_fit_answer(
        other_name, _trace(), asset="BTC", locale="nl",
    )
    assert "botnaam komt niet overeen" in name_answer
    assert "Long term DCA BTC" not in name_answer

    exact_name = QUESTION.replace("BTC Paper-bot", "BTC Paper-bot BTC Paper Bot")
    assert "Long term DCA BTC" in render_profile_paper_fit_answer(
        exact_name, _trace(), asset="BTC", locale="nl",
    )
    rows = [dict(item) for item in _trace()[0]["result"]["results"]]
    portfolio = dict(rows[1]["data"])
    portfolio["bots"] = [{**portfolio["bots"][0], "name": "BTC Paper-bot Alpha"}]
    rows[1] = {**rows[1], "data": portfolio}
    alpha_question = QUESTION.replace("BTC Paper-bot", "BTC Paper-bot Alpha")
    assert "Long term DCA BTC" in render_profile_paper_fit_answer(
        alpha_question,
        ({"name": "get_profile_portfolio_and_bots", "result": {"results": rows}},),
        asset="BTC", locale="nl",
    )


def test_zero_budget_is_not_described_as_active_cap_or_dca_rule():
    trace = _trace()
    rows = [dict(item) for item in trace[0]["result"]["results"]]
    portfolio = dict(rows[1]["data"])
    portfolio["bots"] = [{**portfolio["bots"][0], "budget_total_eur": 0,
                          "budget_limit_enabled": False,
                          "strategy_name": "Do Not DCA"}]
    rows[1] = {**rows[1], "data": portfolio}
    answer = render_profile_paper_fit_answer(
        QUESTION, ({"name": "get_profile_portfolio_and_bots", "result": {"results": rows}},),
        asset="BTC", locale="nl",
    )
    assert "geen botbudgetlimiet ingeschakeld" in answer
    assert "botbudgetlimiet is €0" not in answer
    assert "volgt niet uit de namen alleen" in answer


def test_broad_fit_frontdoor_replaces_uncertain_model_answer(monkeypatch):
    front = FinnResponsesFrontDoor(
        client=object(), session=object(), user_id=7, run_id="profile-fit",
        model_led_coach=True,
    )
    loop_run = AsyncMock(return_value=FinnResponsesResult(
        text="Ik kan de botkoppeling niet verifiëren.", response_id="model-answer",
        tool_trace=_trace(), answer_kind="free_text", model_led_coach=True,
    ))
    monkeypatch.setattr(
        "backend.services.finn_v2_responses_front_door.FinnResponsesLoop.run", loop_run,
    )
    result = asyncio.run(front.run(
        message=QUESTION, instructions="", conversation_context={},
        verified_asset="BTC", previous_response=None,
        workspace_hints={"time_zone": "Europe/Amsterdam"},
    ))
    assert loop_run.await_args.kwargs["required_read_tool_name"] == "get_profile_portfolio_and_bots"
    assert result.response.answer_kind == "factual_source"
    assert "Long term DCA BTC" in result.response.text
    assert "niet verifiëren" not in result.response.text


def test_broad_fit_verifier_accepts_only_exact_owner_source_projection():
    trace = _trace() + ({"name": "evaluate_bot", "result": {"results": [
        {"scope": "read_active_setup", "status": "unavailable", "asset": "BTC"},
    ]}},)
    answer = render_profile_paper_fit_answer(
        QUESTION, trace, asset="BTC", locale="nl", user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    verifier = FinnResponsesAnswerVerifier()
    result = FinnResponsesResult(
        text=answer, response_id="profile-fit", tool_trace=trace,
        answer_kind="factual_source", model_owned_repair=False,
    )
    good = asyncio.run(verifier.verify(
        message=QUESTION, result=result, locale="nl",
        user_time_zone="Europe/Amsterdam",
    ))
    assert good.status == "completed"
    bad = asyncio.run(verifier.verify(
        message=QUESTION, result=FinnResponsesResult(
            text="Een andere BTC-setup is aan de bot gekoppeld.", response_id="profile-fit",
            tool_trace=trace, answer_kind="factual_source", model_owned_repair=False,
        ), locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert bad.status == "unavailable"
    assert bad.reason == "factual_source_mismatch"

    pair_question = QUESTION.replace("BTC Paper-bot", "BTC / USDT Paper-bot")
    pair_answer = render_profile_paper_fit_answer(
        pair_question, trace, asset="BTC", locale="nl",
        user_time_zone="Europe/Amsterdam",
    )
    pair_result = asyncio.run(verifier.verify(
        message=pair_question, result=FinnResponsesResult(
            text=pair_answer, response_id="profile-fit-pair", tool_trace=trace,
            answer_kind="factual_source", model_owned_repair=False,
        ), locale="nl", user_time_zone="Europe/Amsterdam",
    ))
    assert pair_result.status == "completed"
    assert "Long term DCA BTC" not in pair_result.text
