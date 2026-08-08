from __future__ import annotations

from typing import Dict, List, Optional


TECHNICAL_INDICATOR_DEFINITIONS: List[dict] = [
    {
        "name": "rsi",
        "display_name": "RSI",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:rsi",
        "active": True,
    },
    {
        "name": "ma_50",
        "display_name": "50-day moving average",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:ma_50",
        "active": True,
    },
    {
        "name": "ma_200",
        "display_name": "200-day moving average",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:ma_200",
        "active": True,
    },
    {
        "name": "ema_20_gap_pct",
        "display_name": "EMA20 Gap %",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:ema_20_gap_pct",
        "active": True,
    },
    {
        "name": "ema_50_gap_pct",
        "display_name": "EMA50 Gap %",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:ema_50_gap_pct",
        "active": True,
    },
    {
        "name": "macd_hist_pct",
        "display_name": "MACD Histogram %",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:macd_hist_pct",
        "active": True,
    },
    {
        "name": "atr_pct",
        "display_name": "ATR %",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:atr_pct",
        "active": True,
    },
    {
        "name": "adx",
        "display_name": "ADX",
        "category": "technical",
        "source": "twelve_data",
        "link": "twelve_data:adx",
        "active": True,
    },
]


def get_technical_indicator_definition(name: str) -> Optional[Dict[str, object]]:
    normalized = str(name or "").strip().lower()
    for definition in TECHNICAL_INDICATOR_DEFINITIONS:
        if definition["name"] == normalized:
            return dict(definition)
    return None


def get_active_technical_indicator_definitions() -> List[Dict[str, object]]:
    return [dict(definition) for definition in TECHNICAL_INDICATOR_DEFINITIONS if definition.get("active")]
