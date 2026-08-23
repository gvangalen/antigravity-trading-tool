import pytest

from backend.domain.finn_v2_operation_registry import (
    FinnV2OperationRegistry,
    FinnV2OperationUnavailableError,
    OperationContract,
)


def test_registry_manifest_has_one_valid_contract_per_operation():
    registry = FinnV2OperationRegistry()
    contracts = registry.list()

    assert len({contract.operation_id for contract in contracts}) == len(contracts)
    for contract in contracts:
        assert not set(contract.required_scopes).intersection(contract.optional_scopes)
        if contract.supported:
            assert contract.mode


def test_supported_read_contracts_have_canonical_tools_and_no_model_call():
    registry = FinnV2OperationRegistry()

    setup = registry.require_supported("read_active_setup")
    assert setup.model_policy == "never"
    assert setup.tool_names == ("read_active_asset", "read_active_setup")


def test_unimplemented_operations_are_capability_gaps_not_executable():
    registry = FinnV2OperationRegistry()

    with pytest.raises(FinnV2OperationUnavailableError, match="create_strategy_execution_adapter_missing"):
        registry.require_supported("create_strategy")


def test_write_contract_requires_confirmable_proposal():
    with pytest.raises(ValueError, match="write_contract_incomplete"):
        OperationContract(
            operation_id="bad_write",
            version="test",
            domain="test",
            mode="CREATE_PROPOSAL",
            aliases=(),
        )
