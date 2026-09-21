from typing import Dict, List, Optional


MARKET_INDICATOR_DEFINITIONS: List[Dict[str, object]] = [
    {
        "name": "price",
        "display_name": "Price",
        "aliases": ["Prijs", "Preis"],
        "category": "market",
        "active": True,
    },
    {
        "name": "volume",
        "display_name": "Volume",
        "aliases": ["Handelsvolume", "Volumen"],
        "category": "market",
        "active": True,
    },
    {
        "name": "change_24h",
        "display_name": "24h Price Change",
        "aliases": ["24-uurs koerswijziging", "24h Preisänderung"],
        "category": "market",
        "active": True,
    },
]


def get_market_indicator_definition(name: str) -> Optional[Dict[str, object]]:
    normalized = str(name or "").strip().lower()
    for definition in MARKET_INDICATOR_DEFINITIONS:
        if definition["name"] == normalized:
            return dict(definition)
    return None


def get_active_market_indicator_definitions() -> List[Dict[str, object]]:
    return [dict(definition) for definition in MARKET_INDICATOR_DEFINITIONS if definition.get("active")]
