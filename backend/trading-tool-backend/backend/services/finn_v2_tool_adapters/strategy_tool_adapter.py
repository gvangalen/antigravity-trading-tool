from __future__ import annotations

from typing import Any

from backend.schemas.finn_v2_evidence_schema import LinkedStrategyData


class StrategyToolAdapter:
    async def execute(self, *, strategy: dict, resolution_source: str, **_kwargs):
        raw_data = strategy.get("data") if isinstance(strategy.get("data"), dict) else {}
        targets = strategy.get("targets")
        if isinstance(targets, str):
            targets = [item.strip() for item in targets.split(",") if item.strip()]
        elif not isinstance(targets, list):
            targets = []
        payload = LinkedStrategyData(
            strategy_id=strategy.get("id"),
            setup_id=strategy.get("setup_id"),
            name=strategy.get("name"),
            symbol=strategy.get("setup_symbol"),
            timeframe=strategy.get("setup_timeframe"),
            execution_mode=strategy.get("execution_mode"),
            risk_profile=strategy.get("risk_profile"),
            entry=strategy.get("entry"),
            entry_type=self._entry_type(strategy, raw_data),
            stop_loss=strategy.get("stop_loss"),
            targets=targets,
            base_amount=self._coerce_float(strategy.get("base_amount")),
            setup_name=strategy.get("setup_name"),
            setup_type=strategy.get("existing_setup_type") or strategy.get("setup_type"),
        )
        return {
            "data": payload,
            "summary": {"title": "linked_strategy", "strategy_id": payload.strategy_id, "setup_id": payload.setup_id},
            "as_of": strategy.get("created_at"),
            "resolution_source": resolution_source,
            "source": "strategies",
            "schema_name": "LinkedStrategyData",
            "entity_type": "strategy",
            "entity_id": str(payload.strategy_id),
            "asset": payload.symbol,
        }

    def _entry_type(self, strategy: dict[str, Any], raw_data: dict[str, Any]) -> str | None:
        explicit = raw_data.get("entry_type")
        if explicit is not None:
            return str(explicit)
        return str(strategy.get("entry_type")) if strategy.get("entry_type") is not None else None

    def _coerce_float(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
