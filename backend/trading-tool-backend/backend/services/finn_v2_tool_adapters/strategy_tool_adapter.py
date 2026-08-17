from __future__ import annotations


class StrategyToolAdapter:
    async def execute(self, *, strategy: dict, resolution_source: str, **_kwargs):
        payload = {
            "strategy_id": strategy.get("id"),
            "setup_id": strategy.get("setup_id"),
            "name": strategy.get("name"),
            "symbol": strategy.get("setup_symbol"),
            "timeframe": strategy.get("setup_timeframe"),
            "execution_mode": strategy.get("execution_mode"),
            "risk_profile": strategy.get("risk_profile"),
        }
        return {"data": payload, "summary": {"title": "linked_strategy", "strategy_id": payload["strategy_id"], "setup_id": payload["setup_id"]}, "as_of": strategy.get("created_at"), "resolution_source": resolution_source}

