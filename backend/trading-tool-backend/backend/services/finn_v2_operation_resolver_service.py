"""Resolve a provider semantic frame through the immutable operation registry."""
from __future__ import annotations

from copy import copy
from dataclasses import is_dataclass, replace
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry, OperationContract
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection


class FinnV2OperationResolverService:
    """A contract resolver, not a second free-text intent classifier."""

    _GOAL_OBJECT_OPERATIONS = {
        ("capability", None): "capability",
        ("create", "setup"): "create_setup",
        ("create", "strategy"): "create_strategy",
        ("create", "bot"): "create_bot",
        ("create", "indicator"): "create_indicator_configuration",
        ("add", "watchlist"): "watchlist_add",
        ("remove", "watchlist"): "watchlist_remove",
        ("update", "indicator"): "update_indicator_configuration",
        ("delete", "indicator"): "delete_indicator_configuration",
        ("update", "setup"): "update_setup",
        ("delete", "setup"): "delete_setup",
        ("update", "strategy"): "update_strategy",
        ("delete", "strategy"): "delete_strategy",
        ("update", "bot"): "update_bot",
        ("delete", "bot"): "delete_bot",
        ("deactivate", "bot"): "deactivate_bot",
        ("select", "asset"): "select_asset",
        ("activate", "bot"): "activate_bot",
        ("evaluate", "plan"): "evaluate_plan",
        ("evaluate", "setup"): "evaluate_setup",
        ("evaluate", "strategy"): "evaluate_strategy",
        ("evaluate", "bot"): "evaluate_bot",
        ("evaluate", "portfolio"): "evaluate_portfolio",
        ("read", "plan"): "read_active_plan",
        ("read", "setup"): "read_active_setup",
        ("read", "bot"): "read_linked_bot",
        ("read", "indicator"): "read_indicator_configuration",
        ("read", "scores"): "read_scores",
        ("read", "score"): "read_scores",
        ("read", "portfolio"): "read_portfolio",
        ("explain", "score"): "explain_score",
        ("explain", "scores"): "explain_score",
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
        # Legacy callers can provide a selection without a semantic frame.
        # Preserve that selection unless a typed safety invariant requires a
        # fail-closed correction. A provider may validly return an empty frame
        # for an unbound deictic follow-up, which must still clarify instead
        # of becoming an off-topic terminal response.
        if not isinstance(frame, Mapping) or not frame:
            if (
                selection.operation_id == "off_topic"
                and
                bool((request_facts or {}).get("ambiguous_reference"))
                and not self._has_any_eligible_lineage(conversation_context)
                and not self._has_pending_operation(conversation_context)
                and any(contract.operation_id == "clarify_request" for contract in candidates)
            ):
                return self._with_resolved_operation(
                    selection,
                    operation_id="clarify_request",
                    conversation_reference=selection.conversation_reference,
                )
            return selection
        frame = dict(frame)
        candidate_ids = {contract.operation_id for contract in candidates}
        goal = self._normalized(frame.get("goal"))
        object_name = self._normalized(frame.get("object"))
        reference_kind = self._normalized(frame.get("reference_kind"))
        requested_scopes = {
            self._normalized(item)
            for item in frame.get("requested_scopes", ())
            if isinstance(item, str)
        }
        explicit_active_plan = (
            self._normalized((selection.entities or {}).get("concept")) == "active_plan"
            or bool((request_facts or {}).get("explicit_plan_subject"))
        )
        operation_id = self._operation_from_frame(
            goal=goal,
            object_name=object_name,
            reference_kind=reference_kind,
            current=selection.operation_id,
            context=conversation_context,
            requested_scopes=requested_scopes,
        )
        # A structured request fact may make a selected action contract
        # impossible: for example an update frame must not be executed as a
        # create contract for the same typed object.  This does not classify
        # wording a second time; it selects the one registry contract whose
        # polarity agrees with the already typed semantic frame.
        requested_action = str((request_facts or {}).get("action_polarity") or "")
        normalized_text = str((request_facts or {}).get("normalized_text") or "").casefold()
        # "remove" is the canonical watchlist polarity.  For a persisted
        # object it is the same typed user act as the registry's delete
        # contract, so normalize it before comparing contract polarities.
        contract_action = "delete" if requested_action == "remove" and object_name != "watchlist" else requested_action
        polarity_operation = self._GOAL_OBJECT_OPERATIONS.get((contract_action, object_name))
        if polarity_operation in candidate_ids and contract_action in {
            "create", "update", "delete", "add", "remove", "deactivate", "activate", "explain",
        }:
            selected_contract = next(
                (contract for contract in candidates if contract.operation_id == operation_id),
                None,
            )
            if selected_contract is None or selected_contract.action_polarity.value != contract_action:
                operation_id = polarity_operation
        # Selection-required terms are registry constraints. A live-bot
        # selection cannot override the explicit non-live paper qualifier.
        selected_contract = next(
            (contract for contract in candidates if contract.operation_id == operation_id),
            None,
        )
        required_term_contracts = [
            contract for contract in candidates
            if contract.selection_required_terms
            and all(term.casefold() in normalized_text for term in contract.selection_required_terms)
        ]
        if (
            selected_contract is not None
            and selected_contract.operation_id == "activate_bot"
            and required_term_contracts
            and (
                not selected_contract.selection_required_terms
                or not all(term.casefold() in normalized_text for term in selected_contract.selection_required_terms)
            )
        ):
            operation_id = required_term_contracts[0].operation_id
        # Capability is a typed discourse fact, not a nearby plan read. The
        # selector still interprets the user's language, but a contract that
        # contradicts this explicit request act cannot be executed safely.
        if str((request_facts or {}).get("discourse_act") or "") == "capability":
            operation_id = "capability"
        # An explicit typed active-plan reference is the aggregate plan
        # contract. It must not be narrowed merely because the same turn also
        # names graph components.
        if goal == "read" and explicit_active_plan:
            operation_id = "read_active_plan"
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
        # The semantic frame may omit its object while the typed entity ledger
        # has one unambiguous product object.  Use that already extracted fact
        # only to complete registry validation; do not infer an object from
        # arbitrary wording or workspace context.
        if not object_name and len(explicit_entities) == 1:
            object_name = {
                "indicator_configuration": "indicator",
            }.get(next(iter(explicit_entities)), next(iter(explicit_entities)))
            polarity_operation = self._GOAL_OBJECT_OPERATIONS.get((contract_action, object_name))
            if polarity_operation in candidate_ids:
                selected_contract = next(
                    (contract for contract in candidates if contract.operation_id == operation_id),
                    None,
                )
                if selected_contract is None or selected_contract.action_polarity.value != contract_action:
                    operation_id = polarity_operation
        if (
            str((request_facts or {}).get("action_polarity") or "") == "read"
            and not bool((request_facts or {}).get("explicit_plan_subject"))
            and {"setup", "strategy", "bot"}.issubset(explicit_entities)
        ):
            operation_id = (
                "read_linked_bot"
                if bool((request_facts or {}).get("linked_graph_relationship"))
                else "read_active_plan"
            )
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
        # A typed aggregate-plan subject remains broader than a provider's
        # narrower graph-node label. This preserves the registry's complete
        # plan-assessment contract while leaving setup assessments, whose
        # primary subject is ``setup``, untouched.
        if (
            goal == "evaluate"
            and str((request_facts or {}).get("discourse_act") or "") == "evaluation"
            and str((request_facts or {}).get("primary_entity") or "") == "plan"
        ):
            operation_id = "evaluate_plan"
        if (
            bool((request_facts or {}).get("ambiguous_reference"))
            and not self._has_any_eligible_lineage(conversation_context)
            and not self._has_pending_operation(conversation_context)
        ):
            operation_id = "clarify_request"
        # A request to inspect a stored indicator configuration has a typed
        # product object. A general financial-concept explanation is only
        # compatible when the request actually names a concept such as RSI.
        # This protects all catalog assets without introducing asset aliases
        # or prompt-local routing.
        if (
            str((request_facts or {}).get("action_polarity") or "") == "read"
            and "indicator_configuration" in explicit_entities
            and not bool((request_facts or {}).get("financial_concept"))
        ):
            operation_id = "read_indicator_configuration"
        # A lineage-bound question about the consequence or assessment of a
        # bot needs the bot evaluation contract. It cannot be reduced to an
        # evidence-only explanation because the contract owns bot state reads.
        if (
            "bot" in explicit_entities
            and contract_action not in {"create", "update", "delete", "deactivate", "activate"}
            and (
                goal == "consequence"
                or str((request_facts or {}).get("discourse_act") or "") in {
                    "contextual_follow_up", "evaluation",
                }
            )
            and not bool((request_facts or {}).get("explicit_plan_subject"))
        ):
            operation_id = "evaluate_bot"
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
        # A typed financial/workspace fact is a boundary constraint: an
        # off-topic model label cannot erase it.  The registry provides the
        # only safe terminal contracts for an unbound change, an active-asset
        # read, or an execution intent respectively.
        if operation_id == "off_topic" and str((request_facts or {}).get("domain_hint") or "") == "financial":
            action = str((request_facts or {}).get("action_polarity") or "")
            if action == "execute":
                operation_id = "unsupported_financial_operation"
            elif action == "update":
                operation_id = "clarify_request"
            elif action == "read" and explicit_entities == {"asset"}:
                operation_id = "read_active_asset"
        if operation_id == "clarify_request":
            operation_id = self._unique_action_contract_candidate(
                candidates=candidates,
                request_facts=request_facts,
            ) or operation_id
        # A completed owner-scoped action may be the only safe antecedent for
        # a short follow-up such as "delete the linked setup".  Keep the
        # already typed mutation polarity and derive only the object from the
        # persisted result; arbitrary conversation text never supplies this
        # fallback and ambiguous database matches still clarify.
        previous_result = conversation_context.get("previous_action_result")
        if (
            operation_id == "clarify_request"
            and isinstance(previous_result, Mapping)
            and str(previous_result.get("result_status") or "") == "succeeded"
        ):
            prior_object = self._normalized(previous_result.get("entity_type"))
            prior_action = str((request_facts or {}).get("action_polarity") or "")
            prior_operation = self._GOAL_OBJECT_OPERATIONS.get((prior_action, prior_object))
            if prior_operation in candidate_ids:
                operation_id = prior_operation
        if operation_id not in candidate_ids:
            return selection
        reference = selection.conversation_reference
        if self._has_eligible_lineage(conversation_context) and reference_kind in {
            "previous_verified_response", "previous_response", "previous_evidence", "previous_conclusion",
        }:
            reference = "previous_verified_response"
        elif (
            operation_id == "reformulate_previous_response"
            and self._has_released_lineage(conversation_context)
            and reference_kind in {"previous_response", "previous_conclusion", "previous_released_response"}
        ):
            # A released answer is sufficient to restyle, but intentionally
            # cannot be promoted to verified evidence.
            reference = "previous_released_response"
        # Persisted action results are a typed, owner-scoped antecedent for a
        # follow-up mutation. Record that provenance even when the selector
        # correctly omits the internal ID from its structured output.
        previous_result = conversation_context.get("previous_action_result")
        if (
            isinstance(previous_result, Mapping)
            and str(previous_result.get("result_status") or "") == "succeeded"
            and previous_result.get("entity_id") is not None
            and any(field in {"setup_id", "strategy_id", "bot_id"} for field in self.registry.get(operation_id).contextual_reference_inputs)
        ):
            reference = "previous_action_result"
        # A contextual bot implication uses released plan lineage even if the
        # provider frame expresses the implication without an explicit
        # reference-kind token.
        if (
            operation_id == "evaluate_bot"
            and str((request_facts or {}).get("discourse_act") or "") == "contextual_follow_up"
            and self._has_eligible_lineage(conversation_context)
        ):
            reference = "previous_verified_response"
        return self._with_resolved_operation(
            selection,
            operation_id=operation_id,
            conversation_reference=reference,
        )

    @staticmethod
    def _unique_action_contract_candidate(*, candidates, request_facts: Mapping[str, object] | None) -> str | None:
        """Retain an unambiguous registry action when the model over-clarifies.

        This does not infer an operation from wording: candidate construction
        has already applied the registry's discourse, entity and polarity
        constraints. The resolver can only retain the one candidate whose
        canonical polarity equals the typed request fact.
        """
        action = str((request_facts or {}).get("action_polarity") or "")
        if action not in {"create", "update", "delete", "add", "remove", "deactivate", "activate"}:
            return None
        matches = [
            contract
            for contract in candidates
            if contract.action_polarity.value == action
        ]
        return matches[0].operation_id if len(matches) == 1 else None

    @staticmethod
    def _with_resolved_operation(
        selection: FinnV2StructuredOperationSelection,
        *,
        operation_id: str,
        conversation_reference: str | None,
    ) -> FinnV2StructuredOperationSelection:
        """Preserve the typed production selection and compatible test doubles.

        Production selector outputs are frozen dataclasses. A few legacy
        classifier consumers supply a namespace-shaped selection, so resolver
        invariants must not depend on that incidental implementation detail.
        """
        if is_dataclass(selection):
            return replace(selection, operation_id=operation_id, conversation_reference=conversation_reference)
        resolved = copy(selection)
        resolved.operation_id = operation_id
        resolved.conversation_reference = conversation_reference
        return resolved

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
        if reference_kind and (
            self._has_eligible_lineage(context)
            or (goal in {"reformulate", "summarize"} and self._has_released_lineage(context))
        ):
            if goal in {"reformulate", "summarize"}:
                return "reformulate_previous_response"
            # A consequence requested for a concrete bot is a bounded bot
            # assessment. It is not an evidence-only explanation because the
            # contract must load and present the linked bot's current state.
            if goal == "consequence" and object_name == "bot":
                return "evaluate_bot"
            if goal in {"explain", "consequence", "clarify"}:
                return "explain_previous_evidence"
        # A multi-node overview is a plan read.  The plan contract owns the
        # complete setup/strategy/bot graph; a linked-bot read is reserved for
        # an explicit relationship or bot-centric subject.
        if goal == "read" and {"setup", "strategy", "bot"}.issubset(requested_scopes):
            return "read_active_plan"
        if goal in {"clarify", "clarification"}:
            return "clarify_request"
        if goal in {"unsupported", "execute"} and object_name in {"portfolio", "trade", "order"}:
            return "unsupported_financial_operation"
        # A request to make a FINN bot live remains an activation intent even
        # when phrased as an immediate execution. Policy, not selection, owns
        # the subsequent block and keeps the original safety intent visible.
        if goal in {"activate", "execute"} and object_name == "bot":
            return "activate_bot"
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
    def _has_released_lineage(context: Mapping[str, object]) -> bool:
        released = context.get("last_released_context")
        return isinstance(released, Mapping) and bool(released.get("run_id") and released.get("response"))

    @classmethod
    def _has_any_eligible_lineage(cls, context: Mapping[str, object]) -> bool:
        return cls._has_eligible_lineage(context) or cls._has_released_lineage(context)

    @staticmethod
    def _has_pending_operation(context: Mapping[str, object]) -> bool:
        active = context.get("active_guided_operation")
        return isinstance(active, Mapping) and bool(active.get("next_missing_input"))
