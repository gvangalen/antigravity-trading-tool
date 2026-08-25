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


@dataclass(frozen=True)
class SemanticOperationClassification:
    operation_id: str
    action: str
    domain: str
    discourse: str
    confidence: str
    selector_source: str = "deterministic"
    candidate_operation_ids: tuple[str, ...] = ()


class FinnV2OperationClassificationService:
    """Select an operation from registry metadata and conversation lineage."""

    def __init__(
        self,
        registry: Optional[FinnV2OperationRegistry] = None,
        preprocessor: Optional[FinnV2RequestPreprocessorService] = None,
    ):
        self.registry = registry or FinnV2OperationRegistry()
        self.preprocessor = preprocessor or FinnV2RequestPreprocessorService()

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
        continuation = self._conversation_operation(facts=facts, context=conversation_context or {})
        if continuation is not None:
            return continuation
        candidates = self._candidates(facts=facts, context=conversation_context or {})
        selected = self._select_deterministically(facts=facts, candidates=candidates)
        if selected is None:
            return self._result("clarify_request", facts, "low", "clarification", candidates)
        confidence = "high" if len(candidates) == 1 else "medium"
        return self._result(selected.operation_id, facts, confidence, "deterministic", candidates)

    def _conversation_operation(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object]
    ) -> Optional[SemanticOperationClassification]:
        raw_state = context.get("active_guided_operation") or context.get("operation_state")
        if isinstance(raw_state, Mapping) and raw_state.get("missing_required_inputs"):
            operation_id = str(raw_state.get("operation_id") or "")
            # An explicitly new operation must not be hijacked by an unfinished draft.
            if facts.discourse_act == "operation_request" and facts.explicit_entities:
                return None
            if operation_id and facts.action_polarity not in {"confirm", "execute"}:
                return self._result(operation_id, facts, "high", "conversation", (self.registry.get(operation_id),))
        verified = context.get("last_verified_context") or context.get("last_verified_conclusion")
        if verified:
            if facts.discourse_act == "evidence_follow_up":
                return self._result("explain_previous_evidence", facts, "high", "conversation", ())
            if facts.discourse_act == "reformulation":
                return self._result("reformulate_previous_response", facts, "high", "conversation", ())
        return None

    def _candidates(
        self, *, facts: FinnV2PreprocessedRequest, context: Mapping[str, object]
    ) -> tuple[OperationContract, ...]:
        return self.registry.candidate_operations(
            entities=facts.explicit_entities,
            action_polarity=facts.action_polarity,
            discourse_act=facts.discourse_act,
            has_verified_context=bool(
                context.get("last_verified_context") or context.get("last_verified_conclusion")
            ),
            normalized_text=facts.normalized_text,
        )

    def _select_deterministically(
        self, *, facts: FinnV2PreprocessedRequest, candidates: tuple[OperationContract, ...]
    ) -> Optional[OperationContract]:
        if candidates:
            # The registry returns candidates in its declared selection order.
            # Equal-priority candidates are real ambiguity, never a reason to
            # derive a new local operation or mode.
            if len(candidates) == 1 or candidates[0].selection_priority > candidates[1].selection_priority:
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
        )


class FinnV2OperationClassificationValidator:
    """Ensure a selector can only hand a registered supported contract onward."""

    def __init__(self, registry: Optional[FinnV2OperationRegistry] = None):
        self.registry = registry or FinnV2OperationRegistry()

    def validate(self, classification: SemanticOperationClassification) -> bool:
        try:
            self.registry.require_supported(classification.operation_id)
        except ValueError:
            return False
        return classification.selector_source in {"deterministic", "conversation", "structured", "clarification"}
