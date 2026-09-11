import asyncio

import pytest

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
        async def save_strategy(self, payload, raw_payload, user_id, *, allow_incomplete_trade_draft):
            return {
                "id": 91,
                "setup_id": payload.setup_id,
                "user_id": user_id,
                "raw": raw_payload,
                "allow_incomplete_trade_draft": allow_incomplete_trade_draft,
            }

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
    assert result["allow_incomplete_trade_draft"] is True


def test_update_strategy_normalizes_natural_execution_mode_before_persistence():
    class _Strategies:
        async def update_strategy(self, strategy_id, fields, user_id):
            return {"strategy_id": strategy_id, "fields": fields, "user_id": user_id}

    registry = FinnV2ActionAdapterRegistry(session=object())
    registry.flags.execute_strategy_changes_enabled = lambda: True
    registry.strategies = _Strategies()

    result = asyncio.run(registry._update_strategy(
        390,
        {"change": {"strategy_id": 12, "changed_fields": {"execution_mode": "automatisch"}}},
    ))

    assert result["fields"] == {"execution_mode": "fixed"}


def test_update_bot_maps_the_contract_budget_slot_to_the_persisted_schema():
    class _Bots:
        async def update_bot_config(self, bot_id, payload, user_id):
            return {"bot_id": bot_id, "payload": payload.dict(exclude_unset=True), "user_id": user_id}

    registry = FinnV2ActionAdapterRegistry(session=object())
    registry.flags.execute_bot_changes_enabled = lambda: True
    registry.bots = _Bots()

    result = asyncio.run(registry._update_bot(
        390,
        {"change": {"bot_id": 14, "changed_fields": {"budget": 100}}},
    ))

    assert result["payload"] == {"budget_total_eur": 100.0, "risk_acknowledged": True}


def test_supported_v1_write_contracts_resolve_to_exactly_one_registered_adapter():
    """Action fields stay in the registry; adapters only execute that contract."""
    adapters = FinnV2ActionAdapterRegistry(session=object())
    contracts = FinnV2OperationRegistry()

    for operation_id in (
        "select_asset",
        "create_indicator_configuration",
        "update_indicator_configuration",
        "delete_indicator_configuration",
        "create_setup",
        "update_setup",
        "delete_setup",
        "create_strategy",
        "update_strategy",
        "delete_strategy",
        "create_bot",
        "update_bot",
        "delete_bot",
        "deactivate_bot",
        "watchlist_add",
        "watchlist_remove",
    ):
        contract = contracts.require_supported(operation_id)
        assert contract.confirmation_required is True
        assert contract.execution_adapter == operation_id
        assert adapters.get(contract.execution_adapter) is not None


def test_new_mutation_adapters_are_fail_closed_until_their_specific_flag_is_enabled(monkeypatch):
    # The local integration stack explicitly enables non-financial fixture
    # adapters. This unit test verifies the production-default, not that
    # deliberately isolated local environment.
    monkeypatch.delenv("FINN_LOCAL_SAFE_ADAPTERS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("FINN_V2_EXECUTE_ASSET_SELECTION", raising=False)
    monkeypatch.delenv("FINN_V2_EXECUTE_INDICATOR_CHANGES", raising=False)
    monkeypatch.delenv("FINN_V2_EXECUTE_BOT_CHANGES", raising=False)
    registry = FinnV2ActionAdapterRegistry(session=object())

    assert registry.flags.execute_asset_selection_enabled() is False
    assert registry.flags.execute_indicator_changes_enabled() is False
    assert registry.flags.execute_bot_changes_enabled() is False


def test_action_adapter_flags_use_the_canonical_deployment_keys(monkeypatch):
    """Reject lookalike settings so local and deployed policy stay comparable."""
    monkeypatch.delenv("FINN_LOCAL_SAFE_ADAPTERS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    for name in (
        "FINN_V2_EXECUTE_ASSET_SELECTION",
        "FINN_V2_EXECUTE_INDICATOR_CHANGES",
        "FINN_V2_EXECUTE_SETUP_CHANGES",
        "FINN_V2_EXECUTE_STRATEGY_CHANGES",
        "FINN_V2_EXECUTE_BOT_CHANGES",
    ):
        monkeypatch.setenv(name, "true")
        monkeypatch.setenv(f"{name}_ENABLED", "false")

    flags = FinnV2ActionAdapterRegistry(session=object()).flags

    assert flags.execute_asset_selection_enabled() is True
    assert flags.execute_indicator_changes_enabled() is True
    assert flags.execute_setup_changes_enabled() is True
    assert flags.execute_strategy_changes_enabled() is True
    assert flags.execute_bot_changes_enabled() is True


def test_bot_creation_uses_existing_service_and_refuses_implicit_live_mode():
    class _Bots:
        async def create_bot_config(self, payload, user_id):
            return {"ok": True, "user_id": user_id, "is_live": payload.is_live, "strategy_id": payload.strategy_id}

    registry = FinnV2ActionAdapterRegistry(session=object())
    registry.flags.execute_bot_changes_enabled = lambda: True
    registry.bots = _Bots()

    result = asyncio.run(
        registry._create_bot(
            390,
            {"change": {"bot_fields": {"name": "Paper", "strategy_id": 12, "mode": "manual"}}},
        )
    )

    assert result == {"ok": True, "user_id": 390, "is_live": False, "strategy_id": 12}
    with pytest.raises(ValueError, match="live_bot_creation_not_allowed"):
        asyncio.run(
            registry._create_bot(
                390,
                {"change": {"bot_fields": {"name": "Unsafe", "strategy_id": 12, "is_live": True}}},
            )
        )


def test_asset_selection_uses_the_owner_scoped_preferences_repository():
    class _Users:
        async def update_ai_preferences(self, user_id, preferences):
            assert user_id == 390
            assert preferences == {"selected_asset": "ETH"}
            return object()

    registry = FinnV2ActionAdapterRegistry(session=object())
    registry.flags.execute_asset_selection_enabled = lambda: True
    registry.users = _Users()

    result = asyncio.run(registry._select_asset(390, {"change": {"asset": "eth"}}))

    assert result == {"ok": True, "asset": "ETH", "operation": "select_asset"}
