"""Confirmable typed plans need user-owned fields and a fresh market scope."""

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor


CONTRACT = FinnV2OperationRegistry().require_supported("create_setup")
SERVICE = FinnV2OperationStateService()
FULL_PLAN = (
    "Maak een BTC/EUR Trade-plan met naam SMA50 Testplan. Koop €10 met vaste "
    "uitvoering, gebalanceerd risico, entry €68000, stop-loss €60000 en "
    "target €80000. Koop alleen wanneer de afgesloten dagkoers de SMA50 "
    "van onder naar boven kruist. Mijn scorevoorwaarde voor de totale "
    "benchmark is 61–75. Toon eerst het voorstel."
)
PENDING_PLAN = FULL_PLAN.replace("met naam SMA50 Testplan. ", "")


def resolve(message, *, existing=None, supplied=None):
    return SERVICE.resolve(
        contract=CONTRACT, message=message, explicit_asset="BTC" if existing is None else None,
        conversation_context={"active_guided_operation": existing.dict()} if existing else {},
        supplied_inputs=supplied or {}, model_tool_inputs=True,
    )


def test_model_cannot_supply_missing_trade_execution_terms():
    user_message = (
        "Maak een BTC/EUR Trade-plan: koop alleen wanneer de afgesloten dagkoers "
        "de SMA50 van onder naar boven kruist."
    )
    candidate = {
        "name": "Model name", "execution_mode": "fixed", "base_amount": 10,
        "entry": 68000, "stop_loss": 60000, "targets": [80000],
        "risk_profile": "balanced", "price_currency": "EUR",
    }
    state = resolve(user_message, supplied=candidate)
    assert "entry_signal" in state.collected_inputs
    for field in ("execution_mode", "base_amount", "entry", "stop_loss", "targets", "risk_profile", "price_currency"):
        assert field not in state.collected_inputs
        assert field in state.missing_required_inputs or field == "price_currency"


def test_asset_correction_invalidates_old_trade_terms():
    initial = resolve(PENDING_PLAN)
    assert initial.status == "collecting"
    revised = resolve("Corrigeer: ik bedoel ETH/EUR in plaats van BTC/EUR.", existing=initial)
    assert revised.collected_inputs["symbol"] == "ETH"
    assert revised.collected_inputs["quote_currency"] == "EUR"
    for field in ("name", "entry_signal", "base_amount", "entry", "stop_loss", "targets", "min_benchmark_score"):
        assert field not in revised.collected_inputs
    assert revised.status == "collecting"
    assert "entry_signal" in revised.missing_required_inputs


def test_quote_correction_invalidates_old_levels_and_signal():
    initial = resolve(PENDING_PLAN)
    revised = resolve("Corrigeer naar BTC/USDT.", existing=initial)
    assert revised.collected_inputs["symbol"] == "BTC"
    assert revised.collected_inputs["quote_currency"] == "USDT"
    assert "entry_signal" in revised.missing_required_inputs
    assert "entry" not in revised.collected_inputs


def test_setup_type_correction_drops_trade_contract():
    initial = resolve(PENDING_PLAN)
    revised = resolve("Corrigeer dit naar een DCA-setup.", existing=initial)
    assert revised.collected_inputs["setup_type"] == "dca"
    assert "entry_signal" not in revised.collected_inputs
    assert "entry" not in revised.collected_inputs
    assert revised.status == "collecting"


def test_daily_signal_clarification_stays_in_open_trade_plan():
    initial = resolve(
        "Maak een nieuw BTC/EUR Paper-plan: koop voor €10 wanneer de afgesloten "
        "dagkoers de SMA50 van onder naar boven kruist. Toon eerst een voorstel."
    )
    answer = "1D. Controleer dagelijks en koop alleen bij een nieuwe kruising."
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message=answer, contract=CONTRACT, registry=FinnV2OperationRegistry(),
        requested_slot=initial.next_missing_input,
        collected_inputs=initial.collected_inputs,
    )
    revised = resolve(answer, existing=initial)
    assert revised.collected_inputs["setup_type"] == "trade"
    assert revised.collected_inputs["timeframe"] == "1D"
    assert revised.collected_inputs["entry_signal"] == initial.collected_inputs["entry_signal"]
    assert "dca_frequency" not in revised.collected_inputs
