from __future__ import annotations

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
        return FinnV2RuntimeSelection(
            runtime_mode=mode,
            selected_runtime="v2",
            interaction_mode=interaction_mode,
            visible_allowed=True,
            shadow_enabled=False,
            fallback_allowed=self.flags.is_v1_fallback_enabled(),
            reason_codes=[],
        )
