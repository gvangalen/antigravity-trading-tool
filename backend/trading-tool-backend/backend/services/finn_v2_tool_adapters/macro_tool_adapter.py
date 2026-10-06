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
        payload = [
            MacroSnapshotItem(
                indicator=row.name,
                value=float(row.value) if row.value is not None else None,
                trend=row.trend,
                score=(float(row.score) if row.score is not None and
                       score_source_is_fresh("macro", row.name, getattr(row, "source_observed_at", None), symbol=asset)
                       else None),
                timestamp=row.timestamp,
                source_observed_at=getattr(row, "source_observed_at", None),
            )
            for row in rows
        ]
        latest = max((getattr(row, "source_observed_at", None) for row in rows
                      if getattr(row, "source_observed_at", None)), default=None)
        return {
            "data": MacroSnapshotData(symbol=asset, items=payload),
            "summary": {"title": "macro_snapshot", "symbol": asset, "count": len(payload)},
            "as_of": latest,
            "source": "macro_data",
            "schema_name": "MacroSnapshotData",
            "entity_type": "macro_snapshot",
            "asset": asset,
        }
