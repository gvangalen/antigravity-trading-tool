"""Registry-backed semantic operation selection for new FINN V2 runs.

Only the structured provider selects an operation for free user text.  This
module may normalize and validate facts, but must never turn those facts back
into a second local intent router.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry, OperationContract
from backend.services.finn_v2_request_preprocessor_service import (
    FinnV2PreprocessedRequest,
    FinnV2RequestPreprocessorService,
)
from backend.services.finn_v2_structured_operation_selector_service import (
    FinnV2StructuredOperationSelectorService,
)
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


@dataclass(frozen=True)
class SemanticOperationClassification:
    operation_id: str
    action: str
    domain: str
    discourse: str
    confidence: str
    selector_source: str = "deterministic"
    candidate_operation_ids: tuple[str, ...] = ()
    supported: bool = True
    reason_code: Optional[str] = None
    unsupported_capability: Optional[str] = None
    selected_entities: Mapping[str, str] = field(default_factory=dict)
    selected_target_asset: Optional[str] = None
    selected_conversation_reference: Optional[str] = None
    selected_missing_inputs: tuple[str, ...] = ()


class FinnV2OperationClassificationService:
    """Select an operation from registry metadata and conversation lineage."""

    def __init__(
        self,
        registry: Optional[FinnV2OperationRegistry] = None,
        preprocessor: Optional[FinnV2RequestPreprocessorService] = None,
        structured_selector: Optional[FinnV2StructuredOperationSelectorService] = None,
    ):
        self.registry = registry or FinnV2OperationRegistry()
        self.preprocessor = preprocessor or FinnV2RequestPreprocessorService()
        self.structured_selector = structured_selector or FinnV2StructuredOperationSelectorService()

    def classify(
        self,
        *,
        message: str,
        conversation_context: Optional[Mapping[str, object]] = None,
        workspace_hints: Optional[Mapping[str, object]] = None,
        client_context: Optional[Mapping[str, object]] = None,
    ) -> SemanticOperationClassification:
        facts = self.preprocessor.preprocess(
            message=message, workspace_hints=workspace_hints, client_context=client_context
        )
        candidates = self._selector_manifest()
        candidates = self._guided_candidates(facts=facts, context=conversation_context or {}, candidates=candidates)
        selection, error = self.structured_selector.select(
            message=message,
            candidate_contracts=candidates,
            facts={
                "entities": facts.explicit_entities,
                "action_polarity": facts.action_polarity,
                "discourse_act": facts.discourse_act,
                "referenced_asset": facts.referenced_asset,
                "normalized_text": facts.normalized_text,
                "domain_hint": facts.domain_hint,
                "financial_concept": facts.financial_concept,
            },
            verified_context=self._safe_conversation_state(conversation_context or {}),
        )
        safe_terminal_operations = {
            "clarify_request", "off_topic", "unsupported_financial_operation",
        }
        if selection is not None and (
            selection.confidence >= 0.75 or selection.operation_id in safe_terminal_operations
        ):
            return self._result(selection.operation_id, facts, "high", "structured", candidates, selection=selection)
        # A malformed, unavailable, or low-confidence selector response is a
        # typed terminal outcome.  Do not choose a nearby local operation:
        # doing so would reintroduce the retired keyword/default router.
        return self._result(
            "unavailable",
            facts,
            "none",
            "provider_unavailable",
            candidates,
            unsupported_capability=error or "selector_confidence_insufficient",
        )

    def _selector_manifest(self) -> tuple[OperationContract, ...]:
        """Return the versioned registry manifest, not retrieved local guesses."""
        return self.registry.list()

    def _guided_candidates(
        self,
        *,
        facts: FinnV2PreprocessedRequest,
        context: Mapping[str, object],
        candidates: tuple[OperationContract, ...],
    ) -> tuple[OperationContract, ...]:
        """Constrain a typed slot answer without selecting an operation locally."""
        active = context.get("active_guided_operation") or (
            context.get("operation_state") if not context.get("conversation_state_version") else None
        )
        if not isinstance(active, Mapping):
            return candidates
        operation_id = str(active.get("operation_id") or "")
        try:
            contract = self.registry.require_supported(operation_id)
        except ValueError:
            return candidates
        if not contract.required_inputs or not active.get("missing_required_inputs"):
            return candidates
        continues_slot_collection = self._is_guided_continuation(facts)
        if not continues_slot_collection:
            return candidates
        safe = tuple(
            item for item in candidates
            if item.operation_id in {contract.operation_id, "clarify_request", "unavailable"}
        )
        return safe or candidates

    @staticmethod
    def _is_guided_continuation(facts: FinnV2PreprocessedRequest) -> bool:
        return facts.discourse_act == "clarification_answer" or (
            facts.action_polarity == "read"
            and facts.discourse_act not in {
                "capability", "evaluation", "operation_request",
                "evidence_follow_up", "reformulation",
            }
            and facts.domain_hint != "off_topic"
            and set(facts.explicit_entities).issubset({"asset", "setup", "watchlist"})
        )

    @staticmethod
    def _safe_conversation_state(context: Mapping[str, object]) -> Mapping[str, object]:
        state = {
            key: context[key]
            for key in ("last_verified_context", "active_guided_operation", "operation_state", "last_turn_diagnostics")
            if key in context
        }
        # Older persisted records contain only a verified conclusion. Present
        # it as read-only lineage to the selector without reviving legacy
        # intent routing or allowing it to overwrite canonical V2 state.
        if (
            "last_verified_context" not in state
            and not context.get("conversation_state_version")
            and context.get("last_verified_conclusion")
        ):
            state["last_verified_context"] = {
                "conclusion": context.get("last_verified_conclusion"),
                "evidence_refs": context.get("last_evidence_refs") or (),
            }
        return state

    def _result(
        self,
        operation_id: str,
        facts: FinnV2PreprocessedRequest,
        confidence: str,
        source: str,
        candidates: tuple[OperationContract, ...],
        unsupported_capability: Optional[str] = None,
        selection=None,
    ) -> SemanticOperationClassification:
        contract = self.registry.get(operation_id)
        selected_entities = dict(getattr(selection, "entities", {}) or {})
        if operation_id == "explain_financial_concept" and facts.financial_concept:
            selected_entities["concept"] = facts.financial_concept
        selected_missing_inputs = self._resolved_missing_inputs(
            contract=contract,
            facts=facts,
            selected_entities=selected_entities,
            selector_missing=tuple(getattr(selection, "missing_inputs", ()) or ()),
        )
        return SemanticOperationClassification(
            operation_id=operation_id,
            action=self._contract_action(contract, facts.action_polarity),
            domain=contract.domain,
            discourse=facts.discourse_act,
            confidence=confidence,
            selector_source=source,
            candidate_operation_ids=tuple(item.operation_id for item in candidates),
            supported=contract.supported,
            reason_code=unsupported_capability or ("off_topic" if operation_id == "off_topic" else None),
            unsupported_capability=unsupported_capability,
            selected_entities=selected_entities,
            selected_target_asset=getattr(selection, "target_asset", None),
            selected_conversation_reference=getattr(selection, "conversation_reference", None),
            selected_missing_inputs=selected_missing_inputs,
        )

    @staticmethod
    def _resolved_missing_inputs(
        *,
        contract: OperationContract,
        facts: FinnV2PreprocessedRequest,
        selected_entities: Mapping[str, str],
        selector_missing: tuple[str, ...],
    ) -> tuple[str, ...]:
        if contract.operation_id == "clarify_request":
            return ("requested_change",)
        if not contract.required_inputs:
            return ()
        explicit = FinnV2OperationStateService().explicit_inputs(
            contract=contract,
            message=facts.normalized_text,
            explicit_asset=facts.referenced_asset,
        )
        if selected_entities.get("asset"):
            explicit.setdefault("asset", selected_entities["asset"])
            explicit.setdefault("symbol", selected_entities["asset"])
        for field in contract.required_inputs:
            if selected_entities.get(field):
                explicit.setdefault(field, selected_entities[field])
        unresolved = [
            field for field in contract.required_inputs
            if FinnV2OperationStateService._is_missing(explicit.get(field))
        ]
        # The contract and proven inputs are authoritative. Selector telemetry
        # may narrow ambiguity but cannot mark an explicitly supplied slot as
        # missing or invent a slot outside the selected contract.
        return tuple(field for field in unresolved if field in selector_missing or field not in explicit)

    @staticmethod
    def _contract_action(contract: OperationContract, raw_action: str) -> str:
        """Project through the immutable registry, never through local verbs."""
        del raw_action
        return contract.action_polarity.value


class FinnV2OperationClassificationValidator:
    """Validate a selected contract against deterministic request facts.

    This is the final selection boundary.  It deliberately validates only
    contract metadata and user-provided facts: it must not infer a different
    operation, mode, scope, tool or policy after selection.
    """

    def __init__(self, registry: Optional[FinnV2OperationRegistry] = None):
        self.registry = registry or FinnV2OperationRegistry()

    def validate(
        self,
        classification: SemanticOperationClassification,
        *,
        facts: Optional[FinnV2PreprocessedRequest] = None,
        conversation_context: Optional[Mapping[str, object]] = None,
    ) -> bool:
        return self.validation_error(
            classification,
            facts=facts,
            conversation_context=conversation_context,
        ) is None

    def validation_error(
        self,
        classification: SemanticOperationClassification,
        *,
        facts: Optional[FinnV2PreprocessedRequest] = None,
        conversation_context: Optional[Mapping[str, object]] = None,
    ) -> Optional[str]:
        try:
            contract = self.registry.require_supported(classification.operation_id)
        except ValueError:
            return "operation_not_supported"
        if classification.selector_source not in {"structured", "provider_unavailable"}:
            return "selector_source_invalid"
        if classification.action != contract.action_polarity.value:
            return "operation_canonical_action_mismatch"
        if facts is None:
            return None
        # A structured selector may validly continue a persisted guided
        # contract for a short slot answer. This validates lineage only; it
        # never selects an operation without the provider result.
        context = conversation_context or {}
        active = context.get("active_guided_operation") or (
            context.get("operation_state") if not context.get("conversation_state_version") else None
        )
        if (
            FinnV2OperationClassificationService._is_guided_continuation(facts)
            and isinstance(active, Mapping)
            and active.get("operation_id") == contract.operation_id
        ):
            return None
        # Manifest eligibility describes only the user's grammatical directive.
        # The persisted lifecycle action above is always the contract enum.
        if contract.allowed_action_polarities and facts.action_polarity not in contract.allowed_action_polarities:
            return "operation_action_mismatch"
        if contract.required_entities and not set(contract.required_entities).issubset(facts.explicit_entities):
            return "operation_required_entity_missing"
        # `any_entities` guides the model candidate manifest. Values such as
        # setup, plan and bot are semantic subjects, not fields in the typed
        # selector entity schema, so re-checking them with local vocabulary
        # after a schema-valid model selection would reintroduce a shadow
        # keyword router at the validation boundary.
        if contract.requires_verified_context:
            context = conversation_context or {}
            if not (context.get("last_verified_context") or context.get("last_verified_conclusion")):
                return "operation_verified_context_missing"
        # An action contract that receives an explicit target must retain that
        # target; a workspace asset is context, not an action substitute.
        if contract.operation_id in {"watchlist_add", "watchlist_remove"}:
            if facts.explicit_target_asset and not facts.referenced_asset:
                return "operation_target_asset_invalid"
        return None
