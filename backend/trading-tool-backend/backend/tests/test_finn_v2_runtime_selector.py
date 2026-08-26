from backend.services.finn_v2_runtime_selector_service import FinnV2RuntimeSelectorService


class _Flags:
    def runtime_mode(self):
        return "v2_only"

    def is_v1_fallback_enabled(self):
        return False


def test_runtime_selector_selects_v2_only_for_authenticated_requests():
    service = FinnV2RuntimeSelectorService(flag_service=_Flags())
    result = service.select(user_id=7, message="Wat is mijn BTC setup?", surface="assistant_chat")

    assert result.selected_runtime == "v2"
    assert result.visible_allowed is True
    assert result.shadow_enabled is False
    assert result.fallback_allowed is False
    assert result.operation_id is None
    assert result.selector_source is None
    assert result.skip_canonical_context_graph is False
