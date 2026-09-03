"""Versioned, run-bound FINN V2 runtime contract.

The contract is intentionally built once at the terminal persistence boundary.
It records immutable selector intent separately from the final safe response so
transport clients never need to reconstruct an operation from artifacts.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


FINN_RUNTIME_CONTRACT_VERSION = "2026-09-03.runtime-contract.v1"
FINN_PUBLIC_PROJECTION_VERSION = "2026-09-03.terminal-projection.v1"


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

