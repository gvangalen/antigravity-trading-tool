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
