from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import AssetScoresData
from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.services.finn_v2_tool_adapters.display_source_moment import display_source_moment


class ScoreToolAdapter:
    def __init__(self, session):
        self.context = FinnSharedContextService(session)

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        assessment = await self.context.benchmark_for_asset(user_id, asset, setups=[])
        payload = {key: assessment[key] for key in (
            "symbol", "as_of", "source_status", "benchmark_score",
            "benchmark_weights", "reported_scores", "component_source_status",
        )}
        payload["component_status_explanation"] = assessment.get("component_status_explanation") or {}
        payload["component_source_observed_at"] = {
            component: {
                indicator: display_source_moment(moment)
                for indicator, moment in indicators.items()
            }
            for component, indicators in (assessment.get("component_source_observed_at") or {}).items()
        }
        payload["component_indicator_source_status"] = assessment.get("component_indicator_source_status") or {}
        return {
            "data": AssetScoresData(**payload),
            "summary": {"title": "asset_scores", "symbol": asset, "source_status": assessment["source_status"]},
            "as_of": assessment["as_of"],
            "source": "daily_scores_and_source_indicators",
            "schema_name": "AssetScoresData",
            "entity_type": "scores",
            "asset": asset,
        }
