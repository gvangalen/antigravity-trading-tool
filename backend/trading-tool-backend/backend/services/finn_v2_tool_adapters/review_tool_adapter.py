from __future__ import annotations

from datetime import date, timedelta

from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.schemas.finn_v2_evidence_schema import ReviewHistoryData


class ReviewToolAdapter:
    def __init__(self, session):
        self.repository = BotRepository(session)
        self.sources = FinnV2InformationSourceRegistry()

    async def execute(self, *, user_id: int, asset: str | None = None, selector: dict | None = None, **_kwargs):
        self.sources.get("review_history").validate_request(user_id=user_id)
        rows = await self.repository.get_bot_history(user_id, date.today() - timedelta(days=30), date.today())
        if asset:
            rows = [row for row in rows if str(row.get("symbol") or "").upper() == asset.upper()]
        items = [
            f"{row['decision_ts']}: bot {row['bot_name']} ({row['symbol']}) decision "
            f"{row['action']} (status: {row['status']})"
            for row in rows[:20]
        ]
        return {
            "data": ReviewHistoryData(items=[item for item in items if item]),
            "summary": {"title": "review_history", "kind": "bot_decisions", "asset": asset, "count": len(items)},
            "as_of": max((row.get("decision_ts") for row in rows if row.get("decision_ts") is not None), default=None),
            "source": "bot_decisions",
            "schema_name": "ReviewHistoryData",
            "entity_type": "review_history",
        }
