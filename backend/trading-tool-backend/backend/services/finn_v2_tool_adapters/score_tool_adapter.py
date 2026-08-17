from __future__ import annotations

from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.schemas.finn_v2_evidence_schema import AssetScoresData, DailyScoresData, MasterScoreData


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
            "daily_scores": DailyScoresData(
                macro_score=float(daily.get("macro_score")) if daily and daily.get("macro_score") is not None else None,
                technical_score=float(daily.get("technical_score")) if daily and daily.get("technical_score") is not None else None,
                market_score=float(daily.get("market_score")) if daily and daily.get("market_score") is not None else None,
                setup_score=float(daily.get("setup_score")) if daily and daily.get("setup_score") is not None else None,
                report_date=daily.get("report_date") if daily else None,
            ) if daily else None,
            "master_score": MasterScoreData(
                score=float(getattr(master, "avg_score", 0) or 0),
                date=getattr(master, "date", None),
            ) if master else None,
        }
        return {
            "data": AssetScoresData(**payload),
            "summary": {"title": "asset_scores", "symbol": asset, "report_date": str(report_date) if report_date else None},
            "as_of": report_date,
            "source": "daily_scores",
            "schema_name": "AssetScoresData",
            "entity_type": "scores",
            "asset": asset,
        }
