from __future__ import annotations

from typing import Dict, List, Optional


MACRO_INDICATOR_DEFINITIONS: List[dict] = [
    {
        "name": "dxy",
        "display_name": "US Dollar Index (Derived Basket)",
        "source": "derived",
        "link": "derived:dxy",
        "category": "macro",
        "active": True,
    },
    {
        "name": "sp500",
        "display_name": "S&P 500 Index",
        "source": "fred",
        "link": "fred:SP500",
        "category": "macro",
        "active": True,
    },
    {
        "name": "vix",
        "display_name": "CBOE Volatility Index (VIX)",
        "source": "fred",
        "link": "fred:VIXCLS",
        "category": "macro",
        "active": True,
    },
    {
        "name": "gold_price",
        "display_name": "Gold Price",
        "source": "twelve_data",
        "link": "twelve_data:XAU/USD",
        "category": "macro",
        "active": True,
    },
    {
        "name": "oil_price",
        "display_name": "Crude Oil Price (WTI)",
        "source": "fred",
        "link": "fred:DCOILWTICO",
        "category": "macro",
        "active": True,
    },
    {
        "name": "us10y",
        "display_name": "US 10-Year Yield",
        "source": "fred",
        "link": "fred:DGS10",
        "category": "macro",
        "active": True,
    },
    {
        "name": "us02y",
        "display_name": "US 2-Year Yield",
        "source": "fred",
        "link": "fred:DGS2",
        "category": "macro",
        "active": True,
    },
    {
        "name": "interest_rate",
        "display_name": "Fed Funds Rate",
        "source": "fred",
        "link": "fred:FEDFUNDS",
        "category": "macro",
        "active": True,
    },
    {
        "name": "inflation_rate",
        "display_name": "US CPI (Inflation)",
        "source": "fred",
        "link": "fred:CPIAUCSL",
        "category": "macro",
        "active": True,
    },
    {
        "name": "google_trends",
        "display_name": "Google Trends (BTC)",
        "source": "custom",
        "link": "https://trends.google.com/trends/api/widgetdata/multiline",
        "category": "macro",
        "active": False,
    },
    {
        "name": "etf_bitcoin_inflow",
        "display_name": "BTC Spot ETF Inflow",
        "source": "custom",
        "link": "https://bitbo.io/treasuries/etf-flows/",
        "category": "macro",
        "active": True,
    },
]


def get_macro_indicator_definition(name: str) -> Optional[Dict[str, object]]:
    normalized = str(name or "").strip().lower()
    for definition in MACRO_INDICATOR_DEFINITIONS:
        if definition["name"] == normalized:
            return dict(definition)
    return None


def get_active_macro_indicator_definitions() -> List[Dict[str, object]]:
    return [dict(definition) for definition in MACRO_INDICATOR_DEFINITIONS if definition.get("active")]
