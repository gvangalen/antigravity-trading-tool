from __future__ import annotations

from datetime import datetime, timezone


def display_source_moment(value: datetime | str | None) -> datetime | str | None:
    """Present database source moments explicitly as UTC, without subseconds."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).replace(microsecond=0)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat(timespec="seconds")
    return value
