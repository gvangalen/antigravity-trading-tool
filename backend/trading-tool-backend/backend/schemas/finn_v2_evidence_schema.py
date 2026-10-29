from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, validator

from backend.domain.finn_v2_contract import InformationScope


SCHEMA_VERSION = "2026-08-17.block3"


class TraderProfileData(BaseModel):
    trader_profile: dict[str, List[str]] = Field(default_factory=dict)
    trader_context: Optional[str] = None
    has_profile: bool = False


class UserPreferencesData(BaseModel):
    report_style: Optional[str] = None
    tone: Optional[str] = None
    detail_level: Optional[str] = None
    coaching_style: Optional[str] = None
    experience_level: Optional[str] = None
    risk_profile: Optional[str] = None
    selected_asset: Optional[str] = None
    active_asset: Optional[str] = None


class ActiveAssetData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    pair: Optional[str] = None
    display_name: Optional[str] = None
    asset_class: Optional[str] = None
    provider: Optional[str] = None
    exchange: Optional[str] = None
    market_region: Optional[str] = None
    timezone: Optional[str] = None
    quote_currency: Optional[str] = None
    refresh_policy: Optional[str] = None


class IndicatorConfigurationItem(BaseModel):
    indicator: str
    category: str
    priority: Optional[int] = None
    weight: Optional[float] = None
    enabled: bool = True
    symbol: Optional[str] = None
    asset_class: Optional[str] = None
    source_record_id: Optional[int] = None
    provenance: Optional[str] = None


class IndicatorConfigurationData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    pair: Optional[str] = None
    asset_class: Optional[str] = None
    owner_user_id: Optional[int] = None
    requested_symbol: Optional[str] = None
    resolved_symbol: Optional[str] = None
    source_record_ids: List[int] = Field(default_factory=list)
    technical: List[IndicatorConfigurationItem] = Field(default_factory=list)
    market: List[IndicatorConfigurationItem] = Field(default_factory=list)
    macro: List[IndicatorConfigurationItem] = Field(default_factory=list)
    scope_by_category: dict[str, str] = Field(default_factory=dict)
    provenance: str = "user_indicator_configs"


class AssetScoresData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    quote_currency: Optional[str] = None
    pair: Optional[str] = None
    as_of: Optional[date] = None
    source_status: str
    benchmark_score: Optional[float] = None
    benchmark_weights: Optional[Dict[str, float]] = None
    reported_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    component_source_status: Dict[str, str] = Field(default_factory=dict)
    component_status_explanation: Dict[str, str] = Field(default_factory=dict)
    component_source_observed_at: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    component_indicator_source_status: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    indicator_evidence: Dict[str, Dict[str, Dict[str, Any]]] = Field(default_factory=dict)


class SetupMarketMatchesData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    quote_currency: Optional[str] = None
    pair: Optional[str] = None
    as_of: Optional[date] = None
    source_status: str
    benchmark_score: Optional[float] = None
    benchmark_weights: Optional[Dict[str, float]] = None
    reported_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    component_source_status: Dict[str, str] = Field(default_factory=dict)
    component_status_explanation: Dict[str, str] = Field(default_factory=dict)
    component_source_observed_at: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    component_indicator_source_status: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    matches: List[Dict[str, Any]] = Field(default_factory=list)


class MarketSnapshotData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    pair: Optional[str] = None
    price: Optional[float] = None
    quote_currency: Optional[str] = None
    price_provider: Optional[str] = None
    change_24h: Optional[float] = None
    volume: Optional[float] = None
    source: str
    as_of: Optional[datetime] = None
    source_observed_at: Optional[datetime] = None


class MacroSnapshotItem(BaseModel):
    indicator: str
    value: Optional[float] = None
    trend: Optional[str] = None
    score: Optional[float] = None
    source_status: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_observed_at: Optional[datetime] = None


class MacroSnapshotData(BaseModel):
    symbol: str
    items: List[MacroSnapshotItem] = Field(default_factory=list)


class TechnicalSnapshotItem(BaseModel):
    indicator: str
    value: Optional[float] = None
    score: Optional[float] = None
    source_status: Optional[str] = None
    advice: Optional[str] = None
    explanation: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_observed_at: Optional[datetime] = None


class TechnicalSnapshotData(BaseModel):
    symbol: str
    market_id: Optional[int] = None
    pair: Optional[str] = None
    items: List[TechnicalSnapshotItem] = Field(default_factory=list)


class ActiveSetupData(BaseModel):
    setup_id: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    market_id: Optional[int] = None
    quote_currency: Optional[str] = None
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    setup_type: Optional[str] = None
    setup_style: Optional[str] = None
    description: Optional[str] = None
    saved_market_condition: Dict[str, Any] = Field(default_factory=dict)
    dca_frequency: Optional[str] = None
    dca_day: Optional[str] = None
    dca_day_name: Optional[str] = None
    dca_month_day: Optional[int] = None
    min_investment: Optional[float] = None
    min_benchmark_score: Optional[float] = None
    max_benchmark_score: Optional[float] = None
    min_market_score: Optional[float] = None
    max_market_score: Optional[float] = None
    min_macro_score: Optional[float] = None
    max_macro_score: Optional[float] = None
    min_technical_score: Optional[float] = None
    max_technical_score: Optional[float] = None
    setups: List[Dict[str, object]] = Field(default_factory=list)
    setup_count: Optional[int] = None


class SavedSetupInventoryData(BaseModel):
    """Complete owner-scoped setup list; never an active-setup selection."""
    setups: List[Dict[str, object]] = Field(default_factory=list)
    setup_count: int
    asset_filter: Optional[str] = None
    timeframe_filter: Optional[str] = None
    complete: bool = True
    confirmation_rule_field_available: bool = False


class LinkedStrategyData(BaseModel):
    strategy_id: int
    setup_id: Optional[int] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    market_id: Optional[int] = None
    quote_currency: Optional[str] = None
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    execution_mode: Optional[str] = None
    risk_profile: Optional[str] = None
    entry: Optional[str] = None
    price_currency: Optional[str] = None
    price_currency_status: str = "unconfirmed"
    entry_type: Optional[str] = None
    stop_loss: Optional[str] = None
    targets: List[str] = Field(default_factory=list)
    base_amount: Optional[float] = None
    currency: Optional[str] = None
    setup_name: Optional[str] = None
    setup_type: Optional[str] = None
    dca_amount_mode: Optional[str] = None
    score_source: Optional[str] = None
    score_weights: Optional[Dict[str, float]] = None
    score_weights_policy: Optional[str] = None
    low_threshold: Optional[float] = None
    high_threshold: Optional[float] = None
    low_score_percent: Optional[float] = None
    mid_score_percent: Optional[float] = None
    high_score_percent: Optional[float] = None
    dca_score_bands: List[Dict[str, Any]] = Field(default_factory=list)
    level_geometry: Optional[Dict[str, Any]] = None


class LinkedStrategyCollectionData(BaseModel):
    """Every saved strategy for one owner-scoped setup; no strategy is selected."""

    setup_id: int
    setup_name: Optional[str] = None
    strategies: List[LinkedStrategyData] = Field(default_factory=list)
    strategy_count: int
    complete: bool = True


class LinkedBotData(BaseModel):
    bot_id: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    market_id: Optional[int] = None
    quote_currency: Optional[str] = None
    pair: Optional[str] = None
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    setup_id: Optional[int] = None
    setup_name: Optional[str] = None
    is_active: bool = False
    is_live: bool = False
    mode: Optional[str] = None
    budget_total_eur: Optional[float] = None
    budget_limit_enabled: Optional[bool] = None
    paper_initial_cash_eur: Optional[float] = None


class BotStatusData(BaseModel):
    bot_id: int
    is_active: bool = False
    is_live: bool = False
    last_run: Optional[datetime] = None
    mode: Optional[str] = None
    cadence: Optional[str] = None
    latest_decision: Optional[dict] = None


class WatchlistEntryData(BaseModel):
    symbol: str
    present: bool = True


class WatchlistData(BaseModel):
    target_asset: Optional[str] = None
    contains_target_asset: bool = False
    symbols: List[WatchlistEntryData] = Field(default_factory=list)


class PortfolioGlobalData(BaseModel):
    currency: Optional[str] = None
    total_equity: Optional[float] = None
    cash_balance: Optional[float] = None
    invested_value: Optional[float] = None
    current_position_value: Optional[float] = None
    realized_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    total_budget_limit: Optional[float] = None
    allocations_pct: dict[str, float] = Field(default_factory=dict)


class PortfolioBotData(BaseModel):
    bot_id: Optional[int] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    strategy_id: Optional[int] = None
    strategy_name: Optional[str] = None
    setup_id: Optional[int] = None
    setup_name: Optional[str] = None
    mode: Optional[str] = None
    equity: Optional[float] = None
    cash_eur: Optional[float] = None
    position_value_eur: Optional[float] = None
    position_qty: Optional[float] = None
    invested_eur: Optional[float] = None
    realized_pnl_eur: Optional[float] = None
    unrealized_pnl_eur: Optional[float] = None
    result_eur: Optional[float] = None
    portfolio_initialized: bool = False
    valuation_available: bool = False
    valuation_status: str = "unavailable"
    budget_total_eur: Optional[float] = None
    budget_limit_enabled: Optional[bool] = None
    paper_cash_eur: Optional[float] = None
    is_active: Optional[bool] = None
    is_live: Optional[bool] = None
    price_as_of: Optional[datetime] = None
    price_quote_currency: Optional[str] = None
    source_price_as_of: Optional[datetime] = None
    fx_as_of: Optional[datetime] = None
    fx_eur_per_unit: Optional[float] = None


class PortfolioData(BaseModel):
    global_: PortfolioGlobalData = Field(default_factory=PortfolioGlobalData, alias="global")
    bots: List[PortfolioBotData] = Field(default_factory=list)
    read_at: Optional[datetime] = None
    valuation_available: bool = False
    environment: Optional[Literal["paper", "live"]] = None
    valuation_status: str = "unavailable"
    valuation_as_of: Optional[datetime] = None
    unallocated_cash_eur: Optional[float] = None
    available_cash_eur: Optional[float] = None
    reserved_cash_eur: Optional[float] = None
    exchange_name: Optional[str] = None
    balance_time_basis: Optional[str] = None
    covered_scopes: List[str] = Field(default_factory=list)
    excluded_scopes: List[str] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True


class LatestReportData(BaseModel):
    report_type: str
    report_date: Optional[date] = None
    symbol: Optional[str] = None
    status: Optional[str] = None
    id: Optional[int] = None
    generated_at: Optional[datetime] = None
    market_score: Optional[float] = None
    macro_score: Optional[float] = None
    technical_score: Optional[float] = None
    setup_score: Optional[float] = None
    score_source_snapshot: Optional[Dict[str, Any]] = None
    best_setup: Optional[Dict[str, Any]] = None
    top_setups: List[Dict[str, Any]] = Field(default_factory=list)


class ConfirmedTradeLessonEvidenceData(BaseModel):
    lesson_text: str
    confirmed_at: str
    evidence_revision: Optional[int] = None
    source: str = "user_confirmed_reflection_not_trade_fact_or_original_plan"


class ClosedTradeEvidenceData(BaseModel):
    review_id: int
    symbol: str
    environment: str
    bot_id: Optional[int] = None
    bot_name: Optional[str] = None
    entry_at: datetime
    exit_at: datetime
    pnl_eur: Optional[str] = None
    pnl_basis: str
    has_original_plan: bool
    evidence_ids: List[str] = Field(default_factory=list)
    confirmed_lesson: Optional[ConfirmedTradeLessonEvidenceData] = None


class ReviewHistoryData(BaseModel):
    items: List[str] = Field(default_factory=list)
    closed_trade_status: str = "no_data"
    closed_trade_coverage: Dict[str, int] = Field(default_factory=dict)
    closed_trade_review_ids: List[int] = Field(default_factory=list)
    closed_trades: List[ClosedTradeEvidenceData] = Field(default_factory=list)


ToolDataUnion = Union[
    TraderProfileData,
    UserPreferencesData,
    ActiveAssetData,
    IndicatorConfigurationData,
    AssetScoresData,
    SetupMarketMatchesData,
    MarketSnapshotData,
    MacroSnapshotData,
    TechnicalSnapshotData,
    ActiveSetupData,
    SavedSetupInventoryData,
    LinkedStrategyData,
    LinkedStrategyCollectionData,
    LinkedBotData,
    BotStatusData,
    WatchlistData,
    PortfolioData,
    LatestReportData,
    ReviewHistoryData,
]

TOOL_DATA_MODEL_BY_NAME = {
    "TraderProfileData": TraderProfileData,
    "UserPreferencesData": UserPreferencesData,
    "ActiveAssetData": ActiveAssetData,
    "IndicatorConfigurationData": IndicatorConfigurationData,
    "AssetScoresData": AssetScoresData,
    "SetupMarketMatchesData": SetupMarketMatchesData,
    "MarketSnapshotData": MarketSnapshotData,
    "MacroSnapshotData": MacroSnapshotData,
    "TechnicalSnapshotData": TechnicalSnapshotData,
    "ActiveSetupData": ActiveSetupData,
    "SavedSetupInventoryData": SavedSetupInventoryData,
    "LinkedStrategyData": LinkedStrategyData,
    "LinkedStrategyCollectionData": LinkedStrategyCollectionData,
    "LinkedBotData": LinkedBotData,
    "BotStatusData": BotStatusData,
    "WatchlistData": WatchlistData,
    "PortfolioData": PortfolioData,
    "LatestReportData": LatestReportData,
    "ReviewHistoryData": ReviewHistoryData,
}

PAYLOAD_TYPE_TO_SCHEMA_NAME = {
    "profile": "TraderProfileData",
    "preferences": "UserPreferencesData",
    "active_asset": "ActiveAssetData",
    "indicator_configuration": "IndicatorConfigurationData",
    "asset_scores": "AssetScoresData",
    "setup_market_matches": "SetupMarketMatchesData",
    "market_snapshot": "MarketSnapshotData",
    "macro_snapshot": "MacroSnapshotData",
    "technical_snapshot": "TechnicalSnapshotData",
    "active_setup": "ActiveSetupData",
    "saved_setup_inventory": "SavedSetupInventoryData",
    "linked_strategy": "LinkedStrategyData",
    "linked_bot": "LinkedBotData",
    "bot_status": "BotStatusData",
    "watchlist": "WatchlistData",
    "portfolio": "PortfolioData",
    "latest_report": "LatestReportData",
    "review_history": "ReviewHistoryData",
}


def parse_tool_payload(schema_name: str | None, payload):
    if payload is None or not schema_name:
        return payload
    model = TOOL_DATA_MODEL_BY_NAME.get(schema_name)
    if model is None or isinstance(payload, model):
        return payload
    return model.parse_obj(payload)


class EvidenceArtifact(BaseModel):
    artifact_id: str
    run_id: str
    user_id: int
    tool_call_id: int
    tool_name: str
    information_scope: Optional[InformationScope] = None
    operation_id: Optional[str] = None
    operation_contract_version: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    asset: Optional[str] = None
    source: str
    resolution_source: str
    user_scoped: bool
    source_as_of: Optional[datetime] = None
    freshness: Literal["fresh", "stale", "unknown", "not_applicable"]
    schema_name: str
    schema_version: str
    content_hash: str
    payload: Optional[Any] = None
    availability: Literal["available", "stale", "ambiguous", "unavailable", "not_collected"]
    error_codes: List[str] = Field(default_factory=list)
    created_at: datetime
    redacted_at: Optional[datetime] = None

    @validator("payload", pre=True, always=True)
    def _parse_payload(cls, value, values):
        return parse_tool_payload(values.get("schema_name"), value)

    class Config:
        smart_union = True
