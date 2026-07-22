import pytest
from fastapi import HTTPException

from backend.utils.indicator_score_validation import require_indicator_score


def test_require_indicator_score_accepts_and_clamps_numeric_values():
    assert require_indicator_score({"score": 42}, "rsi") == 42.0
    assert require_indicator_score({"score": 120}, "rsi") == 100.0
    assert require_indicator_score({"score": -5}, "rsi") == 0.0


@pytest.mark.parametrize("payload", [None, {}, {"score": None}, {"score": "invalid"}])
def test_require_indicator_score_rejects_missing_or_invalid_values(payload):
    with pytest.raises(HTTPException) as exc_info:
        require_indicator_score(payload, "rsi")

    assert exc_info.value.status_code == 422
    assert "niet opgeslagen" in exc_info.value.detail
