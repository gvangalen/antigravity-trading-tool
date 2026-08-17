from __future__ import annotations

import random
from typing import Optional

from backend.schemas.finn_v2_cutover_schema import FinnV2RuntimeSelection
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


class FinnV2RuntimeSelectorService:
    def __init__(self, *, flag_service: Optional[FinnV2FlagService] = None):
        self.flags = flag_service or FinnV2FlagService()
        self.analysis = FinnV2RequestAnalysisService()

    def select(self, *, user_id: int, message: str, surface: str, workspace_hints: Optional[dict] = None, client_context: Optional[dict] = None) -> FinnV2RuntimeSelection:
        mode = self.flags.runtime_mode()
        analysis = self.analysis.analyze(message=message, workspace_hints=workspace_hints or {}, client_context=client_context or {})
        interaction_mode = analysis.interaction_mode
        visible_allowed = False
        shadow_enabled = mode in {"v1_primary_v2_shadow", "v2_canary_readonly", "v2_primary_with_v1_fallback", "v2_only"}
        fallback_allowed = self.flags.is_v1_fallback_enabled()
        reasons: list[str] = []
        selected_runtime = "v1"
        if mode == "v1_primary":
            return FinnV2RuntimeSelection(runtime_mode=mode, selected_runtime="v1", interaction_mode=interaction_mode, shadow_enabled=False, fallback_allowed=fallback_allowed)
        if mode == "v1_primary_v2_shadow":
            return FinnV2RuntimeSelection(runtime_mode=mode, selected_runtime="v1", interaction_mode=interaction_mode, visible_allowed=False, shadow_enabled=True, fallback_allowed=fallback_allowed)
        if mode == "v2_canary_readonly":
            allowed_user = self.flags.is_canary_user(user_id) or self._sample_percent(user_id)
            allowed_mode = interaction_mode in self.flags.canary_allowed_modes() and interaction_mode not in {"PROPOSAL", "ACTION"}
            visible_allowed = allowed_user and allowed_mode
            selected_runtime = "v2" if visible_allowed else "v1"
            if not allowed_user:
                reasons.append("canary_user_not_allowed")
            if not allowed_mode:
                reasons.append("canary_mode_not_allowed")
        elif mode == "v2_primary_with_v1_fallback":
            visible_allowed = True
            selected_runtime = "v2"
        elif mode == "v2_only":
            visible_allowed = True
            selected_runtime = "v2"
        return FinnV2RuntimeSelection(
            runtime_mode=mode,
            selected_runtime=selected_runtime,
            interaction_mode=interaction_mode,
            visible_allowed=visible_allowed,
            shadow_enabled=shadow_enabled,
            fallback_allowed=fallback_allowed,
            reason_codes=reasons,
        )

    def _sample_percent(self, user_id: int) -> bool:
        percent = self.flags.canary_percent()
        if percent <= 0:
            return False
        random.seed(str(user_id))
        return random.randint(1, 100) <= percent

