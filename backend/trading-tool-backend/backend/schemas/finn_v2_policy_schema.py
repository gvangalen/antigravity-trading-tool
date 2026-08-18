from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


POLICY_VERSION = "2026-08-17.block5"
ELIGIBILITY_VERSION = "2026-08-17.block5"

PolicyClass = Literal[
    "read",
    "advice",
    "proposal",
    "paper_action",
    "live_action",
    "high_risk_action",
    "unsupported_action",
]
OperationType = Literal[
    "update_indicator_configuration",
    "create_setup",
    "update_setup",
    "update_strategy",
    "watchlist_add",
    "watchlist_remove",
    "save_trade_plan",
    "activate_paper_bot",
    "activate_live_bot",
    "portfolio_rebalance",
    "manual_order",
]


class FinnV2PolicyDecision(BaseModel):
    policy_decision_id: str
    run_id: str
    user_id: int
    policy_class: PolicyClass
    operation_type: Optional[OperationType] = None
    allowed: bool
    proposal_allowed: bool
    proposal_input_required: bool = False
    confirmation_required: bool
    step_up_required: bool
    execution_allowed: bool
    shadow_safe: bool
    required_domains: List[str] = Field(default_factory=list)
    evaluated_domain_statuses: Dict[str, str] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    warning_codes: List[str] = Field(default_factory=list)
    blocking_codes: List[str] = Field(default_factory=list)
    snapshot_id: Optional[str] = None
    validation_id: Optional[str] = None
    evidence_set_hash: Optional[str] = None
    policy_version: str = POLICY_VERSION
    created_at: datetime


class StepUpProof(BaseModel):
    proof_id: str
    user_id: int
    assurance_level: str
    issued_at: datetime
    expires_at: datetime
    verified_by: str

    class Config:
        extra = "forbid"


class ExecutionEligibilityDecision(BaseModel):
    eligibility_id: str
    proposal_id: str
    run_id: str
    user_id: int
    eligible: bool
    policy_class: str
    proposal_confirmed: bool
    payload_hash_valid: bool
    evidence_hash_valid: bool
    freshness_valid: bool
    step_up_required: bool
    step_up_satisfied: bool
    kill_switch_clear: bool
    feature_enabled: bool
    duplicate_execution_clear: bool
    blocking_codes: List[str] = Field(default_factory=list)
    eligibility_version: str = ELIGIBILITY_VERSION
    checked_at: datetime
