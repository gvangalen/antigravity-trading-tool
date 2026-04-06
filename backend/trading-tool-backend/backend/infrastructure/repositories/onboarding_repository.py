from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.infrastructure.models import OnboardingStep
from typing import List
from datetime import datetime, timezone

class OnboardingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_steps(self, user_id: int, flow: str) -> List[OnboardingStep]:
        stmt = select(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def insert_steps(self, user_id: int, flow: str, step_keys: List[str]):
        if not step_keys:
            return
        
        instances = [
            OnboardingStep(
                user_id=user_id,
                flow=flow,
                step_key=s,
                completed=False,
                pipeline_started=False
            ) for s in step_keys
        ]
        self.db.add_all(instances)
        await self.db.commit()

    async def mark_step_completed(self, user_id: int, flow: str, step_key: str):
        now = datetime.utcnow()
        stmt = update(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow,
            OnboardingStep.step_key == step_key
        ).values(completed=True, completed_at=now)
        await self.db.execute(stmt)
        await self.db.commit()

    async def mark_flow_completed(self, user_id: int, flow: str):
        now = datetime.utcnow()
        stmt = update(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow,
        ).values(completed=True, completed_at=now)
        await self.db.execute(stmt)
        await self.db.commit()

    async def reset_flow(self, user_id: int, flow: str):
        stmt = update(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow,
        ).values(completed=False, completed_at=None, pipeline_started=False)
        await self.db.execute(stmt)
        await self.db.commit()

    async def mark_pipeline_started(self, user_id: int, flow: str, step_key: str):
        stmt = update(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow,
            OnboardingStep.step_key == step_key
        ).values(pipeline_started=True)
        await self.db.execute(stmt)
        await self.db.commit()
