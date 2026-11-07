from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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


def amsterdam_source_moment(value: datetime | str | None) -> str | None:
    """Give FINN an unambiguous local clock label derived from a UTC instant."""
    instant = display_source_moment(value)
    if isinstance(instant, str):
        try:
            instant = datetime.fromisoformat(instant)
        except ValueError:
            return None
    if not isinstance(instant, datetime):
        return None
    return instant.astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S %Z")
