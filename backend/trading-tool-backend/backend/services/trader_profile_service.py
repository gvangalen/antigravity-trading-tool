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
INTRADAY_TIMEFRAMES = {"5m", "15m", "1h"}
SWING_TIMEFRAMES = {"4h", "1d"}
INVESTOR_TIMEFRAMES = {"1w", "1m"}


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


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _profile_style(profile: Dict[str, List[str]]) -> Optional[str]:
    trader_types = set(profile.get("trader_types") or [])
    if trader_types & {"day_trader", "scalper"}:
        return "intraday"
    if "swing_trader" in trader_types:
        return "swing"
    if trader_types & {"investor", "dca_investor"}:
        return "investor"
    return None


def _infer_request_style(request_context: Optional[dict], query: Optional[str]) -> Optional[str]:
    payload = request_context or {}
    timeframe = _normalized_text(payload.get("timeframe") or payload.get("setup_timeframe"))
    if timeframe in INTRADAY_TIMEFRAMES:
        return "intraday"
    if timeframe in SWING_TIMEFRAMES:
        return "swing"
    if timeframe in INVESTOR_TIMEFRAMES:
        return "investor"

    page = _normalized_text(payload.get("page") or payload.get("page_type") or payload.get("current_flow"))
    if any(token in page for token in ("scalp", "day", "intraday")):
        return "intraday"
    if any(token in page for token in ("swing", "setup", "strategy")):
        return "swing"
    if any(token in page for token in ("invest", "portfolio", "dca")):
        return "investor"

    query_text = _normalized_text(query)
    if any(token in query_text for token in ("scalp", "day trade", "daytrader", "intraday", "5m", "15m")):
        return "intraday"
    if any(token in query_text for token in ("swing", "4h", "daily", "1d")):
        return "swing"
    if any(token in query_text for token in ("dca", "invest", "lange termijn", "long term", "weekly", "monthly", "1w", "1m")):
        return "investor"
    return None


def _profile_conflicts_with_request(profile: Dict[str, List[str]], request_style: Optional[str]) -> bool:
    if not request_style:
        return False
    trader_types = set(profile.get("trader_types") or [])
    if request_style == "intraday":
        return bool(trader_types & {"investor", "dca_investor"}) and not bool(trader_types & {"day_trader", "scalper"})
    if request_style == "investor":
        return bool(trader_types & {"day_trader", "scalper"}) and not bool(trader_types & {"investor", "dca_investor"})
    if request_style == "swing":
        return False
    return False


def build_trader_profile_context(
    preferences: Optional[dict],
    request_context: Optional[dict] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    profile = normalize_trader_profile_preferences(preferences)
    used = has_trader_profile(profile)
    request_style = _infer_request_style(request_context, query)
    multiple_styles = len(set(profile.get("trader_types") or [])) > 1
    conflict = used and _profile_conflicts_with_request(profile, request_style)
    if not used:
        match_mode = "profile_missing_fallback"
        match_reason = "No stored trader profile; FINN should fall back to page and entity context."
    elif multiple_styles and request_style:
        match_mode = "mixed_profile_page_context_priority"
        match_reason = f"Multiple trader styles selected; current {request_style} context gets priority."
    else:
        match_mode = "direct_match"
        match_reason = "Stored trader profile aligns directly with the current page and action context."
    return {
        "trader_profile": profile,
        "trader_profile_summary": build_trader_profile_summary(profile) if used else "",
        "trader_profile_used": used,
        "profile_match_mode": match_mode,
        "profile_match_reason": match_reason,
        "profile_conflict_detected": conflict,
        "profile_request_style": request_style,
    }
