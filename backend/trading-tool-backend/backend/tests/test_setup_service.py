import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from backend.schemas.trading_schema import SetupCreateSchema
from backend.services.setup_service import SetupService
from backend.services.setup_market_match_service import SetupMarketMatchService
from backend.services.strategy_service import normalize_weekday


@pytest.fixture(autouse=True)
def _capture_coach_feed_dispatch(monkeypatch):
    from backend.celery_task.store_daily_scores_task import reconcile_coach_feed_score
    monkeypatch.setattr(reconcile_coach_feed_score, "delay", lambda *_: None)


def _weekly_payload(day):
    return {
        "name": "BTC weekly DCA",
        "symbol": "BTC",
        "timeframe": "1W",
        "setup_type": "dca",
        "dca_frequency": "weekly",
        "dca_day": day,
        "min_benchmark_score": 0,
        "max_benchmark_score": 100,
    }


@pytest.mark.parametrize("raw_day", ["monday", "maandag", "1", 1])
def test_weekly_dca_day_is_normalized_to_text_number(raw_day):
    service = SetupService(None)
    payload = _weekly_payload(raw_day)

    service.validate_setup_payload(payload)

    assert payload["dca_day"] == "1"
    assert payload["dca_month_day"] is None


def test_weekly_dca_rejects_invalid_day():
    service = SetupService(None)
    payload = _weekly_payload("funday")

    with pytest.raises(HTTPException) as exc:
        service.validate_setup_payload(payload)

    assert exc.value.status_code == 400
    assert "dca_day" in exc.value.detail


def test_setup_description_is_optional_trimmed_and_bounded():
    service = SetupService(None)
    payload = _weekly_payload("monday") | {"description": "  Wait for a pullback.  "}
    service.validate_setup_payload(payload)
    assert payload["description"] == "Wait for a pullback."

    payload = _weekly_payload("monday") | {"description": "x" * 1001}
    with pytest.raises(HTTPException) as exc:
        service.validate_setup_payload(payload)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("raw_day", ["15", 15])
def test_monthly_dca_month_day_is_normalized_to_integer(raw_day):
    service = SetupService(None)
    payload = {
        "name": "BTC monthly DCA",
        "symbol": "BTC",
        "timeframe": "1M",
        "setup_type": "dca",
        "dca_frequency": "monthly",
        "dca_month_day": raw_day,
    }

    service.validate_setup_payload(payload)

    assert payload["dca_month_day"] == 15
    assert payload["dca_day"] is None


def test_trade_setup_clears_dca_fields():
    service = SetupService(None)
    payload = {
        "name": "BTC trade",
        "symbol": "BTC",
        "timeframe": "4H",
        "setup_type": "trade",
        "dca_frequency": "weekly",
        "dca_day": "monday",
        "dca_month_day": "15",
    }

    service.validate_setup_payload(payload)

    assert payload["dca_frequency"] is None
    assert payload["dca_day"] is None
    assert payload["dca_month_day"] is None


def test_save_setup_applies_default_timeframe_for_trade_payload():
    service = SetupService(None)
    payload = SetupCreateSchema(name="BTC trade", symbol="BTC", setup_type="trade")
    raw_payload = {
        "name": "BTC trade",
        "symbol": "BTC",
        "setup_type": "trade",
    }

    class Repo:
        async def check_name_exists(self, name, user_id):
            return False

        async def create_setup(self, payload_data, user_id, tags):
            assert payload_data["timeframe"] == "4H"
            return 123

        async def get_setup_by_id(self, setup_id, user_id):
            return {
                "id": setup_id,
                "name": "BTC trade",
                "symbol": "BTC",
                "timeframe": "4H",
                "setup_type": "trade",
                "tags": [],
                "favorite": False,
                "created_at": None,
                "user_id": user_id,
            }

    class Session:
        async def commit(self):
            return None

    async def no_op_onboarding(_user_id):
        return None

    service.repository = Repo()
    service.session = Session()
    service._mark_setup_step_completed_best_effort = no_op_onboarding

    import asyncio
    result = asyncio.run(service.save_setup(payload, raw_payload, 7))

    assert result["status"] == "success"
    assert result["setup"]["timeframe"] == "4H"
    assert result["field_sources"]["min_benchmark_score"] == "absent"
    assert "min_benchmark_score" not in raw_payload


def test_new_crypto_setup_binds_only_the_exact_verified_pair(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    class FakeMarketService:
        def __init__(self, _session):
            pass

        async def resolve(self, base, quote, *, verify_current):
            assert (base, quote, verify_current) == ("BTC", "EUR", True)
            return SimpleNamespace(id=83, quote_currency="EUR", pair="BTC/EUR")

    class Repo:
        async def check_name_exists(self, _name, _user_id):
            return False

        async def create_setup(self, data, _user_id, _tags):
            assert data["market_id"] == 83
            assert data["trading_pair"] == "BTC/EUR"
            return 91

        async def get_setup_by_id(self, _setup_id, _user_id):
            return {"id": 91, "name": "BTC EUR", "symbol": "BTC",
                    "setup_type": "trade", "market_id": 83,
                    "quote_currency": "EUR", "tradingview_symbol": "BINANCE:BTCEUR"}

    monkeypatch.setattr("backend.services.setup_service.TradingMarketService", FakeMarketService)
    service = SetupService(None)
    service.repository = Repo()
    payload = SetupCreateSchema(name="BTC EUR", symbol="BTC", setup_type="trade")
    result = asyncio.run(service.save_setup(
        payload, {"name": "BTC EUR", "symbol": "BTC", "setup_type": "trade",
                  "quote_currency": "EUR"}, 17, commit=False,
    ))
    assert result["setup"]["trading_pair"] == "BTC/EUR"
    assert result["setup"]["tradingview_symbol"] == "BINANCE:BTCEUR"


@pytest.mark.parametrize("raw_day", ["monday", "maandag", "1", 1])
def test_active_strategy_weekday_normalizer_accepts_legacy_values(raw_day):
    assert normalize_weekday(raw_day) == 1


def test_get_active_setup_filters_candidates_by_symbol(monkeypatch):
    service = SetupService(None)
    async def matched(_self, user_id):
        assert user_id == 42
        return {"matches": [
            {"setup_id": 1, "name": "ETH Smart DCA", "symbol": "ETH",
             "is_active": True, "is_best": True, "source_status": "available", "as_of": date.today()},
            {"setup_id": 2, "name": "BTC Smart DCA", "symbol": "BTC",
             "is_active": True, "is_best": True, "source_status": "available", "as_of": date.today()},
        ]}

    monkeypatch.setattr(SetupMarketMatchService, "for_all_assets", matched)

    import asyncio
    result = asyncio.run(service.get_active_setup(42, "BTC"))

    assert result["active"]["setup_id"] == 2
    assert result["active"]["name"] == "BTC Smart DCA"
    assert result["active"]["symbol"] == "BTC"


def test_get_active_setup_does_not_choose_between_two_active_quotes(monkeypatch):
    async def matched(_self, _user_id):
        return {"matches": [
            {"setup_id": 1, "symbol": "BTC", "market_id": 21,
             "is_active": True, "is_best": True},
            {"setup_id": 2, "symbol": "BTC", "market_id": 22,
             "is_active": True, "is_best": True},
        ]}

    monkeypatch.setattr(SetupMarketMatchService, "for_all_assets", matched)
    result = asyncio.run(SetupService(None).get_active_setup(42, "BTC"))
    assert result == {"active": None, "source_status": "ambiguous_market", "as_of": None}


def test_delete_setup_dependency_names_the_owner_scoped_strategy():
    class _Scalars:
        def all(self):
            return ["BTC Breakout"]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Session:
        async def execute(self, _query, params):
            assert params == {"setup_id": 12, "user_id": 7}
            return _Result()

    service = SetupService(_Session())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.delete_setup(12, 7))

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "Deze setup is nog gekoppeld aan strategie ‘BTC Breakout’. "
        "Verwijder eerst de gekoppelde strategie."
    )
