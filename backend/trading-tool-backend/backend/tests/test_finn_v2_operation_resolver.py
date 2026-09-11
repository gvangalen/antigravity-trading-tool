import pytest

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


def test_bot_consequence_uses_evaluate_contract_without_prior_lineage():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_linked_bot", {
            "goal": "consequence", "object": "bot", "reference_kind": None,
        }),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"explicit_entities": ("bot",), "discourse_act": "evaluation"},
    )

    assert resolved.operation_id == "evaluate_bot"


def test_bot_write_polarity_cannot_be_replaced_by_bot_evaluation():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_bot", {"goal": "evaluate", "object": "bot"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"explicit_entities": ("bot",), "action_polarity": "update"},
    )

    assert resolved.operation_id == "update_bot"


def test_object_remove_fact_uses_registry_delete_contract_not_bot_evaluation():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_bot", {"goal": "evaluate", "object": "bot"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"explicit_entities": ("bot",), "action_polarity": "remove"},
    )

    assert resolved.operation_id == "delete_bot"


def test_unambiguous_typed_entity_completes_an_omitted_frame_object_for_delete():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("evaluate_bot", {"goal": "evaluate", "object": None}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"explicit_entities": ("bot",), "action_polarity": "remove"},
    )

    assert resolved.operation_id == "delete_bot"


def test_typed_update_polarity_cannot_execute_create_strategy_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("create_strategy", {"goal": "create", "object": "strategy"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"action_polarity": "update"},
    )

    assert resolved.operation_id == "update_strategy"


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


def test_semantic_frame_resolves_stored_scores_through_the_registered_score_contracts():
    registry = FinnV2OperationRegistry()
    resolver = FinnV2OperationResolverService(registry)

    read = resolver.resolve(
        selection=_selection("clarify_request", {"goal": "read", "object": "score"}),
        candidates=registry.list(),
        conversation_context={},
    )
    explain = resolver.resolve(
        selection=_selection("clarify_request", {"goal": "explain", "object": "scores"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert read.operation_id == "read_scores"
    assert explain.operation_id == "explain_score"


def test_semantic_frame_resolves_portfolio_reads_and_assessments_through_contracts():
    registry = FinnV2OperationRegistry()
    resolver = FinnV2OperationResolverService(registry)

    read = resolver.resolve(
        selection=_selection("clarify_request", {"goal": "read", "object": "portfolio"}),
        candidates=registry.list(),
        conversation_context={},
    )
    evaluate = resolver.resolve(
        selection=_selection("clarify_request", {"goal": "evaluate", "object": "portfolio"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert read.operation_id == "read_portfolio"
    assert evaluate.operation_id == "evaluate_portfolio"


def test_semantic_frame_resolves_strategy_generation_to_the_single_v2_create_contract():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": "create", "object": "strategy"}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == "create_strategy"


def test_unambiguous_registry_update_is_not_replaced_by_a_model_clarification():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": "clarify", "object": "bot"}),
        candidates=(registry.require_supported("update_bot"),),
        conversation_context={},
        request_facts={"action_polarity": "update", "explicit_entities": ("bot",)},
    )

    assert resolved.operation_id == "update_bot"


@pytest.mark.parametrize(
    ("goal", "object_name", "operation_id"),
    [
        ("update", "setup", "update_setup"),
        ("delete", "setup", "delete_setup"),
        ("update", "strategy", "update_strategy"),
        ("delete", "strategy", "delete_strategy"),
        ("create", "bot", "create_bot"),
        ("update", "bot", "update_bot"),
        ("delete", "bot", "delete_bot"),
        ("deactivate", "bot", "deactivate_bot"),
        ("update", "indicator", "update_indicator_configuration"),
    ],
)
def test_semantic_frame_resolves_registered_action_transitions_without_clarifying(goal, object_name, operation_id):
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": goal, "object": object_name}),
        candidates=registry.list(),
        conversation_context={},
    )

    assert resolved.operation_id == operation_id


def test_capability_discourse_rejects_an_incompatible_nearby_plan_read():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("read_active_plan", {"goal": "read", "object": "plan"}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"discourse_act": "capability"},
    )

    assert resolved.operation_id == "capability"


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


def test_financial_workspace_change_without_an_object_requires_clarification_not_off_topic():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {"goal": "off_topic", "object": None}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={"domain_hint": "financial", "action_polarity": "update"},
    )

    assert resolved.operation_id == "clarify_request"


def test_active_asset_fact_cannot_be_erased_as_off_topic():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {"goal": "off_topic", "object": None}),
        candidates=registry.list(),
        conversation_context={},
        request_facts={
            "domain_hint": "financial",
            "action_polarity": "read",
            "explicit_entities": ("asset",),
        },
    )

    assert resolved.operation_id == "read_active_asset"


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


def test_unbound_deictic_reference_still_clarifies_when_provider_frame_is_empty():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("off_topic", {}),
        candidates=registry.list(), conversation_context={},
        request_facts={"ambiguous_reference": True},
    )

    assert resolved.operation_id == "clarify_request"


def test_completed_owner_action_result_resolves_a_typed_delete_follow_up():
    registry = FinnV2OperationRegistry()
    resolved = FinnV2OperationResolverService(registry).resolve(
        selection=_selection("clarify_request", {"goal": "clarify", "object": None}),
        candidates=registry.list(),
        conversation_context={
            "previous_action_result": {"entity_type": "setup", "result_status": "succeeded"},
        },
        request_facts={"action_polarity": "delete"},
    )

    assert resolved.operation_id == "delete_setup"
