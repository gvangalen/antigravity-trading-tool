"""Bounded structured selection between existing FINN V2 contracts.

The selector receives a small manifest-derived candidate set.  It cannot add
operations, modes, tools or policies; the caller validates its result against
the same immutable registry before allowing execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.utils import openai_client


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
    """Use strict JSON only when deterministic registry ranking is tied."""

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
        response = self._provider(
            prompt=str({
                "message": message,
                "facts": dict(facts),
                "verified_context": self._safe_context(verified_context),
                "candidate_operations": [
                    {
                        "operation_id": contract.operation_id,
                        "description": contract.semantic_description,
                        "required_inputs": contract.required_inputs,
                        "required_entities": contract.required_entities,
                        "required_scopes": contract.required_scopes,
                    }
                    for contract in candidate_contracts
                ],
            }),
            system_role=(
                "Select exactly one FINN operation from the supplied candidates. "
                "Do not select tools, modes, policies, or unsupported operations. "
                "Return the strict schema only."
            ),
            schema=self._schema(candidate_ids),
            timeout_seconds=4,
            client_max_retries=0,
        )
        if response.get("error"):
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
    def _schema(candidate_ids: tuple[str, ...]) -> dict[str, object]:
        return {
            "name": "finn_v2_operation_selection",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "operation_id": {"type": "string", "enum": list(candidate_ids)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "entities": {"type": "object", "additionalProperties": {"type": "string"}},
                    "target_asset": {"type": ["string", "null"]},
                    "conversation_reference": {"type": ["string", "null"]},
                    "missing_inputs": {"type": "array", "items": {"type": "string"}},
                    "ambiguity_reason": {"type": ["string", "null"]},
                },
                "required": [
                    "operation_id", "confidence", "entities", "target_asset",
                    "conversation_reference", "missing_inputs", "ambiguity_reason",
                ],
            },
        }

    @staticmethod
    def _safe_context(context: Optional[Mapping[str, object]]) -> Mapping[str, object]:
        raw = context or {}
        return {
            key: raw[key]
            for key in ("operation_id", "contract_version", "mode", "resolved_entities", "evidence_refs")
            if key in raw
        }

    @staticmethod
    def _optional_text(value: object) -> Optional[str]:
        return str(value) if isinstance(value, str) and value else None
