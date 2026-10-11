from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import SavedSetupInventoryData
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import _dca_day_name


class SetupInventoryToolAdapter:
    async def execute(self, *, setups: list[dict], asset_filter: str | None = None,
                      timeframe_filter: str | None = None,
                      strategies: list[dict] | None = None,
                      bots: list[dict] | None = None,
                      complete: bool = True):
        linked_strategies: dict[int, list[dict]] = {}
        strategy_setup: dict[int, int] = {}
        for strategy in strategies or []:
            setup_id = strategy.get("setup_id")
            strategy_id = strategy.get("strategy_id") or strategy.get("id")
            if not isinstance(setup_id, int) or not isinstance(strategy_id, int):
                continue
            strategy_setup[strategy_id] = setup_id
            linked_strategies.setdefault(setup_id, []).append({
                "strategy_id": strategy_id, "name": strategy.get("name"),
            })
        linked_bots: dict[int, list[dict]] = {}
        for bot in bots or []:
            strategy_id = bot.get("strategy_id")
            setup_id = strategy_setup.get(strategy_id) if isinstance(strategy_id, int) else None
            if setup_id is None:
                continue
            linked_bots.setdefault(setup_id, []).append({
                "bot_id": bot.get("bot_id") or bot.get("id"),
                "name": bot.get("name"), "strategy_id": strategy_id,
                "mode": bot.get("mode"), "is_live": bot.get("is_live"),
            })
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
                **{f"{bound}_{component}_score": row.get(f"{bound}_{component}_score")
                   for component in ("market", "macro", "technical")
                   for bound in ("min", "max")},
                "linked_strategies": linked_strategies.get(row.get("setup_id") or row.get("id"), []),
                "linked_bots": linked_bots.get(row.get("setup_id") or row.get("id"), []),
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
