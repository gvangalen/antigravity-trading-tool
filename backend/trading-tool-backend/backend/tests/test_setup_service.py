import pytest
from fastapi import HTTPException

from backend.schemas.trading_schema import SetupCreateSchema
from backend.services.setup_service import SetupService
from backend.services.strategy_service import normalize_weekday


def _weekly_payload(day):
    return {
        "name": "BTC weekly DCA",
        "symbol": "BTC",
        "timeframe": "1W",
        "setup_type": "dca",
        "dca_frequency": "weekly",
        "dca_day": day,
        "min_macro_score": 0,
        "max_macro_score": 100,
        "min_technical_score": 0,
        "max_technical_score": 100,
        "min_market_score": 0,
        "max_market_score": 100,
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


@pytest.mark.parametrize("raw_day", ["15", 15])
def test_monthly_dca_month_day_is_normalized_to_text_number(raw_day):
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

    assert payload["dca_month_day"] == "15"
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


@pytest.mark.parametrize("raw_day", ["monday", "maandag", "1", 1])
def test_active_strategy_weekday_normalizer_accepts_legacy_values(raw_day):
    assert normalize_weekday(raw_day) == 1


def test_get_active_setup_filters_candidates_by_symbol(monkeypatch):
    service = SetupService(None)

    class Repo:
        async def get_all_setups(self, user_id):
            return [
                {
                    "id": 1,
                    "name": "ETH Smart DCA",
                    "symbol": "ETH",
                    "timeframe": "1W",
                    "setup_type": "dca",
                    "min_macro_score": 0,
                    "max_macro_score": 100,
                    "min_technical_score": 0,
                    "max_technical_score": 100,
                    "min_market_score": 0,
                    "max_market_score": 100,
                },
                {
                    "id": 2,
                    "name": "BTC Smart DCA",
                    "symbol": "BTC",
                    "timeframe": "1W",
                    "setup_type": "dca",
                    "min_macro_score": 0,
                    "max_macro_score": 100,
                    "min_technical_score": 0,
                    "max_technical_score": 100,
                    "min_market_score": 0,
                    "max_market_score": 100,
                },
            ]

    class Session:
        async def execute(self, *args, **kwargs):
            class Result:
                def fetchone(self):
                    return (50, 50, 50)
            return Result()

    service.repository = Repo()
    service.session = Session()

    import asyncio
    result = asyncio.run(service.get_active_setup(42, "BTC"))

    assert result["active"]["setup_id"] == 2
    assert result["active"]["name"] == "BTC Smart DCA"
    assert result["active"]["symbol"] == "BTC"
