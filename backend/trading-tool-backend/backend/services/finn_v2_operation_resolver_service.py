"""Resolve a provider semantic frame through the immutable operation registry."""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry, OperationContract
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection


class FinnV2OperationResolverService:
    """A contract resolver, not a second free-text intent classifier."""

    _GOAL_OBJECT_OPERATIONS = {
        ("capability", None): "capability",
        ("create", "setup"): "create_setup",
        ("add", "watchlist"): "watchlist_add",
        ("remove", "watchlist"): "watchlist_remove",
        ("activate", "bot"): "activate_bot",
        ("evaluate", "plan"): "evaluate_plan",
        ("evaluate", "setup"): "evaluate_setup",
        ("evaluate", "strategy"): "evaluate_strategy",
        ("evaluate", "bot"): "evaluate_bot",
        ("read", "plan"): "read_active_plan",
        ("read", "setup"): "read_active_setup",
        ("read", "bot"): "read_linked_bot",
        ("read", "indicator"): "read_indicator_configuration",
        ("explain", "financial_concept"): "explain_financial_concept",
    }

    def __init__(self, registry: Optional[FinnV2OperationRegistry] = None):
        self.registry = registry or FinnV2OperationRegistry()

    def resolve(
        self,
        *,
        selection: FinnV2StructuredOperationSelection,
        candidates: tuple[OperationContract, ...],
        conversation_context: Mapping[str, object],
        request_facts: Mapping[str, object] | None = None,
    ) -> FinnV2StructuredOperationSelection:
        frame = getattr(selection, "semantic_frame", None)
        if not isinstance(frame, Mapping) or not frame:
            return selection
        candidate_ids = {contract.operation_id for contract in candidates}
        goal = self._normalized(frame.get("goal"))
        object_name = self._normalized(frame.get("object"))
        reference_kind = self._normalized(frame.get("reference_kind"))
        requested_scopes = {
            self._normalized(item)
            for item in frame.get("requested_scopes", ())
            if isinstance(item, str)
        }
        operation_id = self._operation_from_frame(
            goal=goal,
            object_name=object_name,
            reference_kind=reference_kind,
            current=selection.operation_id,
            context=conversation_context,
            requested_scopes=requested_scopes,
        )
        # The preprocessor's typed entity ledger records an explicitly named
        # graph even when a provider frame under-projects one of its scopes.
        # A setup, strategy and bot requested together can only be served by
        # the complete linked-bot read contract; returning just the setup
        # would silently omit requested information.
        explicit_entities = {
            self._normalized(item)
            for item in (request_facts or {}).get("explicit_entities", ())
            if isinstance(item, str)
        }
        if (
            selection.operation_id in {"read_active_setup", "read_active_plan", "read_linked_bot"}
            and str((request_facts or {}).get("action_polarity") or "") == "read"
            and {"setup", "strategy", "bot"}.issubset(explicit_entities)
        ):
            operation_id = "read_linked_bot"
        # The provider still extracts the subject from free text.  Once it
        # has identified a plan, however, a deterministic assessment fact
        # makes ``clarify`` semantically incompatible: the user requested a
        # diagnosis, not an unspecified change.
        if (
            goal in {"clarify", "clarification"}
            and object_name == "plan"
            and str((request_facts or {}).get("discourse_act") or "") == "evaluation"
        ):
            operation_id = "evaluate_plan"
        if (
            bool((request_facts or {}).get("ambiguous_reference"))
            and not self._has_eligible_lineage(conversation_context)
            and not self._has_pending_operation(conversation_context)
        ):
            operation_id = "clarify_request"
        # This is a contract invariant, not an alternate intent router: a
        # financial-unsupported contract requires a financial request fact.
        # The provider still extracts meaning; the registry rejects an
        # incompatible financial execution label for an off-topic frame.
        if (
            operation_id == "unsupported_financial_operation"
            and not bool((request_facts or {}).get("financial_execution_intent"))
            and object_name not in {"portfolio", "trade", "order", "investment", "brokerage"}
            and not self._has_pending_operation(conversation_context)
        ):
            operation_id = "off_topic"
        # An explicit execution act is financially consequential even when
        # the provider cannot name its object. It must fail closed through the
        # unsupported contract, never be erased as off-topic.
        if (
            operation_id == "off_topic"
            and str((request_facts or {}).get("action_polarity") or "") == "execute"
            and bool((request_facts or {}).get("financial_execution_intent"))
        ):
            operation_id = "unsupported_financial_operation"
        if operation_id not in candidate_ids:
            return selection
        reference = selection.conversation_reference
        if self._has_eligible_lineage(conversation_context) and reference_kind in {
            "previous_verified_response", "previous_response", "previous_evidence", "previous_conclusion",
        }:
            reference = "previous_verified_response"
        return replace(selection, operation_id=operation_id, conversation_reference=reference)

    def _operation_from_frame(
        self,
        *,
        goal: str,
        object_name: str,
        reference_kind: str,
        current: str,
        context: Mapping[str, object],
        requested_scopes: set[str],
    ) -> str:
        if reference_kind and self._has_eligible_lineage(context):
            if goal in {"reformulate", "summarize"}:
                return "reformulate_previous_response"
            if goal in {"explain", "consequence", "clarify"}:
                return "explain_previous_evidence"
        # A multi-node graph read is represented by the existing linked-bot
        # graph contract, whose immutable scopes include setup and strategy.
        # This consumes model-extracted scopes, not source text.
        if goal == "read" and {"setup", "strategy", "bot"}.issubset(requested_scopes):
            return "read_linked_bot"
        if goal in {"clarify", "clarification"}:
            return "clarify_request"
        if goal in {"unsupported", "execute"} and object_name in {"portfolio", "trade", "order"}:
            return "unsupported_financial_operation"
        # An unbound action cannot safely become an execution intent.
        if goal in {"unsupported", "execute"} and not object_name:
            return "clarify_request"
        if goal in {"off_topic", "unknown"} and not self._has_pending_operation(context):
            return "off_topic"
        return self._GOAL_OBJECT_OPERATIONS.get((goal, object_name), self._GOAL_OBJECT_OPERATIONS.get((goal, None), current))

    @staticmethod
    def _normalized(value: object) -> str:
        return str(value or "").strip().casefold().replace(" ", "_")

    @staticmethod
    def _has_eligible_lineage(context: Mapping[str, object]) -> bool:
        verified = context.get("last_verified_context")
        degraded = context.get("last_degraded_context")
        return bool(verified or (isinstance(degraded, Mapping) and degraded.get("evidence_refs")))

    @staticmethod
    def _has_pending_operation(context: Mapping[str, object]) -> bool:
        active = context.get("active_guided_operation")
        return isinstance(active, Mapping) and bool(active.get("next_missing_input"))
