import asyncio
import json
from types import SimpleNamespace

from backend.scripts import qa_account_answer_examiner as examiner
from backend.scripts.qa_account_answer_examiner import check_judgment


ANSWER = "Plan: vrijdag, €10. Bot: actief in Paper, niet live. Positie: 0,01 BTC. Beslissing: hold om 10:00 UTC."


def judgment(**overrides):
    quotes = {
        "plan_cadence": "Plan: vrijdag", "plan_base_amount_eur": "€10",
        "bot_active": "Bot: actief", "bot_live": "niet live",
        "position_quantity": "Positie: 0,01 BTC",
        "latest_decision_action": "Beslissing: hold om 10:00 UTC",
        "latest_decision_at_utc": "Beslissing: hold om 10:00 UTC",
    }
    return {"claims": [
        {"fact": fact, "verdict": overrides.get(fact, "accurate"), "quote": quote}
        for fact, quote in quotes.items()
    ]}


def test_examiner_requires_all_four_accurate_claims():
    assert check_judgment(answer=ANSWER, judgment=judgment()) == {
        "result": "PASS", "failed_checks": [],
    }
    assert check_judgment(answer=ANSWER, judgment=judgment(position_quantity="contradicted")) == {
        "result": "FAIL", "failed_checks": ["answer_position_quantity_contradicted"],
    }


def test_examiner_does_not_accept_omission_or_fabricated_quote():
    omitted = judgment(position_quantity="omitted")
    omitted["claims"][4]["quote"] = ""
    assert check_judgment(answer=ANSWER, judgment=omitted)["result"] == "FAIL"
    fabricated = judgment()
    fabricated["claims"][0]["quote"] = "Invented plan"
    assert check_judgment(answer=ANSWER, judgment=fabricated) == {
        "result": "UNTESTED", "failed_checks": ["answer_examiner_quote"],
    }


def test_examiner_rejects_duplicate_or_missing_categories():
    duplicate = judgment()
    duplicate["claims"][3]["fact"] = "plan_cadence"
    assert check_judgment(answer=ANSWER, judgment=duplicate)["result"] == "UNTESTED"
    assert check_judgment(answer=ANSWER, judgment={"claims": []})["result"] == "UNTESTED"


def test_independent_examiner_requires_two_agreeing_passes_without_export(monkeypatch):
    import openai

    outputs = [judgment(), judgment(position_quantity="contradicted")]
    seen = []
    class Client:
        responses = None
        def __init__(self, **_kwargs):
            self.responses = self
        def with_options(self, **_kwargs):
            return self
        async def create(self, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(outputs.pop(0)))
        async def close(self):
            return None
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    result = asyncio.run(examiner.examine_answer(
        answer=ANSWER, frozen_facts={
            "plan": {"name": "private-plan"}, "bot": {},
            "position": {}, "latest_decision": {},
        },
    ))
    assert result == {"result": "UNTESTED", "failed_checks": ["answer_examiner_disagreement"]}
    assert len(seen) == 2
    assert all(call["store"] is False and call["tool_choice"] == "none" for call in seen)
    assert "private-plan" not in str(result)
