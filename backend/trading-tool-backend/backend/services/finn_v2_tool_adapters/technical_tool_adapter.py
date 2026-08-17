from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import TechnicalSnapshotData, TechnicalSnapshotItem
from backend.services.technical_data_service import TechnicalDataService


class TechnicalToolAdapter:
    def __init__(self, session):
        self.service = TechnicalDataService(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        rows = await self.service.get_day_indicators(user_id, symbol=asset)
        if not rows:
            raise LookupError("source_unavailable")
        payload = [
            TechnicalSnapshotItem(
                indicator=row.indicator,
                value=float(row.value or 0),
                score=float(row.score or 0),
                advice=row.advies,
                explanation=row.uitleg,
                timestamp=row.timestamp,
            )
            for row in rows
        ]
        latest = max((row.timestamp for row in rows if row.timestamp), default=None)
        return {
            "data": TechnicalSnapshotData(symbol=asset, items=payload),
            "summary": {"title": "technical_snapshot", "symbol": asset, "count": len(payload)},
            "as_of": latest,
            "source": "technical_indicators",
            "schema_name": "TechnicalSnapshotData",
            "entity_type": "technical_snapshot",
            "asset": asset,
        }
