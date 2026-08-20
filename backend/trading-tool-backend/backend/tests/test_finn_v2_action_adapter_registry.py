import asyncio

from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry


class _Session:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return None


def test_watchlist_add_uses_schema_compatible_idempotent_insert_without_on_conflict():
    session = _Session()
    registry = FinnV2ActionAdapterRegistry(session)
    registry.flags.execute_watchlist_changes_enabled = lambda: True

    result = asyncio.run(
        registry._watchlist_add(
            390,
            {"change": {"asset": "ETH", "operation": "add"}},
        )
    )

    assert result == {"ok": True, "asset": "ETH", "operation": "watchlist_add"}
    assert len(session.calls) == 1
    sql, params = session.calls[0]
    assert "INSERT INTO watchlists" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "CAST(:insert_user_id AS INTEGER)" in sql
    assert "CAST(:insert_symbol AS VARCHAR)" in sql
    assert "ON CONFLICT" not in sql
    assert params == {
        "insert_user_id": 390,
        "insert_symbol": "ETH",
        "lookup_user_id": 390,
        "lookup_symbol": "ETH",
    }
