from __future__ import annotations

from datetime import datetime


def display_source_moment(value: datetime | str | None) -> datetime | str | None:
    """Remove subsecond noise from model-facing evidence, preserving the instant."""
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.isoformat(timespec="seconds")
    return value
