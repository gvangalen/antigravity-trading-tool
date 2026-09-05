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


def test_semantic_frame_resolves_a_bot_consequence_to_a_bounded_bot_evaluation():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_linked_bot", {
            "goal": "consequence", "object": "bot", "reference_kind": "previous_verified_response",
        }),
        candidates=registry.list(),
        conversation_context={"last_verified_context": {"verified_response_id": "response-1", "evidence_refs": ["E1"]}},
    )

    assert resolved.operation_id == "evaluate_bot"
    assert resolved.conversation_reference == "previous_verified_response"


def test_semantic_frame_keeps_live_bot_execution_as_typed_activation_for_policy():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {"goal": "execute", "object": "bot"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "activate_bot"


def test_semantic_frame_resolves_a_broad_assessment_to_plan_not_setup():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_setup", {"goal": "evaluate", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "evaluate_plan"


def test_aggregate_plan_assessment_overrides_a_conflicting_node_projection():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_setup", {"goal": "evaluate", "object": "setup"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"discourse_act": "evaluation", "primary_entity": "plan"},
    )

    assert resolved.operation_id == "evaluate_plan"


def test_specific_setup_assessment_is_not_broadened_to_an_aggregate_plan():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_setup", {"goal": "evaluate", "object": "setup"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"discourse_act": "evaluation", "primary_entity": "setup"},
    )

    assert resolved.operation_id == "evaluate_setup"


def test_plan_assessment_fact_rejects_a_contradictory_clarification_frame():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": "clarify", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"discourse_act": "evaluation"},
    )

    assert resolved.operation_id == "evaluate_plan"


def test_non_evaluative_plan_clarification_remains_a_clarification():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": "clarify", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"discourse_act": "information_request"},
    )

    assert resolved.operation_id == "clarify_request"


def test_semantic_frame_resolves_a_complete_graph_overview_to_the_plan_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_setup", {
            "goal": "read", "object": "setup", "requested_scopes": ("setup", "strategy", "bot"),
        }),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "read_active_plan"


def test_linked_graph_relationship_completes_an_underprojected_read_frame():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_setup", {"goal": "read", "object": "setup"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={
            "action_polarity": "read",
            "explicit_entities": ("setup", "strategy", "bot"),
            "linked_graph_relationship": True,
        },
    )

    assert resolved.operation_id == "read_linked_bot"


def test_linked_graph_relationship_overrides_an_aggregate_plan_projection():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_plan", {"goal": "read", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={
            "action_polarity": "read",
            "explicit_entities": ("setup", "strategy", "bot"),
            "linked_graph_relationship": True,
        },
    )

    assert resolved.operation_id == "read_linked_bot"


def test_complete_plan_overview_remains_a_plan_read_without_a_relationship_fact():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_plan", {"goal": "read", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"action_polarity": "read", "explicit_entities": ("setup", "strategy", "bot")},
    )

    assert resolved.operation_id == "read_active_plan"


def test_explicit_plan_subject_keeps_the_complete_plan_read_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_plan", {"goal": "read", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={
            "action_polarity": "read",
            "explicit_plan_subject": True,
            "explicit_entities": ("plan", "setup", "strategy", "bot"),
        },
    )

    assert resolved.operation_id == "read_active_plan"


def test_explicit_current_plan_overrides_a_conflicting_graph_read_projection():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_linked_bot", {
            "goal": "read", "object": "bot", "requested_scopes": ("setup", "strategy", "bot"),
        }),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"explicit_plan_subject": True},
    )

    assert resolved.operation_id == "read_active_plan"


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


def test_explicit_financial_unsupported_frame_remains_safely_unsupported():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("unsupported_financial_operation", {"goal": "unsupported", "object": "portfolio"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"domain_hint": "off_topic"},
    )

    assert resolved.operation_id == "unsupported_financial_operation"


def test_unbound_execution_fact_cannot_be_erased_as_off_topic():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {"goal": "off_topic", "object": None}),
        candidates=registry.list(), conversation_context={},
        request_facts={"action_polarity": "execute", "financial_execution_intent": True},
    )

    assert resolved.operation_id == "unsupported_financial_operation"


def test_indicator_read_fact_rejects_a_conflicting_financial_concept_projection():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("explain_financial_concept", {"goal": "explain", "object": "financial_concept"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={
            "action_polarity": "read",
            "explicit_entities": ("indicator_configuration",),
            "financial_concept": None,
        },
    )

    assert resolved.operation_id == "read_indicator_configuration"


def test_lineage_bound_bot_assessment_overrides_an_evidence_only_frame():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("explain_previous_evidence", {"goal": "explain", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={"last_verified_context": {"verified_response_id": "response-1", "evidence_refs": ["E1"]}},
        request_facts={
            "explicit_entities": ("bot", "strategy"),
            "discourse_act": "evaluation",
            "explicit_plan_subject": False,
        },
    )

    assert resolved.operation_id == "evaluate_bot"


def test_non_financial_execution_fact_cannot_be_coerced_to_unsupported_financial_operation():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {"goal": "off_topic", "object": None}),
        candidates=registry.list(), conversation_context={},
        request_facts={"action_polarity": "execute", "financial_execution_intent": False},
    )

    assert resolved.operation_id == "off_topic"


def test_unbound_deictic_reference_requires_clarification_not_execution():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("unsupported_financial_operation", {"goal": "unsupported", "object": None}),
        candidates=registry.list(), conversation_context={},
        request_facts={"ambiguous_reference": True},
    )

    assert resolved.operation_id == "clarify_request"
