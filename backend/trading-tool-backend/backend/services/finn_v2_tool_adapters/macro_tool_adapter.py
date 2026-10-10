from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.schemas.finn_v2_evidence_schema import MacroSnapshotData, MacroSnapshotItem
from backend.utils.scoring_utils import score_source_is_fresh


def _display_moment(value: datetime | None) -> datetime | None:
    return value.replace(microsecond=0) if value is not None else None


def _display_value(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    measured = float(value)
    # DXY is shown to two decimals in Analyse. Keep the same precision in
    # FINN's read evidence; the stored measurement and score stay untouched.
    if name.strip().casefold() == "dxy":
        return float(Decimal(str(measured)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return float(f"{measured:.6g}")


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
                value=_display_value(row.name, row.value),
                trend=row.trend,
                score=(float(row.score) if row.score is not None and source_status == "fresh"
                       else None),
                source_status=source_status,
                timestamp=_display_moment(row.timestamp),
                source_observed_at=_display_moment(getattr(row, "source_observed_at", None)),
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
            "as_of": _display_moment(latest),
            "freshness_status": freshness_status,
            "source": "macro_data",
            "schema_name": "MacroSnapshotData",
            "entity_type": "macro_snapshot",
            "asset": asset,
        }
