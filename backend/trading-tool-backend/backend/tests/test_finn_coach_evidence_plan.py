from backend.services.finn_v2_coach_evidence_plan import coach_evidence_plan
from backend.services.finn_v2_turn_contract import turn_contract_gap
from backend.services.finn_v2_coach_source_fallback import (
    coach_source_coverage_gap, render_coach_source_fallback,
)


def test_named_asset_coach_question_plans_each_requested_source():
    question = ("Beoordeel mijn AAPL-setup, score, botreden, rapport en koers. "
                "Wat doe ik bij de beursopening? Bespreek alleen.")
    plan = coach_evidence_plan(question, named_asset_count=1, read_only=True)
    assert plan is not None
    assert set(plan.read_tools) == {
        "read_active_setup", "read_linked_strategy", "read_asset_scores",
        "read_bot_status", "read_review_history", "read_latest_report",
        "read_market_snapshot",
    }
    assert plan.decision_required
    assert plan.next_step_required
    assert coach_evidence_plan(question, named_asset_count=2, read_only=True) is None
    assert coach_evidence_plan(question, named_asset_count=1, read_only=False) is None


def test_coach_coverage_rejects_omitted_sources_and_answer_parts():
    plan = coach_evidence_plan(
        "Waarom blokkeerde mijn AAPL-bot bij mijn score en rapport? Wat doe ik nu?",
        named_asset_count=1, read_only=True,
    )
    assert plan is not None
    contract = {"coach_evidence_plan": {
        "topics": plan.topics, "read_tools": plan.read_tools,
        "decision_required": plan.decision_required,
        "next_step_required": plan.next_step_required,
    }, "attempted_scopes": []}
    assert turn_contract_gap(contract, "De score past niet; wacht.") == "coach_sources_not_checked"
    contract["attempted_scopes"] = list(plan.read_tools)
    assert turn_contract_gap(contract, "De score past niet; wacht.") == "coach_topic_missing:bot"
    assert turn_contract_gap(contract, "De setupscore past niet en de bot wacht. "
                             "Het rapport is ouder.") == "coach_bot_decision_missing"
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder.") == "coach_next_step_missing"
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") is None
    contract["coach_evidence_plan"]["benchmark_score"] = 52.7
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") == "coach_verified_score_missing"
    assert turn_contract_gap(contract, "De setupscore is 52,7. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") is None


def test_coach_source_recovery_separates_quote_bot_report_and_missing_score():
    evidence = (
        {"scope": "read_active_setup", "status": "completed", "data": {
            "symbol": "AAPL", "name": "AAPL plan", "min_benchmark_score": 61, "max_benchmark_score": 75}},
        {"scope": "read_asset_scores", "status": "unavailable", "reason": "source_unavailable"},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                                      "decision_at": "2026-11-19T20:30:00+00:00",
                                      "safety_reason": "Reguliere sessie gesloten; actuele koers ontbreekt"}]}},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "symbol": "AAPL", "generated_at": "2026-11-19T19:08:00+00:00"}},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "price": 349.34, "quote_currency": "USD",
            "source_observed_at": "2026-11-19T20:29:00+00:00"}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10005.45}, "read_at": "2026-11-19T21:00:00+00:00"}},
    )
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("setup", "score", "bot", "report", "quote", "portfolio"),
        evidence=evidence,
    )
    assert answer is not None
    for fragment in ("61–75", "geen verifieerbare actuele score", "21:30:00 CET",
                     "Reguliere sessie gesloten", "20:08:00 CET", "349,34 USD",
                     "21:29:00 CET", "10005,45"):
        assert fragment in answer


def test_repeated_source_reads_do_not_make_one_bot_and_portfolio_ambiguous():
    decision = {"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
            "decision_at": "2026-11-20T17:45:31+00:00",
            "safety_reason": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark."}]}}
    portfolio = {"scope": "read_portfolio", "status": "completed", "data": {
        "bots": [{"symbol": "AAPL", "name": "AAPL Paper", "is_live": False,
                  "paper_cash_eur": 405.48}],
        "read_at": "2026-11-20T17:50:00+00:00"}}
    evidence = (decision, portfolio, decision, portfolio)
    assert coach_source_coverage_gap(
        asset="AAPL", topics=("bot", "portfolio"), evidence=evidence,
        answer="De bot deed geen koopvoorstel.",
    ) == "saved_bot_reason_missing"
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("bot", "portfolio"), evidence=evidence,
    )
    assert answer is not None
    assert "Opgeslagen setupvoorwaarden passen niet" in answer
    assert "€405,48" in answer
    assert "geen eenduidig opgeslagen besluit" not in answer
    assert "benchmark.." not in answer


def test_coach_answer_recovery_preserves_exact_bot_reason_and_bot_cash():
    evidence = (
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                "decision_at": "2026-11-20T17:45:00+00:00",
                "safety_reason": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark."}]}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10005.45},
            "bots": [{"name": "AAPL Paper", "symbol": "AAPL", "is_live": False,
                      "paper_cash_eur": 405.48}],
            "read_at": "2026-11-20T17:50:00+00:00"}},
    )
    topics = ("bot", "portfolio")
    assert coach_source_coverage_gap(
        asset="AAPL", topics=topics, evidence=evidence,
        answer="De bot deed geen koopvoorstel; de kas kon ik niet lezen.",
    ) == "saved_bot_reason_missing"
    answer = render_coach_source_fallback(asset="AAPL", topics=topics, evidence=evidence)
    assert answer is not None
    assert "Opgeslagen setupvoorwaarden passen niet" in answer
    assert "AAPL Paper botkas (Paper): €405,48" in answer
    assert "Paper-portefeuille: kas €10005,45" in answer
    assert coach_source_coverage_gap(
        asset="AAPL", topics=topics, evidence=evidence, answer=answer,
    ) is None
