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
from backend.services.finn_v2_operation_resolver_service import FinnV2OperationResolverService
from backend.services.finn_v2_target_asset_resolver import FinnV2TargetAssetResolver


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
    required_inputs: tuple[str, ...] = ()
    supplied_inputs: Mapping[str, object] = field(default_factory=dict)
    derived_inputs: Mapping[str, object] = field(default_factory=dict)
    selected_missing_inputs: tuple[str, ...] = ()
    clarification_required: bool = False
    semantic_frame: Mapping[str, object] = field(default_factory=dict)


class FinnV2OperationClassificationService:
    """Select an operation from registry metadata and conversation lineage."""

    def __init__(
        self,
        registry: Optional[FinnV2OperationRegistry] = None,
        preprocessor: Optional[FinnV2RequestPreprocessorService] = None,
        structured_selector: Optional[FinnV2StructuredOperationSelectorService] = None,
        resolver: Optional[FinnV2OperationResolverService] = None,
    ):
        self.registry = registry or FinnV2OperationRegistry()
        self.preprocessor = preprocessor or FinnV2RequestPreprocessorService()
        self.structured_selector = structured_selector or FinnV2StructuredOperationSelectorService()
        self.resolver = resolver or FinnV2OperationResolverService(self.registry)

    def classify(
        self,
        *,
        message: str,
        conversation_context: Optional[Mapping[str, object]] = None,
        workspace_hints: Optional[Mapping[str, object]] = None,
        client_context: Optional[Mapping[str, object]] = None,
        selector_timeout_seconds: Optional[int] = None,
        selector_max_output_tokens: Optional[int] = None,
    ) -> SemanticOperationClassification:
        facts = self.preprocessor.preprocess(
            message=message, workspace_hints=workspace_hints, client_context=client_context
        )
        candidates = self._selector_manifest()
        guided_contract = self._guided_continuation_contract(facts=facts, context=conversation_context or {})
        if guided_contract is not None:
            # A typed answer to the one pending registry slot is not a new
            # free-text operation. Reuse the persisted contract directly and
            # avoid an otherwise redundant provider call on short turns.
            return self._result(
                guided_contract.operation_id,
                facts,
                "high",
                "guided_state",
                (guided_contract,),
                conversation_context=conversation_context,
            )
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
            timeout_seconds=selector_timeout_seconds,
            max_output_tokens=selector_max_output_tokens,
        )
        if selection is not None:
            selection = self.resolver.resolve(
                selection=selection,
                candidates=candidates,
                conversation_context=conversation_context or {},
                request_facts={
                    "domain_hint": facts.domain_hint,
                    "action_polarity": facts.action_polarity,
                    "discourse_act": facts.discourse_act,
                    "financial_execution_intent": facts.financial_execution_intent,
                    "ambiguous_reference": facts.ambiguous_reference,
                    "explicit_entities": facts.explicit_entities,
                    "explicit_plan_subject": facts.explicit_plan_subject,
                    "linked_graph_relationship": facts.linked_graph_relationship,
                    "primary_entity": facts.primary_entity,
                    "financial_concept": facts.financial_concept,
                },
            )
        safe_terminal_operations = {
            "clarify_request", "off_topic", "unsupported_financial_operation",
        }
        # A context-bound lineage request has an independently persisted safe
        # source record. Do not discard a schema-valid model selection merely
        # because it is less certain than a fresh action request; the
        # downstream registry validator still requires that source record.
        lineage_operations = {
            "explain_previous_evidence", "reformulate_previous_response", "evaluate_bot",
        }
        has_safe_lineage = bool(
            (conversation_context or {}).get("last_verified_context")
            or (conversation_context or {}).get("last_verified_conclusion")
            or (conversation_context or {}).get("last_degraded_context")
        )
        safe_terminal_explanation = bool(
            selection is not None
            and selection.operation_id == "explain_previous_evidence"
            and isinstance((conversation_context or {}).get("last_safe_terminal_context"), Mapping)
        )
        if selection is not None and (
            selection.confidence >= 0.75
            or selection.operation_id in safe_terminal_operations
            or (
                selection.operation_id in lineage_operations
                and (has_safe_lineage or safe_terminal_explanation)
                and selection.confidence >= 0.5
            )
        ):
            return self._result(
                selection.operation_id, facts, "high", "structured", candidates,
                selection=selection, conversation_context=conversation_context,
            )
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
            conversation_context=conversation_context,
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

    def _guided_continuation_contract(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object],
    ) -> OperationContract | None:
        active = context.get("active_guided_operation") or (
            context.get("operation_state") if not context.get("conversation_state_version") else None
        )
        if not isinstance(active, Mapping) or not active.get("missing_required_inputs"):
            return None
        # A persisted guided flow already identifies the operation and its
        # missing slot. Any explicit clarification answer belongs to that
        # contract, whether the value is one token or a natural sentence.
        # New requests retain their own discourse acts and therefore still
        # pass through structured selection.
        if facts.discourse_act != "clarification_answer":
            return None
        try:
            return self.registry.require_supported(str(active.get("operation_id") or ""))
        except ValueError:
            return None

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
            for key in (
                "last_verified_context", "last_degraded_context", "active_guided_operation",
                "operation_state", "last_safe_terminal_context", "last_turn_diagnostics",
            )
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
        conversation_context: Optional[Mapping[str, object]] = None,
    ) -> SemanticOperationClassification:
        contract = self.registry.get(operation_id)
        selected_entities = dict(getattr(selection, "entities", {}) or {})
        target_resolution = FinnV2TargetAssetResolver().resolve(
            explicit_target_asset=facts.referenced_asset,
            selector_target_asset=getattr(selection, "target_asset", None),
            verified_context=conversation_context,
            allow_workspace_fallback=False,
        )
        # The target resolver applies the product-wide precedence contract to
        # this early semantic projection as well as to runtime request plans.
        # No downstream consumer may receive a selector asset that conflicts
        # with the current user's explicit catalog-backed target.
        if target_resolution.target_asset:
            selected_entities["asset"] = target_resolution.target_asset
        if operation_id == "explain_financial_concept" and facts.financial_concept:
            selected_entities["concept"] = facts.financial_concept
        supplied_inputs, derived_inputs, selected_missing_inputs = self._resolved_inputs(
            contract=contract,
            facts=facts,
            selected_entities=selected_entities,
            selector_missing=tuple(getattr(selection, "missing_inputs", ()) or ()),
            conversation_context=conversation_context,
        )
        # The typed input collector is authoritative for user-supplied setup
        # slots. Preserve those values in the public semantic projection when
        # a schema-valid selector omitted a redundant entity field.
        for field in ("setup_type", "timeframe", "name"):
            if not selected_entities.get(field) and supplied_inputs.get(field):
                selected_entities[field] = str(supplied_inputs[field])
        if not selected_entities.get("asset") and supplied_inputs.get("symbol"):
            selected_entities["asset"] = str(supplied_inputs["symbol"])
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
            selected_target_asset=target_resolution.target_asset,
            selected_conversation_reference=getattr(selection, "conversation_reference", None),
            required_inputs=tuple(contract.required_inputs),
            supplied_inputs=supplied_inputs,
            derived_inputs=derived_inputs,
            selected_missing_inputs=selected_missing_inputs,
            clarification_required=(
                operation_id == "clarify_request"
                or (
                    facts.guidance_requested
                    and bool(selected_missing_inputs)
                    and contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}
                )
            ),
            semantic_frame=dict(getattr(selection, "semantic_frame", {}) or {}),
        )

    @staticmethod
    def _resolved_inputs(
        *,
        contract: OperationContract,
        facts: FinnV2PreprocessedRequest,
        selected_entities: Mapping[str, str],
        selector_missing: tuple[str, ...],
        conversation_context: Optional[Mapping[str, object]],
    ) -> tuple[Mapping[str, object], Mapping[str, object], tuple[str, ...]]:
        if contract.operation_id == "clarify_request":
            return {}, {}, ("requested_change",)
        if not contract.required_inputs:
            return {}, {}, ()
        supplied = FinnV2OperationStateService().explicit_inputs(
            contract=contract,
            # Input collection must retain display values such as a setup
            # name. ``normalized_text`` is for semantic comparison only.
            message=facts.original_text,
            explicit_asset=facts.referenced_asset,
        )
        if facts.financial_concept and "concept" in contract.required_inputs:
            supplied.setdefault("concept", facts.financial_concept)
        # A contextual action can use only an identifier already persisted in
        # verified lineage and only when the structured selector returned the
        # same typed identifier. Model text alone never supplies a write slot.
        verified = dict((conversation_context or {}).get("last_verified_context") or {})
        resolved = dict(verified.get("resolved_entities") or {})
        for field in contract.contextual_reference_inputs:
            value = resolved.get(field)
            if value is not None and str(selected_entities.get(field) or "") == str(value):
                supplied.setdefault(field, value)
        # A structured selector may propose a useful display name, but that
        # does not prove the user supplied a required setup slot. Explicit
        # input extraction remains the only authority for user-provided
        # fields; the canonical request asset is handled above.
        unresolved = [
            field for field in contract.required_inputs
            if FinnV2OperationStateService._is_missing(supplied.get(field))
        ]
        # The contract and proven inputs are authoritative. Selector telemetry
        # may narrow ambiguity but cannot mark an explicitly supplied slot as
        # missing or invent a slot outside the selected contract.
        missing = tuple(field for field in unresolved if field in selector_missing or field not in supplied)
        derived = {"target_asset": selected_entities["asset"]} if selected_entities.get("asset") else {}
        return supplied, derived, missing

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
        if classification.selector_source not in {"structured", "provider_unavailable", "guided_state"}:
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
            classification.selector_source == "guided_state"
            and isinstance(active, Mapping)
            and active.get("operation_id") == contract.operation_id
        ):
            return None
        # Selection metadata guides the model before it picks a contract. It
        # must not be replayed against lossy lexical facts afterwards: the
        # selected contract already owns the canonical typed polarity above.
        # `any_entities` guides the model candidate manifest. Values such as
        # setup, plan and bot are semantic subjects, not fields in the typed
        # selector entity schema, so re-checking them with local vocabulary
        # after a schema-valid model selection would reintroduce a shadow
        # keyword router at the validation boundary.
        if contract.requires_verified_context:
            context = conversation_context or {}
            degraded = context.get("last_degraded_context")
            has_degraded_evidence = (
                classification.operation_id in {
                    "explain_previous_evidence", "reformulate_previous_response", "evaluate_bot",
                }
                and isinstance(degraded, Mapping)
                and bool(degraded.get("evidence_refs"))
            )
            has_safe_terminal_boundary = (
                classification.operation_id == "explain_previous_evidence"
                and isinstance(context.get("last_safe_terminal_context"), Mapping)
                and bool(context["last_safe_terminal_context"].get("terminal_reason"))
            )
            if not (
                context.get("last_verified_context")
                or context.get("last_verified_conclusion")
                or has_degraded_evidence
                or has_safe_terminal_boundary
            ):
                return "operation_verified_context_missing"
        # An action contract that receives an explicit target must retain that
        # target; a workspace asset is context, not an action substitute.
        if contract.operation_id in {"watchlist_add", "watchlist_remove"}:
            if facts.explicit_target_asset and not facts.referenced_asset:
                return "operation_target_asset_invalid"
        return None
