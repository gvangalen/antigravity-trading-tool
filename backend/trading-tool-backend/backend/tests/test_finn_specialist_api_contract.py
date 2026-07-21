import json

import pytest
from fastapi import HTTPException

from backend.api.finn_specialist_api import _parse_specialist_payload
from backend.schemas.finn_specialist_schema import IndicatorContextRequest, WorkspaceContextRequest


WORKSPACE_PAYLOAD = {
    "subject_type": "setup",
    "subject_id": 12,
    "symbol": "BTC",
    "timeframe": "1D",
    "period": "day",
    "locale": "nl",
}


def test_workspace_contract_accepts_json_object():
    parsed = _parse_specialist_payload(WORKSPACE_PAYLOAD, WorkspaceContextRequest)

    assert parsed.subject_type == "setup"
    assert parsed.subject_id == 12
    assert parsed.symbol == "BTC"


def test_workspace_contract_accepts_one_legacy_json_string_layer():
    parsed = _parse_specialist_payload(json.dumps(WORKSPACE_PAYLOAD), WorkspaceContextRequest)

    assert parsed.subject_type == "setup"
    assert parsed.period == "day"


def test_indicator_contract_uses_the_same_compatibility_parser():
    parsed = _parse_specialist_payload(
        json.dumps(
            {
                "symbol": "BTC",
                "category": "technical",
                "indicator": "rsi",
                "period": "day",
                "timeframe": "1D",
                "locale": "nl",
            }
        ),
        IndicatorContextRequest,
    )

    assert parsed.indicator == "rsi"
    assert parsed.category == "technical"


@pytest.mark.parametrize("payload", [None, [], "not-json", json.dumps("still-a-string")])
def test_specialist_contract_rejects_non_object_payloads(payload):
    with pytest.raises(HTTPException) as exc_info:
        _parse_specialist_payload(payload, WorkspaceContextRequest)

    assert exc_info.value.status_code == 422
