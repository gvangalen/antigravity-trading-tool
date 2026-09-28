from backend.services.finn_v2_verified_turn_context import project_verified_turn


def test_clarification_context_keeps_choice_evidence_not_unrelated_market_failure():
    prior = {
        "run_id": "prior-run",
        "answer": "Welke setup bedoel je?",
        "terminal_status": "clarification_required",
        "terminal_reason": "setup_ambiguous",
        "tool_trace": [{"result": {"results": [
            {"scope": "read_active_setup", "status": "unavailable", "reason": "setup_ambiguous", "source": "setups"},
            {"scope": "market_snapshot", "status": "unavailable", "reason": "market_stale", "source": "provider"},
            {"scope": "read_profile", "status": "completed", "source": "profile", "as_of": "2026-09-27"},
        ]}}],
    }
    context = project_verified_turn(prior)
    assert context["open_choice"] == "setup_ambiguous"
    assert [item["scope"] for item in context["evidence"]] == ["read_active_setup", "read_profile"]


def test_verified_direct_answer_has_no_operation_or_tool_requirement():
    context = project_verified_turn({
        "run_id": "prior-run", "response_id": "response-1",
        "answer": "We moeten eerst je horizon bepalen.",
        "terminal_status": "completed", "terminal_reason": "verified_direct_answer",
        "tool_trace": [],
    })
    assert context["answer"] == "We moeten eerst je horizon bepalen."
    assert context["evidence"] == []
    assert context["open_choice"] is None
