from backend.services.finn_v2_coach_evidence_plan import coach_evidence_plan
from backend.services.finn_v2_turn_contract import turn_contract_gap


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
