import asyncio

import pytest
from fastapi import HTTPException

from backend.schemas.trading_schema import StrategyCreateSchema
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.services.strategy_service import StrategyService


def test_normalize_strategy_payload_promotes_nested_alias_fields():
    payload = StrategyService.normalize_strategy_payload(
        {
            "strategy": {
                "setupId": 278,
                "setupType": "trade",
                "baseAmount": "1500",
                "executionMode": "fixed",
                "entry": "62000",
                "stopLoss": "59800",
                "targetsText": "64000, 66000",
            }
        }
    )

    assert payload["setup_id"] == 278
    assert payload["setup_type"] == "trade"
    assert payload["base_amount"] == "1500"
    assert payload["execution_mode"] == "fixed"
    assert payload["entry"] == "62000"
    assert payload["stop_loss"] == "59800"
    assert payload["targets"] == "64000, 66000"


@pytest.mark.parametrize("execution_mode", ["manual", "handmatig", "automatic", "automatisch"])
def test_normalize_strategy_payload_maps_natural_execution_modes_to_the_existing_schema(execution_mode):
    payload = StrategyService.normalize_strategy_payload({"execution_mode": execution_mode})

    assert payload["execution_mode"] == "fixed"


def test_validate_trade_strategy_accepts_nested_camelcase_payload():
    service = StrategyService(db_session=None)

    service._validate_trade_strategy(
        {
            "strategy": {
                "entry": 62000,
                "stopLoss": 59800,
                "targetsText": "64000, 66000",
            }
        }
    )


def test_validate_trade_strategy_reads_trade_plan_when_present():
    service = StrategyService(db_session=None)

    service._validate_trade_strategy(
        {
            "trade_plan": {
                "entry": 185,
                "stop_loss": 176,
                "targets": [195, 205],
            }
        }
    )


def test_validate_trade_strategy_accepts_canonical_trade_payload():
    service = StrategyService(db_session=None)

    service._validate_trade_strategy(
        {
            "entry": 62000,
            "stop_loss": 59800,
            "targets": [64000, 66000],
        }
    )


def test_validate_trade_strategy_still_rejects_missing_levels_after_normalization():
    service = StrategyService(db_session=None)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_trade_strategy({"strategy": {"entry": 62000}})

    assert exc_info.value.detail == "entry en stop_loss verplicht voor trade"


class _MultipleStrategyRepository:
    def __init__(self):
        self.rows = []

    async def get_setup_for_verification(self, setup_id, user_id):
        return {
            "id": setup_id,
            "name": "BTC Swing Setup",
            "symbol": "BTC",
            "timeframe": "4H",
            "setup_type": "trade",
        }

    async def check_strategy_name_exists(self, setup_id, user_id, canonical_name, *, exclude_strategy_id=None):
        return any(
            row["setup_id"] == setup_id
            and row["user_id"] == user_id
            and row["canonical_name"] == canonical_name
            and row["id"] != exclude_strategy_id
            for row in self.rows
        )

    async def create_strategy(self, payload, curve_id, raw_data, user_id):
        row = {"id": len(self.rows) + 1, **payload, "data": raw_data, "user_id": user_id}
        self.rows.append(row)
        return row["id"]


class _Session:
    async def commit(self):
        return None


def test_strategy_inherits_exact_setup_quote_and_rejects_mixed_price_currency():
    class _PairRepository(_MultipleStrategyRepository):
        async def get_setup_for_verification(self, setup_id, user_id):
            return {"id": setup_id, "name": "BTC EUR", "symbol": "BTC",
                    "timeframe": "1D", "setup_type": "trade", "market_id": 23,
                    "market_quote_currency": "EUR"}

    async def run():
        service = StrategyService(_Session())
        service.repository = _PairRepository()
        strategy = StrategyCreateSchema(setup_id=77, name="BTC EUR trade",
                                        execution_mode="fixed", base_amount=100)
        levels = {"entry": 60000, "stop_loss": 58000, "targets": [64000]}
        saved = await service.save_strategy(strategy, levels.copy(), 9, commit=False)
        assert saved["trading_pair"] == "BTC/EUR"
        assert service.repository.rows[0]["market_id"] == 23
        assert service.repository.rows[0]["data"]["price_currency"] == "EUR"

        with pytest.raises(HTTPException) as exc_info:
            await service.save_strategy(strategy, {**levels, "price_currency": "USDT"}, 9, commit=False)
        assert exc_info.value.status_code == 422
        assert len(service.repository.rows) == 1

    asyncio.run(run())


def test_general_strategy_write_rejects_unvalidated_exact_dca_marker():
    class _DcaRepository(_MultipleStrategyRepository):
        async def get_setup_for_verification(self, setup_id, user_id):
            return {"id": setup_id, "name": "BTC DCA", "symbol": "BTC", "timeframe": "1D", "setup_type": "dca"}

    async def run():
        service = StrategyService(_Session())
        service.repository = _DcaRepository()
        with pytest.raises(HTTPException) as exc_info:
            await service.save_strategy(
                StrategyCreateSchema(setup_id=77, name="Forged", execution_mode="custom", base_amount=100),
                {"setup_id": 77, "name": "Forged", "execution_mode": "custom", "base_amount": 100,
                 "dca_amount_semantics": "planned_exact", "decision_curve": {"input": "market_score", "points": []}},
                9,
            )
        assert exc_info.value.status_code == 422
        assert service.repository.rows == []

    asyncio.run(run())


def test_multiple_strategies_can_share_a_setup_when_names_differ(monkeypatch):
    async def _mark_step_completed(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend.services.onboarding_service.mark_step_completed", _mark_step_completed)

    async def run():
        service = StrategyService(_Session())
        repository = _MultipleStrategyRepository()
        service.repository = repository

        first = await service.save_strategy(
            StrategyCreateSchema(setup_id=77, name="BTC breakout", execution_mode="fixed", base_amount=100),
            {"setup_id": 77, "name": "BTC breakout", "execution_mode": "fixed", "base_amount": 100,
             "entry": 60000, "stop_loss": 59000, "targets": [62000]},
            9,
        )
        second = await service.save_strategy(
            StrategyCreateSchema(setup_id=77, name="ETH swing", execution_mode="fixed", base_amount=200, symbol="ETH", timeframe="1H"),
            {"setup_id": 77, "name": "ETH swing", "execution_mode": "fixed", "base_amount": 200,
             "symbol": "ETH", "timeframe": "1H", "entry": 3000, "stop_loss": 2900, "targets": [3200]},
            9,
        )
        return first, second, repository

    first, second, repository = asyncio.run(run())

    assert [first["strategy_id"], second["strategy_id"]] == [1, 2]
    assert repository.rows[0]["symbol"] == "BTC"
    assert repository.rows[0]["data"]["asset_source"] == "setup_default"
    assert repository.rows[1]["symbol"] == "ETH"
    assert repository.rows[1]["timeframe"] == "1H"
    assert repository.rows[1]["data"]["asset_source"] == "explicit"


def test_strategy_name_is_unique_only_within_the_same_owner_and_setup():
    service = StrategyService(_Session())
    repository = _MultipleStrategyRepository()
    repository.rows.append({
        "id": 1,
        "setup_id": 77,
        "user_id": 9,
        "canonical_name": "btc breakout",
    })
    service.repository = repository

    async def run():
        await service.save_strategy(
            StrategyCreateSchema(setup_id=77, name=" BTC   Breakout ", execution_mode="fixed", base_amount=100),
            {"setup_id": 77, "name": " BTC   Breakout ", "execution_mode": "fixed", "base_amount": 100,
             "entry": 60000, "stop_loss": 59000, "targets": [62000]},
            9,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())

    assert exc_info.value.status_code == 409


def test_strategy_read_prefers_its_own_asset_and_timeframe_over_the_parent_setup():
    formatted = StrategyService(db_session=None)._format_strategy_row(
        {
            "id": 2,
            "setup_id": 77,
            "setup_name": "BTC Swing Setup",
            "name": "ETH swing",
            "symbol": "ETH",
            "timeframe": "1H",
            "setup_symbol": "BTC",
            "setup_timeframe": "4H",
            "setup_type": "trade",
            "execution_mode": "fixed",
            "base_amount": 200,
            "data": {"asset_source": "explicit", "timeframe_source": "explicit"},
        }
    )

    assert formatted["symbol"] == "ETH"
    assert formatted["timeframe"] == "1H"
    assert formatted["asset_source"] == "explicit"
    assert formatted["timeframe_source"] == "explicit"


def test_strategy_read_exposes_saved_market_pair_separately_from_euro_funding():
    formatted = StrategyService(db_session=None)._format_strategy_row({
        "id": 8, "setup_id": 77, "name": "BTC DCA", "symbol": "BTC",
        "setup_market_id": 12, "market_quote_currency": "USDT",
        "base_amount": 20, "data": {"base_currency": "EUR"},
    })
    assert formatted["market_id"] == 12
    assert formatted["quote_currency"] == "USDT"
    assert formatted["trading_pair"] == "BTC/USDT"
    assert formatted["base_amount"] == 20


def test_strategy_read_preserves_trade_level_currency_separately_from_euro_amount():
    formatted = StrategyService(db_session=None)._format_strategy_row({
        "id": 3, "setup_id": 77, "name": "BTC USD levels", "setup_type": "trade",
        "execution_mode": "fixed", "base_amount": 100,
        "data": {"entry": 84000, "stop_loss": 79800, "targets": [92400],
                 "price_currency": "USD", "price_currency_confirmed": True},
    })
    assert formatted["price_currency"] == "USD"
    assert formatted["entry"] == 84000
    assert formatted["base_amount"] == 100

    from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter
    evidence = asyncio.run(StrategyToolAdapter().execute(
        strategy={**formatted, "data": {"price_currency": "USD", "price_currency_confirmed": True}},
        resolution_source="explicit_name",
    ))["data"]
    assert evidence.price_currency == "USD"
    assert evidence.price_currency_status == "confirmed"
    assert evidence.currency == "EUR"


def test_legacy_strategy_read_does_not_present_default_eur_as_confirmed_quote():
    from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter

    evidence = asyncio.run(StrategyToolAdapter().execute(
        strategy={"id": 4, "setup_id": 77, "entry": "347.14",
                  "stop_loss": "342", "base_amount": 400,
                  "price_currency": "EUR", "data": {"price_currency": "EUR"}},
        resolution_source="setup_id",
    ))["data"]
    assert evidence.price_currency is None
    assert evidence.price_currency_status == "unconfirmed"
    assert evidence.currency == "EUR"


@pytest.mark.parametrize("invalid", ["", "XXX", None])
def test_strategy_rejects_invalid_price_currency_on_create_or_update(invalid):
    with pytest.raises(HTTPException) as exc_info:
        StrategyService._validated_price_currency(invalid)
    assert exc_info.value.status_code == 422
    assert StrategyService._validated_price_currency("usd") == "USD"


def test_strategy_update_binds_numeric_targets_as_postgres_text_array():
    class _Result:
        rowcount = 1

    class _CaptureSession:
        def __init__(self):
            self.params = None

        async def execute(self, _query, params):
            self.params = params
            return _Result()

    async def run():
        session = _CaptureSession()
        repository = StrategyRepository(session)
        result = await repository.update_strategy(
            4,
            9,
            {
                "name": "ETH swing",
                "canonical_name": "eth swing",
                "symbol": "ETH",
                "timeframe": "1H",
                "execution_mode": "fixed",
                "base_amount": 275,
            },
            "trade",
            {"entry": 3000, "targets": [3300, 3500], "stop_loss": 2850},
        )
        return result, session.params

    result, params = asyncio.run(run())

    assert result == 1
    assert params["targets"] == ["3300", "3500"]


def test_delete_strategy_dependency_names_the_owner_scoped_paper_bot():
    class _Scalars:
        def all(self):
            return ["Paper Guardian"]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        async def execute(self, _query, params):
            assert params == {"strategy_id": 44, "user_id": 9}
            return _Result()

    service = StrategyService(_Session())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.delete_strategy(44, 9))

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "Deze strategie is nog gekoppeld aan paper-bot ‘Paper Guardian’. "
        "Verwijder eerst de gekoppelde paper-bot."
    )
