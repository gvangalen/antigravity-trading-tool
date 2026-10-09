from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional

from backend.domain.finn_v2_tools import TOOL_FRESHNESS_MAX_AGE_SECONDS


class FinnV2FreshnessService:
    def freshness_for(self, tool_name: str, as_of: Optional[datetime]) -> str:
        max_age = TOOL_FRESHNESS_MAX_AGE_SECONDS.get(tool_name)
        if max_age is None:
            if tool_name in {
                "read_profile",
                "read_user_preferences",
            }:
                return "not_applicable"
            return "unknown"
        if as_of is None:
            return "unknown"
        now = datetime.now(timezone.utc)
        if tool_name in {"read_asset_scores", "read_setup_market_matches"} and isinstance(as_of, date) and not isinstance(as_of, datetime):
            # These tools expose a daily report date, not a midnight source
            # observation. Component source freshness is checked separately
            # by SetupMarketMatchService. An arbitrary rolling 24-hour check
            # on midnight would contradict that same daily benchmark.
            return "fresh" if as_of == now.date() else "stale"
        candidate = self._normalized_datetime(as_of)
        age_seconds = (now - candidate).total_seconds()
        return "fresh" if age_seconds <= max_age else "stale"

    def _normalized_datetime(self, as_of: date | datetime) -> datetime:
        if isinstance(as_of, datetime):
            return as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        candidate = datetime.combine(as_of, time.min)
        return candidate.replace(tzinfo=timezone.utc)
