from __future__ import annotations

import re


_DISPLAY_NAMES = {
    "dxy": "DXY",
    "rsi": "RSI",
    "ma_50": "MA 50",
    "ma_200": "MA 200",
    "price": "Price",
    "volume": "Volume",
    "change_24h": "24-uurs koerswijziging",
}


def indicator_display_name(value: object) -> str:
    """Return a product label without exposing canonical storage keys."""
    raw = str(value or "").strip()
    normalized = re.sub(r"[\s-]+", "_", raw.casefold())
    if normalized in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[normalized]
    return " ".join(part.upper() if len(part) <= 4 else part.capitalize() for part in normalized.split("_") if part)
