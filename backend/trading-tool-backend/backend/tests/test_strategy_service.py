import pytest
from fastapi import HTTPException

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
