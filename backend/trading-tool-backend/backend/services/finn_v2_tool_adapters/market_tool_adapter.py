from __future__ import annotations

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.schemas.finn_v2_evidence_schema import MarketSnapshotData


class MarketToolAdapter:
    def __init__(self, session):
        self.repository = MarketDataRepository(session)

    async def execute(self, *, asset: str, user_id: int, market_id: int | None = None,
                      quote_currency: str | None = None, **_kwargs):
        snapshot = (await self.repository.get_latest_exact_market_snapshot(market_id)
                    if market_id is not None else
                    await self.repository.get_latest_quoted_snapshot(asset))
        if snapshot is None:
            raise LookupError("source_unavailable")
        if market_id is not None and (
            str(snapshot.symbol or "").upper() != asset or
            str(snapshot.quote_currency or "").upper() != quote_currency
        ):
            raise LookupError("exact_market_source_mismatch")
        # Receipt/update time does not establish the age of the provider's
        # price. Missing source provenance must stay unknown to the coach.
        observed_at = getattr(snapshot, "source_observed_at", None)
        payload = {
            "symbol": snapshot.symbol,
            "market_id": market_id,
            "pair": f"{asset}/{quote_currency}" if market_id is not None else None,
            "price": float(snapshot.price) if snapshot.price is not None else None,
            "quote_currency": (
                str(snapshot.quote_currency).upper()
                if getattr(snapshot, "quote_currency", None) and observed_at else None
            ),
            "price_provider": getattr(snapshot, "price_provider", None) if observed_at else None,
            "change_24h": float(snapshot.change_24h) if snapshot.change_24h is not None else None,
            "volume": float(snapshot.volume) if snapshot.volume is not None else None,
            "source": "market_data",
            "as_of": observed_at,
            "source_observed_at": observed_at,
        }
        return {
            "data": MarketSnapshotData(**payload),
            "summary": {"title": "market_snapshot", "symbol": payload["symbol"], "price": payload["price"]},
            "as_of": observed_at,
            "source": payload["source"],
            "schema_name": "MarketSnapshotData",
            "entity_type": "market_snapshot",
            "asset": payload["symbol"],
        }
