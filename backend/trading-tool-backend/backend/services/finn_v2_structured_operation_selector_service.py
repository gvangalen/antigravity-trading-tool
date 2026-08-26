"""Strict model-first selection from the immutable FINN V2 manifest."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.utils import openai_client
from backend.utils.openai_client import StructuredOutputSpec


@dataclass(frozen=True)
class FinnV2StructuredOperationSelection:
    operation_id: str
    confidence: float
    entities: Mapping[str, str]
    target_asset: Optional[str]
    conversation_reference: Optional[str]
    missing_inputs: tuple[str, ...]
    ambiguity_reason: Optional[str]


class FinnV2StructuredOperationSelectorService:
    """Select one registry contract; never expose tools, modes, or policy."""

    def __init__(self, provider: Optional[Callable[..., Mapping[str, Any]]] = None):
        self._provider = provider or openai_client.ask_gpt_structured_response

    def select(
        self,
        *,
        message: str,
        candidate_contracts: tuple[OperationContract, ...],
        facts: Mapping[str, object],
        verified_context: Optional[Mapping[str, object]],
    ) -> tuple[Optional[FinnV2StructuredOperationSelection], Optional[str]]:
        candidate_ids = tuple(contract.operation_id for contract in candidate_contracts)
        if not candidate_ids:
            return None, "selector_no_candidates"
        try:
            response = self._provider(
                prompt=str({
                    "message": message,
                    "facts": dict(facts),
                    "conversation_state": self._safe_context(verified_context),
                    "operation_manifest": [
                        {
                            "operation_id": contract.operation_id,
                            "semantic_description": contract.semantic_description,
                            "domain": contract.domain,
                            "supported": contract.supported,
                            "executable": bool(contract.execution_adapter),
                            "required_entities": contract.required_entities,
                            "required_conversation_state": contract.requires_verified_context,
                            "required_inputs": contract.required_inputs,
                            "positive_examples": contract.positive_examples,
                            "hard_negative_examples": contract.negative_examples,
                            "allowed_action_polarities": contract.allowed_action_polarities,
                        }
                        for contract in candidate_contracts
                    ],
                }),
                system_role=(
                    "Select exactly one FINN operation from the supplied immutable manifest. "
                    "Do not select modes, tools, scopes, policies, or execution. "
                    "Use clarify_request for ambiguity, unsupported_financial_operation for "
                    "understood but unsupported finance or trading-product requests, and off_topic "
                    "only for requests unrelated to finance, FINN, or a trading workspace. "
                    "When conversation_state has last_verified_context and the user asks for the "
                    "basis, evidence, a shorter version, or a reformulation of the prior answer, "
                    "select the corresponding lineage operation and set conversation_reference to "
                    "previous_verified_response. Treat an overview of a user's setup, strategy, "
                    "and bot as read_active_plan, not as ambiguity. "
                    "Return the strict schema only."
                ),
            output_spec=StructuredOutputSpec(
                name="finn_v2_operation_selection",
                schema=self._schema(candidate_ids),
            ),
                timeout_seconds=self._timeout_seconds(),
                client_max_retries=0,
            )
        except Exception as exc:
            return None, f"selector_provider_exception:{type(exc).__name__}"
        if response.get("error"):
            if response["error"] == "structured_schema_contract_error":
                return None, "selector_schema_contract_error"
            return None, f"selector_{response['error']}"
        parsed = response.get("parsed")
        if not isinstance(parsed, Mapping):
            return None, "selector_schema_invalid"
        operation_id = str(parsed.get("operation_id") or "")
        if operation_id not in candidate_ids:
            return None, "selector_operation_outside_candidates"
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            return None, "selector_confidence_invalid"
        raw_entities = parsed.get("entities")
        if not isinstance(raw_entities, Mapping):
            return None, "selector_entities_invalid"
        raw_inputs = parsed.get("missing_inputs")
        if not isinstance(raw_inputs, list) or not all(isinstance(item, str) for item in raw_inputs):
            return None, "selector_missing_inputs_invalid"
        return FinnV2StructuredOperationSelection(
            operation_id=operation_id,
            confidence=float(confidence),
            entities={str(key): str(value) for key, value in raw_entities.items()},
            target_asset=self._optional_text(parsed.get("target_asset")),
            conversation_reference=self._optional_text(parsed.get("conversation_reference")),
            missing_inputs=tuple(raw_inputs),
            ambiguity_reason=self._optional_text(parsed.get("ambiguity_reason")),
        ), None

    @staticmethod
    def _timeout_seconds() -> int:
        """Keep the provider deadline above normal Responses API latency."""
        return max(15, int(os.getenv("FINN_V2_SELECTOR_TIMEOUT_SECONDS", "30")))

    @staticmethod
    def _schema(candidate_ids: tuple[str, ...]) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "operation_id": {"type": "string", "enum": list(candidate_ids)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                # OpenAI strict JSON Schema requires closed objects to list
                # every property in required. Nullable fields preserve the
                # absence of an entity without reopening the schema.
                "entities": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "concept": {"type": ["string", "null"]},
                        "asset": {"type": ["string", "null"]},
                        "setup_id": {"type": ["string", "null"]},
                        "strategy_id": {"type": ["string", "null"]},
                        "bot_id": {"type": ["string", "null"]},
                    },
                    "required": ["concept", "asset", "setup_id", "strategy_id", "bot_id"],
                },
                "target_asset": {"type": ["string", "null"]},
                "conversation_reference": {"type": ["string", "null"]},
                "missing_inputs": {"type": "array", "items": {"type": "string"}},
                "ambiguity_reason": {"type": ["string", "null"]},
            },
            "required": [
                "operation_id", "confidence", "entities", "target_asset",
                "conversation_reference", "missing_inputs", "ambiguity_reason",
            ],
        }

    @staticmethod
    def _safe_context(context: Optional[Mapping[str, object]]) -> Mapping[str, object]:
        raw = context or {}
        return {
            key: raw[key]
            for key in ("last_verified_context", "active_guided_operation", "last_turn_diagnostics")
            if key in raw
        }

    @staticmethod
    def _optional_text(value: object) -> Optional[str]:
        return str(value) if isinstance(value, str) and value else None
