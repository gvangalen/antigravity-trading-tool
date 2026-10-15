from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.portfolio_overview_service import project_portfolio


class PortfolioToolAdapter:
    def __init__(self, session):
        self.repository = BotRepository(session)

    async def execute(self, *, user_id: int, asset: str | None = None, environment: str | None = None, **_kwargs):
        payload = await self.repository.get_portfolio_intelligence_context(user_id)
        requested_asset = str(asset or "").strip().upper() or None
        data = project_portfolio(payload, asset=asset, environment=environment)
        summary = {
            "title": "portfolio",
            "total_equity": data.global_.total_equity,
            "bot_count": len(data.bots),
            "requested_asset": requested_asset,
        }
        return {
            "data": data,
            "summary": summary,
            "as_of": data.valuation_as_of,
            "source": "bot_portfolios",
            "schema_name": "PortfolioData",
            "entity_type": "portfolio",
            "asset": requested_asset,
        }
