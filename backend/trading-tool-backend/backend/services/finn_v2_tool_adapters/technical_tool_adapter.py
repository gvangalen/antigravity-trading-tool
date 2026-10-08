from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import TechnicalSnapshotData, TechnicalSnapshotItem
from backend.services.technical_data_service import TechnicalDataService
from backend.utils.scoring_utils import score_source_is_fresh


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
                value=float(row.value) if row.value is not None else None,
                score=(float(row.score) if row.score is not None and
                       score_source_is_fresh("technical", row.indicator, getattr(row, "source_observed_at", None), symbol=asset)
                       else None),
                source_status=("fresh" if score_source_is_fresh(
                    "technical", row.indicator, getattr(row, "source_observed_at", None), symbol=asset
                ) else "stale" if getattr(row, "source_observed_at", None) else "unknown"),
                advice=row.advies,
                explanation=row.uitleg,
                timestamp=row.timestamp,
                source_observed_at=getattr(row, "source_observed_at", None),
            )
            for row in rows
        ]
        latest = max((getattr(row, "source_observed_at", None) for row in rows
                      if getattr(row, "source_observed_at", None)), default=None)
        # The scoring pipeline permits a closed crypto candle for 36 hours.
        # A generic six-hour tool TTL must not call the same RSI measurement stale.
        measured = [row for row in rows if row.value is not None]
        freshness_status = (
            "unknown" if not measured else
            "fresh" if all(score_source_is_fresh(
                "technical", row.indicator, getattr(row, "source_observed_at", None), symbol=asset
            ) for row in measured) else "stale"
        )
        return {
            "data": TechnicalSnapshotData(symbol=asset, items=payload),
            "summary": {"title": "technical_snapshot", "symbol": asset, "count": len(payload)},
            "as_of": latest,
            "freshness_status": freshness_status,
            "source": "technical_indicators",
            "schema_name": "TechnicalSnapshotData",
            "entity_type": "technical_snapshot",
            "asset": asset,
        }
