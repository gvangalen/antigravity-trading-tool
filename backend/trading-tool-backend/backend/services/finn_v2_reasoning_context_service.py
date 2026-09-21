from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_reasoning_context_schema import (
    REASONING_CONTEXT_VERSION,
    ReasoningContextPackage,
    ReasoningDomainStatus,
    ReasoningEvidenceBoundary,
    ReasoningEvidenceItem,
    ReasoningPolicyContext,
)
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.schemas.finn_v2_domain_validation_schema import EvidenceValidationResult


class FinnV2ReasoningContextService:
    DOMAIN_BY_TOOL = {
        "read_profile": "identity_context",
        "read_user_preferences": "identity_context",
        "read_active_asset": "identity_context",
        "read_indicator_configuration": "market_context",
        "read_asset_scores": "market_context",
        "read_market_snapshot": "market_context",
        "read_macro_snapshot": "market_context",
        "read_technical_snapshot": "market_context",
        "read_active_setup": "plan_context",
        "read_linked_strategy": "plan_context",
        "read_linked_bot": "automation_context",
        "read_bot_status": "automation_context",
        "read_watchlist": "identity_context",
        "read_portfolio": "portfolio_context",
        "read_latest_report": "report_context",
        "read_review_history": "review_context",
    }
    DOMAIN_BY_REQUIRED_EVIDENCE = {
        "profile": "identity_context",
        "preferences": "identity_context",
        "active_asset": "identity_context",
        "asset": "identity_context",
        "watchlist": "identity_context",
        "indicator_configuration": "market_context",
        "asset_scores": "market_context",
        "scores": "market_context",
        "market_snapshot": "market_context",
        "macro_snapshot": "market_context",
        "technical_snapshot": "market_context",
        "active_setup": "plan_context",
        "linked_strategy": "plan_context",
        "linked_bot": "automation_context",
        "bot_status": "automation_context",
        "portfolio": "portfolio_context",
        "latest_report": "report_context",
        "review_history": "review_context",
    }

    def __init__(self, session: AsyncSession, *, max_evidence_items: int = 30, max_context_bytes: int = 131072):
        self.session = session
        self.evidence_repo = FinnV2EvidenceRepository(session)
        self.runtime_contracts = FinnV2RuntimeContractRepository(session)
        self.max_evidence_items = max_evidence_items
        self.max_context_bytes = max_context_bytes

    async def build(
        self,
        *,
        run,
        orchestrator_result: OrchestratorResult,
        snapshot: FinancialStateSnapshot,
        validation: EvidenceValidationResult,
        policy,
    ) -> ReasoningContextPackage:
        snapshot_model = self._snapshot_model(snapshot)
        validation_model = self._validation_model(validation)
        request_plan = (orchestrator_result.analysis.request_plan.dict() if orchestrator_result.analysis.request_plan else {})
        artifacts = await self.evidence_repo.list_for_run(run_id=run.id, user_id=run.user_id)
        allowed_evidence_run_ids = {run.id}
        previous_run_id = ""
        if request_plan.get("operation_id") in {
            "explain_previous_evidence",
            "reformulate_previous_response",
        }:
            runtime_contract = await self.runtime_contracts.get_for_run(run_id=run.id)
            runtime_state = dict(getattr(runtime_contract, "state_json", None) or {})
            lineage_state = dict(runtime_state.get("lineage_state") or {})
            reference_kind = str(
                request_plan.get("conversation_reference_kind")
                or runtime_state.get("conversation_reference_kind")
                or ""
            )
            degraded = dict(lineage_state.get("last_degraded_context") or {})
            verified = dict(lineage_state.get("last_verified_context") or {})
            released = dict(lineage_state.get("last_released_context") or {})
            if reference_kind == "previous_released_response" and degraded:
                source_key = "last_degraded_context"
                lineage = degraded
            elif reference_kind == "previous_released_response":
                source_key = "last_released_context"
                lineage = released
            else:
                source_key = "last_verified_context"
                lineage = verified
            previous_run_id = str(lineage.get("run_id") or "").strip()
            if previous_run_id:
                prior_artifacts = await self.evidence_repo.list_for_run(
                    run_id=previous_run_id,
                    user_id=run.user_id,
                )
                artifacts = prior_artifacts or artifacts
                allowed_evidence_run_ids.add(previous_run_id)
                operation_state = dict(request_plan.get("operation_state") or {})
                if source_key == "last_degraded_context":
                    operation_state.update(
                        {
                            "previous_degraded_run_id": previous_run_id,
                            "previous_degraded_operation_id": lineage.get("operation_id"),
                            "previous_degraded_released_response": dict(lineage.get("released_response") or {}),
                            "previous_degraded_released_sections": list(lineage.get("released_response_sections") or []),
                            "previous_degraded_evidence_scopes": list(lineage.get("evidence_scopes") or []),
                            "previous_evidence_refs": list(lineage.get("evidence_refs") or []),
                            "resolved_entities": dict(lineage.get("resolved_entities") or {}),
                        }
                    )
                else:
                    prefix = "previous_released" if source_key == "last_released_context" else "previous_verified"
                    operation_state.update(
                        {
                            f"{prefix}_run_id": previous_run_id,
                            f"{prefix}_operation_id": lineage.get("operation_id"),
                            f"{prefix}_conclusion": lineage.get("conclusion"),
                            f"{prefix}_response": lineage.get("response"),
                            "previous_evidence_refs": list(lineage.get("evidence_refs") or []),
                            "resolved_entities": dict(lineage.get("resolved_entities") or {}),
                        }
                    )
                if source_key == "last_verified_context":
                    operation_state["previous_verified_response_id"] = lineage.get("verified_response_id")
                request_plan["operation_state"] = operation_state
        selected_domains = set(orchestrator_result.domain_requirements.required_domains + orchestrator_result.domain_requirements.optional_domains)
        if previous_run_id:
            selected_domains.update(
                domain
                for artifact in artifacts
                if (domain := self.DOMAIN_BY_TOOL.get(artifact.tool_name)) is not None
            )
        tool_plan = getattr(orchestrator_result, "tool_plan", None)
        for evidence_key in list(getattr(tool_plan, "required_evidence", []) or []) + list(getattr(tool_plan, "optional_evidence", []) or []):
            mapped_domain = self.DOMAIN_BY_REQUIRED_EVIDENCE.get(str(evidence_key))
            if mapped_domain:
                selected_domains.add(mapped_domain)
        evidence: list[ReasoningEvidenceItem] = []
        provenance_issues: list[str] = []
        referenced = request_plan.get("referenced_entities") or {}
        expected_asset = self._expected_asset(referenced)
        index = 1
        for artifact in artifacts:
            domain = self.DOMAIN_BY_TOOL.get(artifact.tool_name)
            if domain not in selected_domains:
                continue
            artifact_asset = str(artifact.asset or "").strip().upper() or None
            artifact_run_id = getattr(artifact, "run_id", run.id)
            artifact_owner = getattr(artifact, "user_id", run.user_id)
            if (
                artifact_run_id not in allowed_evidence_run_ids
                or artifact_owner != run.user_id
                or (expected_asset and artifact_asset and artifact_asset != expected_asset)
            ):
                provenance_issues.append("evidence_scope_mismatch")
                continue
            facts = self._sanitize_facts(artifact.payload_json or {}, artifact.tool_name)
            item = ReasoningEvidenceItem(
                evidence_id=f"E{index}",
                artifact_id=artifact.id,
                tool_name=artifact.tool_name,
                information_scope=getattr(artifact, "information_scope", None),
                domain=domain,
                entity_type=artifact.entity_type or "unknown",
                entity_id=artifact.entity_id,
                asset=artifact.asset,
                source=artifact.source,
                as_of=artifact.source_as_of,
                freshness=artifact.freshness,
                availability=artifact.availability,
                confidence=self._confidence_for(artifact.availability, artifact.freshness),
                facts=facts,
            )
            evidence.append(item)
            index += 1
            if len(evidence) >= self.max_evidence_items:
                break

        evidence = self._trim_to_size(evidence)
        domain_statuses = []
        for item in validation_model.domains:
            if item.domain in selected_domains:
                domain_statuses.append(
                    ReasoningDomainStatus(
                        domain=item.domain,
                        status=item.status,
                        confidence=item.confidence,
                        issue_codes=[issue.code for issue in item.issues],
                    )
                )
        policy_context = ReasoningPolicyContext(
            policy_class=policy.policy_class,
            allowed=policy.allowed,
            proposal_allowed=policy.proposal_allowed,
            confirmation_required=policy.confirmation_required,
            step_up_required=policy.step_up_required,
            execution_allowed=policy.execution_allowed,
            operation_type=policy.operation_type,
            warning_codes=list(policy.warning_codes),
            blocking_codes=list(policy.blocking_codes),
            proposal_input_required=getattr(policy, "proposal_input_required", False),
        )
        return ReasoningContextPackage(
            run_id=run.id,
            user_id=run.user_id,
            user_message=run.message,
            locale=self._locale_for(run),
            interaction_mode=orchestrator_result.analysis.interaction_mode,
            subject_scopes=list(orchestrator_result.analysis.subject_scopes),
            required_domains=list(orchestrator_result.domain_requirements.required_domains),
            orchestrator_result_id=orchestrator_result.orchestrator_result_id,
            snapshot_id=snapshot_model.snapshot_id,
            validation_id=validation_model.validation_id,
            policy_decision_id=policy.policy_decision_id,
            evidence_set_hash=validation_model.evidence_set_hash,
            context_version=REASONING_CONTEXT_VERSION,
            evidence=evidence,
            domain_statuses=domain_statuses,
            policy=policy_context,
            allowed_response_modes=[orchestrator_result.analysis.interaction_mode],
            allowed_operation_types=[policy.operation_type] if policy.operation_type else [],
            request_plan=request_plan,
            uncertainty_codes=list(dict.fromkeys([*orchestrator_result.uncertainty_codes, *provenance_issues])),
            evidence_boundary=self._evidence_boundary(evidence),
        )

    @staticmethod
    def _expected_asset(referenced: Dict[str, Any]) -> Optional[str]:
        target = referenced.get("canonical_entity_target")
        if isinstance(target, dict) and target.get("resolution_status") == "resolved":
            relation = target.get("relation")
            if isinstance(relation, dict):
                canonical = str(
                    relation.get("symbol") or relation.get("asset_symbol") or ""
                ).strip().upper()
                if canonical:
                    return canonical
        return str(referenced.get("asset") or "").strip().upper() or None

    @staticmethod
    def _evidence_boundary(evidence: list[ReasoningEvidenceItem]) -> ReasoningEvidenceBoundary:
        """Describe evidence limits without converting an absence into a risk claim."""
        facts: list[str] = []
        absences: list[str] = []
        unknowns: list[str] = []
        forbidden: list[str] = []
        for item in evidence:
            if item.tool_name != "read_indicator_configuration":
                continue
            count = item.facts.get("configured_count")
            if count == 0:
                asset = item.facts.get("symbol") or item.asset or "the requested asset"
                absences.append(f"The canonical indicator source has zero records for {asset}.")
                unknowns.append("Whether a non-canonical source has indicator records is unknown.")
                forbidden.append("Zero configured indicators implies a plan weakness, risk, insufficiency, or causal effect.")
            elif isinstance(count, int):
                facts.append(f"The canonical indicator source reports {count} configured indicators.")
        return ReasoningEvidenceBoundary(
            verified_facts=facts,
            verified_absences=absences,
            unknowns=unknowns,
            forbidden_inferences=forbidden,
        )

    def input_hash(self, context: ReasoningContextPackage, *, prompt_version: str, model: str) -> str:
        payload = {
            "context": context.dict(),
            "prompt_version": prompt_version,
            "model": model,
        }
        return sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()

    def context_bytes(self, context: ReasoningContextPackage) -> int:
        return len(json.dumps(context.dict(), sort_keys=True, default=str).encode("utf-8"))

    def _sanitize_facts(self, payload: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        if tool_name == "read_profile":
            return {"trader_profile": payload.get("trader_profile", {}), "has_profile": payload.get("has_profile")}
        if tool_name == "read_user_preferences":
            return {key: payload.get(key) for key in ["experience_level", "risk_profile", "selected_asset", "active_asset", "detail_level", "coaching_style"] if payload.get(key) is not None}
        if tool_name == "read_active_asset":
            return {key: payload.get(key) for key in ["symbol", "display_name", "asset_class", "market_region", "quote_currency"] if payload.get(key) is not None}
        if tool_name == "read_indicator_configuration":
            source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            technical = source.get("technical", [])[:12]
            market = source.get("market", [])[:12]
            macro = source.get("macro", [])[:12]
            configured_indicators = []
            for item in technical + market + macro:
                configured_indicators.append(
                    {
                        "indicator": item.get("indicator"),
                        "category": item.get("category"),
                        "enabled": item.get("enabled"),
                        "priority": item.get("priority"),
                    }
                )
            return {
                "symbol": source.get("symbol") or summary.get("symbol"),
                "asset_class": source.get("asset_class") or summary.get("asset_class"),
                "owner_user_id": source.get("owner_user_id"),
                "requested_symbol": source.get("requested_symbol"),
                "resolved_symbol": source.get("resolved_symbol"),
                "source_record_ids": source.get("source_record_ids", []),
                "technical": technical,
                "market": market,
                "macro": macro,
                "technical_count": summary.get("technical_count", len(technical)),
                "market_count": summary.get("market_count", len(market)),
                "macro_count": summary.get("macro_count", len(macro)),
                # The response contract promises this aggregate explicitly.
                # Preserve the adapter's canonical summary through to the
                # verifier instead of forcing it to infer from display text.
                "configured_count": summary.get("configured_count", len(technical) + len(market) + len(macro)),
                "configured_indicators": configured_indicators,
                "scope_by_category": source.get("scope_by_category") or {},
            }
        if tool_name == "read_asset_scores":
            return {"symbol": payload.get("symbol"), "daily_scores": payload.get("daily_scores"), "master_score": payload.get("master_score")}
        if tool_name == "read_market_snapshot":
            return {key: payload.get(key) for key in ["symbol", "price", "change_24h", "volume", "source", "as_of"] if payload.get(key) is not None}
        if tool_name == "read_macro_snapshot":
            return {"symbol": payload.get("symbol"), "items": payload.get("items", [])[:8]}
        if tool_name == "read_technical_snapshot":
            return {"symbol": payload.get("symbol"), "items": payload.get("items", [])[:8]}
        if tool_name == "read_active_setup":
            facts = {
                key: payload.get(key)
                for key in ["setup_id", "name", "symbol", "timeframe", "setup_type", "score"]
                if payload.get(key) is not None
            }
            collection = payload.get("setups")
            if isinstance(collection, list):
                facts["setups"] = collection
                facts["setup_count"] = len(collection)
            return facts
        if tool_name == "read_linked_strategy":
            source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                key: source.get(key)
                for key in [
                    "strategy_id",
                    "setup_id",
                    "name",
                    "symbol",
                    "timeframe",
                    "execution_mode",
                    "risk_profile",
                    "entry",
                    "entry_type",
                    "stop_loss",
                    "targets",
                    "base_amount",
                    "setup_name",
                    "setup_type",
                ]
                if source.get(key) is not None
            }
        if tool_name == "read_linked_bot":
            return {
                key: payload.get(key)
                for key in [
                    "bot_id",
                    "name",
                    "symbol",
                    "strategy_id",
                    "is_active",
                    "is_live",
                    "mode",
                    "budget_total_eur",
                ]
                if payload.get(key) is not None
            }
        if tool_name == "read_bot_status":
            return {key: payload.get(key) for key in ["bot_id", "is_active", "is_live", "last_run", "mode", "cadence"] if payload.get(key) is not None}
        if tool_name == "read_watchlist":
            return {
                "target_asset": payload.get("target_asset"),
                "contains_target_asset": payload.get("contains_target_asset"),
                "symbols": payload.get("symbols", [])[:20],
            }
        if tool_name == "read_portfolio":
            global_payload = payload.get("global") or payload.get("global_") or {}
            return {"global": global_payload, "bots": payload.get("bots", [])[:8]}
        if tool_name == "read_latest_report":
            return {key: payload.get(key) for key in ["report_type", "report_date", "symbol", "status", "id"] if payload.get(key) is not None}
        if tool_name == "read_review_history":
            return {"items": payload.get("items", [])[:5]}
        return {}

    def _confidence_for(self, availability: str, freshness: str) -> str:
        if availability in {"ambiguous", "unavailable"}:
            return "low"
        if freshness == "stale":
            return "medium"
        return "high"

    def _trim_to_size(self, evidence: list[ReasoningEvidenceItem]) -> list[ReasoningEvidenceItem]:
        trimmed = list(evidence)
        while trimmed:
            bytes_used = len(json.dumps([item.dict() for item in trimmed], default=str, sort_keys=True).encode("utf-8"))
            if bytes_used <= self.max_context_bytes:
                return trimmed
            trimmed.pop()
        return []

    def _locale_for(self, run) -> str:
        context = getattr(run, "client_context_json", {}) or {}
        hints = getattr(run, "workspace_hints_json", {}) or {}
        explicit = context.get("locale") or hints.get("locale")
        if explicit:
            return str(explicit)
        from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService

        language = FinnV2RequestPreprocessorService._language_from_text(
            str(getattr(run, "message", "") or "").casefold()
        )
        return {"de": "de-DE", "en": "en-US"}.get(language, "nl-NL")

    def _snapshot_model(self, snapshot: Any) -> FinancialStateSnapshot:
        if isinstance(snapshot, FinancialStateSnapshot):
            return snapshot
        if getattr(snapshot, "snapshot_json", None):
            return FinancialStateSnapshot.parse_obj(snapshot.snapshot_json)
        return FinancialStateSnapshot.parse_obj(
            {
                "snapshot_id": getattr(snapshot, "id"),
                "run_id": getattr(snapshot, "run_id"),
                "user_id": getattr(snapshot, "user_id"),
                "revision": getattr(snapshot, "revision", 1),
                "schema_version": getattr(snapshot, "schema_version", None),
                "assembly_version": getattr(snapshot, "assembly_version", None),
                "evidence_set_hash": getattr(snapshot, "evidence_set_hash", ""),
                "nodes": [],
                "edges": [],
                "tool_outcomes": [],
                "assembled_at": getattr(snapshot, "assembled_at"),
                "redacted_at": getattr(snapshot, "redacted_at", None),
            }
        )

    def _validation_model(self, validation: Any) -> EvidenceValidationResult:
        if isinstance(validation, EvidenceValidationResult):
            return validation
        if getattr(validation, "result_json", None):
            return EvidenceValidationResult.parse_obj(validation.result_json)
        return EvidenceValidationResult.parse_obj(
            {
                "validation_id": getattr(validation, "id"),
                "snapshot_id": getattr(validation, "snapshot_id"),
                "run_id": getattr(validation, "run_id"),
                "user_id": getattr(validation, "user_id"),
                "validator_version": getattr(validation, "validator_version", ""),
                "evidence_set_hash": getattr(validation, "evidence_set_hash", ""),
                "integrity_status": getattr(validation, "integrity_status", "degraded"),
                "domains": [],
                "issues": [],
                "validated_at": getattr(validation, "validated_at"),
                "redacted_at": getattr(validation, "redacted_at", None),
            }
        )
