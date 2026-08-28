"""Canonical target-asset projection for an already selected FINN contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from backend.services.asset_catalog_service import resolve_catalog_symbol


@dataclass(frozen=True)
class FinnV2TargetAssetResolution:
    target_asset: Optional[str]
    source: Optional[str]


class FinnV2TargetAssetResolver:
    """Keep user targets distinct from workspace context across the pipeline."""

    def resolve(
        self,
        *,
        explicit_target_asset: object = None,
        selector_target_asset: object = None,
        verified_context: Optional[Mapping[str, object]] = None,
        operation_state: Optional[Mapping[str, object]] = None,
        workspace_asset: object = None,
        allow_workspace_fallback: bool = True,
    ) -> FinnV2TargetAssetResolution:
        # Current user input always wins. Provider extraction may supplement a
        # natural request but can never overwrite an explicit catalog symbol.
        for source, value in (
            ("explicit_message", explicit_target_asset),
            ("selector_message", selector_target_asset),
            ("verified_lineage", self._lineage_asset(verified_context)),
            ("persisted_operation", self._state_asset(operation_state)),
            ("workspace_context", workspace_asset if allow_workspace_fallback else None),
        ):
            asset = self._asset(value)
            if asset:
                return FinnV2TargetAssetResolution(asset, source)
        return FinnV2TargetAssetResolution(None, None)

    @staticmethod
    def _asset(value: object) -> Optional[str]:
        return resolve_catalog_symbol(str(value or "").strip()) or None

    @classmethod
    def _lineage_asset(cls, context: Optional[Mapping[str, object]]) -> object:
        context = context or {}
        verified = context.get("last_verified_context")
        if not isinstance(verified, Mapping):
            verified = context
        entities = verified.get("referenced_entities")
        if not isinstance(entities, Mapping):
            entities = {}
        return verified.get("target_asset") or entities.get("asset") or verified.get("resolved_asset")

    @classmethod
    def _state_asset(cls, state: Optional[Mapping[str, object]]) -> object:
        state = state or {}
        targets = state.get("target_entities")
        if isinstance(targets, Mapping) and targets.get("asset"):
            return targets["asset"]
        collected = state.get("collected_inputs")
        if isinstance(collected, Mapping):
            return collected.get("asset") or collected.get("symbol")
        return state.get("target_asset")
