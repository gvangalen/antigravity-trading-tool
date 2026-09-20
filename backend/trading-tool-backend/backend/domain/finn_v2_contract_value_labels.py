from __future__ import annotations

from typing import Any


_LABELS = {
    "execution_mode": {
        "fixed": {"nl": "vast", "en": "fixed", "de": "fest"},
        "custom": {"nl": "aangepast", "en": "custom", "de": "individuell"},
    },
    "risk_profile": {
        "conservative": {"nl": "voorzichtig", "en": "conservative", "de": "vorsichtig"},
        "balanced": {"nl": "gebalanceerd", "en": "balanced", "de": "ausgewogen"},
        "aggressive": {"nl": "offensief", "en": "aggressive", "de": "offensiv"},
    },
}


def contract_value_label(*, field: str, value: Any, locale: str, unknown: str = "onbekend") -> str:
    """Return localized product copy without exposing contract enum values."""
    language = str(locale or "nl").split("-", 1)[0].casefold()
    labels = _LABELS.get(field, {}).get(str(value or "").strip().casefold(), {})
    return labels.get(language) or labels.get("en") or unknown
