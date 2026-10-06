from __future__ import annotations

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.schemas.finn_v2_evidence_schema import MarketSnapshotData


class MarketToolAdapter:
    def __init__(self, session):
        self.repository = MarketDataRepository(session)
        self.scores = ScoreRepository(session)

    async def execute(self, *, asset: str, user_id: int, **_kwargs):
        snapshot = await self.repository.get_latest_snapshot(asset)
        daily = await self.scores.fetch_daily_scores(user_id, asset.upper())
        if snapshot is None and daily is None:
            raise LookupError("source_unavailable")
        payload = {
            "symbol": snapshot.symbol if snapshot is not None else asset.upper(),
            "price": float(snapshot.price) if snapshot is not None and snapshot.price is not None else None,
            "change_24h": float(snapshot.change_24h) if snapshot is not None and snapshot.change_24h is not None else None,
            "volume": float(snapshot.volume) if snapshot is not None and snapshot.volume is not None else None,
            "source": "market_data_and_daily_scores" if snapshot is not None and daily is not None
                      else "market_data" if snapshot is not None else "daily_scores",
            "as_of": snapshot.timestamp if snapshot is not None else None,
            "saved_market_score": float(daily["market_score"]) if daily and daily.get("market_score") is not None else None,
            "score_report_date": daily.get("report_date") if daily else None,
        }
        return {
            "data": MarketSnapshotData(**payload),
            "summary": {"title": "market_snapshot", "symbol": payload["symbol"], "price": payload["price"],
                        "saved_market_score": payload["saved_market_score"]},
            "as_of": snapshot.timestamp if snapshot is not None else daily.get("report_date"),
            "source": payload["source"],
            "schema_name": "MarketSnapshotData",
            "entity_type": "market_snapshot",
            "asset": payload["symbol"],
        }
