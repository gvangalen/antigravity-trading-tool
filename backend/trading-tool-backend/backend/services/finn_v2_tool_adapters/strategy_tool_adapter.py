from __future__ import annotations

import json
from typing import Any

from backend.schemas.finn_v2_evidence_schema import LinkedStrategyData
from backend.engine.curve_engine import calculate_position_size


class StrategyToolAdapter:
    async def execute(self, *, strategy: dict, resolution_source: str, **_kwargs):
        raw_data = strategy.get("data") if isinstance(strategy.get("data"), dict) else {}
        targets = strategy.get("targets")
        if isinstance(targets, str):
            targets = [item.strip() for item in targets.split(",") if item.strip()]
        elif not isinstance(targets, list):
            targets = []
        dca_rule = self._dca_amount_rule(strategy, raw_data)
        payload = LinkedStrategyData(
            strategy_id=strategy.get("id"),
            setup_id=strategy.get("setup_id"),
            name=strategy.get("name"),
            symbol=strategy.get("symbol") or raw_data.get("symbol") or strategy.get("setup_symbol"),
            timeframe=strategy.get("timeframe") or raw_data.get("timeframe") or strategy.get("setup_timeframe"),
            execution_mode=strategy.get("execution_mode"),
            risk_profile=strategy.get("risk_profile"),
            entry=strategy.get("entry"),
            entry_type=self._entry_type(strategy, raw_data),
            stop_loss=strategy.get("stop_loss"),
            targets=targets,
            base_amount=self._coerce_float(strategy.get("base_amount")),
            setup_name=strategy.get("setup_name"),
            setup_type=strategy.get("existing_setup_type") or strategy.get("setup_type"),
            **dca_rule,
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

    def _dca_amount_rule(self, strategy: dict[str, Any], raw_data: dict[str, Any]) -> dict[str, Any]:
        if raw_data.get("dca_amount_semantics") != "planned_exact":
            return {}
        base = self._coerce_float(strategy.get("base_amount"))
        if base is None:
            return {}
        if strategy.get("execution_mode") == "fixed":
            return {"dca_amount_mode": "fixed"}
        curve = strategy.get("decision_curve") or raw_data.get("decision_curve")
        if isinstance(curve, str):
            try:
                curve = json.loads(curve)
            except (TypeError, ValueError):
                return {}
        if not isinstance(curve, dict) or curve.get("interpolation") != "step":
            return {}
        points = curve.get("points")
        if not isinstance(points, list) or len(points) < 3:
            return {}
        try:
            ordered = sorted(points, key=lambda point: float(point["x"]))
            low = float(ordered[1]["x"])
            high = float(ordered[2]["x"])
            bands = [
                (0.0, low, float(ordered[0]["y"])),
                (low, high, float(ordered[1]["y"])),
                (high, None, float(ordered[2]["y"])),
            ]
            return {
                "dca_amount_mode": "score_bands",
                "score_source": curve.get("input"),
                "score_weights": None,
                "score_weights_policy": curve.get("weights_policy"),
                "low_threshold": low,
                "high_threshold": high,
                "low_score_percent": round(100 * float(ordered[0]["y"]), 2),
                "mid_score_percent": round(100 * float(ordered[1]["y"]), 2),
                "high_score_percent": round(100 * float(ordered[2]["y"]), 2),
                "dca_score_bands": [
                    {
                        "from_score_inclusive": start,
                        "to_score_exclusive": end,
                        "percent_of_base": round(100 * multiplier, 2),
                        "planned_amount": calculate_position_size(
                            base, curve, start,
                            min_multiplier=curve.get("min_multiplier", 0.1),
                            max_multiplier=curve.get("max_multiplier", 3.0),
                        ),
                        "amount_status": "hypothetical_before_exposure_not_purchase",
                    }
                    for start, end, multiplier in bands
                ],
            }
        except (TypeError, ValueError, KeyError):
            return {}
