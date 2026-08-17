from __future__ import annotations

from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


class IndicatorToolAdapter:
    def __init__(self, session):
        self.repository = TechnicalDataRepository(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        configs = await self.repository.get_user_configs(user_id, category="technical", symbol=asset)
        serialized = [
            {
                "indicator": row.indicator,
                "category": row.category,
                "priority": row.priority,
                "enabled": row.enabled,
                "symbol": row.symbol,
                "asset_class": row.asset_class,
            }
            for row in configs
        ]
        return {
            "data": {"symbol": asset, "technical": serialized},
            "summary": {"title": "indicator_configuration", "symbol": asset, "technical_count": len(serialized)},
            "as_of": None,
        }

