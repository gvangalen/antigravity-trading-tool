from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import SavedSetupInventoryData
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import _dca_day_name


class SetupInventoryToolAdapter:
    async def execute(self, *, setups: list[dict], asset_filter: str | None = None,
                      timeframe_filter: str | None = None,
                      complete: bool = True):
        rows = [
            {
                "setup_id": row.get("setup_id") or row.get("id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "timeframe": row.get("timeframe"),
                "setup_type": row.get("setup_type"),
                "description": row.get("description"),
                "dca_frequency": row.get("dca_frequency"),
                "dca_day": row.get("dca_day"),
                "dca_day_name": _dca_day_name(row.get("dca_day")),
                "dca_month_day": row.get("dca_month_day"),
                "min_investment": row.get("min_investment"),
            }
            for row in setups
        ]
        payload = SavedSetupInventoryData(
            setups=rows, setup_count=len(rows), asset_filter=asset_filter,
            timeframe_filter=timeframe_filter, complete=complete,
        )
        return {
            "data": payload,
            "summary": {"title": "saved_setup_inventory", "count": len(rows)},
            "as_of": None,
            "resolution_source": "owner_setup_inventory",
            "source": "setups",
            "schema_name": "SavedSetupInventoryData",
            "entity_type": "setup_collection",
            "entity_id": None,
            "asset": asset_filter,
        }
