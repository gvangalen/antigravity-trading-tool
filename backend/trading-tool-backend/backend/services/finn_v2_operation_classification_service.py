"""Registry-backed operation selection for new FINN V2 runs.

The selector accepts deterministic request facts and resolves a single
OperationContract. It intentionally returns no mode, scopes, tools or policy;
all of those are read from the selected immutable contract by request analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
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
        allow_structured_selection: bool = True,
    ) -> SemanticOperationClassification:
        facts = self.preprocessor.preprocess(
            message=message, workspace_hints=workspace_hints, client_context=client_context
        )
        candidates = self._selector_candidates(facts=facts, context=conversation_context or {})
        if allow_structured_selection:
            selection, _error = self.structured_selector.select(
                message=message,
                candidate_contracts=candidates,
                facts={
                    "entities": facts.explicit_entities,
                    "action_polarity": facts.action_polarity,
                    "discourse_act": facts.discourse_act,
                    "referenced_asset": facts.referenced_asset,
                },
                verified_context=(conversation_context or {}).get("last_verified_context"),
            )
            if selection is not None and selection.confidence >= 0.75:
                return self._result(selection.operation_id, facts, "high", "structured", candidates)
        # This is a provider-failure safety outcome, not a parallel selector.
        # The same manifest candidates and deterministic validator bound it;
        # no context, tool, policy, or operation may be invented here.
        fallback = self._provider_failure_fallback(
            facts=facts,
            candidates=candidates,
            context=conversation_context or {},
        )
        return self._result(
            fallback.operation_id,
            facts,
            "medium",
            "provider_fallback",
            candidates,
            unsupported_capability=fallback.capability_gap,
        )

    def _selector_candidates(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object]
    ) -> tuple[OperationContract, ...]:
        if facts.domain_hint == "off_topic":
            return (self.registry.get("off_topic"),)

        candidates = list(self._candidates(facts=facts, context=context))
        continuation = self._conversation_operation(facts=facts, context=context)
        if continuation is not None:
            candidates.insert(0, self.registry.get(continuation.operation_id))
        if self._is_financial_concept_explanation_request(facts):
            candidates.insert(0, self.registry.get("explain_financial_concept"))
        if not candidates:
            fallback_id = (
                "unavailable"
                if "beste trade" in facts.normalized_text or "best trade" in facts.normalized_text
                else
                "unsupported_financial_operation"
                if facts.domain_hint == "financial" and facts.discourse_act == "operation_request" and facts.explicit_entities
                else "clarify_request"
            )
            candidates.append(self.registry.get(fallback_id))
        # Preserve declared rank while making the safe clarification outcome
        # available when a free-form request remains materially ambiguous.
        if candidates[0].operation_id not in {"off_topic", "clarify_request", "unsupported_financial_operation"}:
            candidates.append(self.registry.get("clarify_request"))
        deduped: list[OperationContract] = []
        for candidate in candidates:
            if candidate.operation_id not in {item.operation_id for item in deduped}:
                deduped.append(candidate)
        return tuple(deduped)

    def _provider_failure_fallback(
        self,
        *,
        facts: FinnV2PreprocessedRequest,
        candidates: tuple[OperationContract, ...],
        context: Mapping[str, object],
    ) -> OperationContract:
        if facts.domain_hint == "off_topic":
            return self.registry.get("off_topic")
        continuation = self._conversation_operation(facts=facts, context=context)
        if continuation is not None:
            return self.registry.get(continuation.operation_id)
        if self._is_financial_concept_explanation_request(facts):
            return self.registry.get("explain_financial_concept")
        if "beste trade" in facts.normalized_text or "best trade" in facts.normalized_text:
            return self.registry.get("unavailable")
        selected = self._select_deterministically(facts=facts, candidates=candidates)
        if selected is not None:
            return selected
        if facts.domain_hint == "financial" and facts.discourse_act == "operation_request" and facts.explicit_entities:
            return self.registry.get("unsupported_financial_operation")
        return self.registry.get("clarify_request")

    @staticmethod
    def _is_financial_concept_explanation_request(facts: FinnV2PreprocessedRequest) -> bool:
        if not facts.financial_concept or facts.discourse_act != "information_request" or facts.explicit_target_asset:
            return False
        if not facts.explicit_entities:
            return True
        normalized = facts.normalized_text
        explanation_pattern = (
            normalized.startswith("wat betekent ")
            or normalized.startswith("wat is ")
            or normalized.startswith("what is ")
            or normalized.startswith("what does ")
            or normalized.startswith("leg uit")
            or normalized.startswith("uitleg")
        )
        return explanation_pattern and set(facts.explicit_entities).issubset({"indicator_configuration"})

    def _conversation_operation(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object]
    ) -> Optional[SemanticOperationClassification]:
        raw_state = self._guided_state_payload(context)
        if isinstance(raw_state, Mapping) and raw_state.get("missing_required_inputs"):
            operation_id = str(raw_state.get("operation_id") or "")
            # Capability requests always start a fresh, read-only operation;
            # an unfinished proposal may resume only after a valid slot answer.
            if facts.discourse_act == "capability":
                return None
            # An explicitly new operation must not be hijacked by an unfinished draft.
            if facts.discourse_act == "operation_request" and facts.explicit_entities:
                return None
            if (
                operation_id
                and facts.discourse_act == "clarification_answer"
                and facts.action_polarity not in {"confirm", "execute"}
            ):
                return self._result(operation_id, facts, "high", "conversation", (self.registry.get(operation_id),))
        verified = context.get("last_verified_context") or context.get("last_verified_conclusion")
        if verified:
            if facts.discourse_act == "evidence_follow_up":
                return self._result("explain_previous_evidence", facts, "high", "conversation", ())
            if facts.discourse_act == "reformulation":
                return self._result("reformulate_previous_response", facts, "high", "conversation", ())
        return None

    @staticmethod
    def _guided_state_payload(context: Mapping[str, object]) -> object:
        from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService

        return FinnV2OperationStateService._guided_state_payload(context)

    def _candidates(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object]
    ) -> tuple[OperationContract, ...]:
        # A deictic phrase without a verified predecessor is still allowed to
        # describe an explicitly named entity in the current request. It must
        # not manufacture a conversation reference or block normal reads.
        discourse = facts.discourse_act
        if discourse == "contextual_follow_up" and not (
            context.get("last_verified_context") or context.get("last_verified_conclusion")
        ):
            discourse = "information_request"
        return self.registry.candidate_operations(
            entities=facts.explicit_entities,
            action_polarity=facts.action_polarity,
            discourse_act=discourse,
            has_verified_context=bool(
                context.get("last_verified_context") or context.get("last_verified_conclusion")
            ),
            normalized_text=facts.normalized_text,
            primary_entity=facts.primary_entity,
        )

    def _select_deterministically(
        self, *, facts: FinnV2PreprocessedRequest, candidates: tuple[OperationContract, ...]
    ) -> Optional[OperationContract]:
        if candidates:
            # The registry returns candidates in its declared selection order.
            # Equal-priority candidates are real ambiguity, never a reason to
            # derive a new local operation or mode.
            first_rank = self.registry.candidate_rank(candidates[0], primary_entity=facts.primary_entity)
            second_rank = self.registry.candidate_rank(candidates[1], primary_entity=facts.primary_entity) if len(candidates) > 1 else None
            if second_rank is None or first_rank > second_rank:
                return candidates[0]
        if not candidates:
            return self.registry.get("unavailable") if facts.discourse_act == "information_request" and not facts.explicit_entities else None
        return None

    def _result(
        self,
        operation_id: str,
        facts: FinnV2PreprocessedRequest,
        confidence: str,
        source: str,
        candidates: tuple[OperationContract, ...],
        unsupported_capability: Optional[str] = None,
    ) -> SemanticOperationClassification:
        contract = self.registry.get(operation_id)
        return SemanticOperationClassification(
            operation_id=operation_id,
            action=facts.action_polarity,
            domain=contract.domain,
            discourse=facts.discourse_act,
            confidence=confidence,
            selector_source=source,
            candidate_operation_ids=tuple(item.operation_id for item in candidates),
            supported=contract.supported,
            reason_code=unsupported_capability or ("off_topic" if operation_id == "off_topic" else None),
            unsupported_capability=unsupported_capability,
        )


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
        if classification.selector_source not in {"deterministic", "conversation", "structured", "clarification", "domain", "capability_gap", "provider_fallback"}:
            return "selector_source_invalid"
        if facts is None:
            return None
        # A continuation is validated against the persisted guided contract,
        # not against the grammatical form of a short slot answer.  For
        # example, a setup name is correctly a read-like utterance while it
        # still fills the required ``name`` input of CREATE_PROPOSAL.
        if classification.selector_source in {"conversation", "provider_fallback"}:
            active = FinnV2OperationClassificationService._guided_state_payload(conversation_context or {})
            if isinstance(active, Mapping) and active.get("operation_id") == contract.operation_id:
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
