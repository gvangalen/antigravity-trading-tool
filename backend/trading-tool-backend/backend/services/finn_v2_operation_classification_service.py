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
        if facts.discourse_act != "clarification_answer":
            return candidates
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
        safe = tuple(
            item for item in candidates
            if item.operation_id in {contract.operation_id, "clarify_request", "unavailable"}
        )
        return safe or candidates

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
            selected_entities=dict(getattr(selection, "entities", {}) or {}),
            selected_target_asset=getattr(selection, "target_asset", None),
            selected_conversation_reference=getattr(selection, "conversation_reference", None),
            selected_missing_inputs=tuple(getattr(selection, "missing_inputs", ()) or ()),
        )

    @staticmethod
    def _contract_action(contract: OperationContract, raw_action: str) -> str:
        """Project a validated contract into one stable lifecycle polarity."""
        actions = {
            "watchlist_add": "add", "watchlist_remove": "remove",
            "create_setup": "create", "activate_bot": "activate",
            "confirm_proposal": "confirm", "execute_proposal": "execute",
            "explain_previous_evidence": "read",
            "reformulate_previous_response": "read",
        }
        if contract.operation_id in actions:
            return actions[contract.operation_id]
        if contract.mode == "EVALUATE":
            return "evaluate"
        if contract.mode in {"READ", "CAPABILITY", "UNAVAILABLE", "CLARIFICATION"}:
            return "read" if contract.operation_id != "clarify_request" else raw_action
        return raw_action


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
            facts.discourse_act == "clarification_answer"
            and isinstance(active, Mapping)
            and active.get("operation_id") == contract.operation_id
        ):
            return None
        if contract.allowed_action_polarities and facts.action_polarity not in contract.allowed_action_polarities:
            return "operation_action_mismatch"
        if contract.required_entities and not set(contract.required_entities).issubset(facts.explicit_entities):
            return "operation_required_entity_missing"
        if contract.any_entities and not set(contract.any_entities).intersection(facts.explicit_entities):
            return "operation_entity_mismatch"
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
