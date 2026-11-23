from backend.services.finn_v2_paper_position_answer import render_paper_position_cash_answer


QUESTION = (
    "Hoeveel AAPL-positie heb ik nu werkelijk open, wat is mijn Paper-kassaldo, "
    "en betekent mijn botbudget van €400 dat ik €400 extra kan kopen?"
)


def _trace(*, rows, status="completed", environment="paper"):
    return ({"result": {"results": [{"scope": "read_portfolio", "status": status,
             "data": {"environment": environment, "bots": rows}}]}},)


def test_answer_uses_only_one_verified_paper_bot_and_rejects_budget_as_extra_cash():
    answer = render_paper_position_cash_answer(QUESTION, _trace(rows=[{
        "symbol": "AAPL", "is_live": False, "position_qty": 0,
        "paper_cash_eur": 405.48, "budget_total_eur": 400,
    }]), asset="AAPL", locale="nl")
    assert "0 AAPL open" in answer
    assert "€405,48 Paper-kas" in answer
    assert "€400" in answer and "geen extra koopruimte" in answer


def test_answer_never_combines_other_bot_or_unverified_live_rows():
    rows = [{"symbol": "AAPL", "is_live": False, "position_qty": 0,
             "paper_cash_eur": 405.48, "budget_total_eur": 400}]
    assert render_paper_position_cash_answer(QUESTION, _trace(rows=rows, status="unavailable"),
                                             asset="AAPL", locale="nl") is None
    assert render_paper_position_cash_answer(QUESTION, _trace(rows=rows, environment="live"),
                                             asset="AAPL", locale="nl") is None
    assert render_paper_position_cash_answer(QUESTION, _trace(rows=rows * 2),
                                             asset="AAPL", locale="nl") is None


def test_named_budget_selects_only_matching_paper_bot():
    rows = [
        {"symbol": "AAPL", "is_live": False, "position_qty": 1,
         "paper_cash_eur": 50, "budget_total_eur": 500},
        {"symbol": "AAPL", "is_live": False, "position_qty": 0,
         "paper_cash_eur": 405.48, "budget_total_eur": 400},
    ]
    answer = render_paper_position_cash_answer(QUESTION, _trace(rows=rows),
                                               asset="AAPL", locale="nl")
    assert "0 AAPL open" in answer
    assert "€405,48 Paper-kas" in answer


def test_live_qa_budget_invested_and_total_cash_are_separate():
    question = ("Wat is de ingestelde budgetlimiet van mijn BTC Paper-bot, hoeveel is "
                "werkelijk belegd en hoeveel kas is er? Noem die drie afzonderlijk; "
                "lees alleen en verander niets.")
    trace = ({"result": {"results": [{"scope": "read_portfolio", "status": "completed",
             "asset": None, "data": {"environment": "paper", "global": {
                 "cash_balance": 10005.45, "invested_value": 0}, "bots": [
                     {"symbol": "BTC", "is_live": False, "position_qty": 0,
                      "invested_eur": 0, "paper_cash_eur": 9599.97, "budget_total_eur": 100},
                     {"symbol": "AAPL", "is_live": False, "position_qty": 0,
                      "invested_eur": 0, "paper_cash_eur": 405.48, "budget_total_eur": 400},
                 ]}}]}},)
    answer = render_paper_position_cash_answer(question, trace, asset="BTC", locale="nl")
    assert "budgetlimiet van je BTC Paper-bot is €100" in answer
    assert "In die bot is €0 werkelijk belegd" in answer
    assert "totale Paper-portefeuille heeft €0 belegd en €10005,45 kas" in answer
    assert "BTC-botkas is daarvan €9599,97" in answer
    trace[0]["result"]["results"][0]["asset"] = "BTC"
    assert render_paper_position_cash_answer(question, trace, asset="BTC", locale="nl") is None
