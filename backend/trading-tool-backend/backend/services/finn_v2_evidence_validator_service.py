from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.schemas.finn_v2_domain_validation_schema import (
    ClarificationCandidate,
    DomainValidationResult,
    EvidenceIssue,
    EvidenceValidationResult,
    VALIDATOR_VERSION,
)
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services.finn_v2_state_redaction_service import FinnV2StateRedactionService


DOMAIN_TOOLS = {
    "identity_context": ["read_profile", "read_user_preferences", "read_active_asset"],
    "market_context": ["read_active_asset", "read_indicator_configuration", "read_asset_scores", "read_market_snapshot", "read_macro_snapshot", "read_technical_snapshot"],
    "plan_context": ["read_active_asset", "read_active_setup", "read_linked_strategy"],
    "automation_context": ["read_active_setup", "read_linked_strategy", "read_linked_bot", "read_bot_status"],
    "portfolio_context": ["read_portfolio"],
    "report_context": ["read_latest_report"],
    "review_context": ["read_review_history"],
}


class FinnV2EvidenceValidatorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.validations = FinnV2ValidationRepository(session)
        self.redaction = FinnV2StateRedactionService()

    async def validate_snapshot(self, snapshot: FinancialStateSnapshot) -> EvidenceValidationResult:
        existing = await self.validations.get_for_snapshot_version(
            snapshot_id=snapshot.snapshot_id,
            user_id=snapshot.user_id,
            validator_version=VALIDATOR_VERSION,
        )
        if existing is not None:
            return EvidenceValidationResult(**(existing.result_json or {}))

        domain_results = [self._validate_domain(snapshot, domain) for domain in DOMAIN_TOOLS]
        global_issues = self._integrity_issues(snapshot)
        integrity_status = "invalid" if any(issue.severity == "blocking" for issue in global_issues) else (
            "degraded" if any(issue.severity == "warning" for issue in global_issues) or any(result.status == "degraded" for result in domain_results) else "valid"
        )
        validation = EvidenceValidationResult(
            validation_id=f"finn-v2-validation-{uuid.uuid4().hex}",
            snapshot_id=snapshot.snapshot_id,
            run_id=snapshot.run_id,
            user_id=snapshot.user_id,
            evidence_set_hash=snapshot.evidence_set_hash,
            integrity_status=integrity_status,
            domains=domain_results,
            issues=global_issues,
            validated_at=datetime.now(timezone.utc),
        )
        await self.validations.create(
            id=validation.validation_id,
            snapshot_id=snapshot.snapshot_id,
            run_id=snapshot.run_id,
            user_id=snapshot.user_id,
            schema_version=validation.schema_version,
            validator_version=VALIDATOR_VERSION,
            evidence_set_hash=snapshot.evidence_set_hash,
            integrity_status=validation.integrity_status,
            result_json=self.redaction.payload_to_jsonable(validation),
            validated_at=validation.validated_at,
        )
        return validation

    def _validate_domain(self, snapshot: FinancialStateSnapshot, domain: str) -> DomainValidationResult:
        outcomes = {item.tool_name: item for item in snapshot.tool_outcomes}
        required = DOMAIN_TOOLS[domain]
        available_artifacts = [outcomes[name].artifact_id for name in required if name in outcomes and outcomes[name].artifact_id]
        issues: list[EvidenceIssue] = []
        clarifications: list[ClarificationCandidate] = []

        for tool_name in required:
            outcome = outcomes.get(tool_name)
            if outcome is None or outcome.status == "not_collected":
                issues.append(EvidenceIssue(code="evidence_not_collected", severity="info", domain=domain, message=f"{tool_name} not collected"))
                continue
            for code in outcome.error_codes:
                severity = "warning"
                if code in {"setup_ambiguous", "strategy_ambiguous", "bot_ambiguous", "asset_ambiguous"}:
                    clarifications.append(self._clarification(domain, code))
                issues.append(EvidenceIssue(code=code, severity=severity, domain=domain, artifact_id=outcome.artifact_id, message=code))
            if outcome.status == "stale":
                issues.append(EvidenceIssue(code=self._stale_code(tool_name), severity="warning", domain=domain, artifact_id=outcome.artifact_id, message=f"{tool_name} stale"))
            if outcome.status == "unavailable" and tool_name == "read_indicator_configuration":
                issues.append(EvidenceIssue(code="indicator_config_missing", severity="warning", domain=domain, artifact_id=outcome.artifact_id, message="Indicator configuration missing"))
            if outcome.status == "unavailable" and tool_name == "read_asset_scores":
                issues.append(EvidenceIssue(code="score_missing", severity="warning", domain=domain, artifact_id=outcome.artifact_id, message="Score missing"))

        status = self._domain_status(domain, required, outcomes, issues)
        confidence = self._domain_confidence(status, issues)
        return DomainValidationResult(
            domain=domain,
            status=status,
            confidence=confidence,
            issues=issues,
            clarification_candidates=clarifications,
            required_artifacts=required,
            available_artifacts=[artifact_id for artifact_id in available_artifacts if artifact_id],
        )

    def _integrity_issues(self, snapshot: FinancialStateSnapshot) -> list[EvidenceIssue]:
        issues: list[EvidenceIssue] = []
        node_map = {node.node_id: node for node in snapshot.nodes}
        setup = next((node for key, node in node_map.items() if key.startswith("setup:")), None)
        strategy = next((node for key, node in node_map.items() if key.startswith("strategy:")), None)
        bot = next((node for key, node in node_map.items() if key.startswith("bot:")), None)
        bot_status = node_map.get("bot_status")
        asset = next((node for key, node in node_map.items() if key.startswith("asset:")), None)

        if asset and setup and self._payload_value(setup.payload, "symbol") and self._payload_value(setup.payload, "symbol") != self._payload_value(asset.payload, "symbol"):
            issues.append(EvidenceIssue(code="conflict_asset_setup", severity="blocking", domain="plan_context", node_id=setup.node_id, message="Setup asset conflicts with resolved asset"))
        setup_id = self._payload_value(setup.payload, "setup_id") if setup else None
        if setup_id is None and setup is not None:
            setup_id = self._coerce_int(setup.entity_id)
        strategy_setup_id = self._payload_value(strategy.payload, "setup_id") if strategy else None
        if setup and strategy and strategy_setup_id is not None and setup_id is not None and strategy_setup_id != setup_id:
            issues.append(EvidenceIssue(code="conflict_setup_strategy", severity="blocking", domain="plan_context", node_id=strategy.node_id, message="Strategy conflicts with setup"))
        strategy_id = self._payload_value(strategy.payload, "strategy_id") or self._coerce_int(strategy.entity_id) if strategy else None
        bot_strategy_id = self._payload_value(bot.payload, "strategy_id") if bot else None
        if strategy and bot and bot_strategy_id is not None and strategy_id is not None and bot_strategy_id != strategy_id:
            issues.append(EvidenceIssue(code="conflict_strategy_bot", severity="blocking", domain="automation_context", node_id=bot.node_id, message="Bot conflicts with strategy"))
        bot_id = self._payload_value(bot.payload, "bot_id") or self._coerce_int(bot.entity_id) if bot else None
        bot_status_id = self._payload_value(bot_status.payload, "bot_id") if bot_status else None
        if bot and bot_status and bot_status_id is not None and bot_id is not None and bot_status_id != bot_id:
            issues.append(EvidenceIssue(code="conflict_bot_status", severity="blocking", domain="automation_context", node_id=bot_status.node_id, message="Bot status conflicts with bot"))
        return issues

    def _payload_value(self, payload, key: str):
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload.get(key)
        return getattr(payload, key, None)

    def _coerce_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _domain_status(self, domain: str, required: list[str], outcomes, issues: list[EvidenceIssue]) -> str:
        if any(issue.severity == "blocking" for issue in issues):
            return "invalid"
        statuses = [outcomes[name].status for name in required if name in outcomes]
        if not statuses:
            return "not_collected"
        if any(status == "ambiguous" for status in statuses):
            return "ambiguous"
        if all(status == "unavailable" for status in statuses):
            return "unavailable"
        if any(status in {"stale", "unavailable", "failed"} for status in statuses):
            if domain == "review_context" and "read_review_history" in required:
                return "unavailable"
            return "degraded"
        return "available"

    def _domain_confidence(self, status: str, issues: list[EvidenceIssue]) -> str:
        if status in {"invalid", "not_collected"}:
            return "none"
        if status == "available" and not any(issue.severity in {"warning", "blocking"} for issue in issues):
            return "high"
        if status == "degraded":
            return "medium"
        return "low"

    def _clarification(self, domain: str, code: str) -> ClarificationCandidate:
        question_map = {
            "asset_ambiguous": ("ambiguous_asset", "Over welke asset wil je dat ik dit beoordeel?", "asset"),
            "setup_ambiguous": ("ambiguous_setup", "Ik zie meerdere setups voor deze asset. Welke setup bedoel je precies?", "setup"),
            "strategy_ambiguous": ("ambiguous_strategy", "Ik zie meerdere strategieën die hierbij kunnen horen. Welke strategie bedoel je precies?", "strategy"),
            "bot_ambiguous": ("ambiguous_bot", "Ik zie meerdere bots die hierbij kunnen horen. Welke bot bedoel je precies?", "bot"),
        }
        candidate_code, question, entity_type = question_map[code]
        return ClarificationCandidate(code=candidate_code, domain=domain, question=question, entity_type=entity_type)

    def _stale_code(self, tool_name: str) -> str:
        # Freshness describes the collected artifact, not the entity returned by
        # the tool. Preserve the source for traceability without manufacturing an
        # entity status such as "bot_status_stale" from source recency.
        return f"evidence_freshness_stale:{tool_name}"
