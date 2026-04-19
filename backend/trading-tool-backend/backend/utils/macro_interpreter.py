import logging
import requests

from backend.utils.scoring_utils import (
    normalize_indicator_name,
    get_score_rule_from_db,
)

logger = logging.getLogger(__name__)

YAHOO_DXY = "https://query1.finance.yahoo.com/v8/finance/chart/%5EDXY"
ALT_FNG = "https://api.alternative.me/fng/?limit=1"


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

    # 🟦 DXY
    if normalized == "dxy":
        try:
            r = requests.get(YAHOO_DXY, timeout=10)
            r.raise_for_status()
            data = r.json()
            value = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
            return {"value": float(value)}
        except Exception:
            return {"value": None}

    # 🟩 Fear & Greed
    if "alternative" in (source or "").lower():
        try:
            r = requests.get(ALT_FNG, timeout=10)
            r.raise_for_status()
            fg = r.json()
            return {"value": float(fg["data"][0]["value"])}
        except Exception:
            return {"value": None}

    # 🟧 BTC Dominance
    if normalized in ("btc_dominance", "bitcoin_dominance"):
        try:
            r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
            r.raise_for_status()
            data = r.json()
            return {"value": float(data["data"]["market_cap_percentage"]["btc"])}
        except Exception:
            return {"value": None}

    # 🟨 Yahoo generic (Handles ^SPX, ^TNX, ^VIX, GC=F, CL=F, etc.)
    if source and "yahoo" in source.lower() and link:
        try:
            r = requests.get(link, timeout=10)
            r.raise_for_status()
            data = r.json()
            meta = data["chart"]["result"][0]["meta"]
            return {"value": float(meta["regularMarketPrice"])}
        except Exception:
            # Fallback for Yahoo (sometimes prices are in result[0].indicators.quote[0].close[-1])
            try:
                data = r.json()
                price = data["chart"]["result"][0]["indicators"]["quote"][0]["close"][-1]
                if price is not None:
                    return {"value": float(price)}
            except:
                pass
            return {"value": None}

    # 🟪 FRED
    if source and "fred" in source.lower() and link:
        try:
            r = requests.get(link, timeout=10)
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
            r = requests.get(link, timeout=10)
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
