from __future__ import annotations

import asyncio

from backend.infrastructure.repositories.setup_repository import SetupRepository


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
