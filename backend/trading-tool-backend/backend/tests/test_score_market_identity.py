import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.infrastructure.repositories.score_repository import ScoreRepository


def test_daily_score_read_uses_exact_market_id_when_selected():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        mappings=lambda: SimpleNamespace(first=lambda: {"market_score": 42}),
    )))
    repo = ScoreRepository(session)

    assert asyncio.run(repo.fetch_daily_scores(7, "BTC", market_id=23)) == {"market_score": 42}
    sql, params = session.execute.await_args.args[0], session.execute.await_args.args[1]
    assert "market_id = :market_id" in str(sql)
    assert params == {"user_id": 7, "symbol": "BTC", "market_id": 23}


def test_legacy_daily_score_read_excludes_exact_markets():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        mappings=lambda: SimpleNamespace(first=lambda: None),
    )))
    repo = ScoreRepository(session)

    assert asyncio.run(repo.fetch_daily_scores(7, "BTC")) is None
    sql, params = session.execute.await_args.args[0], session.execute.await_args.args[1]
    assert "market_id IS NULL" in str(sql)
    assert params == {"user_id": 7, "symbol": "BTC"}
