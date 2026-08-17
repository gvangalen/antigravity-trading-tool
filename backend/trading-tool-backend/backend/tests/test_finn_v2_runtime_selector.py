from types import SimpleNamespace

from backend.services.finn_v2_runtime_selector_service import FinnV2RuntimeSelectorService


class _Flags:
    def runtime_mode(self):
        return "v2_canary_readonly"

    def is_canary_user(self, user_id: int):
        return user_id == 7

    def canary_percent(self):
        return 0

    def canary_allowed_modes(self):
        return {"FACT", "EVALUATION"}

    def is_v1_fallback_enabled(self):
        return True


def test_runtime_selector_allows_visible_v2_for_canary_readonly_fact_mode():
    service = FinnV2RuntimeSelectorService(flag_service=_Flags())
    service.analysis.analyze = lambda **kwargs: SimpleNamespace(interaction_mode="FACT")

    result = service.select(user_id=7, message="Wat is mijn BTC setup?", surface="assistant_chat")

    assert result.selected_runtime == "v2"
    assert result.visible_allowed is True
    assert result.shadow_enabled is True
