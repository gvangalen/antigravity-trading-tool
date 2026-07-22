import math
from typing import Any, Mapping

from fastapi import HTTPException


def require_indicator_score(scored: Mapping[str, Any] | None, indicator: str) -> float:
    """Reject missing scoring rules instead of persisting a fabricated score."""
    raw_score = scored.get("score") if scored else None
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = math.nan

    if not math.isfinite(score):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Onvoldoende data om '{indicator}' betrouwbaar te scoren. "
                "De indicator is niet opgeslagen."
            ),
        )

    return max(0.0, min(100.0, score))
