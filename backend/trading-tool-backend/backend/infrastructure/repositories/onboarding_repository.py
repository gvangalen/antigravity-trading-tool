from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from backend.infrastructure.models import OnboardingStep, User
from typing import List
from datetime import datetime, timezone

from backend.services.trader_profile_service import (
    has_trader_profile,
    normalize_trader_profile_preferences,
)


LEGACY_USER_INDICATOR_CONFIG_COLUMNS = {
    "id",
    "user_id",
    "indicator",
    "category",
    "created_at",
}


class OnboardingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._user_config_columns_cache: set[str] | None = None

    async def _get_user_config_columns(self) -> set[str]:
        if self._user_config_columns_cache is not None:
            return self._user_config_columns_cache

        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'user_indicator_configs'
                    """
                )
            )
            columns = {str(column_name) for column_name in result.scalars().all()}
        except Exception:
            columns = set()

        if not columns:
            columns = set(LEGACY_USER_INDICATOR_CONFIG_COLUMNS)

        self._user_config_columns_cache = columns
        return columns

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

        async def _has_indicator_config(category: str) -> bool:
            if not onboarding_asset:
                return False

            columns = await self._get_user_config_columns()
            conditions = ["user_id = :user_id"]
            params = {"user_id": user_id}

            if "category" in columns:
                conditions.append("category = :category")
                params["category"] = category

            if "enabled" in columns:
                conditions.append("enabled = TRUE")

            if "symbol" in columns:
                conditions.append("UPPER(COALESCE(symbol, '')) = :symbol")
                params["symbol"] = onboarding_asset
            else:
                return False

            return bool(
                await _scalar(
                    f"""
                    SELECT EXISTS (
                        SELECT 1
                        FROM user_indicator_configs
                        WHERE {' AND '.join(conditions)}
                    )
                    """,
                    params,
                )
            )

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
            "has_market": await _has_indicator_config("market"),
            "has_macro": await _has_indicator_config("macro"),
            "has_technical": await _has_indicator_config("technical"),
            "has_setup": has_setup,
            "has_strategy": has_strategy,
            "has_bot": has_bot,
            "has_exchange": has_exchange,
        }
