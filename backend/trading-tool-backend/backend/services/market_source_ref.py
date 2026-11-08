"""Stable provenance for one selected market_data measurement."""

from __future__ import annotations

from datetime import datetime, timezone


def market_source_ref(*, market_id: int | None, measurement_id: int | None,
                      source_observed_at: datetime | str | None) -> dict | None:
    if measurement_id is None or source_observed_at is None:
        return None
    try:
        measurement_id = int(measurement_id)
        if measurement_id <= 0:
            return None
        scoped_market_id = int(market_id) if market_id is not None else None
        if scoped_market_id is not None and scoped_market_id <= 0:
            return None
        moment = (source_observed_at if isinstance(source_observed_at, datetime)
                  else datetime.fromisoformat(str(source_observed_at).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None
    observed_utc = moment.replace(tzinfo=moment.tzinfo or timezone.utc).astimezone(timezone.utc)
    return {
        "market_id": scoped_market_id,
        "measurement_id": measurement_id,
        "source_observed_at_utc": observed_utc.isoformat(),
    }
