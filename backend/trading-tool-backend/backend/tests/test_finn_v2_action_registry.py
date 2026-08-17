from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry


def test_action_registry_contains_safe_block8_adapters():
    registry = FinnV2ActionAdapterRegistry(session=object())

    assert registry.get("update_indicator_configuration") is not None
    assert registry.get("activate_paper_bot") is not None
    assert registry.get("activate_live_bot") is not None
    assert registry.get("manual_order") is None
