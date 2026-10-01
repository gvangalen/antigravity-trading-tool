import pytest

from backend.domain.finn_v2_tools import FINN_V2_EXTERNAL_ERROR_CODES, FINN_V2_TOOL_ORDER
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope, ToolRegistryEntry, ToolSelector


def test_tool_schema_accepts_compact_selector_and_registry_names():
    selector = ToolSelector(asset="btc", setup_id=9)
    entry = ToolRegistryEntry(name="read_profile", description="x")

    assert selector.asset == "btc"
    assert entry.name in FINN_V2_TOOL_ORDER


def test_tool_execution_envelope_preserves_known_error_codes():
    envelope = ToolExecutionEnvelope(
        tool_name="read_review_history",
        status="failed",
        success=False,
        error_codes=["review_history_unavailable"],
    )

    assert envelope.error_codes[0] in FINN_V2_EXTERNAL_ERROR_CODES


def test_tool_execution_envelope_assigns_the_canonical_output_scope():
    envelope = ToolExecutionEnvelope(
        tool_name="read_active_asset",
        status="completed",
        success=True,
        result={"symbol": "BTC"},
    )

    assert envelope.information_scope == "active_asset"


def test_saved_setup_inventory_has_a_valid_owner_scoped_evidence_envelope():
    envelope = ToolExecutionEnvelope(
        tool_name="read_saved_setup_inventory",
        status="completed",
        success=True,
        schema_name="SavedSetupInventoryData",
        result={"setups": [{"setup_id": 9, "name": "BTC Full Base"}], "setup_count": 1},
    )

    assert envelope.information_scope == "active_setup"
    assert envelope.result.setup_count == 1


def test_tool_execution_envelope_rejects_a_mismatched_output_scope():
    with pytest.raises(ValueError, match="information_scope"):
        ToolExecutionEnvelope(
            tool_name="read_active_asset",
            status="completed",
            success=True,
            result={"symbol": "BTC"},
            information_scope="profile",
        )
