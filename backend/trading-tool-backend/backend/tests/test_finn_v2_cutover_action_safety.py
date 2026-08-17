from types import SimpleNamespace

from backend.services.finn_v2_runtime_selector_service import FinnV2RuntimeSelectorService


class _Flags:
    def runtime_mode(self):
        return "v2_canary_readonly"

    def is_canary_user(self, user_id: int):
        return True

    def canary_percent(self):
        return 0

    def canary_allowed_modes(self):
        return {"FACT", "EVALUATION", "PROPOSAL", "ACTION"}

    def is_v1_fallback_enabled(self):
        return True


def test_canary_readonly_never_exposes_action_mode_visibly():
    service = FinnV2RuntimeSelectorService(flag_service=_Flags())
    service.analysis.analyze = lambda **kwargs: SimpleNamespace(interaction_mode="ACTION")

    result = service.select(user_id=7, message="Voer dit nu uit", surface="assistant_chat")

    assert result.selected_runtime == "v1"
    assert result.visible_allowed is False
    assert "canary_mode_not_allowed" in result.reason_codes
