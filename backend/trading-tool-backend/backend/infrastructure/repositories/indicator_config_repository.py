from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
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

    async def get_indicator_rules(self, category: str, indicator: str, user_id: int):
        """
        Returnt user overrides, of valt terug op de template (user_id IS NULL).
        Returnt tuple (rules_list, is_user_override).
        """
        model = self.get_model(category)
        
        # 1. User specific rules
        stmt = select(model).where(
            model.indicator == indicator, 
            model.user_id == user_id
        ).order_by(model.range_min.asc())
        
        res = await self.db.execute(stmt)
        rules = res.scalars().all()
        
        if rules:
            return list(rules), True

        # 2. Template fallback
        stmt = select(model).where(
            model.indicator == indicator, 
            model.user_id.is_(None)
        ).order_by(model.range_min.asc())
        
        res = await self.db.execute(stmt)
        rules = res.scalars().all()
        
        return list(rules), False

    async def delete_user_rules(self, category: str, indicator: str, user_id: int):
        """
        Verwijdert user overrides voor een specifieke indicator.
        """
        model = self.get_model(category)
        stmt = delete(model).where(
            model.indicator == indicator,
            model.user_id == user_id
        )
        await self.db.execute(stmt)

    async def insert_user_rules(self, category: str, indicator: str, user_id: int, rules: list, score_mode: str, weight: float):
        """
        Voegt nieuwe bucket rules toe voor de gebruiker.
        """
        model = self.get_model(category)
        instances = []
        for r in rules:
            instances.append(model(
                indicator=indicator,
                range_min=r["range_min"],
                range_max=r["range_max"],
                score=r["score"],
                trend=r.get("trend"),
                interpretation=r.get("interpretation"),
                action=r.get("action"),
                score_mode=score_mode,
                weight=weight,
                is_active=True,
                user_id=user_id
            ))
        self.db.add_all(instances)

    async def update_settings(self, category: str, indicator: str, user_id: int, score_mode: str, weight: float):
        """
        Hiermee pas je de instellingen aan van actieve user rules.
        (Alleen bruikbaar als de user al overrides heeft)
        """
        model = self.get_model(category)
        stmt = update(model).where(
            model.indicator == indicator,
            model.user_id == user_id
        ).values(score_mode=score_mode, weight=weight)
        
        await self.db.execute(stmt)
