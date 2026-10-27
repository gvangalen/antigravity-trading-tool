from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import AssetScoresData
from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.services.setup_market_match_service import verified_indicator_evidence
from backend.services.finn_v2_tool_adapters.display_source_moment import display_source_moment


class ScoreToolAdapter:
    def __init__(self, session):
        self.context = FinnSharedContextService(session)

    async def execute(self, *, user_id: int, asset: str, market_id: int | None = None,
                      quote_currency: str | None = None, **_kwargs):
        assessment = await self.context.benchmark_for_asset(
            user_id, asset, setups=[], **({"market_id": market_id} if market_id is not None else {}))
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
        verified = verified_indicator_evidence(
            assessment, getattr(getattr(self.context, "matches", None), "last_source_row", None)
        )
        # Pass measurements and scoring facts to Luna, without stored
        # interpretation/action prose from earlier analysis routes.
        factual_fields = ("score", "value", "normalized_value", "source_observed_at",
                          "weight", "rule_origin")
        payload["indicator_evidence"] = {
            category: {
                name: {field: values[field] for field in factual_fields if field in values}
                for name, values in indicators.items() if isinstance(values, dict)
            }
            for category, indicators in verified.items()
        }
        payload["market_id"] = market_id
        payload["quote_currency"] = quote_currency
        payload["pair"] = f"{asset}/{quote_currency}" if market_id is not None else None
        return {
            "data": AssetScoresData(**payload),
            "summary": {"title": "asset_scores", "symbol": asset, "source_status": assessment["source_status"]},
            "as_of": assessment["as_of"],
            "source": "daily_scores_and_source_indicators",
            "schema_name": "AssetScoresData",
            "entity_type": "scores",
            "asset": asset,
        }
