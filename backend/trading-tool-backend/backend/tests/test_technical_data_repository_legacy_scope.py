import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, *, scalars=None, rows=None, first_row=None):
        self._scalars = scalars or []
        self._rows = rows or []
        self._first_row = first_row

    def scalars(self):
        return _ScalarResult(self._scalars)

    def fetchall(self):
        return self._rows

    def first(self):
        return self._first_row


def test_ensure_user_config_legacy_schema_ignores_symbol_and_asset_class_columns():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ExecuteResult(scalars=["id", "user_id", "indicator", "category", "priority", "enabled", "created_at"]),
            _ExecuteResult(first_row=None),
            _ExecuteResult(),
        ]
    )
    repo = TechnicalDataRepository(session)

    async def run():
        return await repo.ensure_user_config(
            2,
            "fear_greed_index",
            category="macro",
            symbol="BTC",
            asset_class="crypto",
            priority=7,
        )

    created = asyncio.run(run())

    assert created.symbol is None
    assert created.asset_class is None

    existing_query = str(session.execute.await_args_list[1].args[0])
    insert_query = str(session.execute.await_args_list[2].args[0])
    insert_params = session.execute.await_args_list[2].args[1]

    assert "symbol" not in existing_query.lower()
    assert "asset_class" not in existing_query.lower()
    assert "symbol" not in insert_query.lower()
    assert "asset_class" not in insert_query.lower()
    assert insert_params == {
        "user_id": 2,
        "indicator": "fear_greed_index",
        "priority": 7,
        "category": "macro",
    }


def test_ensure_user_config_very_legacy_schema_ignores_priority_too():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ExecuteResult(scalars=["id", "user_id", "indicator", "category"]),
            _ExecuteResult(first_row=None),
            _ExecuteResult(),
        ]
    )
    repo = TechnicalDataRepository(session)

    async def run():
        return await repo.ensure_user_config(
            2,
            "fear_greed_index",
            category="macro",
            symbol="BTC",
            asset_class="crypto",
            priority=7,
        )

    created = asyncio.run(run())

    assert created.priority == 100
    assert created.symbol is None
    assert created.asset_class is None

    existing_query = str(session.execute.await_args_list[1].args[0])
    insert_query = str(session.execute.await_args_list[2].args[0])
    insert_params = session.execute.await_args_list[2].args[1]

    assert "priority" not in existing_query.lower()
    assert "enabled" not in existing_query.lower()
    assert "created_at" not in existing_query.lower()
    assert "priority" not in insert_query.lower()
    assert insert_params == {
        "user_id": 2,
        "indicator": "fear_greed_index",
        "category": "macro",
    }


def test_ensure_user_config_existing_row_with_category_does_not_duplicate_namespace_kwargs():
    session = AsyncMock()
    session.flush = AsyncMock()
    existing_row = SimpleNamespace(
        _mapping={
            "id": 11,
            "user_id": 2,
            "indicator": "fear_greed_index",
            "category": "macro",
            "priority": 9,
            "enabled": False,
            "symbol": "BTC",
            "asset_class": "crypto",
        }
    )
    session.execute = AsyncMock(
        side_effect=[
            _ExecuteResult(
                scalars=["id", "user_id", "indicator", "category", "priority", "enabled", "symbol", "asset_class"]
            ),
            _ExecuteResult(first_row=existing_row),
            _ExecuteResult(),
        ]
    )
    repo = TechnicalDataRepository(session)

    async def run():
        return await repo.ensure_user_config(
            2,
            "fear_greed_index",
            category="macro",
            symbol="BTC",
            asset_class="crypto",
            priority=7,
        )

    updated = asyncio.run(run())

    assert updated.category == "macro"
    assert updated.symbol == "BTC"
    assert updated.asset_class == "crypto"
    assert updated.priority == 7
    assert updated.enabled is True


def test_get_user_configs_legacy_schema_returns_global_rows_for_symbol_request():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ExecuteResult(scalars=["id", "user_id", "indicator", "category", "priority", "enabled", "created_at"]),
            _ExecuteResult(
                rows=[
                    SimpleNamespace(
                        _mapping={
                            "id": 11,
                            "user_id": 2,
                            "indicator": "fear_greed_index",
                            "category": "macro",
                            "priority": 1,
                            "enabled": True,
                            "created_at": None,
                        }
                    )
                ]
            ),
        ]
    )
    repo = TechnicalDataRepository(session)

    async def run():
        return await repo.get_user_configs(2, category="macro", symbol="BTC", asset_class="crypto")

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert rows[0].indicator == "fear_greed_index"
    assert rows[0].symbol is None
    assert rows[0].asset_class is None

    query = str(session.execute.await_args_list[1].args[0])
    assert "symbol" not in query.lower()
    assert "asset_class" not in query.lower()


def test_get_user_config_columns_rolls_back_when_schema_probe_fails():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("probe failed"))
    session.rollback = AsyncMock()
    repo = TechnicalDataRepository(session)

    async def run():
        return await repo._get_user_config_columns()

    columns = asyncio.run(run())

    assert columns == {
        "id",
        "user_id",
        "indicator",
        "category",
        "created_at",
    }
    session.rollback.assert_awaited_once()
