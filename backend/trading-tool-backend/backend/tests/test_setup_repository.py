from __future__ import annotations

import asyncio

from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository


def test_create_setup_binds_tags_as_the_canonical_postgres_text_array():
    captured = {}

    class Result:
        def fetchone(self):
            return (41,)

    class Session:
        async def execute(self, query, params):
            captured["sql"] = str(query)
            captured["params"] = params
            return Result()

    payload = {
        "name": "QA setup",
        "symbol": "SOL",
        "timeframe": "4H",
        "setup_type": "dca",
    }
    setup_id = asyncio.run(SetupRepository(Session()).create_setup(payload, user_id=7, tags=["qa", "dca"]))

    assert setup_id == 41
    assert "CAST(:tags AS text[])" in captured["sql"]
    assert captured["params"]["tags"] == ["qa", "dca"]


def test_setup_name_checks_are_owner_scoped_and_canonicalized():
    captured = {}

    class Result:
        def fetchone(self):
            return None

        def scalar(self):
            return 0

    class Session:
        async def execute(self, query, params):
            captured.setdefault("sql", []).append(str(query))
            captured.setdefault("params", []).append(params)
            return Result()

    repository = SetupRepository(Session())
    assert asyncio.run(repository.check_name_exists(" BTC setup ", user_id=7)) is False
    assert asyncio.run(repository.simple_check_name(" BTC setup ", user_id=7)) is False

    assert all("LOWER(BTRIM(name))" in query for query in captured["sql"])
    assert all(params["user_id"] == 7 for params in captured["params"])


def test_strategy_targets_bind_as_the_canonical_postgres_text_array():
    captured = {}

    class Result:
        def fetchone(self):
            return (88,)

    class Session:
        async def execute(self, query, params):
            captured["params"] = params
            return Result()

    strategy_id = asyncio.run(
        StrategyRepository(Session()).create_strategy(
            {
                "setup_id": 41,
                "name": "BTC browser strategy",
                "setup_type": "trade",
                "execution_mode": "fixed",
                "base_amount": 100,
            },
            curve_id=None,
            raw_data={"targets": [65000, 67000]},
            user_id=7,
        )
    )

    assert strategy_id == 88
    assert captured["params"]["targets"] == ["65000", "67000"]
