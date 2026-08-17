from __future__ import annotations

from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository


class MacroToolAdapter:
    def __init__(self, session):
        self.repository = MacroDataRepository(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        rows = await self.repository.get_active_day_macro_data(user_id, symbol=asset)
        if not rows:
            raise LookupError("source_unavailable")
        payload = [
            {
                "indicator": row.name,
                "value": float(row.value or 0),
                "trend": row.trend,
                "score": float(row.score or 0),
                "timestamp": row.timestamp,
            }
            for row in rows
        ]
        latest = max((row.timestamp for row in rows if row.timestamp), default=None)
        return {"data": {"symbol": asset, "items": payload}, "summary": {"title": "macro_snapshot", "symbol": asset, "count": len(payload)}, "as_of": latest}

