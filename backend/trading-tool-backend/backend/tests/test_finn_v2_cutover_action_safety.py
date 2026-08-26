from backend.services.finn_v2_runtime_selector_service import FinnV2RuntimeSelectorService


class _Flags:
    def runtime_mode(self):
        return "v2_only"

    def is_v1_fallback_enabled(self):
        return False


def test_v2_only_runtime_defers_action_mode_to_the_durable_selector_without_v1_fallback():
    service = FinnV2RuntimeSelectorService(flag_service=_Flags())

    result = service.select(user_id=7, message="Voer dit nu uit", surface="assistant_chat")

    assert result.selected_runtime == "v2"
    assert result.visible_allowed is True
    assert result.fallback_allowed is False
    assert result.interaction_mode is None
