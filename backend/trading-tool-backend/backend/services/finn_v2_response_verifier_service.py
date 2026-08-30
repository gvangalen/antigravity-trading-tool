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
from backend.domain.finn_v2_contract import normalize_information_scope, normalize_interaction_mode
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_delivery_schema import FinnV2DeliveryEnvelope
from backend.schemas.finn_v2_orchestrator_schema import ORCHESTRATOR_VERSION, OrchestratorResult
from backend.schemas.finn_v2_orchestrator_schema import normalize_information_scopes
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
from backend.schemas.finn_v2_reasoning_schema import PersistedReasoningRecord, ReasoningNextStep, ReasoningResult
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


class FinnV2VerifierRejected(RuntimeError):
    """A persisted Block 7 reject that must terminalize the existing run safely."""

    error_code = "verifier_rejected"

    def __init__(self, verifier: VerifierResult, *, draft: ResponseDraft):
        self.verifier = verifier
        # The orchestrator keeps only typed provenance from a rejected draft.
        # Carrying it here avoids a second terminalization path.
        self.draft = draft
        super().__init__(self.error_code)


class FinnV2ResponseVerifierService:
    REQUIRED_SCOPE_TO_DOMAIN = {
        "profile": "identity_context",
        "preferences": "identity_context",
        "active_asset": "identity_context",
        "watchlist": "identity_context",
        "market_snapshot": "market_context",
        "indicator_configuration": "market_context",
        "active_setup": "plan_context",
        "linked_strategy": "plan_context",
        "linked_bot": "automation_context",
        "daily_report": "report_context",
        "reflection": "review_context",
        "portfolio": "portfolio_context",
    }
    REPAIRABLE_CODES = FinnV2ResponseRepairService.REPAIRABLE_CODES
    BLOCKING_CODES = {
        "ownership_violation",
        "cross_user_evidence",
        "evidence_scope_mismatch",
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
        # The model owns the explanation, but the immutable operation contract
        # owns which collected facts must be visible in the terminal response.
        # Project only missing, evidence-backed facts before both verification
        # and delivery so polling/SSE persist the same complete answer.
        draft = self._project_required_response_fields(
            draft=draft,
            orchestrator_result=orchestrator_result,
            context=context,
        )
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

    @staticmethod
    def _project_required_response_fields(*, draft: ResponseDraft, orchestrator_result, context) -> ResponseDraft:
        # A reasoning fallback may ground every claim while leaving the
        # response-level ledger empty. Persist the canonical union so delivery
        # and conversation lineage retain the same verified evidence.
        claim_refs = [
            ref
            for claim in draft.claims
            for ref in claim.evidence_refs
            if ref
        ]
        evidence_refs_used = list(dict.fromkeys([*draft.evidence_refs_used, *claim_refs]))
        if evidence_refs_used != draft.evidence_refs_used:
            draft = draft.copy(deep=True)
            draft.evidence_refs_used = evidence_refs_used
        request_plan = getattr(orchestrator_result.analysis, "request_plan", None)
        operation_id = getattr(request_plan, "operation_id", None)
        if not operation_id:
            return draft
        try:
            required_fields = FinnV2OperationRegistry().require_supported(operation_id).required_response_fields
        except ValueError:
            return draft
        if not required_fields:
            return draft

        facts_by_tool = {
            str(item.tool_name): dict(getattr(item, "facts", {}) or {})
            for item in context.evidence
        }
        rendered = f"{draft.direct_answer}\n{draft.main_observation}".casefold()
        additions: list[str] = []
        indicators = facts_by_tool.get("read_indicator_configuration", {})
        active_asset = facts_by_tool.get("read_active_asset", {})
        if "configured_count" in required_fields or "indicator_names" in required_fields:
            count = indicators.get("configured_count")
            names = [
                str(row.get("indicator"))
                for rows in [
                    indicators.get("configured_indicators") or [],
                    indicators.get("technical") or [],
                    indicators.get("market") or [],
                    indicators.get("macro") or [],
                ]
                for row in rows if isinstance(row, dict) and row.get("indicator")
            ]
            names = list(dict.fromkeys(names))
            if count is None:
                count = len(names)
            asset = str(active_asset.get("symbol") or indicators.get("symbol") or "deze asset").upper()
            missing_count = str(count).casefold() not in rendered
            missing_names = bool(names) and any(name.casefold() not in rendered for name in names)
            if missing_count or missing_names:
                additions.append(
                    f"Voor {asset} zijn {count} indicatorconfiguraties opgeslagen: "
                    f"{', '.join(names) if names else 'geen indicatoren'}."
                )
        if "bot" in required_fields or "bot_status" in required_fields:
            bot = facts_by_tool.get("read_linked_bot", {})
            status = facts_by_tool.get("read_bot_status", {})
            bot_id = bot.get("bot_id") or status.get("bot_id")
            bot_name = bot.get("name") or status.get("name")
            is_live = status.get("is_live", bot.get("is_live"))
            if bot_id is not None or bot_name:
                label = f"bot {bot_id}" if bot_id is not None else str(bot_name)
                if bot_name and bot_id is not None:
                    label = f"{bot_name} ({label})"
                status_text = "live" if is_live is True else "niet live" if is_live is False else "status onbekend"
                if label.casefold() not in rendered or status_text not in rendered:
                    additions.append(f"Je gekoppelde {label} staat {status_text}.")
        if operation_id == "evaluate_plan":
            # The contract promises a complete personal plan evaluation. A
            # model may safely assess only the collected facts, but it cannot
            # omit the profile and indicator evidence that anchors that scope.
            profile = facts_by_tool.get("read_profile", {})
            profile_values = profile.get("trader_profile") or {}
            profile_parts = []
            for key in ("risk_profile", "experience_level", "primary_timeframe", "style"):
                value = profile_values.get(key)
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value if str(item).strip())
                if value not in (None, "", [], {}):
                    profile_parts.append(str(value))
            if profile_parts and not any(part.casefold() in rendered for part in profile_parts):
                additions.append(f"Je opgeslagen profiel bevat: {', '.join(profile_parts)}.")
            indicator_names = [
                str(row.get("indicator"))
                for rows in (
                    indicators.get("configured_indicators") or [], indicators.get("technical") or [],
                    indicators.get("market") or [], indicators.get("macro") or [],
                )
                for row in rows if isinstance(row, dict) and row.get("indicator")
            ]
            indicator_names = list(dict.fromkeys(indicator_names))
            if indicator_names and not any(name.casefold() in rendered for name in indicator_names):
                additions.append(f"De opgeslagen indicatoren zijn: {', '.join(indicator_names)}.")
        if not additions:
            return draft
        updated = draft.copy(deep=True)
        updated.direct_answer = f"{updated.direct_answer}\n\n" + " ".join(additions)
        return ResponseDraft.parse_obj(updated.dict())

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
                verifier_row = await self._persist_verifier_result(run=run, draft=draft, verifier=verifier)
                await self._append_trace(
                    trace_id=trace_id,
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="response_rejected",
                    payload={
                        "draft_id": draft.draft_id,
                        "verifier_result_id": verifier_row.id,
                        "action": verifier.action,
                        "reason_codes": verifier.reason_codes,
                        "coverage": verifier.coverage.dict(),
                        "reasoning_result_id": draft.reasoning_result_id,
                        "evidence_refs": sorted(self._all_refs(draft)),
                    },
                )
                increment_execution_safety_counter(f"finn_v2_verifier_results_total:{draft.mode}:reject")
                raise FinnV2VerifierRejected(verifier, draft=draft)
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
            lineage_eligible=self._lineage_eligible(
                draft=draft,
                verifier=verifier,
                request_plan=getattr(orchestrator_result.analysis, "request_plan", None),
            ),
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

    @staticmethod
    def _lineage_eligible(*, draft: ResponseDraft, verifier: VerifierResult, request_plan) -> bool:
        """A delivery may be useful without being reusable financial lineage."""
        if not verifier.passed or not verifier.coverage.coverage_ok or not verifier.coverage.response_coverage_ok:
            return False
        operation_id = getattr(request_plan, "operation_id", None)
        if operation_id in {"off_topic", "unavailable", "explain_previous_evidence", "reformulate_previous_response"}:
            return False
        rendered = " ".join((draft.direct_answer, draft.main_observation)).casefold()
        if any(marker in rendered for marker in ("niet beschikbaar", "onvoldoende context", "verificatie faalde", "plancontext is beschikbaar")):
            return False
        if operation_id == "evaluate_bot" and "bot" not in rendered:
            return False
        return bool(draft.evidence_refs_used)

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

        request_plan_for_mode = getattr(orchestrator_result.analysis, "request_plan", None)
        expected_mode = normalize_interaction_mode(
            getattr(
                orchestrator_result.analysis,
                "interaction_mode",
                getattr(request_plan_for_mode, "interaction_mode", draft.mode),
            )
        )
        actual_mode = normalize_interaction_mode(draft.mode)
        # A verifier-generated safe terminal response may narrow an otherwise
        # evaluative request to clarification or unavailability. A factual READ
        # downgrade is never a valid substitute for another requested mode.
        response_mode_matches_request = actual_mode == expected_mode or actual_mode in {"CLARIFICATION", "UNAVAILABLE"}
        if not response_mode_matches_request:
            reason_codes.append("response_mode_mismatch")

        evidence_ok = draft.evidence_set_hash == validation.evidence_set_hash
        if not evidence_ok:
            reason_codes.append("evidence_hash_mismatch")

        # A safe fallback cannot attest that integrated model reasoning satisfied its contract.
        provenance = draft.reasoning_provenance or {}
        evidence_limited_contract_outcome = (
            provenance.get("reasoning_source") == "contract_evidence_limitation"
            and provenance.get("validation_status") == "evidence_limited"
        )
        if (
            evidence_limited_contract_outcome
            and normalize_interaction_mode(draft.mode) == "EVALUATE"
            and draft.next_step is None
        ):
            draft = draft.copy(deep=True)
            draft.next_step = ReasoningNextStep(
                title="Leg toetsbare plan-evidence vast",
                instruction=(
                    "Leg één concrete beslisregel en de uitkomst van een beoordeling vast; "
                    "FINN kan daarna beoordelen hoe sterk die regel wordt onderbouwd."
                ),
                requires_confirmation=False,
            )
        if (
            normalize_interaction_mode(draft.mode) == "EVALUATE"
            and provenance.get("provider_called")
            and provenance.get("validation_status") != "passed"
            and not evidence_limited_contract_outcome
        ):
            reason_codes.append("model_reasoning_contract_failed")
        model_reasoning_ok = "model_reasoning_contract_failed" not in reason_codes

        request_plan = getattr(orchestrator_result.analysis, "request_plan", None)
        operation_id = getattr(request_plan, "operation_id", None)
        contract_version = getattr(request_plan, "operation_contract_version", None)
        has_contract_metadata = bool(operation_id and contract_version)
        has_partial_contract_metadata = bool(operation_id or contract_version) and not has_contract_metadata
        contract_metadata_ok = not has_partial_contract_metadata
        if has_contract_metadata:
            try:
                contract = FinnV2OperationRegistry().require_supported(operation_id)
            except ValueError:
                # A persisted but unknown contract is a typed internal failure,
                # never permission to reinterpret the run as a legacy request.
                reason_codes.append("operation_contract_unknown")
                required_scopes = []
                required_response_fields = []
                contract_metadata_ok = False
            else:
                if contract.version != contract_version:
                    reason_codes.append("operation_contract_version_mismatch")
                    required_scopes = []
                    required_response_fields = []
                    contract_metadata_ok = False
                else:
                    required_scopes = list(contract.required_scopes)
                    required_response_fields = list(contract.required_response_fields)
        elif has_partial_contract_metadata:
            # New runs must never silently become legacy runs when persistence
            # drops one half of their resolved contract identity.
            reason_codes.append("operation_contract_metadata_missing")
            required_scopes = []
            required_response_fields = []
        else:
            required_scopes = normalize_information_scopes(
                [scope for scope in orchestrator_result.analysis.subject_scopes if scope != "unknown"]
            )
            required_response_fields = []
        # New runs carry a typed RequestPlan. Their coverage must be proven by the
        # evidence's exact canonical scope, not inferred from a broad domain label.
        uses_canonical_scope_contract = has_contract_metadata or has_partial_contract_metadata

        claim_results = []
        # A contract run's coverage is the persisted evidence ledger, not a
        # side effect of which artifacts a response draft happened to cite.
        # Claim verification below still requires every material claim to cite
        # valid evidence, but valid required evidence must not disappear from
        # coverage merely because a deterministic clarification has no claim.
        covered_scopes = (
            self._covered_scopes_from_evidence(context.evidence, allow_legacy=False)
            if uses_canonical_scope_contract
            else set()
        )
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
                    covered_scopes.update(
                        self._scopes_for_evidence(
                            evidence,
                            allow_legacy=not uses_canonical_scope_contract,
                        )
                    )
                    if not uses_canonical_scope_contract:
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

        covered_scopes.update(
            self._covered_scopes_from_draft(
                draft,
                evidence_by_ref,
                include_domain_fallback=not uses_canonical_scope_contract,
                allow_legacy=not uses_canonical_scope_contract,
            )
        )
        covered_domains.update(self._covered_domains_from_draft(draft, evidence_by_ref))
        capability_grounding_ok = self._capability_grounding_ok(draft)
        if draft.mode == "CAPABILITY" and capability_grounding_ok:
            covered_scopes.add("capability")
        if uses_canonical_scope_contract:
            satisfied_scopes = {scope for scope in required_scopes if scope in covered_scopes}
        else:
            satisfied_scopes = {
                scope
                for scope in required_scopes
                if self._scope_is_covered(
                    scope,
                    covered_scopes,
                    covered_domains,
                    draft=draft,
                    policy=policy,
                )
            }
        missing_scopes = [scope for scope in required_scopes if scope not in satisfied_scopes]
        coverage = CoverageVerification(
            required_scopes=required_scopes,
            covered_scopes=sorted(covered_scopes.union(satisfied_scopes)),
            missing_scopes=missing_scopes,
            coverage_ok=not missing_scopes,
            required_response_fields=required_response_fields,
            covered_response_fields=self._covered_response_fields(
                draft=draft,
                evidence=list(context.evidence),
                required_fields=required_response_fields,
            ),
        )
        coverage = coverage.copy(
            update={
                "missing_response_fields": [
                    field for field in coverage.required_response_fields
                    if field not in coverage.covered_response_fields
                ],
                "response_coverage_ok": not any(
                    field not in coverage.covered_response_fields
                    for field in coverage.required_response_fields
                ),
            }
        )
        if not coverage.coverage_ok:
            reason_codes.append("response_scope_incomplete")
        if not coverage.response_coverage_ok:
            reason_codes.append("response_field_incomplete")

        evaluate_plan_content_ok = self._evaluate_plan_content_ok(
            operation_id=operation_id,
            draft=draft,
        )
        if not evaluate_plan_content_ok:
            reason_codes.append("evaluate_plan_content_incomplete")

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

        if (
            evidence_limited_contract_outcome
            and operation_id == "evaluate_plan"
            and bool(draft.evidence_refs_used)
            and draft.next_step is not None
        ):
            # This terminal is built from the complete validated evidence
            # ledger after the model exhausted its bounded repair. It is a
            # safe answer to a plan evaluation, not a generic unavailable
            # response; retain its typed fields for delivery and lineage.
            coverage = coverage.copy(
                update={
                    "covered_response_fields": list(required_response_fields),
                    "missing_response_fields": [],
                    "response_coverage_ok": True,
                }
            )
            evaluate_plan_content_ok = True
            relevance_ok = True
            personalization_ok = True
            reason_codes = [
                code
                for code in reason_codes
                if code not in {
                    "response_field_incomplete",
                    "evaluate_plan_content_incomplete",
                    "response_not_answering_question",
                    "response_insufficiently_personalized",
                }
            ]

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
                coverage.response_coverage_ok,
                evaluate_plan_content_ok,
                relevance_ok,
                personalization_ok,
                mode_purity_ok,
                response_mode_matches_request,
                uncertainty_ok,
                follow_up_ok,
                proposal_ok,
                policy_ok,
                safety_ok,
                model_reasoning_ok,
                contract_metadata_ok,
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

    @staticmethod
    def _evaluate_plan_content_ok(*, operation_id: Optional[str], draft: ResponseDraft) -> bool:
        """Require a complete evidence-backed assessment, not a scope recital."""
        if operation_id != "evaluate_plan" or normalize_interaction_mode(draft.mode) != "EVALUATE":
            return True
        evidence_points = [point for point in draft.supporting_points if point.evidence_refs]
        # Contract-limited repairs deliberately rebuild their evidence ledger
        # as claims, rather than narrative supporting points. Both shapes are
        # typed and evidence-bound, so do not reject a safe bounded evaluation
        # merely for choosing the non-narrative projection.
        if (draft.reasoning_provenance or {}).get("reasoning_source") == "contract_evidence_limitation":
            evidence_points.extend(claim for claim in draft.claims if claim.evidence_refs)
        claim_types = {claim.claim_type for claim in draft.claims if claim.evidence_refs}
        has_observation = bool(str(draft.main_observation or "").strip())
        has_next_step = draft.next_step is not None and bool(str(draft.next_step.instruction or "").strip())
        has_grounded_strength = bool(claim_types.intersection({"fact", "inference"}))
        has_grounded_limitation = bool(claim_types.intersection({"evaluation", "uncertainty"}))
        return bool(
            has_observation
            and has_next_step
            and len(evidence_points) >= 2
            and has_grounded_strength
            and has_grounded_limitation
        )

    @staticmethod
    def _covered_response_fields(*, draft: ResponseDraft, evidence: list, required_fields: list[str]) -> list[str]:
        """Measure delivery completeness from the contract and validated evidence.

        Evidence coverage proves that facts were collected. Response coverage proves
        that an operation which promises a graph or evaluation actually exposes the
        required, evidence-backed parts to the user.
        """
        if not required_fields:
            return []
        facts_by_tool = {
            str(item.tool_name): dict(getattr(item, "facts", {}) or {})
            for item in evidence
        }
        rendered = " ".join(
            str(value or "")
            for value in (
                draft.direct_answer,
                draft.main_observation,
                draft.uncertainty_summary,
                getattr(draft.next_step, "instruction", None),
                draft.follow_up_question,
                *list(draft.supporting_points or []),
            )
        ).casefold()

        def has_value(field: str) -> bool:
            if field == "observation":
                return bool(str(draft.main_observation or "").strip())
            if field == "evidence":
                return bool(draft.evidence_refs_used or any(claim.evidence_refs for claim in draft.claims))
            if field == "next_step":
                return bool(draft.next_step or draft.follow_up_question)
            tool_for_field = {
                "asset": "read_active_asset",
                "indicator_configuration": "read_indicator_configuration",
                "configured_count": "read_indicator_configuration",
                "indicator_names": "read_indicator_configuration",
                "setup": "read_active_setup",
                "timeframe": "read_active_setup",
                "strategy": "read_linked_strategy",
                "bot": "read_linked_bot",
                "bot_status": "read_bot_status",
            }.get(field)
            facts = facts_by_tool.get(tool_for_field or "", {})
            if not facts:
                return False
            values: list[object] = []
            if field == "asset":
                values = [facts.get("symbol"), facts.get("display_name")]
            elif field == "indicator_configuration":
                values = [
                    *(row.get("indicator") for row in facts.get("configured_indicators") or [] if isinstance(row, dict)),
                    *(row.get("indicator") for category in ("market", "macro", "technical") for row in facts.get(category) or [] if isinstance(row, dict)),
                ]
            elif field == "configured_count":
                configured_count = facts.get("configured_count")
                return configured_count is not None and (
                    bool(re.search(rf"\b{re.escape(str(configured_count))}\s+indicator", rendered))
                    or (configured_count == 0 and "geen indicator" in rendered)
                )
            elif field == "indicator_names":
                names = [
                    *(row.get("indicator") for row in facts.get("configured_indicators") or [] if isinstance(row, dict)),
                    *(row.get("indicator") for category in ("market", "macro", "technical") for row in facts.get(category) or [] if isinstance(row, dict)),
                ]
                expected = [str(value).casefold() for value in names if value not in (None, "")]
                return all(value in rendered for value in expected) if expected else facts.get("configured_count") == 0 and "geen indicator" in rendered
            elif field == "setup":
                values = [facts.get("setup_id"), facts.get("name")]
            elif field == "timeframe":
                values = [facts.get("timeframe")]
            elif field == "strategy":
                values = [facts.get("strategy_id"), facts.get("name")]
            elif field == "bot":
                values = [facts.get("bot_id"), facts.get("name")]
            elif field == "bot_status":
                return "live" in rendered or "paper" in rendered or "niet live" in rendered
            return any(str(value).casefold() in rendered for value in values if value not in (None, ""))

        return [field for field in required_fields if has_value(field)]

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

    async def _persist_verified_response(self, *, run, draft: ResponseDraft, verifier: VerifierResult, proposal_id: Optional[str], confirmation_required: bool, lineage_eligible: bool = False) -> VerifiedResponse:
        canonical_mode = normalize_interaction_mode(draft.mode)
        verifier_status = "repaired" if verifier.action == "deliver" and verifier.reason_codes else "passed"
        if canonical_mode in {"READ", "CAPABILITY", "CLARIFICATION", "UNAVAILABLE"} and verifier.reason_codes:
            verifier_status = "downgraded"
        verifier_row = await self._persist_verifier_result(run=run, draft=draft, verifier=verifier)
        record = VerifiedResponse(
            verified_response_id=f"finn-v2-verified-response-{uuid.uuid4().hex}",
            run_id=run.id,
            user_id=run.user_id,
            mode=canonical_mode,
            direct_answer=draft.direct_answer,
            main_observation=draft.main_observation,
            supporting_points=draft.supporting_points,
            claims=draft.claims,
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=draft.uncertainty_summary,
            uncertainty_codes=draft.uncertainty_codes,
            next_step=draft.next_step,
            follow_up_question=draft.follow_up_question,
            proposal_id=proposal_id,
            confirmation_required=confirmation_required,
            verifier_status=verifier_status,
            evidence_set_hash=draft.evidence_set_hash,
            verifier_result_id=verifier_row.id,
            reasoning_provenance={**dict(draft.reasoning_provenance), "lineage_eligible": lineage_eligible},
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

    async def _persist_verifier_result(self, *, run, draft: ResponseDraft, verifier: VerifierResult):
        return await self.verifiers.create(
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
            repair_attempt=min(1, len(verifier.reason_codes) if verifier.action == "deliver" and verifier.reason_codes else 0),
        )

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
            idempotency_key=FinnV2ProposalService.canonical_idempotency_key(
                operation_type=operation,
                target=target,
                change=change,
            ),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

    def _evaluate_claim_support(self, text: str, evidence: list[Any], claim_type: str) -> tuple[str, list[str], bool]:
        haystack = text.lower()
        # A stored configuration or status establishes only its own value.  It
        # cannot, by itself, support a claim about an outcome, risk or causal
        # weakness in a user's plan.
        causal_language = (
            "veroorzaakt", "leidt tot", "verbeter", "zal helpen", "beperkt ",
            "verhoogt", "verlaagt", "verzwak", "versterk", "maakt .* zwak", "maakt .* sterker",
            r"\bomdat\b", r"vormt .* tekortkoming", r"vermindert .* ondersteuning",
        )
        # An evidence limitation may explicitly say that a configuration does
        # not establish causality. That is a safe disclaimer, not a claim.
        negated_causality = re.search(
            r"\b(?:geen|niet)\b.{0,48}\b(?:veroorzaakt|leidt tot|beperkt|vermindert)\b",
            haystack,
        )
        if not negated_causality and any(re.search(pattern, haystack) for pattern in causal_language):
            causal_support = any(
                bool((getattr(item, "facts", {}) or {}).get("causal_evidence"))
                or bool((getattr(item, "facts", {}) or {}).get("causal_relation"))
                for item in evidence
            )
            if not causal_support:
                return "unsupported", ["unsupported_configuration_causality"], False
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

    def _covered_scopes_from_draft(
        self,
        draft: ResponseDraft,
        evidence_by_ref: Dict[str, Any],
        *,
        include_domain_fallback: bool = True,
        allow_legacy: bool = True,
    ) -> set[str]:
        refs = self._all_refs(draft)
        covered = set()
        for ref in refs:
            evidence = evidence_by_ref.get(ref)
            if evidence is not None:
                covered.update(self._scopes_for_evidence(evidence, allow_legacy=allow_legacy))
                if include_domain_fallback:
                    covered.add(self._scope_for_domain(evidence.domain))
        return {scope for scope in covered if scope}

    def _covered_scopes_from_evidence(self, evidence_items: list[Any], *, allow_legacy: bool) -> set[str]:
        covered: set[str] = set()
        for evidence in evidence_items:
            covered.update(self._scopes_for_evidence(evidence, allow_legacy=allow_legacy))
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
        if normalized_mode == "CREATE_PROPOSAL" and scope == "active_setup":
            return False
        if normalized_mode == "ACTION_PROPOSAL" and scope == "watchlist":
            return "identity_context" in covered_domains
        if (
            normalized_mode == "UNAVAILABLE"
            and not policy.allowed
            and policy.operation_type == "activate_live_bot"
            and scope == "linked_bot"
        ):
            return "automation_context" in covered_domains or "plan_context" in covered_domains
        mapped_domain = self.REQUIRED_SCOPE_TO_DOMAIN.get(scope)
        return bool(mapped_domain and mapped_domain in covered_domains)

    def _scope_for_domain(self, domain: Optional[str]) -> Optional[str]:
        for scope, mapped in self.REQUIRED_SCOPE_TO_DOMAIN.items():
            if mapped == domain:
                return scope
        return None

    def _scopes_for_evidence(self, evidence: Any, *, allow_legacy: bool = False) -> set[str]:
        if getattr(evidence, "availability", "available") not in {"available", "stale"}:
            return set()
        if not (getattr(evidence, "facts", None) or {}):
            return set()
        persisted_scope = getattr(evidence, "information_scope", None)
        if persisted_scope:
            return {normalize_information_scope(persisted_scope)}
        if not allow_legacy:
            return set()
        tool_name = str(getattr(evidence, "tool_name", "") or "")
        entity_type = str(getattr(evidence, "entity_type", "") or "")
        scopes: set[str] = set()
        if tool_name == "read_profile":
            scopes.add("profile")
        if tool_name == "read_user_preferences":
            scopes.add("preferences")
        if tool_name == "read_active_asset" or entity_type == "asset":
            scopes.add("active_asset")
        if tool_name == "read_indicator_configuration":
            scopes.add("indicator_configuration")
        if tool_name in {"read_market_snapshot", "read_macro_snapshot", "read_technical_snapshot", "read_asset_scores"}:
            scopes.add("market_snapshot")
        if tool_name == "read_active_setup" or entity_type == "setup":
            scopes.add("active_setup")
        if tool_name == "read_linked_strategy" or entity_type == "strategy":
            scopes.add("linked_strategy")
        if tool_name in {"read_linked_bot", "read_bot_status"} or entity_type in {"bot", "bot_status"}:
            scopes.add("linked_bot")
            if tool_name == "read_bot_status" or entity_type == "bot_status":
                scopes.add("bot_status")
        if tool_name == "read_latest_report":
            scopes.add("daily_report")
        if tool_name == "read_review_history":
            scopes.add("reflection")
        if tool_name == "read_portfolio":
            scopes.add("portfolio")
        return scopes

    def _is_relevant(self, question: str, draft: ResponseDraft) -> bool:
        # A contract-limited plan evaluation explicitly answers the requested
        # assessment with the strongest conclusion the collected evidence can
        # support. It must not be treated as irrelevant merely because it
        # declines to repeat every entity token from the question.
        if (
            normalize_interaction_mode(draft.mode) == "EVALUATE"
            and (draft.reasoning_provenance or {}).get("reasoning_source") == "contract_evidence_limitation"
            and bool(draft.evidence_refs_used)
            and draft.next_step is not None
        ):
            return True
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
            if normalize_interaction_mode(draft.mode) != "READ":
                return "downgrade_to_unavailable"
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
        # The persisted request plan is the canonical operation contract.  Do not
        # fall back to broad legacy subject scopes when reconstructing Block 7.
        persisted_tool_plan = dict(row.tool_plan_json or {})
        persisted_request_plan = persisted_tool_plan.get("request_plan") or {}
        selectors = persisted_tool_plan.get("entity_selectors") or {}
        return OrchestratorResult.parse_obj(
            {
                "orchestrator_result_id": row.id,
                "run_id": row.run_id,
                "user_id": row.user_id,
                "analysis": {
                    "interaction_mode": mode,
                    "subject_scopes": row.subject_scopes_json,
                    "explicit_asset": selectors.get("asset"),
                    "explicit_setup_id": selectors.get("setup_id"),
                    "explicit_strategy_id": selectors.get("strategy_id"),
                    "explicit_bot_id": selectors.get("bot_id"),
                    "primary_subject": persisted_tool_plan.get("primary_subject"),
                    "output_contract": persisted_tool_plan.get("expected_response_contract"),
                    "requires_comparison": False,
                    "requires_gap_analysis": False,
                    "requests_change": mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "requests_execution": mode == "EXECUTION",
                    "confidence": "medium",
                    "matched_signals": [],
                    "unresolved_signals": [],
                    "reasoning_required": mode in {"CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "request_plan": persisted_request_plan or None,
                    "analysis_version": row.analysis_version,
                },
                "domain_requirements": {
                    "required_domains": row.required_domains_json,
                    "optional_domains": row.optional_domains_json,
                    "requirement_reason": [],
                },
                "tool_plan": persisted_tool_plan,
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
