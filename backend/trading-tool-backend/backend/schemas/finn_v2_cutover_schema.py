from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FinnV2ShadowComparisonResult(BaseModel):
    comparison_id: str
    run_id: Optional[str] = None
    user_id: Optional[int] = None
    surface: str
    outcome: Literal["v2_better", "equivalent", "v1_better", "v2_unsafe", "ungradable"]
    mode_match: bool
    asset_match: bool
    follow_up_count_match: bool
    safety_match: bool
    latency_delta_ms: Optional[int] = None
    cost_delta_estimate: Optional[float] = None
    reason_codes: List[str] = Field(default_factory=list)
    created_at: datetime


class FinnV2ReleaseGateResult(BaseModel):
    release_gate_result_id: str
    eval_run_id: Optional[str] = None
    passed: bool
    blocking_gates: Dict[str, bool] = Field(default_factory=dict)
    quality_gates: Dict[str, float] = Field(default_factory=dict)
    operational_gates: Dict[str, float | bool] = Field(default_factory=dict)
    reason_codes: List[str] = Field(default_factory=list)
    created_at: datetime


class FinnV2RuntimeSelection(BaseModel):
    runtime_mode: Literal["v1_primary", "v1_primary_v2_shadow", "v2_canary_readonly", "v2_primary_with_v1_fallback", "v2_only"]
    selected_runtime: Literal["v1", "v2"]
    interaction_mode: Optional[str] = None
    visible_allowed: bool = False
    shadow_enabled: bool = False
    fallback_allowed: bool = False
    reason_codes: List[str] = Field(default_factory=list)


class FinnV2RuntimeStatus(BaseModel):
    runtime_mode: str
    shadow_compare_enabled: bool
    release_gates_enabled: bool
    golden_evals_enabled: bool
    visible_proposals_enabled: bool
    confirmation_routes_enabled: bool
    action_execution_enabled: bool
    canary_user_ids: List[str] = Field(default_factory=list)
    canary_percent: int = 0
    canary_allowed_modes: List[str] = Field(default_factory=list)
    v1_fallback_enabled: bool = True
    post_cutover_kill_switch: bool = False

