"""Resolve category weights without leaking one asset's settings to another."""

from __future__ import annotations

from typing import Any

from backend.domain.finn_dca_plan_contract import normalize_benchmark_weights


def asset_benchmark_weights(preferences: Any, symbol: str) -> tuple[dict[str, float] | None, str]:
    if preferences is None:
        return normalize_benchmark_weights(None), "equal_default"
    if not isinstance(preferences, dict):
        return None, "invalid_preferences"
    by_asset = preferences.get("asset_benchmark_weights")
    saved = by_asset.get(str(symbol or "").upper()) if isinstance(by_asset, dict) else None
    if saved is not None:
        return normalize_benchmark_weights(saved), "asset"
    global_weights = preferences.get("intelligence_weights")
    return (normalize_benchmark_weights(global_weights),
            "user_preferences" if global_weights else "equal_default")
