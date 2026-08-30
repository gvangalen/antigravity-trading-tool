from __future__ import annotations

import re
from typing import Dict, List, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry, FinnV2OperationUnavailableError
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult, RequestPlan
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_target_asset_resolver import FinnV2TargetAssetResolver
from backend.services.finn_v2_operation_classification_service import (
    FinnV2OperationClassificationService,
    FinnV2OperationClassificationValidator,
)


class FinnV2RequestAnalysisService:
    def __init__(self):
        self.operations = FinnV2OperationRegistry()
        self.operation_state = FinnV2OperationStateService()
        self.classifier = FinnV2OperationClassificationService(self.operations)
        self.classification_validator = FinnV2OperationClassificationValidator()
        self.target_resolver = FinnV2TargetAssetResolver()

    def analyze(
        self,
        *,
        message: str,
        workspace_hints: Optional[Dict[str, object]] = None,
        client_context: Optional[Dict[str, object]] = None,
        conversation_context: Optional[Dict[str, object]] = None,
    ) -> RequestAnalysisResult:
        text = str(message or "").strip()
        normalized = self._normalize_text(text)
        semantic = self.classifier.classify(
            message=text,
            conversation_context=conversation_context,
            workspace_hints=workspace_hints,
            client_context=client_context,
        )
        preprocessed = self.classifier.preprocessor.preprocess(
            message=text,
            workspace_hints=workspace_hints,
            client_context=client_context,
        )
        matched_signals: List[str] = []
        unresolved_signals: List[str] = []

        # The preprocessor and OperationContract registry are the only
        # operation-selection inputs for new runs.  Legacy subject labels are
        # reconstructed below strictly for backwards-compatible diagnostics;
        # they never choose a mode, tool, scope or policy.
        scopes: List[str] = []
        # An integrated assessment is about the user's plan even when the
        # message uses a natural reference such as "het hele plaatje".
        integrated_plan = False
        # The preprocessor owns hard request facts. In particular, an explicit
        # target asset can never be replaced by workspace or conversation state.
        message_asset = preprocessed.referenced_asset
        context_asset = preprocessed.workspace_context_asset
        explicit_asset = message_asset or context_asset
        explicit_setup_id = self._extract_entity_id(text, "setup")
        explicit_strategy_id = self._extract_entity_id(text, "strateg")
        explicit_bot_id = self._extract_entity_id(text, "bot")
        # Only the preprocessor may mark a conversation reference.  This
        # avoids turning ordinary Dutch pronouns into stale conversation
        # selectors later in the pipeline.
        reference_markers = set(preprocessed.conversation_reference_markers)
        has_existing_safe_lineage = self._has_safe_lineage(conversation_context or {}, allow_degraded=True)
        # A relational noun such as "gekoppelde bot" can describe the object
        # of a new request. It becomes a prior-turn reference only when a
        # durable lineage actually exists. Evidence and reformulation acts,
        # on the other hand, remain explicit lineage requests and must safely
        # clarify when no prior response is available.
        uses_conversation_reference = bool(reference_markers - {"contextual_entity"}) or (
            "contextual_entity" in reference_markers and has_existing_safe_lineage
        )
        if uses_conversation_reference and not self._has_safe_lineage(
            conversation_context or {},
            allow_degraded=preprocessed.discourse_act in {
                "evidence_follow_up", "reformulation", "contextual_follow_up",
            },
        ):
            unresolved_signals.append("conversation_reference_without_verified_context")
        if uses_conversation_reference:
            context = conversation_context or {}
            verified_entities = dict((context.get("last_verified_context") or {}).get("resolved_entities") or {})
            degraded_entities = dict((context.get("last_degraded_context") or {}).get("resolved_entities") or {})
            lineage_entities = verified_entities or degraded_entities
            explicit_asset = explicit_asset or self._context_asset(
                lineage_entities.get("asset") or context.get("resolved_asset")
            )
            explicit_setup_id = explicit_setup_id or self._context_entity_id(
                lineage_entities.get("setup_id") or context.get("resolved_setup_id")
            )
            explicit_strategy_id = explicit_strategy_id or self._context_entity_id(
                lineage_entities.get("strategy_id") or context.get("resolved_strategy_id")
            )
            explicit_bot_id = explicit_bot_id or self._context_entity_id(
                lineage_entities.get("bot_id") or context.get("resolved_bot_id")
            )
        requested_entities = self._requested_entities(
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
        )
        missing_essential_inputs: List[str] = []
        # New V2 runs select their operation exclusively through the semantic
        # front door.  The legacy analyzer remains below only to reconstruct
        # historical planless records, never to choose a new contract.
        operation_id = semantic.operation_id
        pending_operation_id = self.operation_state.pending_operation_id(conversation_context or {})
        cancelled_guided_state = None
        if pending_operation_id and self.operation_state.is_cancel_intent(text):
            cancelled_guided_state = self.operation_state.cancel(
                operation_id=pending_operation_id,
                conversation_context=conversation_context,
            )
            operation_id = "clarify_request"
        if uses_conversation_reference and "conversation_reference_without_verified_context" in unresolved_signals:
            operation_id = "clarify_request"
        try:
            operation = self.operations.require_supported(operation_id)
        except FinnV2OperationUnavailableError as exc:
            # An unavailable registry capability cannot fall through to a
            # legacy planner or business write path.
            operation_id = "unavailable"
            operation = self.operations.require_supported(operation_id)
            interaction_mode = "UNAVAILABLE"
            unresolved_signals.append(str(exc))
        else:
            # The registry owns the persisted mode for every new request.
            interaction_mode = operation.mode
            validation_error = self.classification_validator.validation_error(
                semantic,
                facts=preprocessed,
                conversation_context=conversation_context,
            )
            if validation_error is not None:
                operation_id = "clarify_request"
                operation = self.operations.require_supported(operation_id)
                interaction_mode = operation.mode
                unresolved_signals.append(validation_error)
        # The model selects the operation, while the registry owns its
        # non-negotiable state requirements. A lineage contract must receive
        # the prior verified record even if the structured model leaves the
        # optional reference field empty.
        if operation.requires_verified_context:
            uses_conversation_reference = True
            has_safe_lineage = self._has_safe_lineage(
                conversation_context or {},
                allow_degraded=operation.operation_id in {
                    "explain_previous_evidence", "reformulate_previous_response", "evaluate_bot",
                },
            )
            if not has_safe_lineage and "conversation_reference_without_verified_context" not in unresolved_signals:
                unresolved_signals.append("conversation_reference_without_verified_context")
                operation_id = "clarify_request"
                operation = self.operations.require_supported(operation_id)
                interaction_mode = operation.mode
        scopes = self._presentation_subject_scopes(operation, preprocessed.explicit_entities)
        integrated_plan = operation.operation_id == "evaluate_plan"
        primary_subject = self._presentation_primary_subject(operation)
        action_risk_class = self._contract_action_risk_class(operation)
        requires_gap_analysis = semantic.discourse == "evaluation" and any(
            token in normalized
            for token in ("ontbreekt", "ontbrekende", "ontbrekend", "missing", "mist", "gap", "zwak", "risico")
        )
        requires_comparison = operation.operation_id in {"evaluate_plan", "evaluate_strategy"}
        requests_change = operation.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}
        requests_execution = operation.mode == "EXECUTION"
        confidence = semantic.confidence
        if interaction_mode == "UNAVAILABLE":
            unresolved_signals.append("financial_domain_unavailable")
            if "beste trade" in normalized or "best trade" in normalized:
                unresolved_signals.append("insufficient_trade_context")
        # A workspace asset may enrich a setup draft, but it is never a
        # substitute for the asset explicitly requested by a write operation.
        preliminary_target = self.target_resolver.resolve(
            explicit_target_asset=message_asset,
            selector_target_asset=semantic.selected_target_asset,
            verified_context=conversation_context,
            operation_state=(conversation_context or {}).get("active_guided_operation") or (conversation_context or {}).get("operation_state"),
            workspace_asset=context_asset,
            allow_workspace_fallback=operation.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"},
        )
        operation_asset = preliminary_target.target_asset
        # ``concept`` is a normalized request fact, not a guided slot.  A
        # selected financial-concept contract therefore has its required input
        # before any stateful clarification logic is considered.
        concept_input_is_present = (
            operation_id == "explain_financial_concept"
            and bool(preprocessed.financial_concept)
        )
        guided_state = cancelled_guided_state or (
            self.operation_state.resolve(
                contract=operation,
                message=text,
                explicit_asset=operation_asset,
                conversation_context=conversation_context,
                supplied_inputs=semantic.supplied_inputs,
                derived_inputs=semantic.derived_inputs,
            ) if operation.required_inputs and not concept_input_is_present else None
        )
        if guided_state is not None:
            missing_essential_inputs = list(guided_state.missing_required_inputs)
        operation_state_payload = guided_state.dict() if guided_state is not None else {}
        if (
            guided_state is None
            and uses_conversation_reference
            and isinstance((conversation_context or {}).get("last_verified_context"), dict)
        ):
            verified = dict((conversation_context or {}).get("last_verified_context") or {})
            operation_state_payload = {
                "previous_verified_response_id": verified.get("verified_response_id"),
                "previous_verified_run_id": verified.get("run_id"),
                "previous_verified_operation_id": verified.get("operation_id"),
                "previous_verified_conclusion": verified.get("conclusion"),
                "previous_verified_response": verified.get("response"),
                "previous_evidence_refs": list(verified.get("evidence_refs") or []),
                "resolved_entities": dict(verified.get("resolved_entities") or {}),
            }
        elif guided_state is None and uses_conversation_reference and self._has_safe_lineage(
            conversation_context or {}, allow_degraded=True
        ):
            # Degraded lineage retains provenance only. It never revives an
            # unverified conclusion or response text for a follow-up.
            degraded = dict((conversation_context or {}).get("last_degraded_context") or {})
            operation_state_payload = {
                "previous_degraded_run_id": degraded.get("run_id"),
                "previous_degraded_operation_id": degraded.get("operation_id"),
                "previous_evidence_refs": list(degraded.get("evidence_refs") or []),
                "previous_degraded_evidence_scopes": list(degraded.get("evidence_scopes") or []),
                "previous_degraded_released_sections": list(degraded.get("released_response_sections") or []),
                "previous_degraded_released_response": dict(degraded.get("released_response") or {}),
                "resolved_entities": dict(degraded.get("resolved_entities") or {}),
            }
        target_resolution = self.target_resolver.resolve(
            explicit_target_asset=message_asset,
            selector_target_asset=semantic.selected_target_asset,
            verified_context=conversation_context,
            operation_state=operation_state_payload or (conversation_context or {}).get("active_guided_operation") or (conversation_context or {}).get("operation_state"),
            workspace_asset=context_asset,
            allow_workspace_fallback=operation.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"},
        )
        request_plan = self._request_plan(
            interaction_mode=interaction_mode,
            scopes=scopes,
            primary_subject=primary_subject,
            normalized=normalized,
            confidence=confidence,
            conversation_context=conversation_context or {},
            integrated_plan=integrated_plan,
            missing_essential_inputs=missing_essential_inputs,
            uses_conversation_reference=uses_conversation_reference,
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
            financial_concept=preprocessed.financial_concept,
            operation_id=operation_id,
            operation=operation,
            operation_state=operation_state_payload,
            context_asset=context_asset,
            target_asset=target_resolution.target_asset,
            referenced_asset=message_asset or explicit_asset,
            # The request plan is the runtime projection consumed by policy
            # and proposal services. Keep its action tied to the immutable
            # contract rather than to a selector or preprocessor verb.
            requested_action=operation.action_polarity.value,
            discourse_type=semantic.discourse,
            selector_source=semantic.selector_source,
            selector_confidence=semantic.confidence,
            candidate_operation_ids=list(semantic.candidate_operation_ids),
            selection_domain=semantic.domain,
            selection_supported=semantic.supported,
            selection_reason_code=semantic.reason_code,
            unsupported_capability=semantic.unsupported_capability,
        )

        return RequestAnalysisResult(
            interaction_mode=interaction_mode,
            subject_scopes=scopes,
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
            primary_subject=primary_subject,
            requested_entities=requested_entities,
            output_contract=operation.response_strategy if operation is not None else "unavailable",
            action_risk_class=action_risk_class,
            missing_essential_inputs=missing_essential_inputs,
            requires_comparison=requires_comparison,
            requires_gap_analysis=requires_gap_analysis,
            requests_change=requests_change,
            requests_execution=requests_execution,
            confidence=confidence,
            matched_signals=matched_signals,
            unresolved_signals=unresolved_signals,
            reasoning_required=bool(operation is not None and operation.model_policy != "never"),
            request_plan=request_plan,
        )

    def _request_plan(
        self,
        *,
        interaction_mode: str,
        scopes: List[str],
        primary_subject: Optional[str],
        normalized: str,
        integrated_plan: bool,
        confidence: str,
        conversation_context: Dict[str, object],
        missing_essential_inputs: List[str],
        uses_conversation_reference: bool,
        explicit_asset: Optional[str],
        explicit_setup_id: Optional[int],
        explicit_strategy_id: Optional[int],
        explicit_bot_id: Optional[int],
        financial_concept: Optional[str],
        operation_id: str,
        operation,
        operation_state: Dict[str, object],
        context_asset: Optional[str],
        target_asset: Optional[str],
        referenced_asset: Optional[str],
        requested_action: Optional[str],
        discourse_type: str,
        selector_source: str,
        selector_confidence: str,
        candidate_operation_ids: List[str],
        selection_domain: Optional[str],
        selection_supported: Optional[bool],
        selection_reason_code: Optional[str],
        unsupported_capability: Optional[str],
    ) -> RequestPlan:
        reference = None
        reference_kind = None
        if uses_conversation_reference:
            verified_context = dict(conversation_context.get("last_verified_context") or {})
            degraded_context = dict(conversation_context.get("last_degraded_context") or {})
            is_canonical_context = bool(conversation_context.get("conversation_state_version"))
            if verified_context.get("verified_response_id"):
                reference = str(verified_context["verified_response_id"])
                reference_kind = "previous_verified_response"
            elif degraded_context.get("run_id"):
                reference = str(degraded_context["run_id"])
                reference_kind = "previous_degraded_response"
            elif not is_canonical_context and conversation_context.get("last_verified_response_id"):
                reference = str(conversation_context["last_verified_response_id"])
                reference_kind = "previous_verified_response"
            elif not is_canonical_context and conversation_context.get("last_user_goal"):
                reference = str(conversation_context["last_user_goal"])
                reference_kind = "previous_verified_response"
        score = {"high": 0.9, "medium": 0.7, "low": 0.4, "none": 0.0}[confidence]
        return RequestPlan(
            user_goal=self._user_goal(interaction_mode, primary_subject, normalized, integrated_plan),
            operation_id=operation_id,
            operation_contract_version=getattr(operation, "version", None),
            skip_canonical_context_graph=getattr(operation, "context_policy", None) == "minimal",
            interaction_mode=interaction_mode,
            primary_domains=list(scopes),
            required_information_scopes=list(getattr(operation, "required_scopes", ())),
            optional_information_scopes=list(getattr(operation, "optional_scopes", ())),
            requested_operation=operation_id if interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"} else None,
            conversation_reference=reference,
            conversation_reference_kind=reference_kind,
            referenced_entities={
                key: value
                for key, value in {
                    "asset": explicit_asset,
                    "setup_id": explicit_setup_id,
                    "strategy_id": explicit_strategy_id,
                    "bot_id": explicit_bot_id,
                    "concept": financial_concept,
                }.items()
                if value is not None
            },
            missing_information=list(missing_essential_inputs),
            operation_state=operation_state,
            context_asset=context_asset,
            target_asset=target_asset,
            referenced_asset=referenced_asset,
            requested_action=requested_action,
            discourse_type=discourse_type,
            selector_source=selector_source,
            selector_confidence=selector_confidence,
            candidate_operation_ids=candidate_operation_ids,
            selection_domain=selection_domain,
            selection_supported=selection_supported,
            selection_reason_code=selection_reason_code,
            unsupported_capability=unsupported_capability,
            clarification_required=bool(missing_essential_inputs) or interaction_mode == "CLARIFICATION",
            confidence_score=score,
        )

    @staticmethod
    def _has_safe_lineage(context: Dict[str, object], *, allow_degraded: bool) -> bool:
        if context.get("last_verified_context") or context.get("last_verified_conclusion"):
            return True
        degraded = context.get("last_degraded_context")
        return bool(
            allow_degraded
            and isinstance(degraded, dict)
            and degraded.get("evidence_refs")
        )

    @staticmethod
    def _user_goal(interaction_mode: str, primary_subject: Optional[str], normalized: str, integrated_plan: bool) -> str:
        if interaction_mode == "EVALUATE" and integrated_plan:
            return "evaluate_complete_plan"
        if interaction_mode == "CREATE_PROPOSAL" and primary_subject == "setup":
            return "propose_setup"
        if interaction_mode == "ACTION_PROPOSAL" and primary_subject == "watchlist":
            return "propose_watchlist_change"
        if interaction_mode == "READ":
            return f"read_{primary_subject or 'context'}"
        return interaction_mode.casefold()

    @staticmethod
    def _presentation_subject_scopes(operation, explicit_entities: tuple[str, ...]) -> List[str]:
        """Map contract facts to legacy response diagnostics only.

        The result is retained for historical API compatibility.  Execution
        services consume the persisted contract scopes, not these labels.
        """
        entity_labels = {
            "profile": "profile",
            "indicator_configuration": "indicators",
            "watchlist": "watchlist",
            "setup": "setup",
            "strategy": "strategy",
            "bot": "bot",
            "bot_status": "bot",
            "asset": "asset",
        }
        labels: List[str] = []
        if operation.operation_id == "capability":
            return ["capability"]
        # These labels are a legacy presentation diagnostic.  They reflect the
        # user's explicit subjects, while the immutable contract still owns
        # the complete evidence scopes consumed by tools and the verifier.
        for entity in ("profile", "indicator_configuration", "setup", "strategy", "bot", "bot_status", "watchlist", "asset"):
            label = entity_labels.get(entity)
            if entity in explicit_entities and label and label not in labels:
                labels.append(label)
        if operation.operation_id == "evaluate_plan" and not labels:
            labels = ["profile", "indicators", "setup", "strategy", "bot"]
        # Linked read contracts expose the intervening plan graph in legacy
        # diagnostics. This is a projection of the selected contract only.
        linked_graph_labels = {
            "read_linked_strategy": ("setup", "strategy"),
            "read_linked_bot": ("setup", "strategy", "bot") if "strategy" in explicit_entities else (),
        }
        for label in linked_graph_labels.get(operation.operation_id, ()):
            if label not in labels:
                labels.append(label)
        domain_label = {
            "setup": "setup", "strategy": "strategy", "bot": "bot",
            "watchlist": "watchlist", "plan": "setup", "indicators": "indicators", "system": "unknown",
        }.get(operation.domain)
        if domain_label and domain_label not in labels:
            labels.append(domain_label)
        diagnostic_order = {
            "profile": 0, "indicators": 1, "setup": 2, "strategy": 3,
            "bot": 4, "watchlist": 5, "asset": 6, "capability": 7,
            "unknown": 8,
        }
        return sorted(labels, key=lambda label: diagnostic_order.get(label, 99)) or ["unknown"]

    @staticmethod
    def _presentation_primary_subject(operation) -> Optional[str]:
        return {
            "system": "capability" if operation.operation_id == "capability" else "unknown",
            "plan": "setup",
        }.get(operation.domain, operation.domain)

    @staticmethod
    def _contract_action_risk_class(operation) -> str:
        if operation.policy_class == "high_risk_action":
            return "live_action"
        if operation.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            return "proposal_action"
        return "read_only"

    def _extract_entity_id(self, original: str, keyword_root: str) -> Optional[int]:
        match = re.search(rf"\b{keyword_root}[a-z]*\s+#?(\d+)\b", original, re.IGNORECASE)
        if not match:
            return None
        try:
            value = int(match.group(1))
        except ValueError:
            return None
        return value if value > 0 else None

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()

    @staticmethod
    def _uses_conversation_reference(normalized: str) -> bool:
        return any(
            re.search(rf"(?<!\w){re.escape(token)}(?!\w)", normalized)
            for token in [
                "die", "dat", "eerder", "onderbouw", "waar baseer",
                "korter", "anders", "herformuleer", "dezelfde conclusie",
            ]
        )

    @staticmethod
    def _context_asset(value: object) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _context_entity_id(value: object) -> Optional[int]:
        try:
            entity_id = int(value)
        except (TypeError, ValueError):
            return None
        return entity_id if entity_id > 0 else None

    def _requested_entities(
        self,
        *,
        explicit_asset: Optional[str],
        explicit_setup_id: Optional[int],
        explicit_strategy_id: Optional[int],
        explicit_bot_id: Optional[int],
    ) -> List[str]:
        entities: List[str] = []
        if explicit_asset:
            entities.append("asset")
        if explicit_setup_id:
            entities.append("setup")
        if explicit_strategy_id:
            entities.append("strategy")
        if explicit_bot_id:
            entities.append("bot")
        return entities
