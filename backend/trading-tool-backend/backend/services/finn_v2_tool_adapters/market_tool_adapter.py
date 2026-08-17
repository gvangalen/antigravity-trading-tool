from __future__ import annotations

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.schemas.finn_v2_evidence_schema import MarketSnapshotData


class MarketToolAdapter:
    def __init__(self, session):
        self.repository = MarketDataRepository(session)

    async def execute(self, *, asset: str, **_kwargs):
        snapshot = await self.repository.get_latest_snapshot(asset)
        if snapshot is None:
            raise LookupError("source_unavailable")
        payload = {
            "symbol": snapshot.symbol,
            "price": float(snapshot.price or 0),
            "change_24h": float(snapshot.change_24h or 0),
            "volume": float(snapshot.volume or 0),
            "source": "market_data",
            "as_of": snapshot.timestamp,
        }
        return {
            "data": MarketSnapshotData(**payload),
            "summary": {"title": "market_snapshot", "symbol": snapshot.symbol, "price": payload["price"]},
            "as_of": snapshot.timestamp,
            "source": "market_data",
            "schema_name": "MarketSnapshotData",
            "entity_type": "market_snapshot",
            "asset": snapshot.symbol,
        }
