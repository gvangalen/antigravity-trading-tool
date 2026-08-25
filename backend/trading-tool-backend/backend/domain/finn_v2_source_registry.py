"""Canonical product-state sources used by FINN V2 information scopes.

Operation contracts decide *which* scopes a run needs.  This manifest decides
where those scopes are allowed to obtain product state.  It deliberately does
not duplicate operation or mode decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceClassification(StrEnum):
    CANONICAL_PRODUCT_STATE = "CANONICAL_PRODUCT_STATE"
    SYSTEM_DEFINITION = "SYSTEM_DEFINITION"
    IMMUTABLE_EVIDENCE_SNAPSHOT = "IMMUTABLE_EVIDENCE_SNAPSHOT"
    DERIVED_VIEW = "DERIVED_VIEW"
    LEGACY_TO_MIGRATE = "LEGACY_TO_MIGRATE"
    DEAD_STORAGE = "DEAD_STORAGE"


class FinnV2CanonicalSourceError(ValueError):
    code = "canonical_source_mismatch"


@dataclass(frozen=True)
class InformationSource:
    scope_id: str
    canonical_table: str
    canonical_repository: str
    classification: SourceClassification
    required_owner_fields: tuple[str, ...] = ("user_id",)
    required_asset_fields: tuple[str, ...] = ()
    cache_namespace: str | None = None
    allowed_writer_paths: tuple[str, ...] = ()
    allowed_reader_paths: tuple[str, ...] = ()
    artifact_provenance_requirements: tuple[str, ...] = ("run_id", "owner_user_id", "source_record_ids")
    legacy_runtime_access_allowed: bool = False

    def validate_request(self, *, user_id: int | None, symbol: str | None = None) -> None:
        if self.required_owner_fields and user_id is None:
            raise FinnV2CanonicalSourceError(f"missing_canonical_owner:{self.scope_id}")
        if self.required_asset_fields and not str(symbol or "").strip():
            raise FinnV2CanonicalSourceError(f"missing_canonical_asset:{self.scope_id}")

    def cache_key(
        self,
        *,
        user_id: int,
        symbol: str | None,
        operation_id: str,
        contract_version: int,
    ) -> str:
        """Return a complete cache identity for an asset-scoped FINN read."""
        self.validate_request(user_id=user_id, symbol=symbol)
        asset = str(symbol or "").strip().upper() or "_"
        return ":".join((
            self.cache_namespace or self.scope_id,
            str(user_id),
            asset,
            operation_id,
            str(contract_version),
        ))


@dataclass(frozen=True)
class LegacyDataSource:
    """A classified non-canonical table that must not power new FINN runs."""

    table_name: str
    classification: SourceClassification
    permitted_use: str
    migration_decision: str
    runtime_access_allowed: bool = False


class FinnV2InformationSourceRegistry:
    """One source manifest shared by FINN V2 tools and product consumers."""

    def __init__(self) -> None:
        self._sources = {source.scope_id: source for source in _SOURCES}
        if len(self._sources) != len(_SOURCES):
            raise FinnV2CanonicalSourceError("duplicate_information_scope")

    def get(self, scope_id: str) -> InformationSource:
        try:
            return self._sources[scope_id]
        except KeyError as exc:
            raise FinnV2CanonicalSourceError(f"unknown_information_scope:{scope_id}") from exc

    def list(self) -> tuple[InformationSource, ...]:
        return tuple(self._sources.values())

    def legacy_sources(self) -> tuple[LegacyDataSource, ...]:
        return _LEGACY_SOURCES


_SOURCES: tuple[InformationSource, ...] = (
    InformationSource("capability", "finn_v2_operation_registry", "FinnV2OperationRegistry", SourceClassification.SYSTEM_DEFINITION, required_owner_fields=(), cache_namespace="capability:v1"),
    InformationSource("active_asset", "user_ai_preferences.selected_asset", "AssistantContextRepository", SourceClassification.CANONICAL_PRODUCT_STATE, cache_namespace="active_asset:v1", allowed_reader_paths=("AssistantContextRepository", "ActiveAssetToolAdapter")),
    InformationSource("profile", "users.ai_preferences", "TraderProfileRepository", SourceClassification.CANONICAL_PRODUCT_STATE, cache_namespace="profile:v1", allowed_reader_paths=("TraderProfileRepository", "ProfileToolAdapter")),
    InformationSource("preferences", "users.ai_preferences", "AssistantContextRepository", SourceClassification.CANONICAL_PRODUCT_STATE, cache_namespace="preferences:v1", allowed_reader_paths=("AssistantContextRepository", "PreferencesToolAdapter")),
    InformationSource("indicator_configuration", "user_indicator_configs", "TechnicalDataRepository", SourceClassification.CANONICAL_PRODUCT_STATE, required_asset_fields=("symbol",), cache_namespace="indicator_configuration:v2", allowed_writer_paths=("TechnicalDataRepository.replace_scope_configs", "TechnicalDataRepository.ensure_user_config"), allowed_reader_paths=("TechnicalDataRepository.get_canonical_indicator_configuration", "IndicatorToolAdapter", "OnboardingRepository")),
    InformationSource("active_setup", "setups", "SetupRepository", SourceClassification.CANONICAL_PRODUCT_STATE, required_asset_fields=("symbol",), cache_namespace="active_setup:v1"),
    InformationSource("linked_strategy", "strategies", "StrategyRepository", SourceClassification.CANONICAL_PRODUCT_STATE, required_asset_fields=("symbol",), cache_namespace="linked_strategy:v1"),
    InformationSource("linked_bot", "bot_configs", "BotRepository", SourceClassification.CANONICAL_PRODUCT_STATE, required_asset_fields=("symbol",), cache_namespace="linked_bot:v1"),
    InformationSource("bot_status", "bot_configs", "BotRepository", SourceClassification.DERIVED_VIEW, required_asset_fields=("symbol",), cache_namespace="bot_status:v1"),
    InformationSource("watchlist", "watchlists", "WatchlistRepository", SourceClassification.CANONICAL_PRODUCT_STATE, cache_namespace="watchlist:v1"),
    InformationSource("portfolio", "portfolio_items", "PortfolioRepository", SourceClassification.CANONICAL_PRODUCT_STATE, required_asset_fields=("symbol",), cache_namespace="portfolio:v1"),
    InformationSource("onboarding_status", "onboarding_steps", "OnboardingRepository", SourceClassification.DERIVED_VIEW, cache_namespace="onboarding_status:v1"),
    InformationSource("conversation_operation_state", "finn_v2_conversations.context_json", "FinnV2ConversationRepository", SourceClassification.CANONICAL_PRODUCT_STATE, cache_namespace="conversation_operation_state:v1"),
    InformationSource("market_snapshot", "market_data", "MarketDataRepository", SourceClassification.DERIVED_VIEW, required_asset_fields=("symbol",), cache_namespace="market_snapshot:v1"),
)


# Rule tables define scoring buckets, not an asset-scoped user selection. Their
# historical user rows do not contain a symbol, so assigning them to an asset
# would be ambiguous and is deliberately prohibited.
_LEGACY_SOURCES: tuple[LegacyDataSource, ...] = (
    LegacyDataSource(
        "user_indicator_configs(symbol IS NULL)",
        SourceClassification.LEGACY_TO_MIGRATE,
        "historical audit only",
        "do_not_assign_without_user_asset_evidence",
    ),
    LegacyDataSource(
        "technical_indicator_rules",
        SourceClassification.SYSTEM_DEFINITION,
        "indicator scoring definitions",
        "not_a_user_asset_selection",
    ),
    LegacyDataSource(
        "market_indicator_rules",
        SourceClassification.SYSTEM_DEFINITION,
        "indicator scoring definitions",
        "not_a_user_asset_selection",
    ),
    LegacyDataSource(
        "macro_indicator_rules",
        SourceClassification.SYSTEM_DEFINITION,
        "indicator scoring definitions",
        "not_a_user_asset_selection",
    ),
)
