from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_eval_repository import FinnV2EvalRepository
from backend.infrastructure.repositories.finn_v2_release_gate_repository import FinnV2ReleaseGateRepository
from backend.infrastructure.repositories.finn_v2_shadow_comparison_repository import FinnV2ShadowComparisonRepository
from backend.schemas.finn_v2_cutover_schema import FinnV2RuntimeStatus
from backend.services.finn_v2_flag_service import FinnV2FlagService


class FinnV2CutoverService:
    def __init__(self, session: AsyncSession, *, flag_service: FinnV2FlagService | None = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.evals = FinnV2EvalRepository(session)
        self.gates = FinnV2ReleaseGateRepository(session)
        self.shadows = FinnV2ShadowComparisonRepository(session)

    async def runtime_status(self) -> FinnV2RuntimeStatus:
        return FinnV2RuntimeStatus(
            runtime_mode=self.flags.runtime_mode(),
            shadow_compare_enabled=self.flags.is_shadow_compare_enabled(),
            release_gates_enabled=self.flags.is_release_gates_enabled(),
            golden_evals_enabled=self.flags.is_golden_evals_enabled(),
            visible_proposals_enabled=self.flags.is_visible_proposals_enabled(),
            confirmation_routes_enabled=self.flags.is_confirmation_routes_enabled(),
            action_execution_enabled=self.flags.is_action_execution_enabled(),
            canary_user_ids=sorted(list(self.flags.canary_user_ids())),
            canary_percent=self.flags.canary_percent(),
            canary_allowed_modes=sorted(list(self.flags.canary_allowed_modes())),
            v1_fallback_enabled=self.flags.is_v1_fallback_enabled(),
            post_cutover_kill_switch=self.flags.is_post_cutover_kill_switch_enabled(),
        )

    async def operator_snapshot(self) -> dict:
        latest_eval = await self.evals.latest_run()
        latest_gate = await self.gates.latest()
        latest_shadow = await self.shadows.latest()
        return {
            "runtime_status": (await self.runtime_status()).dict(),
            "latest_eval_run": latest_eval.id if latest_eval is not None else None,
            "latest_release_gate": latest_gate.id if latest_gate is not None else None,
            "latest_shadow_comparison": latest_shadow.id if latest_shadow is not None else None,
        }

