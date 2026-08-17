from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository


class PortfolioToolAdapter:
    def __init__(self, session):
        self.repository = BotRepository(session)

    async def execute(self, *, user_id: int, **_kwargs):
        payload = await self.repository.get_portfolio_intelligence_context(user_id)
        compact_bots = [
            {
                "bot_id": row.get("bot_id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "equity": row.get("equity"),
                "is_active": row.get("is_active"),
                "is_live": row.get("is_live"),
            }
            for row in payload.get("bots", [])
        ]
        summary = {
            "title": "portfolio",
            "total_equity": payload.get("global", {}).get("total_equity"),
            "bot_count": len(compact_bots),
        }
        return {"data": {"global": payload.get("global", {}), "bots": compact_bots}, "summary": summary, "as_of": None}

