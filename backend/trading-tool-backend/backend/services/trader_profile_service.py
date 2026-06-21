from __future__ import annotations

from typing import Any, Dict, List, Optional

TRADER_TYPE_VALUES = [
    "investor",
    "dca_investor",
    "swing_trader",
    "day_trader",
    "scalper",
    "hybrid",
]
TIMEFRAME_VALUES = ["5m", "15m", "1h", "4h", "1d", "1w", "1m"]
ASSET_FOCUS_VALUES = [
    "bitcoin",
    "crypto_general",
    "stocks",
    "etfs",
    "forex",
    "commodities",
]
GOAL_VALUES = [
    "wealth_building",
    "extra_income",
    "active_trading",
    "financial_independence",
    "retirement",
    "capital_preservation",
]
EXPERIENCE_LEVEL_VALUES = ["beginner", "intermediate", "advanced", "professional"]
RISK_PROFILE_VALUES = ["conservative", "balanced", "aggressive"]


def _ensure_array(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, "", [], {}):
        return []
    text = str(value).strip()
    return [text] if text else []


def _normalize(values: List[str], allowed: List[str]) -> List[str]:
    allowed_set = set(allowed)
    return [value for value in values if value in allowed_set]


def normalize_trader_profile_preferences(preferences: Optional[dict]) -> Dict[str, List[str]]:
    prefs = preferences or {}
    return {
        "trader_types": _normalize(
            _ensure_array(prefs.get("trader_types")) or _ensure_array(prefs.get("trader_type")),
            TRADER_TYPE_VALUES,
        ),
        "primary_timeframes": _normalize(
            _ensure_array(prefs.get("primary_timeframes")),
            TIMEFRAME_VALUES,
        ),
        "asset_focus": _normalize(
            _ensure_array(prefs.get("asset_focus")),
            ASSET_FOCUS_VALUES,
        ),
        "investment_goals": _normalize(
            _ensure_array(prefs.get("investment_goals_list")) or _ensure_array(prefs.get("investment_goals")),
            GOAL_VALUES,
        ),
        "experience_levels": _normalize(
            _ensure_array(prefs.get("experience_levels")) or _ensure_array(prefs.get("experience_level")),
            EXPERIENCE_LEVEL_VALUES,
        ),
        "risk_profiles": _normalize(
            _ensure_array(prefs.get("risk_profiles")) or _ensure_array(prefs.get("risk_profile")),
            RISK_PROFILE_VALUES,
        ),
    }


def has_trader_profile(profile: Optional[Dict[str, List[str]]]) -> bool:
    return any(bool(values) for values in (profile or {}).values())


def build_trader_profile_summary(profile: Optional[Dict[str, List[str]]]) -> str:
    payload = profile or {}
    segments: List[str] = []
    if payload.get("trader_types"):
        segments.append("/".join(payload["trader_types"][:2]))
    if payload.get("primary_timeframes"):
        segments.append(",".join(payload["primary_timeframes"][:3]))
    if payload.get("asset_focus"):
        segments.append(",".join(payload["asset_focus"][:2]))
    if payload.get("experience_levels"):
        segments.append(payload["experience_levels"][0])
    if payload.get("risk_profiles"):
        segments.append(payload["risk_profiles"][0])
    return " | ".join(segments)


def build_trader_profile_context(preferences: Optional[dict]) -> Dict[str, Any]:
    profile = normalize_trader_profile_preferences(preferences)
    used = has_trader_profile(profile)
    return {
        "trader_profile": profile,
        "trader_profile_summary": build_trader_profile_summary(profile) if used else "",
        "trader_profile_used": used,
        "profile_match_mode": "stored_profile" if used else "none",
    }
