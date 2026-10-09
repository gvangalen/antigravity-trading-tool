from __future__ import annotations

from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.schemas.finn_v2_evidence_schema import MacroSnapshotData, MacroSnapshotItem
from backend.utils.scoring_utils import score_source_is_fresh


class MacroToolAdapter:
    def __init__(self, session):
        self.repository = MacroDataRepository(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        rows = await self.repository.get_active_day_macro_data(user_id, symbol=asset)
        if not rows:
            raise LookupError("source_unavailable")
        source_statuses = [
            "fresh" if score_source_is_fresh(
                "macro", row.name, getattr(row, "source_observed_at", None), symbol=asset
            ) else "stale" if getattr(row, "source_observed_at", None) else "unknown"
            for row in rows
        ]
        payload = [
            MacroSnapshotItem(
                indicator=row.name,
                value=float(row.value) if row.value is not None else None,
                trend=row.trend,
                score=(float(row.score) if row.score is not None and source_status == "fresh"
                       else None),
                source_status=source_status,
                timestamp=row.timestamp,
                source_observed_at=getattr(row, "source_observed_at", None),
            )
            for row, source_status in zip(rows, source_statuses)
        ]
        latest = max((getattr(row, "source_observed_at", None) for row in rows
                      if getattr(row, "source_observed_at", None)), default=None)
        # A macro observation follows the same per-indicator release window
        # as Score 2.0. The generic six-hour snapshot TTL would contradict
        # a valid daily DXY or monthly release.
        measured_statuses = [status for row, status in zip(rows, source_statuses)
                             if row.value is not None]
        freshness_status = (
            "unknown" if not measured_statuses else
            measured_statuses[0] if len(set(measured_statuses)) == 1 else "unknown"
        )
        return {
            "data": MacroSnapshotData(symbol=asset, items=payload),
            "summary": {"title": "macro_snapshot", "symbol": asset, "count": len(payload)},
            "as_of": latest,
            "freshness_status": freshness_status,
            "source": "macro_data",
            "schema_name": "MacroSnapshotData",
            "entity_type": "macro_snapshot",
            "asset": asset,
        }
