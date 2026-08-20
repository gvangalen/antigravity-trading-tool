from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import Watchlist


class WatchlistToolAdapter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, *, user_id: int, asset: str | None = None) -> dict:
        stmt = (
            select(Watchlist)
            .where(Watchlist.user_id == user_id)
            .order_by(asc(Watchlist.created_at), asc(Watchlist.id))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        symbols = [str(row.symbol or "").upper() for row in rows if row.symbol]
        target_asset = str(asset or "").upper() or None
        return {
            "data": {
                "target_asset": target_asset,
                "contains_target_asset": bool(target_asset and target_asset in symbols),
                "symbols": [{"symbol": symbol, "present": True} for symbol in symbols],
            },
            "summary": {
                "target_asset": target_asset,
                "contains_target_asset": bool(target_asset and target_asset in symbols),
                "symbol_count": len(symbols),
            },
            "source": "internal",
            "schema_name": "WatchlistData",
            "entity_type": "watchlist",
            "entity_id": str(user_id),
            "asset": target_asset,
            "resolution_source": "user_watchlist",
        }
