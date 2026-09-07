from __future__ import annotations

from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
from backend.infrastructure.repositories.agent_repository import AgentRepository
from backend.schemas.finn_v2_evidence_schema import ReviewHistoryData


class ReviewToolAdapter:
    def __init__(self, session):
        self.repository = AgentRepository(session)
        self.sources = FinnV2InformationSourceRegistry()

    async def execute(self, *, user_id: int, selector: dict | None = None, **_kwargs):
        self.sources.get("review_history").validate_request(user_id=user_id)
        category = str((selector or {}).get("category") or "technical").strip().lower()
        rows = await self.repository.get_reflections_by_category(user_id, category)
        items = [
            str(row.get("comment") or row.get("recommendation") or row.get("indicator") or "")
            for row in rows
        ]
        return {
            "data": ReviewHistoryData(items=[item for item in items if item]),
            "summary": {"title": "review_history", "category": category, "count": len(items)},
            "as_of": max((row.get("timestamp") for row in rows if row.get("timestamp") is not None), default=None),
            "source": "ai_reflections",
            "schema_name": "ReviewHistoryData",
            "entity_type": "review_history",
        }
