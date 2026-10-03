import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import score_service as score_service_module
from backend.services.score_service import ScoreService


def test_daily_scores_read_does_not_initialize_or_refresh_indicators(monkeypatch):
    repository = SimpleNamespace(
        db=object(),
        fetch_daily_scores=AsyncMock(return_value=None),
    )

    def fail_if_initialized(*args, **kwargs):
        raise AssertionError("A read-only score request must not initialize technical data")

    monkeypatch.setattr(
        score_service_module,
        "TechnicalDataRepository",
        fail_if_initialized,
    )

    with pytest.raises(LookupError):
        asyncio.run(ScoreService(repository).get_daily_scores(7, "ETH"))

    repository.fetch_daily_scores.assert_awaited_once_with(7, "ETH")


def test_daily_score_response_preserves_the_saved_report_date():
    report_date = date(2026, 10, 3)
    repository = SimpleNamespace(
        db=object(),
        fetch_daily_scores=AsyncMock(return_value={
            "report_date": report_date,
            "macro_score": 100,
            "technical_score": 75,
            "market_score": 100,
            "setup_score": 50,
        }),
        fetch_active_setups=AsyncMock(return_value=[]),
    )

    result = asyncio.run(ScoreService(repository).get_daily_scores(7, "BTC"))

    assert result.report_date == report_date
