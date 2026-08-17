from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    case_id: str
    category: str
    language: str
    message: str
    workspace: Optional[str] = None
    fixture_user: str
    expected_mode: str
    expected_scopes: List[str] = Field(default_factory=list)
    expected_required_domains: List[str] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    required_entities: List[str] = Field(default_factory=list)
    forbidden_entities: List[str] = Field(default_factory=list)
    required_claim_topics: List[str] = Field(default_factory=list)
    forbidden_claims: List[str] = Field(default_factory=list)
    expected_outcome: Literal["verified_answer", "clarification", "unavailable", "draft_proposal", "policy_block"]
    max_follow_up_questions: int = 1
    required_safety_assertions: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class EvalDimensionScores(BaseModel):
    mode: float = 0.0
    scopes: float = 0.0
    domains: float = 0.0
    tools: float = 0.0
    entities: float = 0.0
    grounding: float = 0.0
    coverage: float = 0.0
    follow_up: float = 0.0
    action_safety: float = 0.0
    paper_live: float = 0.0
    relevance: float = 0.0
    specificity: float = 0.0
    completeness: float = 0.0
    clarity: float = 0.0
    usefulness: float = 0.0
    brevity: float = 0.0
    tone: float = 0.0
    uncertainty_quality: float = 0.0
    next_step_quality: float = 0.0
    language_quality: float = 0.0


class EvalCaseResult(BaseModel):
    eval_case_result_id: str
    eval_run_id: str
    case_id: str
    category: str
    fixture_user: str
    passed: bool
    blocking_passed: bool
    expected_mode: str
    actual_mode: Optional[str] = None
    expected_outcome: str
    actual_outcome: Optional[str] = None
    dimension_scores: EvalDimensionScores = Field(default_factory=EvalDimensionScores)
    blocking_gate_results: Dict[str, bool] = Field(default_factory=dict)
    reason_codes: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    created_at: datetime


class EvalRunResult(BaseModel):
    eval_run_id: str
    dataset_path: str
    model_mode: Literal["mock", "real"]
    total_cases: int
    passed_cases: int
    failed_cases: int
    blocking_gate_results: Dict[str, bool] = Field(default_factory=dict)
    aggregate_scores: Dict[str, float] = Field(default_factory=dict)
    failure_case_ids: List[str] = Field(default_factory=list)
    real_model_validation_blocked: bool = False
    blocker_code: Optional[str] = None
    model_names: List[str] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    estimated_cost: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    created_at: datetime
    completed_at: Optional[datetime] = None

