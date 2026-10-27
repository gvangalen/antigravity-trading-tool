from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


def _setup(message, *, previous=None, explicit_asset="ETH"):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    return service.resolve(
        contract=contract, message=message, explicit_asset=explicit_asset,
        conversation_context={"active_guided_operation": previous.dict()} if previous else {},
        supplied_inputs={"setup_type": "dca"} if previous is None else {},
        model_tool_inputs=True,
    )


def test_crypto_setup_asks_for_pair_even_with_euro_amount_and_preserves_all_other_slots():
    first = _setup(
        "Maak een ETH DCA-setup met naam ETH maandag, 1D, wekelijks op maandag, "
        "vast €100 per aankoop."
    )
    assert first.status == "collecting"
    assert first.missing_required_inputs == ["quote_currency"]
    assert first.collected_inputs["base_amount"] == 100
    assert first.collected_inputs["dca_day"] == "monday"
    assert "EUR" in FinnV2OperationStateService.clarification_question(
        first.next_missing_input, locale="nl"
    )

    completed = _setup("EUR", previous=first, explicit_asset=None)
    assert completed.status == "complete"
    assert completed.collected_inputs["quote_currency"] == "EUR"
    assert completed.collected_inputs["name"] == "ETH maandag"
    assert completed.collected_inputs["base_amount"] == 100


def test_explicit_crypto_pair_is_preserved_in_first_turn():
    state = _setup(
        "Maak een ETH/USDT DCA-setup met naam ETH maandag, 1D, wekelijks op maandag, "
        "vast €100 per aankoop."
    )
    assert state.status == "complete"
    assert state.collected_inputs["symbol"] == "ETH"
    assert state.collected_inputs["quote_currency"] == "USDT"


def test_asset_correction_never_reuses_previous_quote():
    first = _setup(
        "Maak een ETH/EUR DCA-setup met naam ETH maandag, 1D, wekelijks op maandag, "
        "vast €100 per aankoop."
    )
    corrected = _setup("Maak dit voor BTC in plaats van ETH.", previous=first,
                       explicit_asset="BTC")
    assert corrected.collected_inputs["symbol"] == "BTC"
    assert "quote_currency" not in corrected.collected_inputs
    assert "quote_currency" in corrected.missing_required_inputs
