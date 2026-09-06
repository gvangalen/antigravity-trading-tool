"""Strict model-first selection from the immutable FINN V2 manifest."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog
from backend.services.asset_catalog_service import resolve_catalog_symbol
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
    # The provider interprets language into this typed frame.  The operation
    # is resolved separately against the immutable registry.
    semantic_frame: Mapping[str, object] = field(default_factory=dict)


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
        timeout_seconds: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
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
                    # The provider needs semantic contract identity, not the
                    # full runtime registry. Sending tool and policy metadata
                    # here made every free-text turn pay for thousands of
                    # irrelevant tokens before the worker could proceed.
                    "operation_manifest": self._selector_manifest(candidate_contracts),
                }),
                system_role=(
                    "First extract a typed semantic frame, then select exactly one FINN operation from the supplied immutable manifest. "
                    "Do not select modes, tools, scopes, policies, or execution. "
                    "Treat the supplied facts as typed constraints. A capability discourse is always the "
                    "capability contract, even when the question names a plan, setup, strategy, bot, or "
                    "prior conversation. A concrete bot question about identity, configuration, linkage, "
                    "or status is a READ contract; select evaluate_bot only for an actual assessment or "
                    "an implication of a previous assessment. "
                    "Use clarify_request for ambiguity, unsupported_financial_operation for "
                    "understood but unsupported finance or trading-product requests, and off_topic "
                    "only for requests unrelated to finance, FINN, or a trading workspace. "
                    "When conversation_state has last_verified_context or last_degraded_context and the user asks for the "
                    "basis, recorded facts, evidence, a shorter version, or a reformulation of the prior answer, "
                    "select the corresponding lineage operation and set conversation_reference to "
                    "previous_verified_response. A degraded context permits only evidence explanation or safe reformulation, "
                    "never promotion of an unverified financial conclusion. Treat an overview of a user's setup, strategy, "
                    "and bot as read_active_plan, not as ambiguity. "
                    "When conversation_state has last_released_context and the user asks to repeat, restate, shorten, "
                    "simplify, or restyle the immediately released safe response, select reformulate_previous_response. "
                    "Released lineage permits reformulation only; it never authorizes an evidence explanation, action, "
                    "or new financial conclusion. "
                    "A question about what a prior assessment changes, supports, or requires is an evidence "
                    "explanation, even if it mentions a linked bot. A request to repeat, restate, shorten, "
                    "or keep within previously released safe content is a reformulation, not evidence explanation. "
                    "When conversation_state has last_safe_terminal_context and the user asks why the immediately "
                    "previous request was outside FINN's supported boundary, select explain_previous_evidence. "
                    "That contract may explain only the recorded boundary reason and must not create financial lineage. "
                    "For a requested change, select a write contract only when the request identifies "
                    "its required FINN object. A create contract with an identified object may be selected "
                    "even when its remaining required slots are absent; list those slots in missing_inputs. "
                    "Generic requests to change trading settings, configuration, or preferences without an "
                    "identified FINN object must use clarify_request. A request "
                    "that diagnoses the robustness, fragility, quality, risk, or evidential support of an "
                    "explicit plan or trading approach is an evaluation of that plan, even without a ticker "
                    "or requested change; it is not a clarification request. "
                    "about portfolio management, investing, or trading remains financial even if no "
                    "ticker or FINN object is named, so use unsupported_financial_operation rather "
                    "than off_topic. Requests for autonomous buy, sell, investment, portfolio, or "
                    "trading decisions are financial unsupported operations, never off_topic. "
                    "when no supported contract exists. "
                    "When facts.entities includes indicator_configuration and the request is a read, "
                    "select read_indicator_configuration unless facts.discourse_act is evaluation. "
                    "A request for the current selected instrument, symbol, market, or workspace asset "
                    "is read_active_asset even if it does not name a ticker; do not ask for clarification "
                    "when FINN can read that active workspace state. "
                    "When conversation_state contains active_guided_operation, a short answer to its "
                    "next missing field continues that exact operation. Retain its collected values, "
                    "target and operation_id; do not switch it to clarify_request merely because the "
                    "short answer does not repeat the original object. "
                    "The semantic frame records meaning, not implementation: goal, object, explicit setup values, "
                    "persistence intent, all explicitly requested information scopes, and an antecedent kind. When a request "
                    "names linked setup, strategy and bot information, put each in requested_scopes so the registry can select "
                    "the complete graph read. Do not put a setup type in concept or a timeframe in setup_type. "
                    "A named value is supplied, never missing. A request not to save or write remains a create request with proposal_only persistence. "
                    "Return the strict schema only."
                ),
            output_spec=StructuredOutputSpec(
                name="finn_v2_operation_selection",
                schema=self._schema(candidate_ids),
            ),
                timeout_seconds=self._timeout_seconds(timeout_seconds),
                max_output_tokens=max(160, min(300, int(max_output_tokens or 240))),
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
        contract = next(contract for contract in candidate_contracts if contract.operation_id == operation_id)
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            return None, "selector_confidence_invalid"
        raw_entities = parsed.get("entities")
        if not isinstance(raw_entities, Mapping):
            return None, "selector_entities_invalid"
        raw_inputs = parsed.get("missing_inputs")
        if not isinstance(raw_inputs, list) or not all(isinstance(item, str) for item in raw_inputs):
            return None, "selector_missing_inputs_invalid"
        semantic_frame = self._semantic_frame(parsed.get("semantic_frame"))
        entities = {str(key): self._entity_text(value) for key, value in raw_entities.items()}
        self._project_frame_entities(entities=entities, frame=semantic_frame)
        self._canonicalize_entities(entities)
        self._project_contract_entities(contract=contract, message=message, entities=entities)
        canonical_entity_asset = resolve_catalog_symbol(entities.get("asset"))
        if canonical_entity_asset:
            entities["asset"] = canonical_entity_asset
        target_asset = resolve_catalog_symbol(
            self._optional_text(parsed.get("target_asset"))
            or self._optional_text(raw_entities.get("asset"))
            or self._optional_text(entities.get("asset"))
            or self._optional_text(facts.get("referenced_asset"))
        ) or None
        # The canonical entity projection can resolve an asset after raw
        # provider values are read. Keep that typed target for all consumers.
        target_asset = target_asset or resolve_catalog_symbol(entities.get("asset"))
        if target_asset and not entities.get("asset"):
            entities["asset"] = target_asset
        elif target_asset:
            entities["asset"] = target_asset
        if not entities.get("asset"):
            explicit_asset = self._optional_text(facts.get("referenced_asset"))
            if explicit_asset:
                entities["asset"] = explicit_asset
        return FinnV2StructuredOperationSelection(
            operation_id=operation_id,
            confidence=float(confidence),
            # Normalize an occasional JSON delimiter preserved inside a
            # structured string before the entity reaches contract consumers.
            entities=entities,
            target_asset=target_asset,
            conversation_reference=(
                "previous_verified_response"
                if self._may_project_conversation_reference(
                    contract=contract,
                    raw_reference=self._optional_text(parsed.get("conversation_reference")),
                    entities=entities,
                    context=verified_context,
                )
                else None
            ),
            missing_inputs=self._canonical_missing_inputs(contract=contract, raw_inputs=raw_inputs, facts=facts),
            ambiguity_reason=self._optional_text(parsed.get("ambiguity_reason")),
            semantic_frame=semantic_frame,
        ), None

    @staticmethod
    def _timeout_seconds(phase_budget_seconds: Optional[int] = None) -> int:
        """Keep the provider deadline above normal Responses API latency."""
        if phase_budget_seconds is not None:
            return max(3, int(phase_budget_seconds))
        return max(15, int(os.getenv("FINN_V2_SELECTOR_TIMEOUT_SECONDS", "30")))

    @staticmethod
    def _selector_manifest(candidate_contracts: tuple[OperationContract, ...]) -> list[dict[str, object]]:
        """Project registry contracts into the minimal model-facing schema.

        This is deliberately a projection, never a second registry or a
        candidate filter: every offered contract remains selectable and the
        immutable registry still validates the returned operation.
        """
        return [
            {
                "operation_id": contract.operation_id,
                "description": FinnV2StructuredOperationSelectorService._selector_summary(
                    contract.semantic_description
                ),
                "domain": contract.domain,
                "supported": contract.supported,
                "required_entities": list(contract.required_entities),
                "required_inputs": list(contract.required_inputs),
                "requires_verified_context": contract.requires_verified_context,
                "canonical_action_polarity": contract.action_polarity.value,
            }
            for contract in candidate_contracts
        ]

    @staticmethod
    def _selector_summary(description: str, *, maximum_characters: int = 160) -> str:
        """Keep the first complete registry statement for model selection."""
        sentence = re.split(r"(?<=[.!?])\s+", str(description or ""), maxsplit=1)[0].strip()
        if len(sentence) <= maximum_characters:
            return sentence
        truncated = sentence[:maximum_characters].rsplit(" ", 1)[0].rstrip(" ,;:")
        return f"{truncated}."

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
                        "setup_type": {"type": ["string", "null"]},
                        "timeframe": {"type": ["string", "null"]},
                        "name": {"type": ["string", "null"]},
                    },
                    "required": ["concept", "asset", "setup_id", "strategy_id", "bot_id", "setup_type", "timeframe", "name"],
                },
                "target_asset": {"type": ["string", "null"]},
                "conversation_reference": {"type": ["string", "null"]},
                "missing_inputs": {"type": "array", "items": {"type": "string"}},
                "ambiguity_reason": {"type": ["string", "null"]},
                "semantic_frame": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "goal": {"type": ["string", "null"]},
                        "object": {"type": ["string", "null"]},
                        "target_asset": {"type": ["string", "null"]},
                        "setup_type": {"type": ["string", "null"]},
                        "timeframe": {"type": ["string", "null"]},
                        "name": {"type": ["string", "null"]},
                        "action_polarity": {"type": ["string", "null"]},
                        "persistence_intent": {"type": ["string", "null"]},
                        "reference_kind": {"type": ["string", "null"]},
                        "new_data_required": {"type": ["boolean", "null"]},
                        "ambiguities": {"type": "array", "items": {"type": "string"}},
                        "supplied_inputs": {"type": "array", "items": {"type": "string"}},
                        "requested_scopes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "goal", "object", "target_asset", "setup_type", "timeframe", "name",
                        "action_polarity", "persistence_intent", "reference_kind", "new_data_required",
                        "ambiguities", "supplied_inputs", "requested_scopes",
                    ],
                },
            },
            "required": [
                "operation_id", "confidence", "entities", "target_asset",
                "conversation_reference", "missing_inputs", "ambiguity_reason", "semantic_frame",
            ],
        }

    @staticmethod
    def _safe_context(context: Optional[Mapping[str, object]]) -> Mapping[str, object]:
        raw = context or {}
        return {
            key: raw[key]
            for key in (
                "last_verified_context", "last_degraded_context", "last_released_context", "active_guided_operation",
                "last_safe_terminal_context", "last_turn_diagnostics",
            )
            if key in raw
        }

    @staticmethod
    def _optional_text(value: object) -> Optional[str]:
        return str(value) if isinstance(value, str) and value else None

    @staticmethod
    def _entity_text(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip().strip(",;:)}]\"'").strip()

    @classmethod
    def _semantic_frame(cls, value: object) -> Mapping[str, object]:
        """Keep the provider's semantic facts typed and presentation-safe."""
        if not isinstance(value, Mapping):
            return {}
        frame: dict[str, object] = {}
        for field in (
            "goal", "object", "target_asset", "setup_type", "timeframe", "name",
            "action_polarity", "persistence_intent", "reference_kind",
        ):
            item = cls._optional_text(value.get(field))
            if item:
                frame[field] = item
        if isinstance(value.get("new_data_required"), bool):
            frame["new_data_required"] = value["new_data_required"]
        for field in ("ambiguities", "supplied_inputs", "requested_scopes"):
            items = value.get(field)
            if isinstance(items, list) and all(isinstance(item, str) for item in items):
                frame[field] = tuple(item for item in items if item)
        return frame

    @staticmethod
    def _project_frame_entities(*, entities: dict[str, str], frame: Mapping[str, object]) -> None:
        """One projection prevents raw frame slots and response entities drifting."""
        for frame_field, entity_field in (
            ("target_asset", "asset"), ("setup_type", "setup_type"),
            ("timeframe", "timeframe"), ("name", "name"),
        ):
            value = frame.get(frame_field)
            if isinstance(value, str) and value.strip() and not entities.get(entity_field):
                entities[entity_field] = value.strip()

    @staticmethod
    def _canonicalize_entities(entities: dict[str, str]) -> None:
        """Project selector telemetry through the same typed setup catalog as inputs."""
        if entities.get("setup_type"):
            entities["setup_type"] = str(
                FinnV2SetupInputCatalog.canonical_setup_type(entities["setup_type"])
                or entities["setup_type"]
            )
        if entities.get("timeframe"):
            entities["timeframe"] = str(
                FinnV2SetupInputCatalog.canonical_timeframe(entities["timeframe"])
                or entities["timeframe"]
            )
        if entities.get("name"):
            entities["name"] = FinnV2SetupInputCatalog.display_name(entities["name"]) or ""

    @staticmethod
    def _project_contract_entities(
        *, contract: OperationContract, message: str, entities: dict[str, str]
    ) -> None:
        """Keep selector telemetry aligned with the selected typed contract."""
        if contract.operation_id != "create_setup":
            return
        setup_type = FinnV2SetupInputCatalog.setup_type_from_text(message)
        if setup_type:
            entities["setup_type"] = setup_type
        # A DCA setup is a typed setup variant, not an educational concept in
        # the create-setup response projection.
        entities["concept"] = ""

    @staticmethod
    def _may_project_conversation_reference(
        *,
        contract: OperationContract,
        raw_reference: Optional[str],
        entities: Mapping[str, str],
        context: Optional[Mapping[str, object]],
    ) -> bool:
        """Accept only registry-declared, verifiable lineage references."""
        if contract.requires_verified_context:
            return bool(raw_reference)
        if not contract.contextual_reference_inputs:
            return False
        verified = dict((context or {}).get("last_verified_context") or {})
        resolved = dict(verified.get("resolved_entities") or {})
        matches_verified_entity = any(
            str(entities.get(field) or "") == str(resolved.get(field) or "")
            and bool(resolved.get(field))
            for field in contract.contextual_reference_inputs
        )
        # The provider's nullable reference field is telemetry. A contextual
        # action remains safely linked when it selected exactly the persisted
        # registry-declared entity, even if that nullable field is omitted.
        return matches_verified_entity

    @staticmethod
    def _canonical_missing_inputs(*, contract: OperationContract, raw_inputs: list[str], facts: Mapping[str, object]) -> tuple[str, ...]:
        """Keep selector telemetry within the chosen contract's typed slots."""
        missing = [item for item in raw_inputs if item in contract.required_inputs]
        referenced_asset = str(facts.get("referenced_asset") or "").strip()
        if referenced_asset:
            missing = [item for item in missing if item not in {"asset", "symbol"}]
        return tuple(dict.fromkeys(missing))
