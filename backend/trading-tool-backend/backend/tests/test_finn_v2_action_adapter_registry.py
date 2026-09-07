import asyncio

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry


class _Session:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return None


def test_watchlist_add_uses_database_unique_constraint_for_idempotency():
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
    assert "ON CONFLICT (user_id, symbol) DO NOTHING" in sql
    assert "CAST(:user_id AS INTEGER)" in sql
    assert "CAST(:symbol AS VARCHAR)" in sql
    assert params == {
        "user_id": 390,
        "symbol": "ETH",
    }


def test_create_strategy_adapter_delegates_to_existing_strategy_service():
    class _Strategies:
        async def save_strategy(self, payload, raw_payload, user_id):
            return {"id": 91, "setup_id": payload.setup_id, "user_id": user_id, "raw": raw_payload}

    registry = FinnV2ActionAdapterRegistry(session=object())
    registry.flags.execute_strategy_changes_enabled = lambda: True
    registry.strategies = _Strategies()

    result = asyncio.run(
        registry._create_strategy(
            390,
            {"change": {"strategy_fields": {"setup_id": 12, "execution_mode": "fixed", "base_amount": 100}}},
        )
    )

    assert result["setup_id"] == 12
    assert result["user_id"] == 390


def test_supported_v1_write_contracts_resolve_to_exactly_one_registered_adapter():
    """Action fields stay in the registry; adapters only execute that contract."""
    adapters = FinnV2ActionAdapterRegistry(session=object())
    contracts = FinnV2OperationRegistry()

    for operation_id in (
        "create_setup",
        "update_setup",
        "create_strategy",
        "update_strategy",
        "watchlist_add",
        "watchlist_remove",
    ):
        contract = contracts.require_supported(operation_id)
        assert contract.confirmation_required is True
        assert contract.execution_adapter == operation_id
        assert adapters.get(contract.execution_adapter) is not None
