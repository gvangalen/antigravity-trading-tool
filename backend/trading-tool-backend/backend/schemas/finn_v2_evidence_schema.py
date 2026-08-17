from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, validator


SCHEMA_VERSION = "2026-08-17.block3"


class TraderProfileData(BaseModel):
    trader_profile: dict[str, List[str]] = Field(default_factory=dict)
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
    enabled: bool = True
    symbol: Optional[str] = None
    asset_class: Optional[str] = None


class IndicatorConfigurationData(BaseModel):
    symbol: str
    technical: List[IndicatorConfigurationItem] = Field(default_factory=list)


class MasterScoreData(BaseModel):
    score: float = 0.0
    date: Optional[date] = None


class DailyScoresData(BaseModel):
    macro_score: Optional[float] = None
    technical_score: Optional[float] = None
    market_score: Optional[float] = None
    setup_score: Optional[float] = None
    report_date: Optional[date] = None


class AssetScoresData(BaseModel):
    symbol: str
    daily_scores: Optional[DailyScoresData] = None
    master_score: Optional[MasterScoreData] = None


class MarketSnapshotData(BaseModel):
    symbol: str
    price: float = 0.0
    change_24h: float = 0.0
    volume: float = 0.0
    source: str
    as_of: Optional[datetime] = None


class MacroSnapshotItem(BaseModel):
    indicator: str
    value: float = 0.0
    trend: Optional[str] = None
    score: float = 0.0
    timestamp: Optional[datetime] = None


class MacroSnapshotData(BaseModel):
    symbol: str
    items: List[MacroSnapshotItem] = Field(default_factory=list)


class TechnicalSnapshotItem(BaseModel):
    indicator: str
    value: float = 0.0
    score: float = 0.0
    advice: Optional[str] = None
    explanation: Optional[str] = None
    timestamp: Optional[datetime] = None


class TechnicalSnapshotData(BaseModel):
    symbol: str
    items: List[TechnicalSnapshotItem] = Field(default_factory=list)


class ActiveSetupData(BaseModel):
    setup_id: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    score: Optional[float] = None


class LinkedStrategyData(BaseModel):
    strategy_id: int
    setup_id: Optional[int] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    execution_mode: Optional[str] = None
    risk_profile: Optional[str] = None


class LinkedBotData(BaseModel):
    bot_id: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    strategy_id: Optional[int] = None
    is_active: bool = False
    is_live: bool = False
    mode: Optional[str] = None


class BotStatusData(BaseModel):
    bot_id: int
    is_active: bool = False
    is_live: bool = False
    last_run: Optional[datetime] = None
    mode: Optional[str] = None
    cadence: Optional[str] = None


class PortfolioGlobalData(BaseModel):
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
    equity: Optional[float] = None
    is_active: Optional[bool] = None
    is_live: Optional[bool] = None


class PortfolioData(BaseModel):
    global_: PortfolioGlobalData = Field(default_factory=PortfolioGlobalData, alias="global")
    bots: List[PortfolioBotData] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True


class LatestReportData(BaseModel):
    report_type: str
    report_date: Optional[date] = None
    symbol: Optional[str] = None
    status: Optional[str] = None
    id: Optional[int] = None


class ReviewHistoryData(BaseModel):
    items: List[str] = Field(default_factory=list)


ToolDataUnion = Union[
    TraderProfileData,
    UserPreferencesData,
    ActiveAssetData,
    IndicatorConfigurationData,
    AssetScoresData,
    MarketSnapshotData,
    MacroSnapshotData,
    TechnicalSnapshotData,
    ActiveSetupData,
    LinkedStrategyData,
    LinkedBotData,
    BotStatusData,
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
    "MarketSnapshotData": MarketSnapshotData,
    "MacroSnapshotData": MacroSnapshotData,
    "TechnicalSnapshotData": TechnicalSnapshotData,
    "ActiveSetupData": ActiveSetupData,
    "LinkedStrategyData": LinkedStrategyData,
    "LinkedBotData": LinkedBotData,
    "BotStatusData": BotStatusData,
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
    "market_snapshot": "MarketSnapshotData",
    "macro_snapshot": "MacroSnapshotData",
    "technical_snapshot": "TechnicalSnapshotData",
    "active_setup": "ActiveSetupData",
    "linked_strategy": "LinkedStrategyData",
    "linked_bot": "LinkedBotData",
    "bot_status": "BotStatusData",
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
    payload: Optional[ToolDataUnion] = None
    availability: Literal["available", "stale", "ambiguous", "unavailable", "not_collected"]
    error_codes: List[str] = Field(default_factory=list)
    created_at: datetime
    redacted_at: Optional[datetime] = None

    @validator("payload", pre=True, always=True)
    def _parse_payload(cls, value, values):
        return parse_tool_payload(values.get("schema_name"), value)

    class Config:
        smart_union = True
