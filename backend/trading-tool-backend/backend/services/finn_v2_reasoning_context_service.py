from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_reasoning_context_schema import (
    REASONING_CONTEXT_VERSION,
    ReasoningContextPackage,
    ReasoningDomainStatus,
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
        "read_portfolio": "portfolio_context",
        "read_latest_report": "report_context",
        "read_review_history": "review_context",
    }

    def __init__(self, session: AsyncSession, *, max_evidence_items: int = 30, max_context_bytes: int = 131072):
        self.session = session
        self.evidence_repo = FinnV2EvidenceRepository(session)
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
        artifacts = await self.evidence_repo.list_for_run(run_id=run.id, user_id=run.user_id)
        selected_domains = set(orchestrator_result.domain_requirements.required_domains + orchestrator_result.domain_requirements.optional_domains)
        evidence: list[ReasoningEvidenceItem] = []
        index = 1
        for artifact in artifacts:
            domain = self.DOMAIN_BY_TOOL.get(artifact.tool_name)
            if domain not in selected_domains:
                continue
            facts = self._sanitize_facts(artifact.payload_json or {}, artifact.tool_name)
            item = ReasoningEvidenceItem(
                evidence_id=f"E{index}",
                artifact_id=artifact.id,
                tool_name=artifact.tool_name,
                domain=domain,
                entity_type=artifact.entity_type or "unknown",
                entity_id=artifact.entity_id,
                asset=artifact.asset,
                source=artifact.source,
                as_of=artifact.source_as_of,
                freshness=artifact.freshness,
                confidence=self._confidence_for(artifact.availability, artifact.freshness),
                facts=facts,
            )
            evidence.append(item)
            index += 1
            if len(evidence) >= self.max_evidence_items:
                break

        evidence = self._trim_to_size(evidence)
        domain_statuses = []
        for item in validation.domains:
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
            snapshot_id=snapshot.snapshot_id,
            validation_id=validation.validation_id,
            policy_decision_id=policy.policy_decision_id,
            evidence_set_hash=validation.evidence_set_hash,
            context_version=REASONING_CONTEXT_VERSION,
            evidence=evidence,
            domain_statuses=domain_statuses,
            policy=policy_context,
            allowed_response_modes=[orchestrator_result.analysis.interaction_mode],
            allowed_operation_types=[policy.operation_type] if policy.operation_type else [],
            uncertainty_codes=list(orchestrator_result.uncertainty_codes),
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
            return {
                "symbol": payload.get("symbol"),
                "configured_indicators": [
                    {
                        "indicator": item.get("indicator"),
                        "category": item.get("category"),
                        "enabled": item.get("enabled"),
                        "priority": item.get("priority"),
                    }
                    for item in payload.get("technical", [])[:12]
                ],
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
            return {key: payload.get(key) for key in ["setup_id", "name", "symbol", "timeframe", "score"] if payload.get(key) is not None}
        if tool_name == "read_linked_strategy":
            return {key: payload.get(key) for key in ["strategy_id", "setup_id", "name", "symbol", "timeframe", "execution_mode", "risk_profile"] if payload.get(key) is not None}
        if tool_name == "read_linked_bot":
            return {key: payload.get(key) for key in ["bot_id", "name", "symbol", "strategy_id", "is_active", "is_live", "mode"] if payload.get(key) is not None}
        if tool_name == "read_bot_status":
            return {key: payload.get(key) for key in ["bot_id", "is_active", "is_live", "last_run", "mode", "cadence"] if payload.get(key) is not None}
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
        return str(context.get("locale") or hints.get("locale") or "nl-NL")
