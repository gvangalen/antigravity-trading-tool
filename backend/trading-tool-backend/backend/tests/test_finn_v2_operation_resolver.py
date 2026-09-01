from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_operation_resolver_service import FinnV2OperationResolverService
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection


def _selection(operation_id: str, frame: dict) -> FinnV2StructuredOperationSelection:
    return FinnV2StructuredOperationSelection(
        operation_id=operation_id,
        confidence=0.91,
        entities={},
        target_asset=None,
        conversation_reference=None,
        missing_inputs=(),
        ambiguity_reason=None,
        semantic_frame=frame,
    )


def test_semantic_frame_resolves_a_complete_proposal_only_setup_without_rewriting_slots():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {
            "goal": "create", "object": "setup", "target_asset": "ETH",
            "setup_type": "DCA", "timeframe": "daily", "name": "Patient Builder",
            "persistence_intent": "proposal_only",
        }),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "create_setup"
    assert resolved.semantic_frame["name"] == "Patient Builder"
    assert resolved.semantic_frame["persistence_intent"] == "proposal_only"


def test_semantic_frame_resolves_a_consequence_to_verified_evidence_not_a_bot_read():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_linked_bot", {
            "goal": "consequence", "object": "bot", "reference_kind": "previous_verified_response",
        }),
        candidates=registry.list(),
        conversation_context={"last_verified_context": {"verified_response_id": "response-1", "evidence_refs": ["E1"]}},
    )

    assert resolved.operation_id == "explain_previous_evidence"
    assert resolved.conversation_reference == "previous_verified_response"


def test_semantic_frame_resolves_a_broad_assessment_to_plan_not_setup():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_setup", {"goal": "evaluate", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "evaluate_plan"


def test_semantic_frame_resolves_a_complete_linked_graph_to_the_linked_bot_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_setup", {
            "goal": "read", "object": "setup", "requested_scopes": ("setup", "strategy", "bot"),
        }),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "read_linked_bot"


def test_unbound_execute_frame_fails_to_clarification_not_an_execution_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("unsupported_financial_operation", {"goal": "execute", "object": None}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "clarify_request"


def test_non_financial_frame_cannot_resolve_to_unsupported_execute_intent():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("unsupported_financial_operation", {"goal": "unsupported", "object": "other"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"domain_hint": "off_topic"},
    )

    assert resolved.operation_id == "off_topic"
