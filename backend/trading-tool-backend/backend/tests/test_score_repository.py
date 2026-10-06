import asyncio

from backend.infrastructure.repositories.score_repository import ScoreRepository


def test_active_setups_use_owner_scoped_current_match_without_legacy_scores(monkeypatch):
    from backend.infrastructure.repositories.setup_repository import SetupRepository
    from backend.services.setup_market_match_service import SetupMarketMatchService

    async def setups(_repository, user_id):
        assert user_id == 7
        return [
            {"id": 1, "name": "BTC A", "symbol": "BTC"},
            {"id": 2, "name": "BTC B", "symbol": "BTC"},
        ]

    async def matches(_service, user_id, *, setups):
        assert user_id == 7
        assert [item["id"] for item in setups] == [1, 2]
        return {"matches": [
            {"setup_id": 1, "score": None, "is_active": False, "is_best": False,
             "status": "insufficient_data", "components": {}},
            {"setup_id": 2, "score": 83, "is_active": True, "is_best": True,
             "status": "matches", "components": {"market": {"score": 80}}},
        ]}

    monkeypatch.setattr(SetupRepository, "get_all_setups", setups)
    monkeypatch.setattr(SetupMarketMatchService, "for_all_assets", matches)
    rows = asyncio.run(ScoreRepository(object()).fetch_active_setups(7))

    assert [row["id"] for row in rows] == [2, 1]
    assert rows[0]["score"] == 83
    assert rows[0]["score_semantics"] == "benchmark_setup_match_v1"
    assert rows[1]["score"] is None
