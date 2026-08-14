import logging
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.repositories.onboarding_repository import OnboardingRepository
from backend.schemas.onboarding_schema import OnboardingStatusResponse

logger = logging.getLogger("onboarding")

DEFAULT_FLOW = "default"

DEFAULT_STEPS: List[str] = [
    "profile",
    "asset",
    "market",
    "macro",
    "technical",
    "setup",
    "strategy",
    "bot",
]

PIPELINE_STEP = "bot"

STEP_FLAG_MAP = {
    "profile": "has_profile",
    "asset": "has_asset",
    "market": "has_market",
    "macro": "has_macro",
    "technical": "has_technical",
    "setup": "has_setup",
    "strategy": "has_strategy",
    "bot": "has_bot",
}

REQUIRED_COMPLETION_STEPS: List[str] = [
    "asset",
    "market",
    "macro",
    "technical",
    "setup",
    "strategy",
    "bot",
]

PHASE_ORDER: List[str] = ["profile", "analysis", "plan", "automation", "complete"]

class OnboardingService:
    def __init__(self, repository: OnboardingRepository):
        self.repository = repository

    async def _ensure_steps_for_user(self, user_id: int):
        existing_steps = await self.repository.get_user_steps(user_id, DEFAULT_FLOW)
        existing_keys = {s.step_key for s in existing_steps}

        missing = [s for s in DEFAULT_STEPS if s not in existing_keys]
        if missing:
            await self.repository.insert_steps(user_id, DEFAULT_FLOW, missing)
            logger.info(f"[Onboarding] Steps aangemaakt voor user_id={user_id}: {missing}")

    async def get_status_dict(self, user_id: int) -> OnboardingStatusResponse:
        await self._ensure_steps_for_user(user_id)
        
        steps = await self.repository.get_user_steps(user_id, DEFAULT_FLOW)
        completed = {s.step_key: s.completed for s in steps}
        inferred_completed = await self.repository.infer_completed_steps(user_id)
        inferred_state_getter = getattr(self.repository, "infer_onboarding_state", None)
        inferred_state = (
            await inferred_state_getter(user_id)
            if callable(inferred_state_getter)
            else {
                "active_asset": None,
                "has_profile": inferred_completed.get("profile", False),
                "has_asset": inferred_completed.get("asset", False),
                "has_market": inferred_completed.get("market", False),
                "has_macro": inferred_completed.get("macro", False),
                "has_technical": inferred_completed.get("technical", False),
                "has_setup": inferred_completed.get("setup", False),
                "has_strategy": inferred_completed.get("strategy", False),
                "has_bot": inferred_completed.get("bot", False),
                "has_exchange": inferred_completed.get("bot", False),
            }
        )
        missing_completed_steps = [
            step_key
            for step_key, is_completed in inferred_completed.items()
            if is_completed and not completed.get(step_key, False)
        ]

        if missing_completed_steps:
            await self.repository.mark_steps_completed(user_id, DEFAULT_FLOW, missing_completed_steps)
            completed.update({step_key: True for step_key in missing_completed_steps})
            logger.info(
                f"[Onboarding] Legacy completion backfill user_id={user_id} "
                f"steps={missing_completed_steps}"
            )

        pipeline_started = any(s.pipeline_started for s in steps if s.step_key == PIPELINE_STEP)

        status_kwargs = {
            STEP_FLAG_MAP[s]: completed.get(s, False)
            for s in DEFAULT_STEPS
        }
        phases_completed = self._build_phase_completion_map(status_kwargs, inferred_state)
        phases_unlocked = self._build_phase_unlock_map(phases_completed)
        phase_missing = self._build_phase_missing_map(status_kwargs, inferred_state)
        current_phase = self._resolve_current_phase(phases_completed)
        next_action = self._resolve_next_action(status_kwargs, inferred_state, current_phase)
        next_route = self._resolve_next_route(
            status_kwargs,
            inferred_state,
            current_phase,
            next_action,
        )

        status_kwargs["onboarding_complete"] = phases_completed["complete"]
        status_kwargs["pipeline_started"] = pipeline_started
        status_kwargs["active_asset"] = inferred_state.get("active_asset")
        status_kwargs["current_phase"] = current_phase
        status_kwargs["next_action"] = next_action
        status_kwargs["next_route"] = next_route
        status_kwargs["phases_completed"] = phases_completed
        status_kwargs["phases_unlocked"] = phases_unlocked
        status_kwargs["phase_missing"] = phase_missing

        logger.info(
            f"[Onboarding] Status user_id={user_id} "
            f"completed={completed} phases={phases_completed} "
            f"current_phase={current_phase} next_action={next_action} "
            f"pipeline_started={pipeline_started}"
        )

        return OnboardingStatusResponse(**status_kwargs)

    async def _kickstart_user_pipeline(self, user_id: int):
        await self._ensure_steps_for_user(user_id)
        
        steps = await self.repository.get_user_steps(user_id, DEFAULT_FLOW)
        
        strategy_step = next((s for s in steps if s.step_key == PIPELINE_STEP), None)
        if not strategy_step:
            logger.warning(f"[Onboarding] Geen strategy-step voor user_id={user_id}")
            return
            
        strategy_completed = strategy_step.completed
        pipeline_started = strategy_step.pipeline_started
        
        completed_map = {s.step_key: s.completed for s in steps}
        all_completed = all(completed_map.get(s, False) for s in REQUIRED_COMPLETION_STEPS)

        logger.info(
            f"[Onboarding] Pipeline check user_id={user_id} "
            f"strategy_completed={strategy_completed} "
            f"all_completed={all_completed} "
            f"pipeline_started={pipeline_started}"
        )

        if not all_completed or not strategy_completed or pipeline_started:
            return

        await self.repository.mark_pipeline_started(user_id, DEFAULT_FLOW, PIPELINE_STEP)

        # Import the Celery task lazily so simple API startup and status reads
        # do not pull the full onboarding pipeline graph into app boot.
        from backend.celery_task.onboarding_task import run_onboarding_pipeline

        run_onboarding_pipeline.delay(user_id)
        logger.info(f"[Onboarding] Pipeline gestart voor user_id={user_id}")

    async def complete_step(self, user_id: int, step_key: str) -> OnboardingStatusResponse:
        if step_key not in DEFAULT_STEPS:
            raise ValueError(f"Ongeldige step: {step_key}")

        await self.repository.mark_step_completed(user_id, DEFAULT_FLOW, step_key)
        logger.info(f"[Onboarding] Step '{step_key}' voltooid voor user_id={user_id}")
        
        await self._kickstart_user_pipeline(user_id)
        return await self.get_status_dict(user_id)

    async def finish_onboarding(self, user_id: int) -> OnboardingStatusResponse:
        await self._ensure_steps_for_user(user_id)
        status = await self.get_status_dict(user_id)

        if not status.onboarding_complete:
            logger.info(
                "[Onboarding] Finish genegeerd voor user_id=%s omdat de flow nog niet compleet is",
                user_id,
            )
            return status

        await self._kickstart_user_pipeline(user_id)
        return await self.get_status_dict(user_id)

    async def reset_onboarding(self, user_id: int) -> OnboardingStatusResponse:
        await self._ensure_steps_for_user(user_id)
        await self.repository.reset_flow(user_id, DEFAULT_FLOW)
        logger.info(f"[Onboarding] Reset uitgevoerd voor user_id={user_id}")
        return await self.get_status_dict(user_id)

    def _build_phase_completion_map(self, status_kwargs: Dict[str, bool], inferred_state: Dict[str, object]) -> Dict[str, bool]:
        profile_complete = bool(status_kwargs.get("has_profile"))
        analysis_complete = all(
            bool(status_kwargs.get(key))
            for key in ["has_asset", "has_market", "has_macro", "has_technical"]
        )
        plan_complete = bool(status_kwargs.get("has_setup")) and bool(status_kwargs.get("has_strategy"))
        # V1 onboarding finishes after one saved bot. Exchange connection can be added later.
        automation_complete = bool(status_kwargs.get("has_bot"))
        return {
            "profile": profile_complete,
            "analysis": analysis_complete,
            "plan": plan_complete,
            "automation": automation_complete,
            "complete": profile_complete and analysis_complete and plan_complete and automation_complete,
        }

    def _build_phase_unlock_map(self, phases_completed: Dict[str, bool]) -> Dict[str, bool]:
        return {
            "profile": True,
            "analysis": phases_completed.get("profile", False),
            "plan": phases_completed.get("analysis", False),
            "automation": phases_completed.get("plan", False),
            "complete": phases_completed.get("automation", False),
        }

    def _build_phase_missing_map(self, status_kwargs: Dict[str, bool], inferred_state: Dict[str, object]) -> Dict[str, List[str]]:
        return {
            "profile": [
                "profile_preferences"
            ] if not status_kwargs.get("has_profile") else [],
            "analysis": [
                token
                for token, done in [
                    ("asset", status_kwargs.get("has_asset")),
                    ("market_indicator", status_kwargs.get("has_market")),
                    ("macro_indicator", status_kwargs.get("has_macro")),
                    ("technical_indicator", status_kwargs.get("has_technical")),
                ]
                if not done
            ],
            "plan": [
                token
                for token, done in [
                    ("setup", status_kwargs.get("has_setup")),
                    ("strategy", status_kwargs.get("has_strategy")),
                ]
                if not done
            ],
            "automation": [
                token
                for token, done in [
                    ("exchange_connection", inferred_state.get("has_exchange")),
                    ("bot", status_kwargs.get("has_bot")),
                ]
                if not done
            ],
            "complete": [],
        }

    def _resolve_current_phase(self, phases_completed: Dict[str, bool]) -> str:
        for phase in PHASE_ORDER[:-1]:
            if not phases_completed.get(phase, False):
                return phase
        return "complete"

    def _resolve_next_action(
        self,
        status_kwargs: Dict[str, bool],
        inferred_state: Dict[str, object],
        current_phase: str,
    ) -> str:
        if current_phase == "profile":
            return "complete_profile"
        if current_phase == "analysis":
            if not status_kwargs.get("has_asset"):
                return "select_asset"
            if not status_kwargs.get("has_market"):
                return "add_market_indicator"
            if not status_kwargs.get("has_macro"):
                return "add_macro_indicator"
            if not status_kwargs.get("has_technical"):
                return "add_technical_indicator"
            return "review_analysis"
        if current_phase == "plan":
            if not status_kwargs.get("has_setup"):
                return "create_setup"
            if not status_kwargs.get("has_strategy"):
                return "create_strategy"
            return "confirm_plan"
        if current_phase == "automation":
            if not status_kwargs.get("has_bot"):
                return "create_bot"
            return "review_automation"
        return "go_to_analysis"

    def _resolve_next_route(
        self,
        status_kwargs: Dict[str, bool],
        inferred_state: Dict[str, object],
        current_phase: str,
        next_action: str,
    ) -> str:
        raw_symbol = inferred_state.get("active_asset")
        symbol = str(raw_symbol).upper() if raw_symbol else ""
        symbol_query = f"&symbol={symbol}" if symbol else ""

        if current_phase == "profile":
            return "/onboarding/profile"
        if next_action == "select_asset":
            return f"/onboarding/analysis?onboarding=1&step=analysis{symbol_query}"
        if next_action in {"add_market_indicator", "add_macro_indicator", "add_technical_indicator", "review_analysis"}:
            return f"/onboarding/analysis?onboarding=1&step=analysis{symbol_query}"
        if next_action in {"create_setup", "create_strategy", "confirm_plan"}:
            return f"/onboarding/plan?onboarding=1&step=plan{symbol_query}"
        if next_action in {"create_bot", "review_automation"}:
            action = "new_bot"
            return f"/bot?onboarding=1&step=bot&action={action}{symbol_query}"
        return f"/dashboard?symbol={symbol}" if symbol else "/dashboard"

async def mark_step_completed(user_id: int, step_key: str, session: AsyncSession) -> OnboardingStatusResponse:
    """
    Convenience function to mark an onboarding step as completed.
    Follows Clean Architecture by using the repository and service layers.
    """
    repo = OnboardingRepository(session)
    service = OnboardingService(repo)
    return await service.complete_step(user_id, step_key)
