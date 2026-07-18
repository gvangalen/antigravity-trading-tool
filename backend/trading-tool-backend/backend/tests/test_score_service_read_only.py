import asyncio
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
