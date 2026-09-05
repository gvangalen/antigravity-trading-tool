"""Versioned, run-bound FINN V2 runtime contract.

New runs create this contract before any selector, resolver, tool, or reasoning
phase. Terminal delivery is a projection of persisted contract state, never a
second reconstruction from orchestration artifacts.
"""
from __future__ import annotations

from hashlib import sha256
import json
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


FINN_RUNTIME_CONTRACT_VERSION = "2026-09-03.runtime-contract.v1"
FINN_PUBLIC_PROJECTION_VERSION = "2026-09-03.terminal-projection.v1"
# Persistent contracts use the same semantic version as the public projection,
# but retain a separate name for the repository boundary.
RUNTIME_CONTRACT_VERSION = "2026-09-04.runtime-contract.v1"
PENDING_STATUS = "pending"


class RuntimeContractConflictError(RuntimeError):
    pass


class RuntimeContractImmutableFieldError(ValueError):
    pass


class FinnRuntimeContract(BaseModel):
    """Safe terminal provenance for exactly one FINN run."""

    contract_version: str = FINN_RUNTIME_CONTRACT_VERSION
    run_id: str
    conversation_id: Optional[str] = None
    identity: Dict[str, Any] = Field(default_factory=dict)
    immutable_intent: Dict[str, Any] = Field(default_factory=dict)
    initial_operation_id: Optional[str] = None
    requested_mode: Optional[str] = None
    canonical_target: Optional[str] = None
    target_type: Optional[str] = None
    target_source: Optional[str] = None
    original_target_text: Optional[str] = None
    conversation_reference: Optional[str] = None
    conversation_reference_kind: Optional[str] = None
    loaded_state_revision: Optional[int] = None
    execution_requirements: Dict[str, Any] = Field(default_factory=dict)
    validation_result: Dict[str, Any] = Field(default_factory=dict)
    policy_result: Dict[str, Any] = Field(default_factory=dict)
    provider_result: Dict[str, Any] = Field(default_factory=dict)
    verifier_result: Dict[str, Any] = Field(default_factory=dict)
    final_operation_id: Optional[str] = None
    final_mode: Optional[str] = None
    operation_change_reason: Optional[str] = None
    terminal_response_type: Optional[str] = None
    terminal_status: Optional[str] = None
    lineage_state_update: Dict[str, Any] = Field(default_factory=dict)
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    total_ms: Optional[float] = None
    public_projection_version: str = FINN_PUBLIC_PROJECTION_VERSION
    public_projection_hash: Optional[str] = None

    class Config:
        extra = "forbid"

    def public_projection(self) -> Dict[str, Any]:
        """Return the only transport-visible contract projection.

        No raw provider payload, evidence body, user message, or tool result is
        included here. These values can safely accompany every poll and SSE
        event without creating artifact fan-out or leaking sensitive context.
        """
        return {
            "version": self.public_projection_version,
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "initial_operation_id": self.initial_operation_id,
            "final_operation_id": self.final_operation_id,
            "requested_mode": self.requested_mode,
            "final_mode": self.final_mode,
            "operation_change_reason": self.operation_change_reason,
            "canonical_target": self.canonical_target,
            "target_type": self.target_type,
            "target_source": self.target_source,
            "conversation_reference": self.conversation_reference,
            "conversation_reference_kind": self.conversation_reference_kind,
            "validation": self.validation_result,
            "policy": self.policy_result,
            "provider": self.provider_result,
            "verifier": self.verifier_result,
            "lineage": self.lineage_state_update,
            "terminal_response_type": self.terminal_response_type,
            "terminal_status": self.terminal_status,
            "timings_ms": self.timings_ms,
            "total_ms": self.total_ms,
        }

    def with_projection_hash(self) -> "FinnRuntimeContract":
        payload = self.public_projection()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return self.copy(update={"public_projection_hash": sha256(encoded).hexdigest()})


def build_terminal_runtime_contract(
    *,
    run: Any,
    artifacts: Dict[str, Any],
    terminal_status: str,
    final_mode: Optional[str],
    terminal_response_type: str,
) -> FinnRuntimeContract:
    """Materialize one immutable terminal contract from persisted artifacts."""
    orchestrator = dict(artifacts.get("orchestrator_result") or {})
    tool_plan = dict(orchestrator.get("tool_plan") or {})
    plan = dict(tool_plan.get("request_plan") or {})
    reasoning = dict(artifacts.get("reasoning_result") or {})
    reasoning_result = dict(reasoning.get("result") or {})
    verifier = dict(artifacts.get("verifier_result") or {})
    validation = dict(artifacts.get("validation_result") or {})
    policy = dict(artifacts.get("policy_result") or {})
    operation_state = dict(plan.get("operation_state") or {})
    provenance = dict(reasoning_result.get("reasoning_provenance") or {})
    timings = {
        key: value for key, value in {
            "reasoning_provider": reasoning.get("latency_ms"),
        }.items() if isinstance(value, (int, float))
    }
    contract = FinnRuntimeContract(
        run_id=str(getattr(run, "id", "") or ""),
        conversation_id=getattr(run, "conversation_id", None),
        identity={"user_id": getattr(run, "user_id", None), "trace_id": getattr(run, "trace_id", None)},
        immutable_intent={
            "operation_id": plan.get("initial_operation_id") or plan.get("operation_id"),
            "requested_action": plan.get("requested_action"),
            "selector_source": plan.get("selector_source"),
            "selector_confidence": plan.get("selector_confidence"),
        },
        initial_operation_id=plan.get("initial_operation_id") or plan.get("operation_id"),
        requested_mode=orchestrator.get("interaction_mode") or plan.get("interaction_mode"),
        canonical_target=plan.get("target_asset"),
        target_type="asset" if plan.get("target_asset") else None,
        target_source=plan.get("target_asset_source"),
        original_target_text=plan.get("referenced_asset"),
        conversation_reference=plan.get("conversation_reference"),
        conversation_reference_kind=plan.get("conversation_reference_kind"),
        loaded_state_revision=operation_state.get("state_revision"),
        execution_requirements={
            "confirmation_required": bool(plan.get("confirmation_required")),
            "missing_inputs": list(plan.get("missing_information") or []),
        },
        validation_result={"integrity_status": validation.get("integrity_status"), "validation_id": validation.get("validation_id")},
        policy_result={"allowed": policy.get("allowed"), "policy_class": policy.get("policy_class"), "blocking_codes": policy.get("blocking_codes") or []},
        provider_result={
            "status": provenance.get("provider_status") or reasoning.get("status"),
            "parse_status": provenance.get("parse_status"),
            "validation_status": provenance.get("validation_status"),
            "response_id": provenance.get("provider_response_id"),
        },
        verifier_result={"passed": verifier.get("passed"), "action": verifier.get("action"), "reason_codes": verifier.get("reason_codes") or []},
        final_operation_id=plan.get("operation_id"),
        final_mode=final_mode,
        operation_change_reason=plan.get("operation_change_reason"),
        terminal_response_type=terminal_response_type,
        terminal_status=terminal_status,
        lineage_state_update={
            "reference_kind": plan.get("conversation_reference_kind"),
            "active_flow_operation_id": plan.get("active_flow_operation_id"),
            "clarification_state_transition": plan.get("clarification_state_transition"),
        },
        timings_ms=timings,
        total_ms=reasoning.get("latency_ms") if isinstance(reasoning.get("latency_ms"), (int, float)) else None,
    )
    return contract.with_projection_hash()


def new_runtime_contract_state(*, run: Any, contract_id: str) -> Dict[str, Any]:
    """Create authoritative persisted state before selector execution."""
    return {
        "contract_id": contract_id,
        "contract_version": RUNTIME_CONTRACT_VERSION,
        "identity": {
            "run_id": run.id,
            "conversation_id": run.conversation_id,
            "trace_id": run.trace_id,
            "user_id": run.user_id,
        },
        "immutable_intent": {"message": run.message},
        "initial_operation_id": None,
        "requested_mode": None,
        "canonical_target": None,
        "target_type": None,
        "target_source": None,
        "original_target_text": None,
        "conversation_reference": None,
        "conversation_reference_kind": None,
        "selector_provenance": {},
        "lineage_state": {},
        "guided_state": {},
        "final_operation_id": None,
        "final_mode": None,
        "operation_change_reason": None,
        "terminal_status": PENDING_STATUS,
        "terminal_response_type": None,
        "transition_log": [],
    }


def record_initial_intent(state: Dict[str, Any], *, operation_id: str, requested_mode: str) -> Dict[str, Any]:
    """Write the selector decision exactly once; idempotent replay is harmless."""
    state = dict(state)
    existing_operation = state.get("initial_operation_id")
    existing_mode = state.get("requested_mode")
    if existing_operation is not None and (existing_operation != operation_id or existing_mode != requested_mode):
        raise RuntimeContractImmutableFieldError("runtime_contract_initial_intent_is_immutable")
    state["initial_operation_id"] = operation_id
    state["requested_mode"] = requested_mode
    return state


def record_selection(
    state: Dict[str, Any],
    *,
    canonical_target: Optional[str],
    target_source: Optional[str],
    original_target_text: Optional[str],
    target_type: Optional[str],
    conversation_reference: Optional[str],
    conversation_reference_kind: Optional[str],
    selector_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist the canonical target and selector provenance before tools run."""
    state = dict(state)
    for field, value in {
        "canonical_target": canonical_target,
        "target_source": target_source,
        "original_target_text": original_target_text,
        "target_type": target_type,
    }.items():
        existing = state.get(field)
        if existing is not None and existing != value:
            raise RuntimeContractImmutableFieldError(f"runtime_contract_{field}_is_immutable")
        if existing is None:
            state[field] = value
    state["conversation_reference"] = conversation_reference
    state["conversation_reference_kind"] = conversation_reference_kind
    state["selector_provenance"] = dict(selector_provenance or {})
    return state


def record_conversation_state(
    state: Dict[str, Any], *, lineage_state: Dict[str, Any], guided_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Persist typed, safe continuation state for the next contract run."""
    state = dict(state)
    state["lineage_state"] = dict(lineage_state or {})
    state["guided_state"] = dict(guided_state or {})
    return state


def terminal_projection(
    state: Dict[str, Any],
    *,
    status: str,
    mode: Optional[str],
    response: Optional[Dict[str, Any]],
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the sole public terminal read model for a persisted contract."""
    identity = dict(state.get("identity") or {})
    timings_ms: Dict[str, int] = {}
    timestamps = dict(state.get("phase_timestamps") or {})
    try:
        created_at = datetime.fromisoformat(str(timestamps["created_at"]).replace("Z", "+00:00"))
        terminal_at = datetime.fromisoformat(str(timestamps["terminal_at"]).replace("Z", "+00:00"))
        timings_ms["total"] = max(0, int((terminal_at - created_at).total_seconds() * 1000))
        previous_at = created_at
        for phase in ("queued", "collecting", "planned", "reasoning", "verifying"):
            if phase not in timestamps:
                continue
            current_at = datetime.fromisoformat(str(timestamps[phase]).replace("Z", "+00:00"))
            timings_ms[f"until_{phase}"] = max(0, int((current_at - previous_at).total_seconds() * 1000))
            previous_at = current_at
        timings_ms["terminal_persist"] = max(0, int((terminal_at - previous_at).total_seconds() * 1000))
    except (KeyError, TypeError, ValueError):
        # Historical projections remain readable without invented timings.
        timings_ms = {}
    return {
        "version": FINN_PUBLIC_PROJECTION_VERSION,
        "projection_version": RUNTIME_CONTRACT_VERSION,
        "contract_id": state.get("contract_id"),
        "run_id": identity.get("run_id"),
        "conversation_id": identity.get("conversation_id"),
        "trace_id": identity.get("trace_id"),
        "initial_operation_id": state.get("initial_operation_id"),
        "final_operation_id": state.get("final_operation_id") or state.get("initial_operation_id"),
        "requested_mode": state.get("requested_mode"),
        "final_mode": mode or state.get("final_mode") or state.get("requested_mode"),
        "operation_change_reason": state.get("operation_change_reason"),
        "canonical_target": state.get("canonical_target"),
        "target_source": state.get("target_source"),
        "conversation_reference": state.get("conversation_reference"),
        "terminal_status": status,
        "terminal_response_type": state.get("terminal_response_type") or ("failure" if status == "failed" else "response"),
        "timings_ms": timings_ms,
        "error_code": error_code,
        "response": dict(response or {}),
    }
