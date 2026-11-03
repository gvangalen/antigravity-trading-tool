"""One confirmed pair-bound Trade plan, split into setup and strategy writes."""

from __future__ import annotations

import math
from typing import Any

from backend.domain.entry_signal import validate_entry_signal


STRATEGY_FIELDS = frozenset({
    "entry_signal", "execution_mode", "base_amount", "entry", "stop_loss",
    "targets", "risk_profile", "price_currency",
})


def split_confirmed_trade_plan(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reject incomplete or mismatched rules before either domain row is written."""
    if str(fields.get("setup_type") or "").lower() != "trade":
        raise ValueError("trade_setup_required")
    if fields.get("plan_scope") != "setup_and_strategy":
        raise ValueError("trade_signal_requires_strategy")
    quote = str(fields.get("quote_currency") or "").upper()
    if quote not in {"EUR", "USDT"}:
        raise ValueError("trade_pair_required")
    price_currency = str(fields.get("price_currency") or quote).upper()
    if price_currency != quote:
        raise ValueError("trade_price_currency_mismatch")
    signal = validate_entry_signal(fields.get("entry_signal"))
    if fields.get("timeframe") != signal["timeframe"]:
        raise ValueError("trade_signal_timeframe_mismatch")
    minimum, maximum = fields.get("min_benchmark_score"), fields.get("max_benchmark_score")
    if (type(minimum) not in {int, float} or type(maximum) not in {int, float}
            or not math.isfinite(minimum) or not math.isfinite(maximum)
            or not 0 <= minimum <= maximum <= 100):
        raise ValueError("trade_benchmark_range_required")
    if fields.get("execution_mode") != "fixed":
        raise ValueError("trade_execution_mode_required")
    amount = fields.get("base_amount")
    if type(amount) not in {int, float} or not math.isfinite(amount) or amount <= 0:
        raise ValueError("trade_base_amount_required")
    entry, stop = fields.get("entry"), fields.get("stop_loss")
    targets = fields.get("targets")
    if (type(entry) not in {int, float} or type(stop) not in {int, float}
            or not math.isfinite(entry) or not math.isfinite(stop)
            or not 0 < stop < entry or not isinstance(targets, list)
            or not targets or any(type(t) not in {int, float} or not math.isfinite(t) or t <= entry for t in targets)):
        raise ValueError("trade_price_levels_required")
    if fields.get("risk_profile") not in {"conservative", "balanced", "aggressive"}:
        raise ValueError("trade_risk_profile_required")
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("trade_setup_name_required")
    setup = {key: value for key, value in fields.items() if key not in STRATEGY_FIELDS and key != "plan_scope"}
    strategy = {key: fields[key] for key in STRATEGY_FIELDS if key in fields}
    strategy.update({
        "name": f"{name} Strategy",
        "entry_signal": signal,
        "price_currency": price_currency,
        "symbol": str(fields.get("symbol") or "").upper(),
        "timeframe": fields.get("timeframe"),
    })
    return setup, strategy
