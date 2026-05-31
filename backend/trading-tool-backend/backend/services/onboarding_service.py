import logging
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.repositories.onboarding_repository import OnboardingRepository
from backend.schemas.onboarding_schema import OnboardingStatusResponse

logger = logging.getLogger("onboarding")

DEFAULT_FLOW = "default"

DEFAULT_STEPS: List[str] = [
    "market",
    "macro",
    "technical",
    "setup",
    "strategy",
]

PIPELINE_STEP = "strategy"

STEP_FLAG_MAP = {
    "market": "has_market",
    "macro": "has_macro",
    "technical": "has_technical",
    "setup": "has_setup",
    "strategy": "has_strategy",
}

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
        pipeline_started = any(s.pipeline_started for s in steps if s.step_key == PIPELINE_STEP)

        status_kwargs = {
            STEP_FLAG_MAP[s]: completed.get(s, False)
            for s in DEFAULT_STEPS
        }
        status_kwargs["onboarding_complete"] = all(completed.get(s, False) for s in DEFAULT_STEPS)
        status_kwargs["pipeline_started"] = pipeline_started

        logger.info(
            f"[Onboarding] Status user_id={user_id} "
            f"completed={completed} pipeline_started={pipeline_started}"
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
        all_completed = all(completed_map.get(s, False) for s in DEFAULT_STEPS)

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
        await self.repository.mark_flow_completed(user_id, DEFAULT_FLOW)
        
        await self._kickstart_user_pipeline(user_id)
        return await self.get_status_dict(user_id)

    async def reset_onboarding(self, user_id: int) -> OnboardingStatusResponse:
        await self._ensure_steps_for_user(user_id)
        await self.repository.reset_flow(user_id, DEFAULT_FLOW)
        logger.info(f"[Onboarding] Reset uitgevoerd voor user_id={user_id}")
        return await self.get_status_dict(user_id)

async def mark_step_completed(user_id: int, step_key: str, session: AsyncSession) -> OnboardingStatusResponse:
    """
    Convenience function to mark an onboarding step as completed.
    Follows Clean Architecture by using the repository and service layers.
    """
    repo = OnboardingRepository(session)
    service = OnboardingService(repo)
    return await service.complete_step(user_id, step_key)
