import logging
import requests
import csv
from datetime import date, timedelta
from io import StringIO

from backend.services.providers.twelve_data_macro_provider import (
    DXY_BASE_FACTOR,
    DXY_COMPONENT_WEIGHTS,
    TwelveDataMacroProvider,
)
from backend.utils.scoring_utils import (
    normalize_indicator_name,
    get_score_rule_from_db,
)

logger = logging.getLogger(__name__)

YAHOO_DXY = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
ALT_FNG = "https://api.alternative.me/fng/?limit=1"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_date}"
YAHOO_SP500_GSPC = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
YAHOO_SP500 = "https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX"
YAHOO_VIX = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
YAHOO_GOLD = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
YAHOO_OIL = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
YAHOO_US10Y = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
YAHOO_US02Y = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX"
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


def _fetch_text(url: str, timeout: int = 10):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _fred_csv_url(series_id: str) -> str:
    start_date = (date.today() - timedelta(days=730)).isoformat()
    return FRED_CSV_URL.format(series_id=series_id, start_date=start_date)


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


def _extract_last_csv_value(csv_text: str) -> float | None:
    rows = _extract_csv_rows(csv_text)
    if not rows:
        return None
    return _coerce_first_numeric(rows[-1][1])


def _extract_csv_rows(csv_text: str) -> list[tuple[str, str]]:
    reader = csv.reader(StringIO(csv_text))
    next(reader, None)
    rows: list[tuple[str, str]] = []
    for row in reader:
        if len(row) < 2:
            continue
        observation_date = (row[0] or "").strip()
        value = (row[1] or "").strip()
        if not observation_date or value in ("", ".", None):
            continue
        rows.append((observation_date, value))
    return rows


def _extract_inflation_yoy_from_csv(csv_text: str) -> float | None:
    rows = _extract_csv_rows(csv_text)
    if len(rows) < 13:
        return None

    latest_value = _coerce_first_numeric(rows[-1][1])
    prior_value = _coerce_first_numeric(rows[-13][1])
    if latest_value in (None, 0) or prior_value in (None, 0):
        return None

    return ((latest_value / prior_value) - 1.0) * 100.0


def _fetch_dxy_from_twelve_data(provider: TwelveDataMacroProvider):
    """
    Exacte DXY-reconstructie met de officiële componenten en exponenten:
    EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 *
    USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036 * 50.14348112
    """
    return provider.fetch_derived_dxy()


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

    source_lower = str(source or "").strip().lower()
    link_lower = str(link or "").strip().lower()
    use_twelve_data = source_lower == "twelve_data" or link_lower.startswith("twelve_data:")
    effective_source = source
    effective_link = link

    twelve_data_provider = TwelveDataMacroProvider()
    if use_twelve_data and twelve_data_provider.supports_indicator(normalized):
        try:
            value = twelve_data_provider.fetch_latest_value(normalized)
            if value is not None:
                return {"value": value}
        except Exception:
            logger.warning("Twelve Data macro fallback mislukt voor %s", normalized, exc_info=True)

        legacy_fallbacks = {
            "sp500": ("yahoo", YAHOO_SP500),
            "vix": ("yahoo", YAHOO_VIX),
            "gold_price": ("yahoo", YAHOO_GOLD),
            "oil_price": ("yahoo", YAHOO_OIL),
            "us10y": ("yahoo", YAHOO_US10Y),
            "us02y": ("yahoo", YAHOO_US02Y),
        }
        effective_source, effective_link = legacy_fallbacks.get(normalized, (source, link))

    # 🟦 Derived DXY basket
    if normalized == "dxy" and source_lower == "derived":
        try:
            value = _fetch_dxy_from_twelve_data(twelve_data_provider)
            if value is not None:
                return {"value": value}
        except Exception:
            logger.warning("Twelve Data DXY fallback mislukt", exc_info=True)

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
    if "alternative" in (effective_source or "").lower():
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

    # 🟪 Official FRED CSV export
    if effective_source and "fred" in effective_source.lower() and effective_link:
        try:
            series_id = effective_link.split(":", 1)[1] if effective_link.lower().startswith("fred:") else None
            csv_url = _fred_csv_url(series_id) if series_id else effective_link
            csv_text = _fetch_text(csv_url, timeout=20)
            if normalized == "inflation_rate":
                return {"value": _extract_inflation_yoy_from_csv(csv_text)}
            return {"value": _extract_last_csv_value(csv_text)}
        except Exception:
            return {"value": None}

    # 🟨 Yahoo generic (legacy fallback only)
    if effective_source and "yahoo" in effective_source.lower() and effective_link:
        try:
            r = _http_get(effective_link, timeout=10)
            r.raise_for_status()
            data = r.json()
            value = _extract_yahoo_chart_value(data)
            if value is None and normalized == "sp500" and effective_link != YAHOO_SP500_GSPC:
                fallback_response = _http_get(YAHOO_SP500_GSPC, timeout=10)
                fallback_response.raise_for_status()
                value = _extract_yahoo_chart_value(fallback_response.json())
            return {"value": value}
        except Exception:
            return {"value": None}

    # 🟫 Generic
    if effective_link:
        try:
            r = _http_get(effective_link, timeout=10)
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
