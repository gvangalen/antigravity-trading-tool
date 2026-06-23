from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from backend.infrastructure.models import OnboardingStep, User
from typing import List
from datetime import datetime, timezone

from backend.services.trader_profile_service import (
    has_trader_profile,
    normalize_trader_profile_preferences,
)

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

    async def mark_steps_completed(self, user_id: int, flow: str, step_keys: List[str]):
        if not step_keys:
            return

        now = datetime.utcnow()
        stmt = update(OnboardingStep).where(
            OnboardingStep.user_id == user_id,
            OnboardingStep.flow == flow,
            OnboardingStep.step_key.in_(step_keys),
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

    async def infer_completed_steps(self, user_id: int) -> dict:
        user = await self.db.get(User, user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        profile = normalize_trader_profile_preferences(preferences)

        async def _has_rows(table_name: str) -> bool:
            query = text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE user_id = :user_id)")
            result = await self.db.execute(query, {"user_id": user_id})
            return bool(result.scalar())

        return {
            "profile": has_trader_profile(profile),
            "market": await _has_rows("market_data_indicators"),
            "macro": await _has_rows("macro_data"),
            "technical": await _has_rows("technical_indicators"),
            "setup": await _has_rows("setups"),
            "strategy": await _has_rows("strategies"),
        }
