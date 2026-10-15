from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.portfolio_overview_service import project_portfolio
from backend.services.live_portfolio_allocation_service import read_allocations, read_live_account


class PortfolioToolAdapter:
    def __init__(self, session):
        self.session = session
        self.repository = BotRepository(session)

    async def execute(self, *, user_id: int, asset: str | None = None, environment: str | None = None, **_kwargs):
        payload = await self.repository.get_portfolio_intelligence_context(user_id)
        requested_asset = str(asset or "").strip().upper() or None
        if environment == "live":
            account = await read_live_account(self.session, user_id)
            payload["live_account"] = account
            payload["live_allocations"] = (
                await read_allocations(self.session, user_id, account["exchange_name"])
                if account else {}
            )
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
