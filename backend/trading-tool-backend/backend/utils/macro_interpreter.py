import logging
import math
import os
import requests

from backend.services.providers.twelve_data_macro_provider import TwelveDataMacroProvider
from backend.utils.scoring_utils import (
    normalize_indicator_name,
    get_score_rule_from_db,
)

logger = logging.getLogger(__name__)

YAHOO_DXY = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
ALT_FNG = "https://api.alternative.me/fng/?limit=1"
YAHOO_SP500_GSPC = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}


def _coerce_first_numeric(*candidates):
    for candidate in candidates:
        if candidate in ("", ".", None):
            continue
        try:
            return float(candidate)
        except Exception:
            continue
    return None


def _extract_last_non_null(sequence):
    if not sequence:
        return None
    for value in reversed(sequence):
        if value not in ("", ".", None):
            return value
    return None


def _http_get(url: str, timeout: int = 10):
    return requests.get(url, timeout=timeout, headers=REQUEST_HEADERS)


def _fetch_json(url: str, timeout: int = 10):
    response = _http_get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _extract_yahoo_chart_value(data):
    result = data.get("chart", {}).get("result") or []
    if not result:
        return None

    payload = result[0]
    meta = payload.get("meta", {}) or {}
    quote = (payload.get("indicators", {}).get("quote") or [{}])[0] or {}
    return _coerce_first_numeric(
        meta.get("regularMarketPrice"),
        meta.get("previousClose"),
        meta.get("chartPreviousClose"),
        _extract_last_non_null(quote.get("close") or []),
    )


def _fetch_dxy_from_frankfurter():
    """
    Bereken DXY via publieke FX-rates.
    Dit is stabieler dan de Yahoo ^DXY endpoint die op productie vaak leeg of rate-limited terugkomt.
    """
    usd_cross = _fetch_json("https://api.frankfurter.app/latest?from=USD&to=JPY,CAD,SEK,CHF")
    eur_usd = _fetch_json("https://api.frankfurter.app/latest?from=EUR&to=USD")
    gbp_usd = _fetch_json("https://api.frankfurter.app/latest?from=GBP&to=USD")

    usd_rates = usd_cross.get("rates", {})
    eurusd = (eur_usd.get("rates") or {}).get("USD")
    gbpusd = (gbp_usd.get("rates") or {}).get("USD")
    usdjpy = usd_rates.get("JPY")
    usdcad = usd_rates.get("CAD")
    usdsek = usd_rates.get("SEK")
    usdchf = usd_rates.get("CHF")

    components = [eurusd, usdjpy, gbpusd, usdcad, usdsek, usdchf]
    if any(value in ("", ".", None) for value in components):
        return None

    return (
        50.14348112
        * math.pow(float(eurusd), -0.576)
        * math.pow(float(usdjpy), 0.136)
        * math.pow(float(gbpusd), -0.119)
        * math.pow(float(usdcad), 0.091)
        * math.pow(float(usdsek), 0.042)
        * math.pow(float(usdchf), 0.036)
    )


# ============================================================
# 🌐 Macro waarde ophalen (RAW ONLY)
# ============================================================
def fetch_macro_value(name: str, source: str = None, link: str = None):
    """
    Haalt macro waarde op.
    Crasht nooit.
    Geeft ALTIJD raw value terug.
    """

    normalized = normalize_indicator_name(name)
    logger.info(f"🌐 Fetch macro '{normalized}'")

    twelve_data_provider = TwelveDataMacroProvider()
    if twelve_data_provider.supports_indicator(normalized):
        try:
            value = twelve_data_provider.fetch_latest_value(normalized)
            if value is not None:
                return {"value": value}
        except Exception:
            logger.warning("Twelve Data macro fallback mislukt voor %s", normalized, exc_info=True)

    # 🟦 DXY
    if normalized == "dxy":
        try:
            value = _fetch_dxy_from_frankfurter()
            if value is not None:
                return {"value": value}
        except Exception:
            logger.warning("Frankfurter DXY fallback mislukt", exc_info=True)

        try:
            r = _http_get(YAHOO_DXY, timeout=10)
            r.raise_for_status()
            data = r.json()
            result = data.get("chart", {}).get("result") or []
            if not result:
                return {"value": None}

            payload = result[0]
            meta = payload.get("meta", {}) or {}
            quote = (payload.get("indicators", {}).get("quote") or [{}])[0] or {}

            value = _coerce_first_numeric(
                meta.get("regularMarketPrice"),
                meta.get("previousClose"),
                meta.get("chartPreviousClose"),
                _extract_last_non_null(quote.get("close") or []),
            )
            return {"value": value}
        except Exception:
            return {"value": None}

    # 🟩 Fear & Greed
    if "alternative" in (source or "").lower():
        try:
            r = _http_get(ALT_FNG, timeout=10)
            r.raise_for_status()
            fg = r.json()
            return {"value": float(fg["data"][0]["value"])}
        except Exception:
            return {"value": None}

    # 🟧 BTC Dominance
    if normalized in ("btc_dominance", "bitcoin_dominance"):
        try:
            r = _http_get("https://api.coingecko.com/api/v3/global", timeout=10)
            r.raise_for_status()
            data = r.json()
            return {"value": float(data["data"]["market_cap_percentage"]["btc"])}
        except Exception:
            return {"value": None}

    # 🟨 Yahoo generic (Handles ^SPX, ^TNX, ^VIX, GC=F, CL=F, etc.)
    if source and "yahoo" in source.lower() and link:
        try:
            r = _http_get(link, timeout=10)
            r.raise_for_status()
            data = r.json()
            value = _extract_yahoo_chart_value(data)
            if value is None and normalized == "sp500" and link != YAHOO_SP500_GSPC:
                fallback_response = _http_get(YAHOO_SP500_GSPC, timeout=10)
                fallback_response.raise_for_status()
                value = _extract_yahoo_chart_value(fallback_response.json())
            return {"value": value}
        except Exception:
            return {"value": None}

    # 🟪 FRED
    if source and "fred" in source.lower() and link:
        try:
            r = _http_get(link, timeout=10)
            r.raise_for_status()
            fred = r.json()
            obs = fred.get("observations", [])
            if obs and obs[-1]["value"] not in ("", ".", None):
                return {"value": float(obs[-1]["value"])}
        except Exception:
            pass
        return {"value": None}

    # 🟫 Generic
    if link:
        try:
            r = _http_get(link, timeout=10)
            r.raise_for_status()
            data = r.json()
            for key in ("value", "price", "index"):
                if key in data:
                    return {"value": float(data[key])}
        except Exception:
            pass

    return {"value": None}


# ============================================================
# 🔹 Macro normalisatie naar 0–100
# ============================================================
def normalize_macro_value(indicator: str, value: float) -> float:
    """
    Zet macro raw value om naar genormaliseerde 0–100 schaal.
    """

    try:
        if value is None:
            return 0

        value = float(value)

        # Fear & Greed is al 0–100
        if indicator in ("fear_greed", "fear_and_greed", "fear_greed_index"):
            return max(0, min(100, value))

        # BTC dominance 0–100%
        if indicator in ("btc_dominance", "bitcoin_dominance"):
            return max(0, min(100, value))

        # DXY → schaal rond 80–120
        if indicator == "dxy":
            low, high = 80, 120
            normalized = ((value - low) / (high - low)) * 100
            return max(0, min(100, normalized))

        # S&P 500 → schaal rond 3000–6500
        if indicator == "sp500":
            low, high = 3000, 6500
            normalized = ((value - low) / (high - low)) * 100
            return max(0, min(100, normalized))

        # 10Y Yield → schaal 0–6%
        if indicator == "us10y":
            low, high = 0, 6
            normalized = ((value - low) / (high - low)) * 100
            return max(0, min(100, normalized))

        # Gold → schaal 1500–3000
        if indicator == "gold_price":
            low, high = 1500, 3000
            normalized = ((value - low) / (high - low)) * 100
            return max(0, min(100, normalized))

        # ETF Inflow (BTC) → schaal -500M tot +1000M
        if indicator == "etf_bitcoin_inflow":
            low, high = -500, 1000
            normalized = ((value - low) / (high - low)) * 100
            return max(0, min(100, normalized))

        # Fallback → clamp
        return max(0, min(100, value))

    except Exception:
        logger.error("Macro normalisatie fout", exc_info=True)
        return 0


# ============================================================
# 🧠 Macro interpretatie via DB rules (USER-AWARE)
# ============================================================
def interpret_macro_indicator(name: str, value: float, user_id: int):
    """
    Flow:
    raw_value → normalized_value → DB rules (user → template fallback)
    """

    try:
        normalized_name = normalize_indicator_name(name)

        # 🔥 eerst normaliseren
        normalized_value = normalize_macro_value(normalized_name, value)

        rule = get_score_rule_from_db(
            "macro",
            normalized_name,
            normalized_value,
            user_id=user_id,   # ✅ FIX: user-id meegeven
        )

        if not rule:
            return {
                "score": 10,
                "trend": "neutral",
                "interpretation": "Geen scoreregel match",
                "action": "Geen actie",
            }

        return {
            "score": max(0, min(100, rule.get("score", 10))),
            "trend": rule.get("trend") or "neutral",
            "interpretation": rule.get("interpretation"),
            "action": rule.get("action"),
        }

    except Exception:
        logger.error("interpret_macro_indicator error", exc_info=True)
        return {
            "score": 10,
            "trend": "neutral",
            "interpretation": "Interpretatiefout",
            "action": "Controleer logs",
        }
