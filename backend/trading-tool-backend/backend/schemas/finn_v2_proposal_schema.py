from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, constr, root_validator, validator

from backend.schemas.finn_v2_policy_schema import OperationType


PROPOSAL_VERSION = "2026-08-17.block5"
ProposalStatus = Literal["draft", "pending_confirmation", "confirmed", "invalidated", "expired", "canceled"]


class ProposalTarget(BaseModel):
    target_type: Literal[
        "indicator_configuration",
        "setup",
        "strategy",
        "trade_plan",
        "bot",
        "portfolio",
        "order",
    ]
    target_id: Optional[str] = None
    asset: Optional[str] = None

    @validator("asset")
    def _normalize_asset(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    class Config:
        extra = "forbid"


class IndicatorConfigurationChange(BaseModel):
    indicator_id: str
    operation: Literal["add", "update", "remove"]
    before: Optional[dict] = None
    after: Optional[dict] = None

    class Config:
        extra = "forbid"


class SetupChange(BaseModel):
    setup_id: int
    changed_fields: Dict[str, Any]

    class Config:
        extra = "forbid"


class SetupCreateChange(BaseModel):
    setup_fields: Dict[str, Any]

    class Config:
        extra = "forbid"


class StrategyChange(BaseModel):
    strategy_id: int
    changed_fields: Dict[str, Any]

    class Config:
        extra = "forbid"


class TradePlanChange(BaseModel):
    plan_id: Optional[str] = None
    changed_fields: Dict[str, Any]

    class Config:
        extra = "forbid"


class BotActivationChange(BaseModel):
    bot_id: int
    requested_mode: Literal["paper", "live"]
    current_is_live: bool

    class Config:
        extra = "forbid"


class PortfolioRebalanceChange(BaseModel):
    target_allocations: Dict[str, Decimal]

    class Config:
        extra = "forbid"


class ManualOrderChange(BaseModel):
    asset: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Optional[Decimal] = None
    notional: Optional[Decimal] = None
    limit_price: Optional[Decimal] = None

    @validator("asset")
    def _normalize_asset(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if not normalized:
            raise ValueError("asset_required")
        return normalized

    @root_validator
    def _validate_order_shape(cls, values):
        quantity = values.get("quantity")
        notional = values.get("notional")
        order_type = values.get("order_type")
        limit_price = values.get("limit_price")
        if quantity is None and notional is None:
            raise ValueError("quantity_or_notional_required")
        if order_type == "limit" and limit_price is None:
            raise ValueError("limit_price_required")
        return values

    class Config:
        extra = "forbid"


ProposalChangeUnion = Union[
    IndicatorConfigurationChange,
    SetupCreateChange,
    SetupChange,
    StrategyChange,
    TradePlanChange,
    BotActivationChange,
    PortfolioRebalanceChange,
    ManualOrderChange,
]


class ValidatedProposalInput(BaseModel):
    operation_type: OperationType
    target: ProposalTarget
    change: ProposalChangeUnion
    impact_summary: str
    risk_summary: str
    source_run_id: str
    source_snapshot_id: str
    source_validation_id: str
    evidence_set_hash: str
    idempotency_key: constr(min_length=16, max_length=128)
    expires_at: datetime

    @root_validator
    def _validate_change_matches_operation(cls, values):
        operation = values.get("operation_type")
        change = values.get("change")
        expected = {
            "update_indicator_configuration": IndicatorConfigurationChange,
            "create_setup": SetupCreateChange,
            "update_setup": SetupChange,
            "update_strategy": StrategyChange,
            "save_trade_plan": TradePlanChange,
            "activate_paper_bot": BotActivationChange,
            "activate_live_bot": BotActivationChange,
            "portfolio_rebalance": PortfolioRebalanceChange,
            "manual_order": ManualOrderChange,
        }
        if operation and change and not isinstance(change, expected[operation]):
            raise ValueError("operation_change_mismatch")
        if operation == "activate_paper_bot" and isinstance(change, BotActivationChange) and change.requested_mode != "paper":
            raise ValueError("operation_change_mismatch")
        if operation == "activate_live_bot" and isinstance(change, BotActivationChange) and change.requested_mode != "live":
            raise ValueError("operation_change_mismatch")
        return values

    class Config:
        extra = "forbid"
        smart_union = True


class FinnV2ProposalRecord(BaseModel):
    proposal_id: str
    run_id: str
    user_id: int
    policy_decision_id: str
    status: ProposalStatus
    operation_type: OperationType
    target: ProposalTarget
    payload_json: dict
    payload_hash: str
    evidence_set_hash: str
    idempotency_key: str
    requires_step_up_auth: bool
    proposal_version: str = PROPOSAL_VERSION
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
