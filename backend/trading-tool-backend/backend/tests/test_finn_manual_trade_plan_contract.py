import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from backend.domain.finn_manual_trade_plan_contract import validate_manual_trade_plan
from backend.services.finn_manual_trade_plan_service import save_manual_trade_plan
from backend.services.finn_manual_trade_suggestion_service import derive_suggested_plan, verify_suggested_manual_trade_plan
from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_proposal_schema import ManualTradePlanChange
from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall


def terms(**changes):
    return {
        "asset": "BTC", "quote_currency": "EUR", "direction": "long",
        "entry_type": "limit", "entry_price": "70000", "quantity": "0.1",
        "stop_loss": "65000", "targets": ["80000", "85000"], **changes,
    }


def test_long_short_and_stock_are_typed_and_risk_is_recomputed():
    long = validate_manual_trade_plan(terms())
    assert long["max_loss_quote"] == "500.0"
    assert long["reward_risk_by_target"] == ["2", "3"]
    assert long["risk_pct_of_position"].startswith("7.142857")
    assert long["executable"] is False
    assert long["level_source"] == "user_stated"
    assert ManualTradePlanChange.parse_obj({"plan_fields": long}).plan_fields == long

    from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
    user_stated = FinnV2ReasoningFallbackService._proposal_changes(
        operation_id="create_manual_trade_plan",
        supplied_inputs={**terms(), "setup_id": 6}, evidence_by_tool={},
    )
    assert "setup_id" not in user_stated["plan_fields"]

    short = validate_manual_trade_plan(terms(
        asset="ETH", quote_currency="USDT", direction="short",
        entry_price="3000", stop_loss="3300", quantity="2", targets=["2400", "2700"],
    ))
    assert short["targets"] == ["2700", "2400"]
    assert short["max_loss_quote"] == "600"
    assert short["reward_risk_by_target"] == ["1", "2"]

    stock = validate_manual_trade_plan(terms(
        asset="AAPL", quote_currency="USD", entry_price="250", stop_loss="230",
        quantity="10", targets=["290"],
    ))
    assert stock["venue"] == "NASDAQ"
    assert stock["max_loss_quote"] == "200"


@pytest.mark.parametrize("change", [
    {"quote_currency": "USDT", "asset": "AAPL"},
    {"entry_price": "NaN"}, {"quantity": "-1"},
    {"quantity": "1e999999"}, {"quantity": "1" * 10000},
    {"stop_loss": "71000"}, {"targets": ["69000"]},
    {"targets": ["80000", "80000"]}, {"targets": []},
    {"max_loss_quote": "0"}, {"executable": True},
])
def test_invalid_or_tampered_plan_is_rejected(change):
    with pytest.raises(ValueError):
        validate_manual_trade_plan(terms(**change))


def test_manual_plan_routes_separately_and_collects_only_stated_terms():
    classifier = FinnV2OperationClassificationService()
    complete = classifier.classify(message=(
        "Maak een handmatig tradevoorstel voor BTC/EUR, long, "
        "entry 70000, hoeveelheid 0.1, stop 65000, target 80000."
    ))
    assert complete.operation_id == "create_manual_trade_plan"
    assert not complete.selected_missing_inputs
    assert classifier.classify(message="Maak een tradeplan voor BTC/EUR").operation_id == "create_setup"
    assert classifier.classify(message="Plaats een kooporder BTC/EUR").operation_id != "create_manual_trade_plan"

    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    assert FinnV2OperationStateService()._requested_slot_value(
        field="entry_type", text="Limietinstap.", contract=contract,
    ) == "limit"
    state = FinnV2OperationStateService().resolve(
        contract=contract, message="Maak een handmatig tradevoorstel voor ETH/USDT",
        explicit_asset="ETH", conversation_context={},
        supplied_inputs={"entry_price": 123, "stop_loss": 100, "targets": [200]},
        model_tool_inputs=True,
    )
    assert state.collected_inputs == {"asset": "ETH", "quote_currency": "USDT"}
    assert "entry_price" in state.missing_required_inputs


def test_manual_terms_keep_locale_decimals_and_every_target():
    parse = FinnV2OperationStateService._manual_trade_inputs
    values = parse("BTC/EUR long entry 70.000,50, hoeveelheid 0.001, stop 65.000,25, targets 80.000,50 en 85.000,50")
    assert values["entry_price"] == "70000.50"
    assert values["quantity"] == "0.001"
    assert values["stop_loss"] == "65000.25"
    assert values["targets"] == ["80000.50", "85000.50"]
    assert parse("BTC/EUR long entry 70000, hoeveelheid 0.1, stop 65000, targets 80000, 85000")["targets"] == ["80000", "85000"]
    tiny = parse("BTC/EUR long entry 70000, hoeveelheid 0.00001, stop 65000, target 80000")
    assert validate_manual_trade_plan(terms(quantity=tiny["quantity"]))["quantity"] == "0.00001"
    assert "quantity" not in parse("BTC/EUR long hoeveelheid 1.234")
    assert "quantity" not in parse("BTC/EUR long hoeveelheid 1e-3")
    assert "targets" not in parse("BTC/EUR long targets 80000 en -85000")
    assert "targets" not in parse("BTC/EUR long targets 80000 en 1e-3")
    assert "targets" not in parse("BTC/EUR long targets 80000,85000")
    for invalid in ("1,2,3", "1.2.3", "1,,2", "1/2", "1 000", "1_000",
                    "100 euro", "100 USDT", "10% van portfolio"):
        assert "quantity" not in parse(f"BTC/EUR long hoeveelheid {invalid}")
    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    for field, value in (("quantity", "-1"), ("quantity", "1e-3"),
                         ("quantity", "1,2,3"), ("quantity", "100 euro"),
                         ("quantity", "1/2"), ("quantity", "10% van portfolio"),
                         ("entry_price", "-70000"), ("targets", "80000 en 1e-3")):
        assert FinnV2OperationStateService()._requested_slot_value(
            field=field, text=value, contract=contract,
        ) is None
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message="quantity 1/2", contract=contract, registry=FinnV2OperationRegistry(),
        requested_slot="quantity", collected_inputs={"asset": "BTC", "quote_currency": "EUR"},
    )


def _completed_candles(price="100", now=None):
    now = now or datetime.now(timezone.utc)
    day = now.date() - timedelta(days=1)
    return [
        {"id": index + 1, "open": price, "high": str(int(price) + 2), "low": str(int(price) - 2),
         "price": price, "source_observed_at": datetime.combine(
             day - timedelta(days=14 - index), datetime.min.time(), timezone.utc,
         ) + timedelta(hours=23, minutes=59)}
        for index in range(15)
    ]


@pytest.mark.parametrize("asset,quote,market_id,direction", [
    ("BTC", "EUR", 42, "long"), ("ETH", "USDT", 43, "short"),
    ("AAPL", "USD", None, "long"),
])
def test_market_suggestion_is_pair_bound_risk_capped_and_non_executable(asset, quote, market_id, direction):
    plan = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction=direction,
        max_loss_quote="20", candles=_completed_candles(), market_id=market_id,
    )
    assert plan["level_source"] == "market_derived"
    assert plan["source_evidence"]["market_id"] == market_id
    assert len(plan["source_evidence"]["candle_ids"]) == 15
    assert float(plan["max_loss_quote"]) <= 20
    assert plan["executable"] is False
    assert plan["reward_risk_by_target"] == ["1", "2"]
    if asset == "AAPL":
        assert "." in plan["quantity"]
    assert validate_manual_trade_plan(plan) == plan


@pytest.mark.parametrize("asset,quote,market_id", [
    ("BTC", "EUR", 42), ("ETH", "USDT", 43),
])
def test_crypto_database_numeric_padding_does_not_invalidate_verified_candles(asset, quote, market_id):
    plain = _completed_candles(price="100")
    padded = [{**row, **{
        key: Decimal(str(row[key])).quantize(Decimal("0.000000000000000000"))
        for key in ("open", "high", "low", "price")
    }} for row in plain]
    original = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction="long",
        max_loss_quote="20", candles=plain, market_id=market_id,
    )
    from_database = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction="long",
        max_loss_quote="20", candles=padded, market_id=market_id,
    )
    assert from_database == original
    assert from_database["executable"] is False
    padded[0]["price"] = Decimal("100.0000000000001")
    changed_source = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction="long",
        max_loss_quote="20", candles=padded, market_id=market_id,
    )
    assert changed_source["source_evidence"]["candles_sha256"] != original["source_evidence"]["candles_sha256"]
    assert changed_source["entry_price"] == original["entry_price"]


def test_candle_source_precision_is_exact_and_bounded():
    from backend.services.finn_manual_trade_suggestion_service import _candle_decimal

    assert _candle_decimal(Decimal("123456789012.000000000000000000"), "candle_close") == Decimal("123456789012")
    for value in (
        "123456789012.000000000000000001",
        "123456789012.123456789012000001",
        "999999999999.000000000000000001",
    ):
        assert _candle_decimal(Decimal(value), "candle_close") == Decimal(value)
    for value in (
        "1234567890123", "0." + "0" * 48 + "1",
        "1E-100000", "1E+100000", "NaN", "Infinity", "-1", "0",
    ):
        with pytest.raises(ValueError, match="candle_close_invalid"):
            _candle_decimal(Decimal(value), "candle_close")
    for value in (1.1, True, "1e-3", "1" * 10000):
        with pytest.raises(ValueError, match="candle_close_invalid"):
            _candle_decimal(value, "candle_close")
    assert _candle_decimal(Decimal("1." + "0" * 47 + "1"), "candle_close") == Decimal("1." + "0" * 47 + "1")
    with pytest.raises(ValueError, match="candle_close_invalid"):
        _candle_decimal(Decimal("0.000000000000000000"), "candle_close")


@pytest.mark.parametrize("asset,quote,market_id,direction", [
    ("BTC", "EUR", 42, "long"), ("ETH", "USDT", 43, "short"),
])
def test_high_precision_crypto_source_has_exact_hash_and_tick_bounded_risk(asset, quote, market_id, direction):
    from backend.services.finn_manual_trade_suggestion_service import METHOD_VERSION

    rows = _completed_candles()
    for row in rows:
        row.update({
            "open": Decimal("100.123456789012345678"),
            "high": Decimal("102.123456789012345678"),
            "low": Decimal("98.123456789012345678"),
            "price": Decimal("100.123456789012345678"),
        })
    context = {"recommendation": "reduced_risk", "risk_factor": "0.5"}
    plan = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction=direction,
        max_loss_quote="20", candles=rows, market_id=market_id, context=context,
    )
    assert plan["entry_price"] == "100.12345679"
    assert all(-Decimal(value).as_tuple().exponent <= 8
               for value in (plan["entry_price"], plan["stop_loss"], *plan["targets"]))
    assert -Decimal(plan["quantity"]).as_tuple().exponent <= 8
    assert Decimal(plan["max_loss_quote"]) <= Decimal("10")
    assert plan["executable"] is False
    assert plan["source_evidence"]["method_version"] == METHOD_VERSION
    assert validate_manual_trade_plan(plan) == plan
    assert ManualTradePlanChange.parse_obj({"plan_fields": plan}).plan_fields == plan

    changed = [{**row} for row in rows]
    changed[0]["open"] = Decimal("100.123456789012345679")
    changed_plan = derive_suggested_plan(
        asset=asset, quote_currency=quote, direction=direction,
        max_loss_quote="20", candles=changed, market_id=market_id, context=context,
    )
    assert changed_plan["entry_price"] == plan["entry_price"]
    assert changed_plan["source_evidence"]["candles_sha256"] != plan["source_evidence"]["candles_sha256"]


def test_old_source_method_and_changed_high_precision_candle_fail_confirmation(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    rows = _completed_candles()
    rows[-1]["price"] = Decimal("100.000000000000000001")
    plan = derive_suggested_plan(
        asset="BTC", quote_currency="EUR", direction="long",
        max_loss_quote="20", candles=rows, market_id=42,
    )
    old = {**plan, "source_evidence": {**plan["source_evidence"],
                                      "method_version": "daily_tr_14_stop_1_5r_targets_1r_2r_v1"}}
    with pytest.raises(ValueError, match="manual_trade_source_version_invalid"):
        asyncio.run(verify_suggested_manual_trade_plan(object(), old))

    async def source(_session, *, asset, quote_currency):
        assert (asset, quote_currency) == ("BTC", "EUR")
        return 42, rows

    monkeypatch.setattr(service, "_source_candles", source)
    asyncio.run(verify_suggested_manual_trade_plan(object(), plan))
    rows[-1]["price"] = Decimal("100.000000000000000002")
    with pytest.raises(ValueError, match="manual_trade_source_changed"):
        asyncio.run(verify_suggested_manual_trade_plan(object(), plan))


def test_market_suggestion_rejects_stale_or_missing_evidence():
    with pytest.raises(ValueError, match="candles_insufficient"):
        derive_suggested_plan(asset="BTC", quote_currency="EUR", direction="long",
                              max_loss_quote="20", candles=_completed_candles()[:-1], market_id=42)
    with pytest.raises(ValueError, match="candles_stale"):
        derive_suggested_plan(asset="BTC", quote_currency="EUR", direction="long",
                              max_loss_quote="20", candles=_completed_candles(now=datetime.now(timezone.utc)-timedelta(days=10)), market_id=42)


def test_stock_source_uses_catalog_provider_and_completed_exchange_days(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service
    from backend.services import market_data_provider_registry
    from backend.schemas.market_provider_schema import OHLCVCandleDTO
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    today = datetime.now(ny).date()
    old = [today - timedelta(days=offset) for offset in range(24, 0, -1)
           if (today - timedelta(days=offset)).weekday() < 5]
    records = [OHLCVCandleDTO(
        symbol="AAPL", provider="twelve_data", provider_symbol="AAPL", timeframe="1day",
        open=100, high=102, low=98, close=100,
        period_start=datetime.combine(day, datetime.min.time(), ny),
        raw_payload={"open": "100.00", "high": "102.00", "low": "98.00", "close": "100.00",
                     "_source_meta": {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ"}},
    ) for day in old]
    records.append(OHLCVCandleDTO(
        symbol="AAPL", provider="twelve_data", provider_symbol="AAPL", timeframe="1day",
        open=100, high=102, low=98, close=100,
        period_start=datetime.combine(today, datetime.min.time(), ny),
        raw_payload={"open": "100.00", "high": "102.00", "low": "98.00", "close": "100.00",
                     "_source_meta": {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ"}},
    ))
    records.append(OHLCVCandleDTO(
        symbol="AAPL", provider="other", provider_symbol="AAPL", timeframe="1day",
        open=100, high=102, low=98, close=100,
        period_start=datetime.combine(today - timedelta(days=1), datetime.min.time(), ny),
        raw_payload={"open": "100.00", "high": "102.00", "low": "98.00", "close": "100.00",
                     "_source_meta": {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ"}},
    ))

    class Provider:
        provider_name = "twelve_data"
        async def fetch_candles(self, asset, timeframe, limit):
            assert (asset.symbol, asset.provider_symbol, timeframe, limit) == ("AAPL", "AAPL", "1day", 40)
            return records

    monkeypatch.setattr(market_data_provider_registry.MarketDataProviderRegistry,
                        "resolve_for_asset", lambda self, asset: Provider())
    market_id, candles = asyncio.run(service._source_candles(
        object(), asset="AAPL", quote_currency="USD",
    ))
    assert market_id is None
    assert len(candles) == 15
    assert all(candle["source_observed_at"].astimezone(ny).date() < today for candle in candles)
    assert all(candle["id"] != int(today.strftime("%Y%m%d")) for candle in candles)
    plan = derive_suggested_plan(asset="AAPL", quote_currency="USD", direction="long",
                                 max_loss_quote="20", candles=candles, market_id=None)
    assert plan["source_evidence"]["provider"] == "twelve_data"
    assert plan["source_evidence"]["provider_symbol"] == "AAPL"
    original_hash = plan["source_evidence"]["candles_sha256"]
    records[-3].raw_payload["close"] = "100.000000000000000001"
    _, changed_candles = asyncio.run(service._source_candles(
        object(), asset="AAPL", quote_currency="USD",
    ))
    changed_plan = derive_suggested_plan(asset="AAPL", quote_currency="USD", direction="long",
                                         max_loss_quote="20", candles=changed_candles, market_id=None)
    assert changed_plan["entry_price"] == plan["entry_price"]
    assert changed_plan["source_evidence"]["candles_sha256"] != original_hash
    for record in records[:3]:
        record.raw_payload["_source_meta"]["currency"] = "EUR"
    records[-1].raw_payload["_source_meta"]["exchange"] = "OTHER"
    with pytest.raises(ValueError, match="candles_insufficient"):
        market_id, candles = asyncio.run(service._source_candles(
            object(), asset="AAPL", quote_currency="USD",
        ))
        derive_suggested_plan(asset="AAPL", quote_currency="USD", direction="long",
                              max_loss_quote="20", candles=candles, market_id=market_id)


def test_signed_stock_candidate_verifies_owner_without_refetching_provider(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    context = {"recommendation": "wait", "risk_factor": "0.5",
               "reason": "manual_trade_setup_outside_conditions"}
    plan = derive_suggested_plan(asset="AAPL", quote_currency="USD", direction="long",
                                 max_loss_quote="20", candles=_completed_candles(),
                                 market_id=None, context=context)
    signed = service._attest_plan(plan, 17)

    async def owner(_session, **kwargs):
        assert kwargs["user_id"] == 17
        return context

    async def no_provider(*args, **kwargs):
        raise AssertionError("provider refetch during confirmation")

    monkeypatch.setattr(service, "_owner_trade_context", owner)
    monkeypatch.setattr(service, "_source_candles", no_provider)
    asyncio.run(service.verify_suggested_manual_trade_plan(object(), signed, user_id=17))
    with pytest.raises(ValueError, match="attestation_invalid"):
        asyncio.run(service.verify_suggested_manual_trade_plan(object(), signed, user_id=18))
    altered = {**signed, "quantity": "2"}
    with pytest.raises(ValueError, match="attestation_invalid"):
        asyncio.run(service.verify_suggested_manual_trade_plan(object(), altered, user_id=17))


def test_market_suggestion_is_recomputed_before_confirmation(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service
    candles = _completed_candles()
    plan = derive_suggested_plan(asset="BTC", quote_currency="EUR", direction="long",
                                 max_loss_quote="20", candles=candles, market_id=42)

    async def source(_session, *, asset, quote_currency):
        assert (asset, quote_currency) == ("BTC", "EUR")
        return 42, candles

    monkeypatch.setattr(service, "_source_candles", source)
    asyncio.run(verify_suggested_manual_trade_plan(object(), plan))
    tampered = {**plan, "entry_price": "101"}
    with pytest.raises(ValueError, match="source_changed"):
        asyncio.run(verify_suggested_manual_trade_plan(object(), tampered))
    candles[-1] = {**candles[-1], "price": "101"}
    with pytest.raises(ValueError, match="source_changed"):
        asyncio.run(verify_suggested_manual_trade_plan(object(), plan))


def test_guided_market_suggestion_fills_card_from_verified_candles(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    async def source(_session, *, asset, quote_currency):
        assert (asset, quote_currency) == ("BTC", "EUR")
        return 42, _completed_candles()

    monkeypatch.setattr(service, "_source_candles", source)
    async def owner_context(_session, *, user_id, asset, quote_currency, market_id):
        assert (user_id, asset, quote_currency, market_id) == (17, "BTC", "EUR", 42)
        return {"setup_id": 3, "risk_factor": "0.5", "setup_match_status": "outside_conditions"}

    monkeypatch.setattr(service, "_owner_trade_context", owner_context)

    class SessionFactory:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, *_args):
            return None

    selector = FinnResponsesProposalSelection()
    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    call = FinnResponsesToolCall(
        name="create_manual_trade_plan_proposal", operation_id="create_manual_trade_plan",
        inputs={}, read_tools=(), required_inputs=contract.required_inputs,
        missing_inputs=(), draft_intent="new",
    )
    context = {}
    for message in ("Zet een trade voor BTC klaar", "BTC/EUR", "long", "maximaal verlies 20"):
        analysis = selector.from_call(call=call, message=message,
                                      conversation_context=context, verified_asset="BTC")
        context = {"active_guided_operation": analysis.request_plan.operation_state}
    assert not analysis.request_plan.clarification_required
    frontdoor = FinnResponsesFrontDoor.__new__(FinnResponsesFrontDoor)
    frontdoor.user_id = 17
    frontdoor.reads = SimpleNamespace(session_factory=SessionFactory)
    completed = asyncio.run(frontdoor._complete_manual_trade_suggestion(analysis))
    fields = completed.request_plan.operation_state["collected_inputs"]
    assert set(completed.request_plan.referenced_entities) <= set(contract.input_fields)
    assert fields["level_source"] == "market_derived"
    assert fields["source_evidence"]["market_id"] == 42
    assert fields["source_evidence"]["owner_context"]["risk_factor"] == "0.5"
    assert float(fields["max_loss_quote"]) <= 10
    assert fields["proposal_mode"] == "market_suggested"


def test_suggested_risk_budget_rejects_partial_or_wrong_currency():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    for invalid in ("1e3", "20%", "20 USDT extra", "1,2,3", "-20"):
        assert service._requested_slot_value(field="risk_budget_quote", text=invalid, contract=contract) is None
        assert "risk_budget_quote" not in service._manual_trade_inputs(f"maximaal verlies {invalid}")
    assert service._requested_slot_value(field="risk_budget_quote", text="20 EUR", contract=contract) == "20"
    state = service.resolve(contract=contract,
                            message="Zet een trade voor BTC/EUR klaar, long, maximaal verlies 20 USDT",
                            explicit_asset="BTC", conversation_context={})
    assert "risk_budget_quote" not in state.collected_inputs
    assert "risk_budget_quote" in state.missing_required_inputs
    for message in ("Zet een trade voor BTC/USDT klaar, long, maximaal verlies €20",
                    "Zet een trade voor BTC/EUR klaar, long, maximaal verlies $20"):
        state = service.resolve(contract=contract, message=message,
                                explicit_asset="BTC", conversation_context={})
        assert "risk_budget_quote" not in state.collected_inputs
        assert "risk_budget_quote" in state.missing_required_inputs
    first = service.resolve(contract=contract,
                            message="Zet een trade voor BTC klaar, long, maximaal verlies 20 EUR",
                            explicit_asset="BTC", conversation_context={})
    assert "risk_budget_quote" not in first.collected_inputs
    second = service.resolve(contract=contract, message="BTC/USDT", explicit_asset="BTC",
                             conversation_context={"active_guided_operation": first.dict()})
    assert "risk_budget_quote" in second.missing_required_inputs
    first_pair = service.resolve(contract=contract,
                                 message="Zet een trade voor BTC/EUR klaar, long, maximaal verlies 20 EUR",
                                 explicit_asset="BTC", conversation_context={})
    assert first_pair.collected_inputs["risk_budget_quote"] == "20"
    proposed = first_pair.copy(update={"status": "proposed", "open_proposal_id": "proposal-test"})
    changed_pair = service.resolve(contract=contract, message="Gebruik BTC/USDT", explicit_asset="BTC",
                                   conversation_context={"active_guided_operation": proposed.dict(),
                                                         "proposal_revision": {"proposal_id": "proposal-test",
                                                                               "operation_id": "create_manual_trade_plan"}})
    assert "risk_budget_quote" in changed_pair.missing_required_inputs
    assert changed_pair.collected_inputs["proposal_mode"] == "market_suggested"
    assert changed_pair.collected_inputs["direction"] == "long"
    stock = service.resolve(contract=contract,
                            message="Zet een trade voor Apple klaar, long, maximaal verlies 20 USD",
                            explicit_asset="AAPL", conversation_context={})
    assert stock.collected_inputs["quote_currency"] == "USD"
    assert stock.collected_inputs["risk_budget_quote"] == "20"


def test_user_supplied_levels_switch_guided_suggestion_to_user_stated_plan():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    first = service.resolve(contract=contract, message="Maak een handmatig tradevoorstel voor BTC/EUR",
                            explicit_asset="BTC", conversation_context={})
    assert first.collected_inputs.get("proposal_mode") != "market_suggested"
    second = service.resolve(
        contract=contract,
        message="Long, entry 70000, hoeveelheid 0.001, stop 65000, targets 80000 en 85000.",
        explicit_asset="BTC", conversation_context={"active_guided_operation": first.dict()},
    )
    assert second.collected_inputs["proposal_mode"] == "user_stated"
    assert not second.missing_required_inputs


def test_owner_context_adapts_risk_and_classifies_wait(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service
    from backend.infrastructure.repositories import setup_repository, user_repository
    from backend.services import setup_market_match_service

    profile = {"risk_profile": "balanced", "primary_timeframes": ["1d"]}
    setup = {"id": 5, "name": "Daily BTC", "symbol": "BTC", "market_id": 42,
             "quote_currency": "EUR",
             "setup_type": "trade", "timeframe": "1d"}
    assessment = {"source_status": "available", "benchmark_score": 68,
                  "as_of": "2026-11-10", "matches": [{"status": "matches", "score": 85,
                  "components": {"benchmark": {"score": 68, "minimum": 60, "maximum": 70}}}]}

    class UserRepo:
        def __init__(self, _session):
            pass
        async def get_by_id(self, user_id):
            assert user_id == 17
            return SimpleNamespace(ai_preferences=profile)

    class SetupRepo:
        def __init__(self, _session):
            pass
        async def get_all_setups(self, user_id):
            assert user_id == 17
            return [setup]

    class MatchService:
        def __init__(self, _session):
            pass
        async def for_asset(self, user_id, asset, **kwargs):
            assert (user_id, asset, kwargs["market_id"]) == (17, "BTC", 42)
            return assessment

    monkeypatch.setattr(user_repository, "UserRepository", UserRepo)
    monkeypatch.setattr(setup_repository, "SetupRepository", SetupRepo)
    monkeypatch.setattr(setup_market_match_service, "SetupMarketMatchService", MatchService)
    evaluate = lambda: asyncio.run(service._owner_trade_context(
        object(), user_id=17, asset="BTC", quote_currency="EUR", market_id=42,
    ))
    matching = evaluate()
    assert matching["recommendation"] == "review"
    assert matching["risk_factor"] == "1"

    assessment["matches"][0] = {"status": "outside_conditions", "score": 56,
                                "components": {"benchmark": {"score": 72, "minimum": 60, "maximum": 70}}}
    near = evaluate()
    assert near["recommendation"] == "reduced_risk"
    assert near["risk_factor"] == "0.5"
    assessment["matches"][0]["components"]["benchmark"]["score"] = 80
    far = evaluate()
    assert far["recommendation"] == "wait"
    assert far["risk_factor"] == "0.5"
    assessment["source_status"] = "stale_sources"
    unavailable = evaluate()
    assert unavailable["recommendation"] == "wait"
    assert unavailable["reason"] == "manual_trade_benchmark_unavailable"


def test_multiple_exact_market_setups_require_owner_choice(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service
    from backend.infrastructure.repositories import setup_repository, user_repository
    from backend.services import setup_market_match_service

    setups = [
        {"id": 5, "name": "Daily Base", "symbol": "BTC", "market_id": 42,
         "quote_currency": "EUR", "setup_type": "trade", "timeframe": "1d"},
        {"id": 6, "name": "Daily Swing", "symbol": "BTC", "market_id": 42,
         "quote_currency": "EUR", "setup_type": "trade", "timeframe": "1d"},
        {"id": 7, "name": "Other Pair", "symbol": "BTC", "market_id": 43,
         "quote_currency": "USDT", "setup_type": "trade", "timeframe": "1d"},
    ]

    class UserRepo:
        def __init__(self, _session):
            pass
        async def get_by_id(self, _user_id):
            return SimpleNamespace(ai_preferences={"risk_profile": "balanced", "primary_timeframes": ["1d"]})

    class SetupRepo:
        def __init__(self, _session):
            pass
        async def get_all_setups(self, _user_id):
            return setups

    class MatchService:
        def __init__(self, _session):
            pass
        async def for_asset(self, _user_id, _asset, **kwargs):
            assert [row["id"] for row in kwargs["setups"]] == [6]
            return {"source_status": "available", "benchmark_score": 68,
                    "as_of": "2026-11-10", "matches": [{"status": "matches"}]}

    monkeypatch.setattr(user_repository, "UserRepository", UserRepo)
    monkeypatch.setattr(setup_repository, "SetupRepository", SetupRepo)
    monkeypatch.setattr(setup_market_match_service, "SetupMarketMatchService", MatchService)
    context = lambda selected=None: asyncio.run(service._owner_trade_context(
        object(), user_id=17, asset="BTC", quote_currency="EUR", market_id=42,
        selected_setup_id=selected,
    ))
    ambiguous = context()
    assert ambiguous["reason"] == "manual_trade_setup_ambiguous"
    assert [item["id"] for item in ambiguous["setup_options"]] == [5, 6]
    assert context(6)["setup_id"] == 6
    assert context(7)["reason"] == "manual_trade_setup_selection_invalid"


def test_multiple_setup_choice_stays_in_guided_trade_draft(monkeypatch):
    selector = FinnResponsesProposalSelection()
    contract = FinnV2OperationRegistry().require_supported("create_manual_trade_plan")
    analysis = selector.from_call(
        call=FinnResponsesToolCall(
            name="create_manual_trade_plan_proposal", operation_id="create_manual_trade_plan",
            inputs={}, read_tools=(), required_inputs=contract.required_inputs,
            missing_inputs=(), draft_intent="new",
        ),
        message="Zet een trade voor BTC/EUR klaar, long, maximaal verlies 20 EUR",
        conversation_context={}, verified_asset="BTC",
    )
    frontdoor = FinnResponsesFrontDoor.__new__(FinnResponsesFrontDoor)
    frontdoor.run_id = "test-run"
    choice = frontdoor._manual_trade_setup_choice_result(
        analysis, [{"id": 5, "name": "Daily Base"}, {"id": 6, "name": "Daily Swing"}],
        None, "nl",
    )
    plan = choice.proposal_analysis.request_plan
    assert plan.clarification_required
    assert plan.missing_information == ["setup_id"]
    assert plan.operation_state["next_missing_input"] == "setup_id"
    assert len(plan.operation_state["setup_options"]) == 2
    assert plan.operation_state["collected_inputs"]["risk_budget_quote"] == "20"

    resumed = selector.from_call(
        call=FinnResponsesToolCall(
            name="create_manual_trade_plan_proposal", operation_id="create_manual_trade_plan",
            inputs={"setup_id": 6}, read_tools=(), required_inputs=contract.required_inputs,
            missing_inputs=("setup_id",), draft_intent="new",
        ),
        message="setup 6",
        conversation_context={"active_guided_operation": plan.operation_state},
        verified_asset="BTC", verified_target_inputs={"setup_id": 6},
    )
    resumed_state = resumed.request_plan.operation_state
    assert not resumed.request_plan.clarification_required
    assert resumed_state["collected_inputs"]["setup_id"] == 6
    assert resumed_state["input_sources"]["setup_id"] == "verified_owner_target"
    assert resumed_state["collected_inputs"]["risk_budget_quote"] == "20"

    from backend.services import finn_manual_trade_suggestion_service as service

    async def suggested(_session, **kwargs):
        assert kwargs["selected_setup_id"] == 6
        return service.derive_suggested_plan(
            asset="BTC", quote_currency="EUR", direction="long", max_loss_quote="20",
            candles=_completed_candles(), market_id=42,
            context={"setup_id": 6, "risk_factor": "1", "recommendation": "review"},
        )

    class Factory:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(service, "suggest_manual_trade_plan", suggested)
    frontdoor.user_id = 17
    frontdoor.reads = SimpleNamespace(session_factory=Factory)
    complete = asyncio.run(frontdoor._complete_manual_trade_suggestion(resumed))
    complete_inputs = complete.request_plan.operation_state["collected_inputs"]
    assert "setup_id" not in complete_inputs
    assert "setup_id" not in complete.request_plan.referenced_entities
    assert complete_inputs["source_evidence"]["owner_context"]["setup_id"] == 6
    from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService

    proposal = FinnV2ReasoningFallbackService._proposal_changes(
        operation_id="create_manual_trade_plan", supplied_inputs=complete_inputs,
        evidence_by_tool={},
    )
    assert proposal["plan_fields"]["source_evidence"]["owner_context"]["setup_id"] == 6
    assert proposal["plan_fields"]["executable"] is False


def test_manual_trade_setup_options_reach_terminal_projection():
    from backend.domain.finn_v2_runtime_contract import record_guided_draft, terminal_projection

    options = [{"id": 5, "name": "Daily Base"}, {"id": 6, "name": "Daily Swing"}]
    state = record_guided_draft(
        {"initial_operation_id": "create_manual_trade_plan",
         "final_operation_id": "create_manual_trade_plan",
         "identity": {"run_id": "run-1", "conversation_id": "conversation-1"}},
        guided_state={"collected_inputs": {"asset": "BTC", "quote_currency": "EUR"},
                      "missing_required_inputs": ["setup_id"],
                      "next_missing_input": "setup_id", "setup_options": options},
    )
    projection = terminal_projection(state, status="clarification_required", mode="CREATE_PROPOSAL", response={})
    assert projection["action_draft"]["setup_options"] == options
    assert projection["action_draft"]["requested_slot"] == "setup_id"


def test_unverified_owner_context_cannot_become_confirmable_trade_card(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    async def source(_session, *, asset, quote_currency):
        assert (asset, quote_currency) == ("ETH", "USDT")
        return 42, _completed_candles()

    async def owner(_session, *, user_id, asset, quote_currency, market_id):
        assert (user_id, asset, quote_currency, market_id) == (17, "ETH", "USDT", 42)
        return {"recommendation": "wait", "reason": "manual_trade_benchmark_unavailable",
                "risk_factor": "0.5"}

    monkeypatch.setattr(service, "_source_candles", source)
    monkeypatch.setattr(service, "_owner_trade_context", owner)
    with pytest.raises(service.ManualTradeWait, match="manual_trade_benchmark_unavailable"):
        asyncio.run(service.suggest_manual_trade_plan(
            object(), asset="ETH", quote_currency="USDT", direction="long",
            max_loss_quote="20", user_id=17,
        ))


def test_verified_score_mismatch_keeps_card_with_wait_advice(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    async def source(_session, *, asset, quote_currency):
        assert (asset, quote_currency) == ("ETH", "USDT")
        return 42, _completed_candles()

    async def owner(_session, *, user_id, asset, quote_currency, market_id):
        assert (user_id, asset, quote_currency, market_id) == (17, "ETH", "USDT", 42)
        return {"recommendation": "wait", "reason": "manual_trade_setup_outside_conditions",
                "risk_factor": "0.5"}

    monkeypatch.setattr(service, "_source_candles", source)
    monkeypatch.setattr(service, "_owner_trade_context", owner)
    plan = asyncio.run(service.suggest_manual_trade_plan(
        object(), asset="ETH", quote_currency="USDT", direction="long",
        max_loss_quote="20", user_id=17,
    ))
    assert plan["source_evidence"]["owner_context"]["recommendation"] == "wait"
    assert plan["executable"] is False
    assert float(plan["max_loss_quote"]) <= 10


def test_previously_signed_unverified_wait_card_cannot_be_saved(monkeypatch):
    from backend.services import finn_manual_trade_suggestion_service as service

    context = {"recommendation": "wait", "reason": "manual_trade_benchmark_unavailable",
               "risk_factor": "0.5"}
    plan = derive_suggested_plan(
        asset="AAPL", quote_currency="USD", direction="long", max_loss_quote="20",
        candles=_completed_candles(), market_id=None, context=context,
    )
    signed = service._attest_plan(plan, 17)

    async def owner(_session, *, user_id, asset, quote_currency, market_id):
        assert (user_id, asset, quote_currency, market_id) == (17, "AAPL", "USD", None)
        return context

    monkeypatch.setattr(service, "_owner_trade_context", owner)
    with pytest.raises(service.ManualTradeWait, match="manual_trade_benchmark_unavailable"):
        asyncio.run(service.verify_suggested_manual_trade_plan(object(), signed, user_id=17))


def test_adapter_saves_only_one_non_executable_owner_plan():
    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def mappings(self):
            return self

        def one(self):
            return self.value

    class Session:
        def __init__(self):
            self.calls = []
            self.saved = None

        async def execute(self, statement, params):
            sql = str(statement)
            self.calls.append(sql)
            if "SELECT id FROM trading_markets" in sql:
                return Result(42)
            if "INSERT INTO finn_manual_trade_plans" in sql:
                if self.saved is None:
                    import json
                    self.saved = {"id": params["id"], "plan_json": json.loads(params["plan_json"])}
                    return Result(params["id"])
                return Result(None)
            if "SELECT id,plan_json FROM finn_manual_trade_plans" in sql:
                return Result(self.saved)
            raise AssertionError(sql)

    session = Session()
    payload = terms()
    first = asyncio.run(save_manual_trade_plan(
        session, user_id=17, source_run_id="run-17", fields=payload,
    ))
    replay = asyncio.run(save_manual_trade_plan(
        session, user_id=17, source_run_id="run-17", fields=payload,
    ))
    assert first == replay
    assert first["executable"] is False
    assert session.saved["plan_json"]["market_id"] == 42
    assert all("orders" not in sql and "bot_configs" not in sql for sql in session.calls)


def test_manual_plan_postcondition_uses_saved_result_id():
    class Result:
        def mappings(self):
            return self
        def one_or_none(self):
            return {"id": "plan-1", "plan_json": {
                "asset": "BTC", "quote_currency": "EUR", "executable": False,
            }}

    class Session:
        async def execute(self, _statement, params):
            assert params == {"user_id": 7, "plan_id": "plan-1"}
            return Result()

    adapters = FinnV2ActionAdapterRegistry.__new__(FinnV2ActionAdapterRegistry)
    adapters.session = Session()
    digest = asyncio.run(adapters.postcondition_hash(
        "create_manual_trade_plan", user_id=7,
        payload={"id": "plan-1", "asset": "BTC", "quote_currency": "EUR"},
    ))
    assert len(digest) == 64


def test_saved_plan_read_is_owner_scoped_and_missing_owner_gets_404():
    from backend.api.ai_assistant_api import assistant_v2_get_manual_trade_plan

    class Result:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def one_or_none(self):
            return self.row

    class Session:
        def __init__(self):
            self.params = None

        async def execute(self, statement, params):
            self.params = params
            assert "user_id=:user_id" in str(statement)
            return Result(None)

    session = Session()
    with pytest.raises(HTTPException) as error:
        asyncio.run(assistant_v2_get_manual_trade_plan(
            "plan-other-owner", current_user={"id": 17}, db=session,
        ))
    assert error.value.status_code == 404
    assert session.params == {"plan_id": "plan-other-owner", "user_id": 17}
