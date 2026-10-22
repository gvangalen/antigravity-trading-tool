from types import SimpleNamespace

from backend.services.finn_v2_run_service import (
    _clear_superseded_strategy_draft,
    _new_independent_strategy_supersedes_guided,
    _previous_strategy_clarification,
    _select_open_strategy_for_correction,
)


def test_waiver_recovers_only_immediately_prior_owner_scoped_clarification():
    previous = SimpleNamespace(
        run_id="prior-run",
        state_json={
            "terminal_status": "clarification_required",
            "responses_clarification": {
                "run_id": "prior-run",
                "conversation_id": "this-conversation",
                "reason": "strategy_rule_not_captured",
                "original_message": "Create a strategy with an unsupported trend rule.",
            },
        },
    )
    recovered = _previous_strategy_clarification(previous, "this-conversation")
    assert recovered["original_message"].startswith("Create a strategy")
    assert not _previous_strategy_clarification(previous, "other-conversation")
    previous.state_json["terminal_status"] = "completed"
    assert not _previous_strategy_clarification(previous, "this-conversation")
    previous.state_json["terminal_status"] = "clarification_required"
    previous.state_json["responses_clarification"]["run_id"] = "older-run"
    assert not _previous_strategy_clarification(previous, "this-conversation")


def test_named_price_reentry_never_borrows_another_open_strategy():
    proposal = SimpleNamespace(
        operation_type="create_strategy",
        payload_json={"change": {"strategy_fields": {"name": "Rustige A"}}},
    )
    current = (proposal, SimpleNamespace(state_json={}))
    message = (
        "Voor setup BTC QA Plan en strategie Rustige B zijn de actuele koersniveaus "
        "allemaal in EUR: entry 75.000, stop-loss 71.000 en target 82.000."
    )
    assert _select_open_strategy_for_correction([current], message) is None
    proposal.payload_json["change"]["strategy_fields"]["name"] = "Rustige B"
    assert _select_open_strategy_for_correction([current], message) is current


def test_complete_independent_strategy_starts_without_previous_guided_fields():
    guided = {"operation_id": "create_strategy", "collected_inputs": {"name": "Rustige A"}}
    message = (
        "Dit is een andere, zelfstandige strategie: Rustige B voor mijn opgeslagen "
        "setup BTC QA Plan. Gebruik BTC 4H, €100 vast per uitvoering, voorzichtig "
        "risico, entry 84.000 USD, stop 79.800 USD en target 93.000 USD. "
        "Neem geen voorwaarden uit de vorige strategie over. Laat alleen het concept zien."
    )
    assert _new_independent_strategy_supersedes_guided(message, guided)
    assert not _new_independent_strategy_supersedes_guided(
        message.replace("Rustige B", "Rustige A"), guided,
    )
    assert not _new_independent_strategy_supersedes_guided(
        message.replace("Neem geen voorwaarden uit de vorige strategie over.",
                        "Neem de trendregel uit de vorige strategie over."), guided,
    )
    context = {
        "proposal_revision": {"guided_state": guided},
        "operation_state": {"collected_inputs": {"name": "Rustige A"}},
        "strategy_rule_block": {"original_message": "a separate blocked rule"},
    }
    assert _clear_superseded_strategy_draft(context, message)
    assert "proposal_revision" not in context
    assert "operation_state" not in context
    assert "strategy_rule_block" in context


