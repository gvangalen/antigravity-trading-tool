from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_responses_front_door import (
    FinnResponsesFrontDoor, _explicit_create_operation_request,
)
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_run_service import (
    _prior_inputs_for_open_correction, _scheduled_dca_draft_revision,
)
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.asset_catalog_service import corrected_catalog_instrument


def test_same_asset_restatement_binds_to_open_dca_draft():
    registry = FinnV2OperationRegistry()
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message="een wekelijkse dca setup voor eth",
        contract=registry.require_supported("create_setup"),
        registry=registry,
        requested_slot="timeframe",
        collected_inputs={
            "symbol": "ETH", "setup_type": "dca", "dca_frequency": "weekly",
        },
    )


def test_score_band_followup_stays_with_open_smart_dca_draft():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    collected = {
        "symbol": "BTC", "quote_currency": "USDT", "setup_type": "dca",
        "dca_trigger_mode": "benchmark", "dca_frequency": "weekly",
    }
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=("Gebruik benchmarkscorebanden: meer kopen als de markt zwaar "
                 "onder druk is en bij een sterke markt steeds minder. "
                 "Maak het concrete voorstel."),
        contract=contract, registry=registry, requested_slot="low_threshold",
        collected_inputs=collected,
    )
    assert not FinnResponsesFrontDoor.binds_guided_slot(
        message="Maak een nieuwe aparte setup voor ETH/USDT met scorebanden.",
        contract=contract, registry=registry, requested_slot="low_threshold",
        collected_inputs=collected,
    )


def test_no_fixed_weekday_corrects_open_dca_draft_instead_of_abandoning_it():
    registry = FinnV2OperationRegistry()
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=("Geen vaste weekdag. Juist scoregestuurd: hoogstens één "
                 "aankoop per week wanneer de volledige benchmark geldig is."),
        contract=registry.require_supported("create_setup"), registry=registry,
        requested_slot="dca_day",
        collected_inputs={
            "symbol": "BTC", "quote_currency": "USDT", "setup_type": "dca",
            "dca_frequency": "weekly", "dca_amount_mode": "fixed",
        },
    )


def test_smart_dca_threshold_followup_preserves_score_ladder_and_benchmark_trigger():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    service = FinnV2OperationStateService()
    first = service.resolve(
        contract=contract,
        message=("Maak voor BTC/USDT een setup met de naam Smart DCA QA, op 1D. "
                 "Ik wil wekelijks maximaal een keer €200 basisbedrag inzetten, zonder vaste koopdag. "
                 "Gebruik de volledige benchmarkscore van Markt, Macro en Technisch: "
                 "bij lage scores 150%, bij middenscores 100% en bij hoge scores 50%. "
                 "Toon eerst een voorstel; activeer geen bot en plaats geen order."),
        explicit_asset="BTC",
        conversation_context=None,
    )
    context = {
        "conversation_state_version": service.CONTEXT_STATE_VERSION,
        "active_guided_operation": first.dict(),
    }
    second = service.resolve(
        contract=contract,
        message=("Gebruik onder 26 voor laag: 150% van €200. Van 26 tot onder 76 is midden: "
                 "100%. Vanaf 76 is hoog: 50%. BTC/USDT, wekelijks zonder vaste dag, "
                 "volledige benchmark. Maak de bevestigbare setupkaart en gekoppelde strategie; "
                 "geen bot of order."),
        explicit_asset="BTC",
        conversation_context=context,
    )
    inputs = second.collected_inputs
    assert inputs["symbol"] == "BTC"
    assert inputs["quote_currency"] == "USDT"
    assert inputs["dca_trigger_mode"] == "benchmark"
    assert inputs["dca_amount_mode"] == "score_bands"
    assert inputs["low_threshold"] == 26
    assert inputs["high_threshold"] == 76
    assert "dca_day" not in inputs
    assert second.missing_required_inputs == []


def test_calendar_dca_negated_score_cue_keeps_fixed_amount_and_guided_draft():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    service = FinnV2OperationStateService()
    first = service.resolve(
        contract=contract,
        message=("Maak voor BTC/USDT een setup met de naam Kalender DCA QA, op 1D. "
                 "Koop elke week op vrijdag een vast bedrag van €50. Dit is gewone "
                 "kalender-DCA, niet scoregestuurd. Toon een voorstel en activeer geen bot of order."),
        explicit_asset="BTC", conversation_context=None,
    )
    assert first.missing_required_inputs == []
    assert first.collected_inputs["dca_amount_mode"] == "fixed"
    assert first.collected_inputs["base_amount"] == 50
    assert first.collected_inputs["dca_day"] == "friday"
    assert "score_source" not in first.collected_inputs
    alternate = service.resolve(
        contract=contract,
        message=("Maak voor BTC/USDT een setup met de naam Kalender DCA QA, op 1D. "
                 "Dit is gewone kalender-DCA: koop elke week op vrijdag een vast "
                 "bedrag van €50, niet op basis van scores. Toon eerst een voorstel, "
                 "activeer geen bot en plaats geen order."),
        explicit_asset="BTC", conversation_context=None,
    )
    assert alternate.missing_required_inputs == []
    assert alternate.collected_inputs["dca_amount_mode"] == "fixed"

    answer = ("Het bedragstype is een vast bedrag: iedere vrijdag €50, zonder "
              "scoregestuurde aanpassing. Maak nu de bevestigbare setupkaart "
              "voor BTC/USDT op 1D.")
    draft = first.dict()
    draft["collected_inputs"].pop("dca_amount_mode")
    draft["missing_required_inputs"] = ["dca_amount_mode"]
    draft["next_missing_input"] = "dca_amount_mode"
    draft["status"] = "collecting"
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=answer, contract=contract, registry=registry,
        requested_slot="dca_amount_mode", collected_inputs=draft["collected_inputs"],
    )
    second = service.resolve(
        contract=contract, message=answer, explicit_asset="BTC",
        conversation_context={
            "conversation_state_version": service.CONTEXT_STATE_VERSION,
            "active_guided_operation": draft,
        },
    )
    assert second.missing_required_inputs == []
    assert second.collected_inputs["name"] == "Kalender DCA QA"
    assert second.collected_inputs["dca_amount_mode"] == "fixed"
    assert second.collected_inputs["base_amount"] == 50
    assert second.collected_inputs["dca_day"] == "friday"


def test_conversational_request_with_asset_starts_new_setup_draft():
    assert _explicit_create_operation_request(
        "kan je voor eth ook een setup maken?"
    ) == "create_setup"
    assert _explicit_create_operation_request(
        "kan je uitleggen hoe je een setup maakt?"
    ) is None


def test_known_asset_replacement_preserves_dca_fields_but_not_old_asset():
    origin = {
        "symbol": "ETH", "name": "ETH concept", "setup_type": "dca",
        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": "monday",
        "dca_amount_mode": "fixed", "base_amount": 100,
        "min_benchmark_score": None, "setup_id": 123,
        "market_id": 456, "quote_currency": "EUR",
    }
    carried = _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=False,
        explicit_proposal_correction=True, corrected_instrument="AAPL",
        corrected_fields={}, corrected_name=None,
    )
    assert carried == {
        "name": "ETH concept", "setup_type": "dca", "timeframe": "1D",
            "dca_frequency": "weekly", "dca_day": "monday",
        "dca_amount_mode": "fixed", "base_amount": 100,
        "min_benchmark_score": None,
    }
    assert _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=True,
        explicit_proposal_correction=True, corrected_instrument="AAPL",
        corrected_fields={}, corrected_name=None,
    ) == {}
    assert _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=False,
        explicit_proposal_correction=False, corrected_instrument=None,
        corrected_fields={}, corrected_name=None,
    )["dca_frequency"] == "weekly"


def test_collecting_asset_switch_keeps_prior_user_rules_for_coverage():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    old_request = "Maak een ETH DCA-setup en koop alleen wanneer RSI onder 30 is."
    correction = (
        "Correctie: ik bedoel AAPL in plaats van ETH. Behoud 1D en wekelijks "
        "maandag; noem de setup AAPL DCA. Toon het concept."
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message=correction,
        conversation_context={"proposal_correction_result": {
            "status": "cancelled", "operation_id": "create_setup",
            "previous_asset": "ETH", "requested_instrument": "AAPL",
            "prior_inputs": {
                "setup_type": "dca", "timeframe": "1D",
                "dca_frequency": "weekly", "dca_day": "monday",
            },
            "prior_user_messages": [old_request],
            "prior_history_truncated": True,
        }},
        verified_asset=None,
    )
    state = analysis.request_plan.operation_state
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["dca_day"] == "monday"
    assert state["guided_user_messages"] == [old_request, correction]
    assert state["guided_history_truncated"] is True


def test_asset_replacement_keeps_explicit_dca_amount_without_silent_setup_only_downgrade():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    correction = {
        "status": "cancelled", "operation_id": "create_setup",
        "previous_asset": "ETH", "requested_instrument": "AAPL",
        "prior_inputs": {
            "setup_type": "dca", "timeframe": "1D", "dca_frequency": "weekly",
            "dca_day": "monday", "dca_amount_mode": "fixed", "base_amount": 100,
        },
    }
    state = FinnResponsesProposalSelection().from_call(
        call=call, message="Ik bedoel: maak een nieuwe setup voor Apple in plaats van ETH",
        conversation_context={"proposal_correction_result": correction},
        verified_asset=None,
    ).request_plan.operation_state
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["base_amount"] == 100
    assert state["collected_inputs"]["dca_amount_mode"] == "fixed"
    assert state["collected_inputs"].get("plan_scope") != "setup_only"

    setup_only = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Ik bedoel: maak alleen een nieuwe setup voor Apple in plaats van ETH, zonder strategie.",
        conversation_context={"proposal_correction_result": correction},
        verified_asset=None,
    ).request_plan.operation_state
    assert setup_only["collected_inputs"]["plan_scope"] == "setup_only"
    assert "base_amount" not in setup_only["collected_inputs"]


def test_unspecified_asset_switch_asks_for_ticker_then_keeps_dca_schedule():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    correction = {"status": "cancelled", "operation_id": "create_setup",
                  "previous_asset": "ETH", "requested_instrument": None,
                  "awaiting_instrument": True,
                  "prior_inputs": {"setup_type": "dca", "timeframe": "1D",
                                   "dca_frequency": "weekly"}}
    first = FinnResponsesProposalSelection().from_call(
        call=call, message="ik bedoel een aandeel in plaats van ETH",
        conversation_context={"proposal_correction_result": correction},
        verified_asset="ETH",
    ).request_plan.operation_state
    assert first["collected_inputs"] == {
        "setup_type": "dca", "timeframe": "1D", "dca_frequency": "weekly",
    }
    assert first["next_missing_input"] == "symbol"
    second = FinnResponsesProposalSelection().from_call(
        call=call, message="AAPL",
        conversation_context={"proposal_correction_result": correction,
                              "active_guided_operation": first},
        verified_asset=None,
    ).request_plan.operation_state
    assert second["collected_inputs"]["symbol"] == "AAPL"
    assert second["collected_inputs"]["dca_frequency"] == "weekly"


def test_explicit_asset_switch_keeps_the_replacement_asset_out_of_old_eth_context():
    message = (
        "Correctie: AAPL in plaats van ETH; behoud 1D, wekelijks maandag en "
        "26–45. Noem de setup QA AAPL Voorwaarde 2510; bevestig niets."
    )
    assert corrected_catalog_instrument(message) == "AAPL"
    assert corrected_catalog_instrument(
        "Ik wil toch een nieuwe AAPL DCA-setup in plaats van ETH: 1D, vrijdag."
    ) == "AAPL"
    assert corrected_catalog_instrument(
        "Ik bedoel: maak een nieuwe setup voor Apple in plaats van ETH"
    ) == "AAPL"
    assert corrected_catalog_instrument("Wat als ik AAPL in plaats van ETH gebruik?") is None
    assert corrected_catalog_instrument(
        "Ik wissel nu expliciet naar ETH/EUR voor een nieuw apart plan. "
        "Het open BTC/EUR-concept mag niet meer bevestigd worden."
    ) == "ETH/EUR"


def test_deferred_name_is_not_treated_as_a_literal_setup_name():
    message = (
        "Maak een nieuwe ETH DCA-setup op analysetijdsframe 1D, wekelijks "
        "op maandag, zonder extra scorefilter. De naam geef ik zo. Bevestig niets."
    )
    assert FinnV2OperationStateService._requests_name_prompt(message)
    assert FinnV2OperationStateService._name_input_from_text(message) is None
    assert FinnV2OperationStateService._name_input_from_text(
        "Maak een wekelijkse DCA-setup voor ETH. Welke naam raad je aan?"
    ) is None


def test_scheduled_purchase_sentence_fills_open_dca_draft_without_becoming_its_name():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    state = FinnV2OperationStateService()
    sentence = "Koop elke vrijdag voor 40 euro"
    assert state._requested_slot_value(field="name", text=sentence, contract=contract) is None
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=sentence, contract=contract, registry=registry,
        requested_slot="name",
        collected_inputs={"symbol": "ETH", "setup_type": "dca", "timeframe": "1D"},
    )
    assert not FinnResponsesFrontDoor.binds_guided_slot(
        message="Koop nu ETH voor 40 euro", contract=contract, registry=registry,
        requested_slot="name",
        collected_inputs={"symbol": "ETH", "setup_type": "dca", "timeframe": "1D"},
    )
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    original = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een ETH DCA-setup op 1D",
        conversation_context={}, verified_asset="ETH",
    ).request_plan.operation_state
    updated = FinnResponsesProposalSelection().from_call(
        call=call, message=sentence,
        conversation_context={"active_guided_operation": original},
        verified_asset="ETH",
    ).request_plan.operation_state
    assert updated["collected_inputs"]["symbol"] == "ETH"
    assert updated["collected_inputs"]["dca_day"] == "friday"
    assert updated["collected_inputs"]["base_amount"] == 40
    assert "name" not in updated["collected_inputs"]


def test_dca_name_digits_are_not_a_currency_amount():
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    states = FinnV2OperationStateService()
    message = (
        "Gebruik de naam AAPL DCA QA Herkeur 2710 en timeframe 1D. "
        "Toon alleen het concept, bevestig niets."
    )
    assert states.explicit_inputs(
        contract=contract, message=message, explicit_asset=None,
        known_setup_type="dca",
    ).get("base_amount") is None
    assert states.explicit_inputs(
        contract=contract,
        message="Koop elke vrijdag voor 40 euro",
        explicit_asset=None, known_setup_type="dca",
    )["base_amount"] == 40


def test_only_bounded_schedule_can_revise_open_dca_card():
    fixed = {"setup_type": "dca", "dca_amount_mode": "fixed"}
    assert _scheduled_dca_draft_revision("Koop elke vrijdag voor 40 euro", fixed)
    assert not _scheduled_dca_draft_revision("Koop nu direct AAPL voor 40 euro", fixed)
    assert not _scheduled_dca_draft_revision("Koop elke vrijdag voor 40 euro zonder bevestiging", fixed)
    assert not _scheduled_dca_draft_revision("Koop elke vrijdag voor 40 euro en activeer live", fixed)
    assert not _scheduled_dca_draft_revision("Koop elke vrijdag voor 40 USDT", fixed)
    assert not _scheduled_dca_draft_revision(
        "Koop elke vrijdag voor 40 euro", {"setup_type": "dca", "dca_amount_mode": "score_bands"},
    )
    assert not _scheduled_dca_draft_revision(
        "Koop elke vrijdag voor 40 euro", {"setup_type": "trade", "dca_amount_mode": "fixed"},
    )


def test_owner_bound_scheduled_dca_revision_retains_original_fields():
    original = {
        "symbol": "AAPL", "name": "AAPL DCA QA Herkeur 2710",
        "setup_type": "dca", "timeframe": "1D", "dca_day": "friday",
        "dca_frequency": "weekly", "base_amount": 40.0,
        "dca_amount_mode": "fixed",
    }
    retained = _prior_inputs_for_open_correction(
        original, retain_parent_ids=False, target_change_requested=False,
        explicit_proposal_correction=False, corrected_instrument=None,
        corrected_fields={}, corrected_name=None,
    )
    assert retained["base_amount"] == 40.0
    assert retained["name"] == "AAPL DCA QA Herkeur 2710"
    assert "symbol" not in retained
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    replacement = FinnResponsesProposalSelection().from_call(
        call=call, message="Koop elke vrijdag voor 40 euro",
        conversation_context={"proposal_correction_result": {
            "proposal_id": "previous-owner-card", "operation_id": "create_setup",
            "status": "cancelled", "previous_asset": "AAPL",
            "requested_instrument": "AAPL", "prior_inputs": retained,
            "corrected_fields": {}, "scheduled_dca_revision": True,
        }},
        verified_asset=None,
    )
    inputs = replacement.request_plan.operation_state["collected_inputs"]
    assert inputs["symbol"] == "AAPL"
    assert inputs["name"] == "AAPL DCA QA Herkeur 2710"
    assert inputs["base_amount"] == 40.0
    assert inputs["dca_day"] == "friday"
    assert not replacement.request_plan.missing_information

    corrected = FinnResponsesProposalSelection().from_call(
        call=call, message="Koop elke vrijdag voor 40 euro",
        conversation_context={"proposal_correction_result": {
            "proposal_id": "incorrect-owner-card", "operation_id": "create_setup",
            "status": "cancelled", "previous_asset": "AAPL",
            "requested_instrument": "AAPL",
            "prior_inputs": {**retained, "base_amount": 2710.0},
            "corrected_fields": {"base_amount": 40.0},
            "scheduled_dca_revision": True,
        }},
        verified_asset=None,
    )
    assert corrected.request_plan.operation_state["collected_inputs"]["base_amount"] == 40.0


def test_open_setup_asset_switch_retains_explicit_scope_schedule_and_score_bounds():
    message = (
        "Correctie: AAPL in plaats van ETH. Behoud het analysetijdsframe 1D, "
        "wekelijks maandag en de bestaande extra benchmarkscorevoorwaarde "
        "26-45. Nieuwe naam QA AAPL Voorwaarde 2510. Trek de ETH-kaart in en "
        "toon het AAPL-concept, bevestig niets."
    )
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message=message,
        conversation_context={"proposal_correction_result": {
            "status": "cancelled", "operation_id": "create_setup",
            "previous_asset": "ETH", "requested_instrument": "AAPL",
            "prior_inputs": {
                "setup_type": "dca", "timeframe": "1D", "plan_scope": "setup_only",
                "dca_frequency": "weekly", "dca_day": "monday",
                "min_benchmark_score": 26, "max_benchmark_score": 45,
            },
        }},
        verified_asset=None,
    )
    state = result.request_plan.operation_state
    assert state["missing_required_inputs"] == []
    assert state["collected_inputs"] == {
        "name": "QA AAPL Voorwaarde 2510", "symbol": "AAPL",
        "setup_type": "dca", "timeframe": "1D", "plan_scope": "setup_only",
        "dca_frequency": "weekly", "dca_trigger_mode": "calendar", "dca_day": "monday",
        "min_benchmark_score": 26, "max_benchmark_score": 45,
    }


def test_new_asset_setup_request_during_draft_does_not_require_strategy_amount():
    message = (
        "Ik wil toch een nieuwe AAPL DCA-setup in plaats van ETH. Gebruik 1D, "
        "wekelijks op vrijdag en geen scorefilter. Noem hem QA AAPL Vrijdag 2510 B. "
        "Toon de conceptkaart en bevestig niets."
    )
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call, message=message,
        conversation_context={"proposal_correction_result": {
            "status": "cancelled", "operation_id": "create_setup",
            "previous_asset": "ETH", "requested_instrument": "AAPL",
            "prior_inputs": {"setup_type": "dca", "timeframe": "1D",
                             "dca_frequency": "weekly", "dca_day": "monday"},
        }},
        verified_asset=None,
    )
    state = result.request_plan.operation_state
    assert state["missing_required_inputs"] == []
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["plan_scope"] == "setup_only"
    assert state["collected_inputs"]["dca_day"] == "friday"
    assert state["collected_inputs"]["name"] == "QA AAPL Vrijdag 2510 B"
    assert "dca_amount_mode" not in state["collected_inputs"]


def test_asset_replacement_with_amount_still_builds_strategy():
    assert not FinnV2OperationStateService.setup_only_intent(
        "Maak een nieuwe AAPL DCA-setup in plaats van ETH, elke vrijdag €100 vast bedrag."
    )
    assert not FinnV2OperationStateService.setup_only_intent(
        "Maak een nieuwe AAPL DCA-setup in plaats van ETH, bedrag 100 per aankoop."
    )
