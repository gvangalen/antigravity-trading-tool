import pytest
from fastapi import HTTPException

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


@pytest.mark.parametrize("raw_day", ["monday", "maandag", "1", 1])
def test_active_strategy_weekday_normalizer_accepts_legacy_values(raw_day):
    assert normalize_weekday(raw_day) == 1
