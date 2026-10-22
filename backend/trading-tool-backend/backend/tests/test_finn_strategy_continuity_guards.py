from types import SimpleNamespace

from backend.services.finn_v2_run_service import (
    _adjacent_open_strategy_for_mixed_correction,
    _bounded_strategy_rule_waiver_inputs,
    _bounded_waiver_name_confirmed,
    _freeform_strategy_rule_waiver_inputs,
    _strategy_request_after_bounded_waiver,
    _clear_superseded_strategy_draft,
    _mixed_strategy_price_request,
    _new_independent_strategy_supersedes_guided,
    _previous_strategy_clarification,
    _select_open_strategy_for_correction,
)
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


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


def test_long_owner_scoped_strategy_edit_remains_a_correction():
    message = (
        "Pas alleen het nog niet opgeslagen concept Strategie voor rustig handelen "
        "met mijn volledige Bitcoin plan voor setup Bitcoin volledig opgebouwde "
        "lange termijn test aan: vervang target 93.000 USD door 92.400 USD. "
        "Naam, 4H, €100, voorzichtig risico, entry 84.000 USD en stop 79.800 USD blijven gelijk."
    )
    assert FinnV2OperationStateService._is_explicit_correction(message)


def test_mixed_strategy_price_units_never_form_a_confirmable_draft():
    assert _mixed_strategy_price_request(
        "Maak een BTC-strategie: entry 84.000 USD, stop 79.800 USD en target 82.000 EUR."
    )
    assert _mixed_strategy_price_request(
        "Pas alleen het target van 93.000 USD naar 82.000 EUR aan."
    )
    assert not _mixed_strategy_price_request(
        "Entry 75.000 EUR, stop-loss 71.000 EUR en target 82.000 EUR."
    )


def test_rule_waiver_keeps_typed_prices_with_new_strategy_wording():
    original = (
        "Maak voor mijn opgeslagen setup BTC QA Plan een nieuwe Paper-strategie "
        "met naam Rustige A. BTC 4H, vast bedrag €100, entry 84.000 USD, "
        "stop-loss 79.800 USD, target 92.400 USD en voorzichtig risico. "
        "Ik wil daarnaast alleen handelen bij stijgende 1D-trend en maximaal "
        "twee trades per dag. Toon alleen een concept."
    )
    waiver = (
        "Maak het voorstel voor Rustige A bij setup BTC QA Plan zonder uitsluitend "
        "de stijgende 1D-trend en limiet van twee trades per dag. Ik geef daarvoor "
        "expliciet toestemming. Bewaar BTC, 4H, vast €100, voorzichtig risico en "
        "mijn vaste entry 84.000 USD, stop 79.800 USD en target 92.400 USD. "
        "Alleen een concept, geen aankoop of opslag."
    )
    assert _bounded_strategy_rule_waiver_inputs(waiver, original) == {
        "base_amount": 100, "entry": 84000, "stop_loss": 79800,
        "targets": [92400], "risk_profile": "conservative", "price_currency": "USD",
        "name": "rustige a", "symbol": "BTC", "timeframe": "4H",
    }
    assert _bounded_strategy_rule_waiver_inputs(
        waiver, original.replace(
            "Toon alleen een concept.",
            "Koop ook alleen bij een MACD-kruising. Toon alleen een concept.",
        ),
    ) is None
    conditional_name = "Rustige A zodra RSI boven 70"
    assert _bounded_strategy_rule_waiver_inputs(
        waiver.replace("Rustige A", conditional_name),
        original.replace("Rustige A", conditional_name),
    ) is None


def test_exact_protected_waiver_shape_retains_typed_levels():
    original = (
        "Ik wil bij setup BTC QA Plan een Paper-strategie Rustige A op 4H, "
        "€100 vast per keer, voorzichtig risico, entry 84.000 USD, stop 79.800 USD "
        "en doel 92.400 USD. Vereis daarnaast een stijgende 1D-trend en maximaal "
        "twee trades per dag. Geef nog geen bevestigbare kaart als je die "
        "automatische regels niet kunt bewaren."
    )
    waiver = (
        "Maak het voorstel voor Rustige A bij setup BTC QA Plan zonder uitsluitend "
        "de stijgende 1D-trend en limiet van twee trades per dag. Ik geef daarvoor "
        "expliciet toestemming. Bewaar BTC, 4H, vast €100, voorzichtig risico en "
        "mijn vaste entry 84.000 USD, stop 79.800 USD en target 92.400 USD. "
        "Alleen een concept, geen aankoop of opslag."
    )
    assert _bounded_strategy_rule_waiver_inputs(waiver, original) == {
        "base_amount": 100, "entry": 84000, "stop_loss": 79800,
        "targets": [92400], "risk_profile": "conservative",
        "price_currency": "USD", "name": "rustige a", "symbol": "BTC", "timeframe": "4H",
    }


def test_exact_open_card_mixed_quote_correction_is_conflict():
    assert _mixed_strategy_price_request(
        "Ik corrigeer het doel van de open kaart naar 92.400 EUR, maar entry "
        "en stop staan nog in USD. Trek een ongeldige oude kaart in en vraag "
        "wat je nodig hebt; bevestig of voer niets uit."
    )


def test_unquoted_name_needs_separate_visible_confirmation_before_waiver():
    original = (
        "Ik wil bij setup BTC QA Plan een Paper-strategie Rustige A wacht tot VIX laag "
        "op 4H, €100 vast per keer, voorzichtig risico, entry 84.000 USD, "
        "stop 79.800 USD en doel 92.400 USD. Vereis daarnaast een stijgende "
        "1D-trend en maximaal twee trades per dag. Geef nog geen bevestigbare "
        "kaart als je die automatische regels niet kunt bewaren."
    )
    waiver = (
        "Maak het voorstel voor Rustige A wacht tot VIX laag bij setup BTC QA Plan "
        "zonder uitsluitend de stijgende 1D-trend en limiet van twee trades per dag. "
        "Ik geef daarvoor expliciet toestemming. Bewaar BTC, 4H, vast €100, "
        "voorzichtig risico en mijn vaste entry 84.000 USD, stop 79.800 USD "
        "en target 92.400 USD. Alleen een concept, geen aankoop of opslag."
    )
    block = {"original_message": original, "source_run_id": "w02"}
    assert not _bounded_waiver_name_confirmed(waiver, block)
    block.update(name_boundary_prompted=True, prompted_name="rustige a wacht tot vix laag")
    assert _bounded_waiver_name_confirmed(waiver, block)
    assert not _bounded_waiver_name_confirmed(
        "Maak strategievoorstel zonder deze automatische regels", block,
    )
    assert not _bounded_waiver_name_confirmed(
        waiver.replace("Rustige A wacht tot VIX laag", "Rustige A"), block,
    )


def test_mixed_quote_adjacent_card_cannot_override_explicit_name_rejection():
    first = (SimpleNamespace(
        operation_type="create_strategy", run_id="older",
        payload_json={"change": {"strategy_fields": {"name": "Rustige A"}}},
    ), SimpleNamespace())
    second = (SimpleNamespace(
        operation_type="create_strategy", run_id="previous",
        payload_json={"change": {"strategy_fields": {"name": "Rustige B"}}},
    ), SimpleNamespace())
    items = [second, first]
    message = (
        "Ik corrigeer het doel van de open kaart naar 92.400 EUR, maar entry "
        "en stop staan nog in USD. Trek een ongeldige oude kaart in en vraag "
        "wat je nodig hebt; bevestig of voer niets uit."
    )
    assert _adjacent_open_strategy_for_mixed_correction(items, message, "previous") == second
    assert _adjacent_open_strategy_for_mixed_correction(
        items, message + " Rustige B bedoel ik niet.", "previous",
    ) is None
    assert _adjacent_open_strategy_for_mixed_correction(
        items,
        "Ik corrigeer de open kaart Rustige A of Rustige B: target 92.400 EUR, "
        "maar entry en stop staan nog in USD.",
        "previous",
    ) is None
    assert _adjacent_open_strategy_for_mixed_correction(
        items,
        "Ik corrigeer de open kaart Rustige C: target 92.400 EUR, "
        "maar entry en stop staan nog in USD.",
        "previous",
    ) is None


def test_freeform_name_rule_cannot_bypass_visible_name_ratification():
    original = (
        "Maak een Paper-strategie voor mijn opgeslagen setup BTC QA Plan. "
        "De strategie heet BTC Veilig wacht tot VIX laag. Vast bedrag €100, "
        "voorzichtig risico, entry 84.000 USD, stop-loss 79.800 USD en "
        "koersdoel 92.400 USD. Koop alleen bij een stijgende trend en niet "
        "als RSI zwak is."
    )
    waiver = (
        "Laat alleen die twee automatische regels weg; behoud mijn opgeslagen "
        "setup BTC QA Plan, de naam BTC Veilig wacht tot VIX laag, vast bedrag "
        "€100, voorzichtig risico, entry 84.000 USD, stop-loss 79.800 USD "
        "en koersdoel 92.400 USD. Toon alleen een concept."
    )
    assert _freeform_strategy_rule_waiver_inputs(waiver, original) is not None
    block = {"original_message": original, "source_run_id": "w02"}
    assert not _bounded_waiver_name_confirmed(waiver, block)
    block.update(name_boundary_prompted=True, prompted_name="BTC Veilig wacht tot VIX laag")
    assert _bounded_waiver_name_confirmed(waiver, block)
    residual = _strategy_request_after_bounded_waiver(original)
    assert residual is not None and "VIX laag" in residual
    assert "Koop alleen" not in residual


