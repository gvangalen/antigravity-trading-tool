from __future__ import annotations

from typing import Optional

from backend.schemas.finn_v2_cutover_schema import FinnV2RuntimeSelection
from backend.services.finn_v2_flag_service import FinnV2FlagService


class FinnV2RuntimeSelectorService:
    def __init__(self, *, flag_service: Optional[FinnV2FlagService] = None):
        self.flags = flag_service or FinnV2FlagService()

    def select(self, *, user_id: int, message: str, surface: str, workspace_hints: Optional[dict] = None, client_context: Optional[dict] = None) -> FinnV2RuntimeSelection:
        mode = self.flags.runtime_mode()
        # Runtime eligibility is intentionally independent from semantic
        # operation selection.  The durable run owns the latter so a selector
        # provider failure still has one observable run and dispatch record.
        # Do not inspect free-form message text here: that would create a
        # second operation router ahead of the model-first lifecycle.
        return FinnV2RuntimeSelection(
            runtime_mode=mode,
            selected_runtime="v2",
            interaction_mode=None,
            operation_id=None,
            selector_source=None,
            reasoning_required=True,
            # This is populated from the selected immutable contract inside
            # the lifecycle, never inferred at the HTTP boundary.
            skip_canonical_context_graph=False,
            visible_allowed=True,
            shadow_enabled=False,
            fallback_allowed=self.flags.is_v1_fallback_enabled(),
            reason_codes=[],
        )
