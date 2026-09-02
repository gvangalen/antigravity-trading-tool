"""Canonical active-setup selection shared by FINN context and tool paths."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class FinnV2ActivePlanResolution:
    setup: Optional[dict[str, Any]]
    source: str


class FinnV2ActivePlanResolver:
    """Resolve one user-scoped active setup without cross-path fallbacks."""

    def resolve(
        self,
        *,
        asset: Optional[str],
        active_setup: Optional[Mapping[str, Any]],
        candidates: Iterable[Mapping[str, Any]],
    ) -> FinnV2ActivePlanResolution:
        normalized_asset = self._symbol(asset)
        active = dict(active_setup) if active_setup else None
        if active and self._matches_asset(active, normalized_asset):
            return FinnV2ActivePlanResolution(active, "active_setup")

        matching = [
            dict(candidate)
            for candidate in candidates
            if self._matches_asset(candidate, normalized_asset)
        ]
        explicitly_active = [
            candidate
            for candidate in matching
            if bool(candidate.get("is_active") or candidate.get("is_best"))
        ]
        if len(explicitly_active) == 1:
            return FinnV2ActivePlanResolution(explicitly_active[0], "asset_active_setup")
        if len(matching) == 1:
            return FinnV2ActivePlanResolution(
                matching[0],
                "single_asset_setup" if normalized_asset else "single_user_setup",
            )
        if len(matching) > 1:
            return FinnV2ActivePlanResolution(None, "setup_ambiguous")
        return FinnV2ActivePlanResolution(None, "setup_not_resolved")

    @staticmethod
    def _symbol(value: object) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        return normalized or None

    def _matches_asset(self, candidate: Mapping[str, Any], asset: Optional[str]) -> bool:
        return asset is None or self._symbol(candidate.get("symbol")) == asset
