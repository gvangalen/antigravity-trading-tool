from backend.services.finn_v2_target_asset_resolver import FinnV2TargetAssetResolver


def test_explicit_asset_wins_over_stale_workspace_and_lineage():
    result = FinnV2TargetAssetResolver().resolve(
        explicit_target_asset="BTC",
        verified_context={"last_verified_context": {"target_asset": "ETH"}},
        operation_state={"target_entities": {"asset": "ADA"}},
        workspace_asset="AAPL",
    )

    assert result.target_asset == "BTC"
    assert result.source == "explicit_message"


def test_persisted_guided_target_wins_over_workspace_context():
    result = FinnV2TargetAssetResolver().resolve(
        operation_state={"target_entities": {"asset": "ADA"}},
        workspace_asset="BTC",
    )

    assert result.target_asset == "ADA"
    assert result.source == "persisted_operation"


def test_persisted_guided_target_wins_over_previous_conversation_asset():
    result = FinnV2TargetAssetResolver().resolve(
        verified_context={"last_verified_context": {"target_asset": "BTC"}},
        operation_state={"collected_inputs": {"symbol": "SOL"}},
        workspace_asset="AAPL",
    )

    assert result.target_asset == "SOL"
    assert result.source == "persisted_operation"


def test_persisted_guided_target_cannot_be_overwritten_by_selector_projection():
    result = FinnV2TargetAssetResolver().resolve(
        explicit_target_asset=None,
        selector_target_asset="ETH",
        verified_context={"last_verified_context": {"target_asset": "BTC"}},
        operation_state={"target_entities": {"asset": "SOL"}},
        workspace_asset="AAPL",
    )

    assert result.target_asset == "SOL"
    assert result.source == "persisted_operation"
