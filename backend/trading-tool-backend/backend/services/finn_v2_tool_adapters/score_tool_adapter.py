from __future__ import annotations

from backend.infrastructure.repositories.score_repository import ScoreRepository


class ScoreToolAdapter:
    def __init__(self, session):
        self.repository = ScoreRepository(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        daily = await self.repository.fetch_daily_scores(user_id, asset)
        master = await self.repository.get_master_score(user_id, asset)
        if not daily and not master:
            raise LookupError("source_unavailable")
        report_date = daily.get("report_date") if daily else getattr(master, "date", None)
        payload = {
            "symbol": asset,
            "daily_scores": daily or {},
            "master_score": {
                "score": float(getattr(master, "avg_score", 0) or 0),
                "date": getattr(master, "date", None),
            } if master else None,
        }
        return {
            "data": payload,
            "summary": {"title": "asset_scores", "symbol": asset, "report_date": str(report_date) if report_date else None},
            "as_of": report_date,
        }

