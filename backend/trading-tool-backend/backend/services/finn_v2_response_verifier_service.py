from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_orchestrator_repository import FinnV2OrchestratorRepository
from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.infrastructure.repositories.finn_v2_reasoning_repository import FinnV2ReasoningRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.infrastructure.repositories.finn_v2_verifier_repository import FinnV2VerifierRepository
from backend.infrastructure.repositories.finn_v2_verified_response_repository import FinnV2VerifiedResponseRepository
from backend.domain.finn_v2_contract import normalize_interaction_mode
from backend.schemas.finn_v2_delivery_schema import FinnV2DeliveryEnvelope
from backend.schemas.finn_v2_orchestrator_schema import ORCHESTRATOR_VERSION, OrchestratorResult
from backend.schemas.finn_v2_policy_schema import POLICY_VERSION, FinnV2PolicyDecision
from backend.schemas.finn_v2_proposal_schema import (
    BotActivationChange,
    IndicatorConfigurationChange,
    ManualOrderChange,
    PortfolioRebalanceChange,
    ProposalTarget,
    SetupCreateChange,
    SetupChange,
    StrategyChange,
    TradePlanChange,
    ValidatedProposalInput,
    WatchlistChange,
)
from backend.schemas.finn_v2_reasoning_context_schema import REASONING_CONTEXT_VERSION
from backend.schemas.finn_v2_reasoning_schema import PersistedReasoningRecord, ReasoningResult
from backend.schemas.finn_v2_response_schema import FINN_V2_VERIFIED_RESPONSE_VERSION, ResponseDraft, VerifiedResponse
from backend.schemas.finn_v2_verifier_schema import ClaimVerification, CoverageVerification, SemanticVerificationResult, VerifierResult
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_capability_registry_service import FinnV2CapabilityRegistryService
from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_proposal_service import FinnV2ProposalService
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_response_downgrade_service import FinnV2ResponseDowngradeService
from backend.services.finn_v2_response_draft_service import FinnV2ResponseDraftService
from backend.services.finn_v2_response_repair_service import FinnV2ResponseRepairService
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.services.platform_metrics import increment_execution_safety_counter


class FinnV2ResponseVerifierService:
    REQUIRED_SCOPE_TO_DOMAIN = {
        "profile": "identity_context",
        "watchlist": "identity_context",
        "analysis": "market_context",
        "indicators": "market_context",
        "setup": "plan_context",
        "strategy": "plan_context",
        "bot": "automation_context",
        "daily_report": "report_context",
        "reflection": "review_context",
        "portfolio": "portfolio_context",
    }
    REPAIRABLE_CODES = FinnV2ResponseRepairService.REPAIRABLE_CODES
    BLOCKING_CODES = {
        "ownership_violation",
        "cross_user_evidence",
        "evidence_hash_mismatch",
        "policy_violation",
        "paper_live_mismatch",
        "invalid_proposal_target",
        "snapshot_integrity_invalid",
        "safety_violation",
    }

    def __init__(self, session: AsyncSession, *, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.capabilities = FinnV2CapabilityRegistryService()
        self.runs = FinnV2RunRepository(session)
        self.orchestrators = FinnV2OrchestratorRepository(session)
        self.policies = FinnV2PolicyRepository(session)
        self.reasoning = FinnV2ReasoningRepository(session)
        self.snapshots = FinnV2StateRepository(session)
        self.validations = FinnV2ValidationRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.verifiers = FinnV2VerifierRepository(session)
        self.verified = FinnV2VerifiedResponseRepository(session)
        self.contexts = FinnV2ReasoningContextService(session)
        self.drafts = FinnV2ResponseDraftService()
        self.semantic = FinnV2SemanticVerifierService(self.flags)
        self.repairs = FinnV2ResponseRepairService(self.flags)
        self.downgrades = FinnV2ResponseDowngradeService()
        self.proposals = FinnV2ProposalService(session, flag_service=self.flags)

    async def verify_run(self, *, user_id: int, run_id: str, trace_id: str) -> VerifiedResponse:
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")

        orchestrator_row = await self.orchestrators.get_for_run_version(run_id=run_id, user_id=user_id, orchestrator_version=ORCHESTRATOR_VERSION)
        if orchestrator_row is None:
            raise ValueError("orchestrator_not_ready")
        reasoning_row = await self.reasoning.get_reusable_result(
            run_id=run_id,
            user_id=user_id,
            context_version=REASONING_CONTEXT_VERSION,
            evidence_set_hash=getattr(orchestrator_row, "validation_id", "") or "",
            prompt_version="2026-08-17.block6",
            model=self.flags.reasoning_model_override() or "unknown",
        )
        if reasoning_row is None:
            reasoning_row = await self._latest_reasoning_for_run(run_id=run_id, user_id=user_id)
        if reasoning_row is None:
            raise ValueError("reasoning_not_ready")

        reasoning_record = self._reasoning_record_from_row(reasoning_row)
        orchestrator_result = self._orchestrator_result_from_row(orchestrator_row)
        validation = await self.validations.get_by_id_for_user(validation_id=reasoning_record.validation_id, user_id=user_id)
        snapshot = await self.snapshots.get_by_id_for_user(snapshot_id=reasoning_record.snapshot_id, user_id=user_id)
        policy_row = await self.policies.get_for_run_version(run_id=run_id, user_id=user_id, policy_version=POLICY_VERSION)
        if validation is None or snapshot is None or policy_row is None:
            raise ValueError("verifier_dependencies_missing")
        policy = FinnV2PolicyDecision.parse_obj(policy_row.decision_json)
        context = await self.contexts.build(
            run=run,
            orchestrator_result=orchestrator_result,
            snapshot=snapshot,
            validation=validation,
            policy=policy,
        )

        draft = self.drafts.build(reasoning_record=reasoning_record)
        await self._append_trace(trace_id=trace_id, run_id=run_id, user_id=user_id, event_type="response_draft_built", payload={"draft_id": draft.draft_id, "mode": draft.mode})
        verified = await self._verify_draft(
            run=run,
            orchestrator_result=orchestrator_result,
            policy=policy,
            context=context,
            validation=validation,
            draft=draft,
            trace_id=trace_id,
            repair_attempt=0,
        )
        return verified

    async def _verify_draft(self, *, run, orchestrator_result, policy, context, validation, draft: ResponseDraft, trace_id: str, repair_attempt: int) -> VerifiedResponse:
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_verification_started", payload={"draft_id": draft.draft_id, "repair_attempt": repair_attempt, "mode": draft.mode})
        verifier = self._deterministic_verify(
            run=run,
            orchestrator_result=orchestrator_result,
            policy=policy,
            context=context,
            validation=validation,
            draft=draft,
            repair_attempt=repair_attempt,
        )
        semantic_result = SemanticVerificationResult(available=False, passes=True)
        if verifier.passed and self._should_run_semantic(mode=draft.mode):
            await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="semantic_verification_started", payload={"draft_id": draft.draft_id, "mode": draft.mode})
            semantic_result = self.semantic.verify(
                mode=draft.mode,
                user_message=run.message,
                sanitized_draft=self.drafts.sanitize_for_semantic_verifier(draft),
                compact_evidence=self.drafts.compact_evidence(context.evidence, self._all_refs(draft)),
                deterministic_summary={"passed": verifier.passed, "reason_codes": verifier.reason_codes, "coverage": verifier.coverage.dict()},
            )
            await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="semantic_verification_completed", payload={"draft_id": draft.draft_id, "available": semantic_result.available, "passes": semantic_result.passes, "reason_codes": semantic_result.reason_codes})
            verifier = self._merge_semantic(verifier, semantic_result, draft.mode)

        if verifier.action == "repair_once" and self.repairs.can_repair(reason_codes=verifier.reason_codes, repair_attempt=repair_attempt):
            await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_repair_started", payload={"draft_id": draft.draft_id, "reason_codes": verifier.reason_codes})
            repaired = self.repairs.repair(draft=draft, reason_codes=verifier.reason_codes, uncertainty_summary=self._default_uncertainty(validation, context))
            await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_repair_completed", payload={"draft_id": repaired.draft_id})
            return await self._verify_draft(
                run=run,
                orchestrator_result=orchestrator_result,
                policy=policy,
                context=context,
                validation=validation,
                draft=repaired,
                trace_id=trace_id,
                repair_attempt=repair_attempt + 1,
            )

        if not verifier.passed:
            if verifier.action == "downgrade_to_fact":
                draft = self.downgrades.downgrade_to_fact(draft=draft)
            elif verifier.action == "downgrade_to_clarification":
                draft = self.downgrades.downgrade_to_clarification(draft=draft, orchestrator_result=orchestrator_result)
            elif verifier.action == "downgrade_to_unavailable":
                draft = self.downgrades.downgrade_to_unavailable(draft=draft, reason=verifier.reason_codes[0] if verifier.reason_codes else None)
            elif verifier.action == "reject":
                await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_rejected", payload={"draft_id": draft.draft_id, "reason_codes": verifier.reason_codes})
                raise ValueError("response_rejected")
            if verifier.action.startswith("downgrade_"):
                await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_downgraded", payload={"draft_id": draft.draft_id, "action": verifier.action})
                verifier = self._deterministic_verify(
                    run=run,
                    orchestrator_result=orchestrator_result,
                    policy=policy,
                    context=context,
                    validation=validation,
                    draft=draft,
                    repair_attempt=repair_attempt,
                    force_action="deliver",
                )

        proposal_id = None
        if draft.proposal_candidate is not None and normalize_interaction_mode(draft.mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"} and verifier.proposal_ok and verifier.policy_ok:
            proposal_id = await self._create_draft_proposal(
                run=run,
                policy=policy,
                draft=draft,
                validation=validation,
                trace_id=trace_id,
            )

        persisted = await self._persist_verified_response(
            run=run,
            draft=draft,
            verifier=verifier,
            proposal_id=proposal_id,
            confirmation_required=bool(policy.confirmation_required and normalize_interaction_mode(draft.mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}),
        )
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="response_verification_completed", payload={"verifier_result_id": verifier.verifier_result_id, "action": verifier.action, "passed": verifier.passed, "reason_codes": verifier.reason_codes})
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="verified_response_persisted", payload={"verified_response_id": persisted.verified_response_id, "mode": persisted.mode, "verifier_status": persisted.verifier_status})
        envelope = FinnV2DeliveryEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status="completed",
            response=persisted,
            proposal_id=proposal_id,
            confirmation_required=persisted.confirmation_required,
        )
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="delivery_envelope_built", payload={"run_id": run.id, "delivery_source": envelope.delivery_source})
        return persisted

    def _deterministic_verify(self, *, run, orchestrator_result, policy, context, validation, draft: ResponseDraft, repair_attempt: int, force_action: Optional[str] = None) -> VerifierResult:
        reason_codes: list[str] = []
        evidence_by_ref = {item.evidence_id: item for item in context.evidence}
        schema_ok = True
        try:
            ResponseDraft.parse_obj(draft.dict())
        except Exception:
            schema_ok = False
            reason_codes.append("schema_invalid")

        ownership_ok = draft.user_id == run.user_id and draft.run_id == run.id and all(item.user_id == run.user_id for item in [run])
        if not ownership_ok:
            reason_codes.append("ownership_violation")

        evidence_ok = draft.evidence_set_hash == validation.evidence_set_hash
        if not evidence_ok:
            reason_codes.append("evidence_hash_mismatch")

        claim_results = []
        covered_scopes = set()
        covered_domains = set()
        for claim in draft.claims:
            refs_valid = bool(claim.evidence_refs) or claim.claim_type in {"recommendation", "uncertainty"}
            if claim.claim_type in {"fact", "inference", "evaluation"} and not claim.evidence_refs:
                refs_valid = False
            ownership_valid = True
            entailment_valid = True
            status = "supported"
            claim_reasons: list[str] = []
            matched_evidence = [evidence_by_ref.get(ref) for ref in claim.evidence_refs if ref in evidence_by_ref]
            if any(ref not in evidence_by_ref for ref in claim.evidence_refs):
                refs_valid = False
                ownership_valid = False
                status = "unsupported"
                claim_reasons.append("invalid_evidence_ref")
            if matched_evidence:
                for evidence in matched_evidence:
                    covered_scopes.update(self._scopes_for_evidence(evidence))
                    covered_scopes.add(self._scope_for_domain(evidence.domain))
                    if evidence.domain:
                        covered_domains.add(evidence.domain)
                status, claim_reasons, entailment_valid = self._evaluate_claim_support(claim.text, matched_evidence, claim.claim_type)
            elif claim.claim_type not in {"recommendation", "uncertainty"}:
                status = "unverifiable"
                claim_reasons.append("missing_evidence")
            claim_results.append(
                ClaimVerification(
                    claim_id=claim.claim_id,
                    status=status,
                    evidence_refs_valid=refs_valid,
                    ownership_valid=ownership_valid,
                    entailment_valid=entailment_valid,
                    reason_codes=claim_reasons,
                )
            )
            if status in {"unsupported", "contradicted", "unverifiable"}:
                evidence_ok = False
                reason_codes.extend(code for code in claim_reasons if code not in reason_codes)

        required_scopes = [scope for scope in orchestrator_result.analysis.subject_scopes if scope != "unknown"]
        covered_scopes.update(self._covered_scopes_from_draft(draft, evidence_by_ref))
        covered_domains.update(self._covered_domains_from_draft(draft, evidence_by_ref))
        capability_grounding_ok = self._capability_grounding_ok(draft)
        if draft.mode == "CAPABILITY" and capability_grounding_ok:
            covered_scopes.add("capability")
        satisfied_scopes = {scope for scope in required_scopes if self._scope_is_covered(scope, covered_scopes, covered_domains, draft=draft, policy=policy)}
        missing_scopes = [scope for scope in required_scopes if scope not in satisfied_scopes]
        coverage = CoverageVerification(
            required_scopes=required_scopes,
            covered_scopes=sorted(covered_scopes.union(satisfied_scopes)),
            missing_scopes=missing_scopes,
            coverage_ok=not missing_scopes,
        )
        if not coverage.coverage_ok:
            reason_codes.append("response_scope_incomplete")

        relevance_ok = self._is_relevant(run.message, draft)
        if not relevance_ok:
            reason_codes.append("response_not_answering_question")

        personalization_ok = self._evaluate_personalization_ok(
            run.message,
            draft,
            context,
            requested_scopes=getattr(getattr(orchestrator_result, "analysis", None), "subject_scopes", None),
        )
        if not personalization_ok:
            reason_codes.append("response_insufficiently_personalized")

        mode_purity_ok = self._mode_purity_ok(draft)
        if not mode_purity_ok:
            reason_codes.append("mode_purity_violation")

        if draft.mode == "CAPABILITY" and not capability_grounding_ok:
            reason_codes.append("capability_claim_not_registered")

        uncertainty_ok = self._uncertainty_ok(draft, context)
        if not uncertainty_ok:
            reason_codes.append("missing_uncertainty")

        follow_up_ok = self._follow_up_ok(draft)
        if not follow_up_ok:
            reason_codes.append("follow_up_invalid")

        normalized_mode = normalize_interaction_mode(draft.mode)
        policy_ok = bool(policy.allowed)
        if not policy.allowed and normalized_mode in {"UNAVAILABLE", "CLARIFICATION"}:
            policy_ok = True
        if normalized_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"} and not policy.proposal_allowed:
            policy_ok = False
        if not policy_ok:
            reason_codes.append("policy_violation")

        proposal_ok = self._proposal_ok(draft, policy, evidence_by_ref)
        if draft.proposal_candidate is not None and not proposal_ok:
            reason_codes.append("invalid_proposal_target")

        safety_ok = self._safety_ok(draft)
        if not safety_ok:
            reason_codes.append("safety_violation")

        if validation.integrity_status == "invalid":
            reason_codes.append("snapshot_integrity_invalid")
        if self._paper_live_mismatch(draft, evidence_by_ref):
            reason_codes.append("paper_live_mismatch")

        passed = all(
            [
                schema_ok,
                ownership_ok,
                evidence_ok,
                coverage.coverage_ok,
                relevance_ok,
                personalization_ok,
                mode_purity_ok,
                uncertainty_ok,
                follow_up_ok,
                proposal_ok,
                policy_ok,
                safety_ok,
                validation.integrity_status != "invalid",
                "paper_live_mismatch" not in reason_codes,
            ]
        )
        action = force_action or self._decide_action(
            draft=draft,
            reason_codes=reason_codes,
            passed=passed,
            repair_attempt=repair_attempt,
            has_clarification=bool(orchestrator_result.selected_clarification),
        )
        verifier = VerifierResult(
            verifier_result_id=f"finn-v2-verifier-{uuid.uuid4().hex}",
            run_id=run.id,
            user_id=run.user_id,
            draft_id=draft.draft_id,
            passed=passed,
            action=action,
            claim_results=claim_results,
            coverage=coverage,
            schema_ok=schema_ok,
            ownership_ok=ownership_ok,
            evidence_ok=evidence_ok,
            relevance_ok=relevance_ok,
            mode_purity_ok=mode_purity_ok,
            uncertainty_ok=uncertainty_ok,
            follow_up_ok=follow_up_ok,
            proposal_ok=proposal_ok,
            policy_ok=policy_ok,
            safety_ok=safety_ok,
            reason_codes=self._dedupe(reason_codes),
            semantic_verifier_used=False,
            created_at=datetime.now(timezone.utc),
        )
        return verifier

    def _merge_semantic(self, verifier: VerifierResult, semantic: SemanticVerificationResult, mode: str) -> VerifierResult:
        if not semantic.available:
            if not self.flags.is_semantic_verifier_enabled():
                return verifier
            if mode in self.flags.semantic_verifier_required_modes():
                reason_codes = self._dedupe(verifier.reason_codes + ["semantic_verifier_unavailable"])
                return verifier.copy(update={"passed": False, "action": "downgrade_to_unavailable", "reason_codes": reason_codes, "semantic_verifier_used": True})
            return verifier.copy(update={"semantic_verifier_used": True})
        if semantic.passes:
            return verifier.copy(update={"semantic_verifier_used": True})
        reason_codes = self._dedupe(verifier.reason_codes + list(semantic.reason_codes))
        return verifier.copy(
            update={
                "passed": False,
                "action": self._decide_action(draft=type("D", (), {"mode": mode})(), reason_codes=reason_codes, passed=False, repair_attempt=0, has_clarification=True),
                "relevance_ok": verifier.relevance_ok and semantic.relevance_ok,
                "mode_purity_ok": verifier.mode_purity_ok and semantic.mode_purity_ok,
                "follow_up_ok": verifier.follow_up_ok and semantic.follow_up_ok,
                "semantic_verifier_used": True,
                "reason_codes": reason_codes,
            }
        )

    async def _persist_verified_response(self, *, run, draft: ResponseDraft, verifier: VerifierResult, proposal_id: Optional[str], confirmation_required: bool) -> VerifiedResponse:
        verifier_status = "repaired" if verifier.action == "deliver" and verifier.reason_codes else "passed"
        if normalize_interaction_mode(draft.mode) in {"READ", "CAPABILITY", "CLARIFICATION", "UNAVAILABLE"} and verifier.reason_codes:
            verifier_status = "downgraded"
        verifier_row = await self.verifiers.create(
            id=verifier.verifier_result_id,
            run_id=run.id,
            user_id=run.user_id,
            draft_id=draft.draft_id,
            reasoning_result_id=draft.reasoning_result_id,
            passed=verifier.passed,
            action=verifier.action,
            result_json=to_json_safe(verifier.dict()),
            reason_codes_json=verifier.reason_codes,
            deterministic_version=verifier.verifier_version,
            semantic_verifier_used=verifier.semantic_verifier_used,
            semantic_model=self.flags.semantic_verifier_model(),
            repair_attempt=min(1, len(verifier.reason_codes) if verifier_status == "repaired" else 0),
        )
        record = VerifiedResponse(
            verified_response_id=f"finn-v2-verified-response-{uuid.uuid4().hex}",
            run_id=run.id,
            user_id=run.user_id,
            mode=draft.mode,
            direct_answer=draft.direct_answer,
            main_observation=draft.main_observation,
            supporting_points=draft.supporting_points,
            claims=draft.claims,
            uncertainty_summary=draft.uncertainty_summary,
            uncertainty_codes=draft.uncertainty_codes,
            next_step=draft.next_step,
            follow_up_question=draft.follow_up_question,
            proposal_id=proposal_id,
            confirmation_required=confirmation_required,
            verifier_status=verifier_status,
            evidence_set_hash=draft.evidence_set_hash,
            verifier_result_id=verifier_row.id,
            reasoning_provenance=dict(draft.reasoning_provenance),
            response_version=FINN_V2_VERIFIED_RESPONSE_VERSION,
            created_at=datetime.now(timezone.utc),
        )
        await self.verified.create(
            id=record.verified_response_id,
            run_id=record.run_id,
            user_id=record.user_id,
            verifier_result_id=record.verifier_result_id,
            mode=record.mode,
            verifier_status=record.verifier_status,
            response_json=to_json_safe(record.dict()),
            evidence_set_hash=record.evidence_set_hash,
            response_version=record.response_version,
            created_at=record.created_at,
        )
        increment_execution_safety_counter(f"finn_v2_verifier_results_total:{record.mode}:{verifier.action}")
        increment_execution_safety_counter(f"finn_v2_verified_responses_total:{record.mode}:{record.verifier_status}")
        return record

    async def _create_draft_proposal(self, *, run, policy: FinnV2PolicyDecision, draft: ResponseDraft, validation, trace_id: str) -> Optional[str]:
        proposal_input = self._proposal_input_from_candidate(run=run, draft=draft, validation=validation)
        if proposal_input is None:
            return None
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="proposal_candidate_verified", payload={"operation_type": proposal_input.operation_type, "target_type": proposal_input.target.target_type})
        record = await self.proposals.create_proposal(
            user_id=run.user_id,
            run_id=run.id,
            trace_id=trace_id,
            policy=policy,
            proposal_input=proposal_input,
        )
        await self._append_trace(trace_id=trace_id, run_id=run.id, user_id=run.user_id, event_type="draft_proposal_created", payload={"proposal_id": record.proposal_id, "operation_type": record.operation_type})
        increment_execution_safety_counter(f"finn_v2_verified_proposal_candidates_total:{record.operation_type}")
        return record.proposal_id

    def _proposal_input_from_candidate(self, *, run, draft: ResponseDraft, validation) -> Optional[ValidatedProposalInput]:
        candidate = draft.proposal_candidate
        if candidate is None:
            return None
        target = ProposalTarget(target_type=candidate.target_type, target_id=candidate.target_id, asset=candidate.asset)
        changes = candidate.proposed_changes or {}
        operation = candidate.operation_type
        if operation == "update_indicator_configuration":
            change = IndicatorConfigurationChange(
                indicator_id=str(changes.get("indicator_id") or changes.get("indicator") or "indicator"),
                operation=str(changes.get("operation") or "update"),
                before=changes.get("before"),
                after=changes.get("after"),
            )
        elif operation == "create_setup":
            change = SetupCreateChange(
                setup_fields=dict(changes.get("setup_fields") or changes.get("changed_fields") or changes),
            )
        elif operation == "update_setup":
            change = SetupChange(setup_id=int(candidate.target_id or changes.get("setup_id") or 0), changed_fields=dict(changes.get("changed_fields") or changes))
        elif operation == "update_strategy":
            change = StrategyChange(strategy_id=int(candidate.target_id or changes.get("strategy_id") or 0), changed_fields=dict(changes.get("changed_fields") or changes))
        elif operation in {"watchlist_add", "watchlist_remove"}:
            change = WatchlistChange(
                asset=str(changes.get("asset") or candidate.asset or "").upper(),
                operation="remove" if operation == "watchlist_remove" else "add",
            )
        elif operation == "save_trade_plan":
            change = TradePlanChange(plan_id=str(candidate.target_id or changes.get("plan_id") or "") or None, changed_fields=dict(changes.get("changed_fields") or changes))
        elif operation in {"activate_paper_bot", "activate_live_bot"}:
            change = BotActivationChange(
                bot_id=int(candidate.target_id or changes.get("bot_id") or 0),
                requested_mode="live" if operation == "activate_live_bot" else "paper",
                current_is_live=bool(changes.get("current_is_live", operation == "activate_live_bot")),
            )
        elif operation == "portfolio_rebalance":
            change = PortfolioRebalanceChange(target_allocations=dict(changes.get("target_allocations") or {}))
        elif operation == "manual_order":
            change = ManualOrderChange(
                asset=str(changes.get("asset") or candidate.asset or "").upper(),
                side=str(changes.get("side") or "buy"),
                order_type=str(changes.get("order_type") or "market"),
                quantity=changes.get("quantity"),
                notional=changes.get("notional"),
                limit_price=changes.get("limit_price"),
            )
        else:
            return None
        return ValidatedProposalInput(
            operation_type=operation,
            target=target,
            change=change,
            impact_summary=candidate.impact_summary,
            risk_summary=candidate.risk_summary,
            source_run_id=run.id,
            source_snapshot_id=getattr(validation, "snapshot_id", ""),
            source_validation_id=validation.id,
            evidence_set_hash=validation.evidence_set_hash,
            idempotency_key=f"{run.id[:8]}-{draft.draft_id[-8:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

    def _evaluate_claim_support(self, text: str, evidence: list[Any], claim_type: str) -> tuple[str, list[str], bool]:
        haystack = text.lower()
        for item in evidence:
            facts = item.facts or {}
            fact_blob = str(facts).lower()
            if self._is_supported_indicator_absence(haystack, item):
                return "supported", [], True
            if self._mentions_live_mode(haystack) and "is_live" in facts:
                wants_live = self._asserts_live_mode(haystack)
                if bool(facts.get("is_live")) != wants_live:
                    return "contradicted", ["paper_live_mismatch"], False
            if item.asset and item.asset.lower() not in haystack and any(token in haystack for token in ["btc", "eth", "sol", "aapl", "tsla", "nvda"]):
                return "unsupported", ["asset_scope_mismatch"], False
            if "score" in haystack and ("score': 0.0" in fact_blob or '"score": 0.0' in fact_blob) and "0" not in haystack:
                return "unsupported", ["fabricated_score"], False
            if any(str(value).lower() in haystack for value in facts.values() if value not in (None, "", [], {})):
                return "supported", [], True
        if claim_type == "recommendation":
            return "partially_supported", [], True
        return "unverifiable", ["unsupported_noncritical_claim"], False

    @staticmethod
    def _is_supported_indicator_absence(text: str, evidence: Any) -> bool:
        if str(getattr(evidence, "tool_name", "") or "") != "read_indicator_configuration":
            return False
        facts = getattr(evidence, "facts", {}) or {}
        absence_checks = {
            "macro": facts.get("macro_count"),
            "market": facts.get("market_count"),
            "technical": facts.get("technical_count"),
        }
        return any(
            count == 0
            and keyword in text
            and any(marker in text for marker in ("geen", "no ", "without", "ontbreekt", "ontbreken", "mist", "missing"))
            for keyword, count in absence_checks.items()
        )

    def _covered_scopes_from_draft(self, draft: ResponseDraft, evidence_by_ref: Dict[str, Any]) -> set[str]:
        refs = self._all_refs(draft)
        covered = set()
        for ref in refs:
            evidence = evidence_by_ref.get(ref)
            if evidence is not None:
                covered.update(self._scopes_for_evidence(evidence))
                covered.add(self._scope_for_domain(evidence.domain))
        return {scope for scope in covered if scope}

    def _covered_domains_from_draft(self, draft: ResponseDraft, evidence_by_ref: Dict[str, Any]) -> set[str]:
        refs = self._all_refs(draft)
        return {
            evidence.domain
            for ref in refs
            for evidence in [evidence_by_ref.get(ref)]
            if evidence is not None and evidence.domain
        }

    def _scope_is_covered(self, scope: str, covered_scopes: set[str], covered_domains: set[str], *, draft: ResponseDraft, policy: FinnV2PolicyDecision) -> bool:
        if scope in covered_scopes:
            return True
        normalized_mode = normalize_interaction_mode(draft.mode)
        if normalized_mode == "CREATE_PROPOSAL" and scope == "setup":
            return "identity_context" in covered_domains or "plan_context" in covered_domains
        if normalized_mode == "ACTION_PROPOSAL" and scope == "watchlist":
            return "identity_context" in covered_domains
        if (
            normalized_mode == "UNAVAILABLE"
            and not policy.allowed
            and policy.operation_type == "activate_live_bot"
            and scope == "bot"
        ):
            return "automation_context" in covered_domains or "plan_context" in covered_domains
        mapped_domain = self.REQUIRED_SCOPE_TO_DOMAIN.get(scope)
        return bool(mapped_domain and mapped_domain in covered_domains)

    def _scope_for_domain(self, domain: Optional[str]) -> Optional[str]:
        for scope, mapped in self.REQUIRED_SCOPE_TO_DOMAIN.items():
            if mapped == domain:
                return scope
        return None

    def _scopes_for_evidence(self, evidence: Any) -> set[str]:
        tool_name = str(getattr(evidence, "tool_name", "") or "")
        entity_type = str(getattr(evidence, "entity_type", "") or "")
        scopes: set[str] = set()
        if tool_name in {"read_profile", "read_user_preferences"}:
            scopes.add("profile")
        if tool_name == "read_indicator_configuration":
            scopes.add("indicators")
        if tool_name in {"read_market_snapshot", "read_macro_snapshot", "read_technical_snapshot", "read_asset_scores"}:
            scopes.add("analysis")
        if tool_name == "read_active_setup" or entity_type == "setup":
            scopes.add("setup")
        if tool_name == "read_linked_strategy" or entity_type == "strategy":
            scopes.add("strategy")
        if tool_name in {"read_linked_bot", "read_bot_status"} or entity_type in {"bot", "bot_status"}:
            scopes.add("bot")
        if tool_name == "read_latest_report":
            scopes.add("daily_report")
        if tool_name == "read_review_history":
            scopes.add("reflection")
        if tool_name == "read_portfolio":
            scopes.add("portfolio")
        return scopes

    def _is_relevant(self, question: str, draft: ResponseDraft) -> bool:
        lowered = question.lower()
        answer = f"{draft.direct_answer} {draft.main_observation}".lower()
        keywords = [
            token
            for token in [
                "profile",
                "profiel",
                "indicator",
                "indicatoren",
                "setup",
                "strategy",
                "strategie",
                "bot",
                "plan",
                "watchlist",
                "volglijst",
                "portfolio",
                "report",
                "review",
                "btc",
                "eth",
                "sol",
                "aapl",
            ]
            if token in lowered
        ]
        if not keywords:
            return True
        return any(token in answer for token in keywords)

    def _mode_purity_ok(self, draft: ResponseDraft) -> bool:
        text = f"{draft.direct_answer} {draft.main_observation}".lower()
        if normalize_interaction_mode(draft.mode) == "READ":
            return not any(
                token in text
                for token in ["aangepast", "uitgevoerd", "executed", "order geplaatst"]
            ) and draft.proposal_candidate is None
        if draft.mode == "CAPABILITY":
            disallowed = [
                "koop",
                "kopen",
                "verkoop",
                "buy",
                "sell",
                "long",
                "short",
                "instappen",
                "uitstappen",
                "trade",
                "order",
            ]
            return draft.proposal_candidate is None and not any(token in text for token in disallowed)
        if normalize_interaction_mode(draft.mode) == "CLARIFICATION":
            return bool(draft.follow_up_question) and draft.proposal_candidate is None
        if normalize_interaction_mode(draft.mode) == "UNAVAILABLE":
            return draft.proposal_candidate is None
        if normalize_interaction_mode(draft.mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
            if "already live" in text:
                return False
            if "uitgevoerd" in text and not any(phrase in text for phrase in ["niet uitgevoerd", "nog niet uitgevoerd"]):
                return False
            if "executed" in text and not any(phrase in text for phrase in ["not executed", "not yet executed"]):
                return False
            return True
        return True

    def _evaluate_personalization_ok(
        self,
        question: str,
        draft: ResponseDraft,
        context,
        *,
        requested_scopes: Optional[list[str]] = None,
    ) -> bool:
        if normalize_interaction_mode(draft.mode) != "EVALUATE":
            return True
        lowered_question = question.lower()
        asks_for_plan_gap = (
            "belangrijkste ontbrekende onderdeel" in lowered_question
            or ("concrete observatie" in lowered_question and "vervolgstap" in lowered_question)
        )
        if not asks_for_plan_gap:
            return True

        scopes = set(requested_scopes or [])
        if not scopes:
            scopes = set(getattr(getattr(context, "analysis", None), "subject_scopes", []) or [])
        if not scopes:
            scopes = set(getattr(context, "subject_scopes", []) or [])
        required_scopes = {"profile", "indicators", "setup", "strategy", "bot"}
        if not required_scopes.issubset(scopes):
            return True

        evidence_by_tool = {
            str(getattr(item, "tool_name", "") or ""): item
            for item in getattr(context, "evidence", []) or []
        }
        profile = evidence_by_tool.get("read_profile")
        indicators = evidence_by_tool.get("read_indicator_configuration")
        setup = evidence_by_tool.get("read_active_setup")
        strategy = evidence_by_tool.get("read_linked_strategy")
        bot = evidence_by_tool.get("read_linked_bot")
        text = f"{draft.direct_answer} {draft.main_observation} {getattr(draft.next_step, 'instruction', '')}".lower()

        plan_anchors: list[str] = []
        for facts in [
            getattr(setup, "facts", {}) if setup else {},
            getattr(strategy, "facts", {}) if strategy else {},
            getattr(bot, "facts", {}) if bot else {},
        ]:
            for key in ("symbol", "name", "timeframe", "setup_id", "strategy_id", "bot_id", "execution_mode"):
                value = facts.get(key)
                if value not in (None, "", [], {}):
                    plan_anchors.append(str(value).lower())

        profile_anchors: list[str] = []
        profile_facts = getattr(profile, "facts", {}) if profile else {}
        trader_profile = profile_facts.get("trader_profile") or {}
        for key in (
            "risk_profile",
            "risk_profiles",
            "experience_level",
            "experience_levels",
            "experience",
            "primary_timeframe",
            "primary_timeframes",
            "secondary_timeframe",
        ):
            value = trader_profile.get(key)
            if value not in (None, "", [], {}):
                if isinstance(value, list):
                    profile_anchors.extend(str(item).lower() for item in value if str(item).strip())
                else:
                    profile_anchors.append(str(value).lower())
        style = trader_profile.get("style") or trader_profile.get("trader_types")
        if isinstance(style, list):
            profile_anchors.extend(str(item).lower() for item in style if str(item).strip())
        elif style not in (None, "", [], {}):
            profile_anchors.append(str(style).lower())

        indicator_anchors: list[str] = []
        indicator_facts = getattr(indicators, "facts", {}) if indicators else {}
        for row in indicator_facts.get("configured_indicators") or []:
            indicator = (row or {}).get("indicator")
            category = (row or {}).get("category")
            if indicator:
                indicator_anchors.append(str(indicator).lower())
            if category:
                indicator_anchors.append(str(category).lower())

        has_plan_anchor = any(anchor and anchor in text for anchor in plan_anchors)
        has_profile_or_indicator_anchor = any(anchor and anchor in text for anchor in profile_anchors + indicator_anchors)
        has_next_step = draft.next_step is not None and bool(getattr(draft.next_step, "instruction", "").strip())
        return has_plan_anchor and has_profile_or_indicator_anchor and has_next_step

    def _uncertainty_ok(self, draft: ResponseDraft, context) -> bool:
        requires_uncertainty = bool(context.uncertainty_codes) or any(item.freshness in {"stale", "unknown"} or item.confidence == "low" for item in context.evidence)
        if not requires_uncertainty:
            return True
        return bool(draft.uncertainty_summary)

    def _follow_up_ok(self, draft: ResponseDraft) -> bool:
        if draft.follow_up_question is None:
            return True
        question = draft.follow_up_question.strip()
        if question.count("?") != 1:
            return False
        if "meer weten" in question.lower():
            return False
        return " en " not in question.lower()

    def _proposal_ok(self, draft: ResponseDraft, policy: FinnV2PolicyDecision, evidence_by_ref: Dict[str, Any]) -> bool:
        candidate = draft.proposal_candidate
        if candidate is None:
            return True
        if normalize_interaction_mode(draft.mode) not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
            return False
        if policy.operation_type and candidate.operation_type != policy.operation_type:
            return False
        if not candidate.confirmation_required == bool(policy.confirmation_required):
            return False
        if not candidate.evidence_refs or any(ref not in evidence_by_ref for ref in candidate.evidence_refs):
            return False
        if candidate.target_id:
            return any((item.entity_id and str(item.entity_id) == str(candidate.target_id)) or (item.facts.get("bot_id") and str(item.facts.get("bot_id")) == str(candidate.target_id)) or (item.facts.get("strategy_id") and str(item.facts.get("strategy_id")) == str(candidate.target_id)) or (item.facts.get("setup_id") and str(item.facts.get("setup_id")) == str(candidate.target_id)) for item in evidence_by_ref.values())
        return True

    def _safety_ok(self, draft: ResponseDraft) -> bool:
        text = f"{draft.direct_answer}\n{draft.main_observation}".lower()
        forbidden = ["api key", "password", "token", "secret", "credential"]
        return not any(token in text for token in forbidden)

    def _paper_live_mismatch(self, draft: ResponseDraft, evidence_by_ref: Dict[str, Any]) -> bool:
        text = f"{draft.direct_answer} {draft.main_observation}".lower()
        if (
            normalize_interaction_mode(draft.mode) == "UNAVAILABLE"
            and "ik kan deze bot niet live activeren" in text
        ):
            return False
        if not self._mentions_live_mode(text):
            return False
        refs = self._all_refs(draft)
        for ref in refs:
            evidence = evidence_by_ref.get(ref)
            if evidence is None:
                continue
            if "is_live" not in evidence.facts:
                continue
            if self._asserts_live_mode(text) and not bool(evidence.facts.get("is_live")):
                return True
            if self._asserts_paper_mode(text) and bool(evidence.facts.get("is_live")):
                return True
        return False

    def _mentions_live_mode(self, text: str) -> bool:
        return self._asserts_live_mode(text) or self._asserts_paper_mode(text)

    def _asserts_live_mode(self, text: str) -> bool:
        if re.search(r"\b(niet|geen|not)\s+live\b", text):
            return False
        return bool(re.search(r"\blive\b", text)) and not self._asserts_paper_mode(text)

    def _asserts_paper_mode(self, text: str) -> bool:
        return bool(re.search(r"\bpaper\b", text))

    def _decide_action(self, *, draft, reason_codes: list[str], passed: bool, repair_attempt: int, has_clarification: bool) -> str:
        if passed:
            return "deliver"
        if any(code in self.BLOCKING_CODES for code in reason_codes):
            return "downgrade_to_unavailable"
        if any(code in self.REPAIRABLE_CODES for code in reason_codes) and repair_attempt < self.flags.response_max_repair_attempts():
            return "repair_once"
        if "response_scope_incomplete" in reason_codes or "response_not_answering_question" in reason_codes:
            return "downgrade_to_clarification" if has_clarification else "downgrade_to_unavailable"
        if "response_insufficiently_personalized" in reason_codes:
            return "downgrade_to_unavailable"
        if "unsupported_noncritical_claim" in reason_codes or "mode_purity_violation" in reason_codes:
            return "downgrade_to_fact"
        if "follow_up_invalid" in reason_codes:
            return "downgrade_to_clarification"
        if normalize_interaction_mode(draft.mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
            return "downgrade_to_unavailable"
        return "reject"

    def _capability_grounding_ok(self, draft: ResponseDraft) -> bool:
        if draft.mode != "CAPABILITY":
            return True
        if draft.proposal_candidate is not None or draft.claims:
            return False
        allowed_titles = self.capabilities.claimable_titles()
        point_titles = {point.title for point in draft.supporting_points}
        if not point_titles:
            return False
        if not point_titles.issubset(allowed_titles):
            return False
        text = f"{draft.direct_answer}\n{draft.main_observation}".casefold()
        forbidden_claims = [
            "garantie",
            "guarantee",
            "altijd winst",
            "profit",
            "buy now",
            "sell now",
            "koop nu",
            "verkoop nu",
            "live order",
        ]
        return not any(token in text for token in forbidden_claims)

    def _default_uncertainty(self, validation, context) -> str:
        if context.uncertainty_codes:
            return "Een deel van de onderliggende gegevens is verouderd of onvolledig, dus deze beoordeling bevat onzekerheid."
        if validation.integrity_status == "degraded":
            return "Niet alle vereiste gegevens waren volledig beschikbaar tijdens deze beoordeling."
        return "Een deel van de context is onzeker of beperkt."

    def _should_run_semantic(self, *, mode: str) -> bool:
        return self.flags.is_semantic_verifier_enabled() or mode in self.flags.semantic_verifier_required_modes()

    def _all_refs(self, draft: ResponseDraft) -> set[str]:
        # The model's top-level references are part of the structured contract.
        # Excluding them made complete EVALUATE answers look ungrounded unless
        # every scope was repeated inside a claim or supporting point.
        refs = set(draft.evidence_refs_used)
        for claim in draft.claims:
            refs.update(claim.evidence_refs)
        for point in draft.supporting_points:
            refs.update(point.evidence_refs)
        if draft.proposal_candidate is not None:
            refs.update(draft.proposal_candidate.evidence_refs)
        return refs

    async def _append_trace(self, *, trace_id: str, run_id: str, user_id: int, event_type: str, payload: dict) -> None:
        await self.traces.append_event(run_id=run_id, user_id=user_id, trace_id=trace_id, event_type=event_type, payload_json=payload)

    async def _latest_reasoning_for_run(self, *, run_id: str, user_id: int):
        from sqlalchemy import select
        from backend.infrastructure.models import FinnV2ReasoningResult as FinnV2ReasoningResultModel

        result = await self.session.execute(
            select(FinnV2ReasoningResultModel)
            .where(FinnV2ReasoningResultModel.run_id == run_id, FinnV2ReasoningResultModel.user_id == user_id)
            .order_by(FinnV2ReasoningResultModel.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    def _reasoning_record_from_row(self, row) -> PersistedReasoningRecord:
        return PersistedReasoningRecord(
            reasoning_result_id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            orchestrator_result_id=row.orchestrator_result_id,
            policy_decision_id=row.policy_decision_id,
            snapshot_id=row.snapshot_id,
            validation_id=row.validation_id,
            status=row.status,
            mode=row.mode,
            context_version=row.context_version,
            evidence_set_hash=row.evidence_set_hash,
            input_hash=row.input_hash,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            reasoning_version=row.reasoning_version,
            model=row.model,
            result=ReasoningResult.parse_obj(row.result_json) if row.result_json else None,
            error_codes=row.error_codes_json,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            reasoning_tokens=row.reasoning_tokens,
            latency_ms=row.latency_ms,
            retry_count=row.retry_count,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )

    def _orchestrator_result_from_row(self, row) -> OrchestratorResult:
        mode = normalize_interaction_mode(row.interaction_mode)
        return OrchestratorResult.parse_obj(
            {
                "orchestrator_result_id": row.id,
                "run_id": row.run_id,
                "user_id": row.user_id,
                "analysis": {
                    "interaction_mode": mode,
                    "subject_scopes": row.subject_scopes_json,
                    "explicit_asset": None,
                    "explicit_setup_id": None,
                    "explicit_strategy_id": None,
                    "explicit_bot_id": None,
                    "requires_comparison": False,
                    "requires_gap_analysis": False,
                    "requests_change": mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "requests_execution": mode == "EXECUTION",
                    "confidence": "medium",
                    "matched_signals": [],
                    "unresolved_signals": [],
                    "reasoning_required": mode in {"CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "analysis_version": row.analysis_version,
                },
                "domain_requirements": {
                    "required_domains": row.required_domains_json,
                    "optional_domains": row.optional_domains_json,
                    "requirement_reason": [],
                },
                "tool_plan": row.tool_plan_json,
                "snapshot_id": row.snapshot_id,
                "validation_id": row.validation_id,
                "outcome": row.outcome,
                "selected_clarification": row.selected_clarification_json,
                "unavailable_codes": row.unavailable_codes_json,
                "uncertainty_codes": row.uncertainty_codes_json,
                "orchestrator_version": row.orchestrator_version,
                "created_at": row.created_at,
            }
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        ordered = []
        seen = set()
        for value in values:
            if value and value not in seen:
                ordered.append(value)
                seen.add(value)
        return ordered
