import asyncio
import pytest
from fastapi import HTTPException

from backend.domain.finn_manual_trade_plan_contract import validate_manual_trade_plan
from backend.services.finn_manual_trade_plan_service import save_manual_trade_plan
from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_proposal_schema import ManualTradePlanChange
from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor


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
