from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import TradingMarket, Watchlist


class WatchlistToolAdapter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, *, user_id: int, asset: str | None = None) -> dict:
        stmt = (
            select(Watchlist, TradingMarket)
            .outerjoin(TradingMarket, Watchlist.market_id == TradingMarket.id)
            .where(Watchlist.user_id == user_id)
            .order_by(asc(Watchlist.created_at), asc(Watchlist.id))
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        symbols = []
        for row, market in rows:
            symbol = str(row.symbol or "").upper()
            if not symbol:
                continue
            quote = str(market.quote_currency or "").upper() if market else None
            symbols.append({
                "symbol": symbol,
                "market_id": row.market_id,
                "quote_currency": quote,
                "pair": f"{symbol}/{quote}" if quote else None,
                "present": True,
            })
        target_asset = str(asset or "").upper() or None
        return {
            "data": {
                "target_asset": target_asset,
                "contains_target_asset": bool(target_asset and any(item["symbol"] == target_asset for item in symbols)),
                "symbols": symbols,
            },
            "summary": {
                "target_asset": target_asset,
                "contains_target_asset": bool(target_asset and any(item["symbol"] == target_asset for item in symbols)),
                "symbol_count": len(symbols),
            },
            "source": "internal",
            "schema_name": "WatchlistData",
            "entity_type": "watchlist",
            "entity_id": str(user_id),
            "asset": target_asset,
            "resolution_source": "user_watchlist",
        }
