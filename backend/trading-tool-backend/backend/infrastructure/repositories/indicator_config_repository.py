from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.infrastructure.models import MarketIndicatorRule, MacroIndicatorRule, TechnicalIndicatorRule

MODEL_MAP = {
    "market": MarketIndicatorRule,
    "macro": MacroIndicatorRule,
    "technical": TechnicalIndicatorRule,
}

class IndicatorConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def get_model(self, category: str):
        if category not in MODEL_MAP:
            raise ValueError(f"Invalid category: {category}")
        return MODEL_MAP[category]

    async def get_system_indicator_rules(self, category: str, indicator: str):
        """Return read-only system bucket definitions, never user preferences."""
        model = self.get_model(category)
        stmt = select(model).where(
            model.indicator == indicator,
            model.user_id.is_(None)
        ).order_by(model.range_min.asc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
