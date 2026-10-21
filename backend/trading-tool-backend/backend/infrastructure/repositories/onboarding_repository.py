from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from backend.infrastructure.models import OnboardingStep, User
from typing import List
from datetime import datetime, timezone

from backend.services.trader_profile_service import (
    has_trader_profile,
    normalize_trader_profile_preferences,
)
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository

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
        state = await self.infer_onboarding_state(user_id)
        return {
            "profile": bool(state.get("has_profile")),
            "asset": bool(state.get("has_asset")),
            "market": bool(state.get("has_market")),
            "macro": bool(state.get("has_macro")),
            "technical": bool(state.get("has_technical")),
            "setup": bool(state.get("has_setup")),
            "strategy": bool(state.get("has_strategy")),
            "bot": bool(state.get("has_bot")),
        }

    async def infer_onboarding_state(self, user_id: int) -> dict:
        user = await self.db.get(User, user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        profile = normalize_trader_profile_preferences(preferences)
        onboarding_asset = str(
            preferences.get("onboarding_asset")
            or preferences.get("selected_asset")
            or ""
        ).strip().upper()

        async def _scalar(query: str, params: dict | None = None):
            result = await self.db.execute(text(query), params or {})
            return result.scalar()

        async def _has_rows(table_name: str) -> bool:
            query = text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE user_id = :user_id)")
            result = await self.db.execute(query, {"user_id": user_id})
            return bool(result.scalar())

        symbol_params = {"user_id": user_id, "symbol": onboarding_asset}
        configured_indicators = (
            await TechnicalDataRepository(self.db).get_configured_indicator_names(user_id, symbol=onboarding_asset)
            if onboarding_asset
            else {"market": [], "macro": [], "technical": []}
        )

        async def _has_scored_choice(category: str) -> bool:
            if not onboarding_asset:
                return False
            table = {
                "market": "market_data_indicators",
                "macro": "macro_data",
                "technical": "technical_indicators",
            }[category]
            name_column = "indicator" if category == "technical" else "name"
            interpretation_column = "uitleg" if category == "technical" else "interpretation"
            names = configured_indicators.get(category) or []
            if not names:
                return False
            for name in names:
                result = await self.db.execute(text(f"""
                    SELECT value, score,
                           {interpretation_column} AS interpretation
                    FROM {table}
                    WHERE user_id = :user_id
                      AND UPPER(COALESCE(symbol, '')) = :symbol
                      AND LOWER({name_column}) = :name
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
                """), {
                    "user_id": user_id,
                    "symbol": onboarding_asset,
                    "name": name.lower(),
                })
                row = result.first()
                # Completion is durable once the chosen indicator was scored.
                # Runtime source freshness is checked by the workspace and bot.
                if (row and row.value is not None and row.score is not None
                        and "fallback" not in str(row.interpretation or "").lower()):
                    return True
            return False

        has_setup = bool(
            await _scalar(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM setups
                    WHERE user_id = :user_id
                      AND UPPER(COALESCE(symbol, '')) = :symbol
                )
                """,
                symbol_params,
            )
        ) if onboarding_asset else False
        has_strategy = bool(
            await _scalar(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM strategies s
                    JOIN setups st ON st.id = s.setup_id
                    WHERE s.user_id = :user_id
                      AND UPPER(COALESCE(st.symbol, '')) = :symbol
                )
                """,
                symbol_params,
            )
        ) if onboarding_asset else False
        has_bot = bool(
            await _scalar(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM bot_configs b
                    LEFT JOIN strategies s ON s.id = b.strategy_id
                    LEFT JOIN setups st ON st.id = s.setup_id
                    WHERE b.user_id = :user_id
                      AND UPPER(COALESCE(b.symbol, st.symbol, '')) = :symbol
                )
                """,
                symbol_params,
            )
        ) if onboarding_asset else False
        has_exchange = bool(
            await _scalar(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM exchange_keys
                    WHERE user_id = :user_id
                      AND is_active = TRUE
                )
                """,
                {"user_id": user_id},
            )
        )

        return {
            "active_asset": onboarding_asset or None,
            "has_profile": has_trader_profile(profile),
            "has_asset": bool(onboarding_asset),
            "has_market": await _has_scored_choice("market"),
            "has_macro": await _has_scored_choice("macro"),
            "has_technical": await _has_scored_choice("technical"),
            "has_setup": has_setup,
            "has_strategy": has_strategy,
            "has_bot": has_bot,
            "has_exchange": has_exchange,
        }
