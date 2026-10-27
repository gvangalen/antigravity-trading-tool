import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


def test_reselecting_ma200_keeps_owner_scoring_config():
    class Session:
        def __init__(self):
            self.calls = []

        async def execute(self, statement, params):
            self.calls.append((str(statement), params))

    session = Session()
    repo = TechnicalDataRepository(session)
    repo._resolve_effective_scope = AsyncMock(return_value=("BTC", "crypto"))
    owner_row = SimpleNamespace(indicator="ma_200", config_json={"score_mode": "custom", "curve": [20, 80]})
    repo.ensure_user_config = AsyncMock(return_value=owner_row)

    rows = asyncio.run(repo.replace_scope_configs(7, [("ma_200", 1)], symbol="BTC"))

    assert rows == [owner_row]
    assert rows[0].config_json["score_mode"] == "custom"
    query, params = session.calls[0]
    assert "LOWER(indicator) NOT IN" in query
    assert "market_id IS NULL" in query
    assert params["retained"] == ["ma_200"]
    repo.ensure_user_config.assert_awaited_once_with(
        7, "ma_200", category="technical", symbol="BTC", asset_class="crypto", priority=1,
    )


def test_empty_preference_still_removes_all_indicators():
    class Session:
        def __init__(self):
            self.calls = []

        async def execute(self, statement, params):
            self.calls.append((str(statement), params))

    session = Session()
    repo = TechnicalDataRepository(session)
    repo._resolve_effective_scope = AsyncMock(return_value=("BTC", "crypto"))

    assert asyncio.run(repo.replace_scope_configs(7, [], symbol="BTC")) == []
    query, params = session.calls[0]
    assert "NOT IN" not in query
    assert "market_id IS NULL" in query
    assert params == {"user_id": 7, "category": "technical", "symbol": "BTC"}


def test_case_variant_reuses_existing_owner_config():
    existing = {
        "id": 12, "indicator": "RSI", "priority": 1, "enabled": True,
        "category": "technical", "symbol": "BTC", "asset_class": "crypto",
        "config_json": {"score_mode": "custom"}, "provenance": "indicator_config_api",
    }

    class Result:
        def first(self):
            return SimpleNamespace(_mapping=existing)

    class Session:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, params):
            self.statements.append(str(statement))
            return Result()

        async def flush(self):
            pass

    session = Session()
    repo = TechnicalDataRepository(session)
    repo._resolve_effective_scope = AsyncMock(return_value=("BTC", "crypto"))

    row = asyncio.run(repo.ensure_user_config(7, "rsi", symbol="BTC", priority=1))

    assert row.config_json == {"score_mode": "custom"}
    assert "LOWER(indicator) = LOWER(:indicator)" in session.statements[0]
    assert not any("INSERT INTO user_indicator_configs" in statement for statement in session.statements)


def test_case_variant_metadata_update_targets_existing_owner_row():
    class Session:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, params):
            self.statements.append((str(statement), params))

        async def flush(self):
            pass

    session = Session()
    repo = TechnicalDataRepository(session)
    repo._resolve_effective_scope = AsyncMock(return_value=("BTC", "crypto"))
    repo.ensure_user_config = AsyncMock(return_value=SimpleNamespace(
        id=12, indicator="RSI", config_json={}, provenance="product_api", source_record_id=None,
    ))

    row = asyncio.run(repo.set_indicator_config_metadata(
        7, "rsi", "technical", symbol="BTC", config_json={"score_mode": "custom"},
    ))

    assert row.config_json == {"score_mode": "custom"}
    query, params = session.statements[0]
    assert "LOWER(indicator) = LOWER(:indicator)" in query
    assert params["indicator"] == "rsi"
