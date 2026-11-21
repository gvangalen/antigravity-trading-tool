from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.domain.plan_price_comparison import compare_plan_entry_with_market

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


_PUBLIC_PROPOSAL_FIELDS = frozenset({
    "name", "symbol", "timeframe", "setup_type", "dca_frequency", "dca_trigger_mode", "dca_day",
    "dca_month_day", "min_investment", "benchmark_score_min", "benchmark_score_max",
    "macro_score_min", "macro_score_max", "technical_score_min", "technical_score_max",
    "execution_mode", "base_amount", "entry", "stop_loss", "targets", "price_currency",
    "risk_profile", "budget_total_eur", "paper_initial_cash_eur",
    "score_source", "low_threshold", "high_threshold", "low_score_percent",
    "mid_score_percent", "high_score_percent",
})


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

        feed_evidence = await self._current_feed_evidence(run)
        if feed_evidence:
            # This is freshly owner-scoped database evidence, never client copy.
            # Keep it ahead of older tool results if the context is trimmed.
            evidence = [*feed_evidence, *evidence]
            selected_domains.add("plan_context")
            evidence = evidence[:self.max_evidence_items]
        self._attach_plan_price_comparisons(evidence)
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

    async def _current_feed_evidence(self, run) -> list[ReasoningEvidenceItem]:
        context = getattr(run, "client_context_json", {}) or {}
        item_id = str(context.get("feed_item_id") or "").strip()
        selection_origin = "current_run" if item_id else "conversation"
        if not item_id and getattr(run, "conversation_id", None):
            from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
            saved = await FinnV2ConversationRepository(self.session).get_context(
                conversation_id=run.conversation_id, user_id=run.user_id,
            )
            selected = saved.get("feed_event") or {}
            if isinstance(selected, dict) and selected.get("read_only_context") is True:
                item_id = str(selected.get("item_id") or "").strip()
        if not item_id:
            return []
        from backend.services.finn_coach_feed_service import FinnCoachFeedService
        item = await FinnCoachFeedService(self.session).detail(
            user_id=run.user_id, item_id=item_id,
        )
        if not item:
            return []
        event_type = item.get("event_type")
        if event_type != "proposal_pending":
            recorded = item.get("evidence") or {}
            historical = {}
            for key in ("status", "match_status", "plan_status", "source_status",
                        "market_id", "trading_pair", "direction", "change_24h", "benchmark_score",
                        "setup_name", "setup_id", "strategy_id", "strategy_name", "trading_pair_status",
                        "score_as_of", "conditions", "components",
                        "component_source_status", "source_observed_at",
                        "quote_source_observed_at",
                        "setup_ids", "action", "decision_id", "bot_id",
                        "exposure_pct", "limit_pct", "valuation_as_of",
                        "week_start", "week_end", "trades", "plans", "notes",
                        "report_type", "report_date", "attention_pair", "attention_kind",
                        "analyzed", "pending", "unavailable",
                        "confirmed_repeated_lessons", "suggestion_kind",
                        "affected_categories", "indicator_revision",
                        "weight_revision", "order_status", "amount_eur",
                        "decision_kind"):
                value = recorded.get(key)
                if value is not None and len(json.dumps(value, default=str)) <= 1500:
                    historical[key] = value
            if event_type == "bot_decision":
                reasons = recorded.get("reasons")
                if isinstance(reasons, list):
                    historical["recorded_reason_text_untrusted"] = [
                        value.strip()[:240] for value in reasons[:2]
                        if isinstance(value, str) and value.strip()]
            if event_type == "weekly_reflection" and historical.get("week_end"):
                try:
                    historical["week_end_exclusive"] = historical["week_end"]
                    historical["week_end"] = (
                        date.fromisoformat(str(historical["week_end_exclusive"])) - timedelta(days=1)
                    ).isoformat()
                except ValueError:
                    pass
            historical_facts = {"feed_item_id": item_id, "event_type": event_type,
                     "symbol": item.get("symbol"),
                     "selection_origin": selection_origin,
                     "notification_status": item.get("status"),
                     "historical_notification": True,
                     "current_trade_signal_confirmed": False,
                     "historical_event_facts": historical,
                     "historical_source_observed_at": item.get("source_observed_at")}
            subject = item.get("subject_type")
            symbol = item.get("symbol")
            current_facts = None
            current_available = False
            current_source = "owner_scoped_current_score"
            current_as_of = datetime.now(timezone.utc)
            if symbol and event_type in {"plan_match", "plan_review", "data_blocked", "market_move",
                                         "improvement_suggestion", "analysis_ready", "strategy_next_step",
                                         "paper_next_step"}:
                from backend.services.setup_market_match_service import SetupMarketMatchService
                matcher = SetupMarketMatchService(self.session)
                selected_setup_id = (item.get("subject_id") if subject == "setup" else None)
                if event_type == "data_blocked" and not selected_setup_id:
                    setup_ids = recorded.get("setup_ids")
                    if isinstance(setup_ids, list) and len(setup_ids) == 1:
                        selected_setup_id = setup_ids[0]
                owned_setup = None
                if str(selected_setup_id or "").isdigit():
                    from backend.infrastructure.repositories.setup_repository import SetupRepository
                    owned_setup = await SetupRepository(self.session).get_setup_by_id(
                        int(selected_setup_id), run.user_id)
                    assessment = await matcher.for_asset(
                        run.user_id, symbol,
                        setups=[dict(owned_setup)] if owned_setup else [],
                        market_id=owned_setup.get("market_id") if owned_setup else None,
                    )
                else:
                    if event_type in {"improvement_suggestion", "analysis_ready", "strategy_next_step",
                                      "paper_next_step"}:
                        market_id = recorded.get("market_id")
                        if type(market_id) is not int or market_id <= 0:
                            market_id = None
                        assessment = await matcher.for_asset(run.user_id, symbol,
                                                             market_id=market_id)
                    else:
                        assessment = await matcher.for_asset(run.user_id, symbol)
                current_facts = {"feed_item_id": item_id,
                                 "current_source_status": assessment.get("source_status"),
                                 "current_trade_signal_confirmed": False}
                if event_type in {"analysis_ready", "strategy_next_step", "paper_next_step"}:
                    current_facts["current_benchmark_score"] = (
                        assessment.get("benchmark_score")
                        if assessment.get("source_status") == "available" else None
                    )
                    current_facts["current_score_as_of"] = str(assessment.get("as_of") or "")
                if selected_setup_id:
                    current = next((match for match in assessment.get("matches", [])
                                    if str(match.get("setup_id")) == str(selected_setup_id)), None)
                    current_facts["current_setup"] = ({"id": current.get("setup_id") if current else owned_setup.get("id"),
                                                "name": current.get("name") if current else owned_setup.get("name"),
                                                "status": current.get("status") if current else "not_assessed",
                                                "trading_pair": (
                                                    f"{symbol}/{owned_setup['quote_currency']}"
                                                    if owned_setup and owned_setup.get("market_id")
                                                    and owned_setup.get("quote_currency") else None),
                                                "trading_pair_status": (
                                                    "saved" if owned_setup and owned_setup.get("market_id")
                                                    and owned_setup.get("quote_currency")
                                                    else "not_saved_on_setup")}
                                               if (current or owned_setup) else None)
                if event_type in {"data_blocked", "improvement_suggestion"}:
                    current_facts["current_component_source_status"] = assessment.get("component_source_status")
                if event_type in {"strategy_next_step", "paper_next_step"}:
                    strategy_row = None
                    if owned_setup:
                        strategy_result = await self.session.execute(text("""
                            SELECT id, name, setup_type,
                                   data->>'execution_ready' AS execution_ready
                            FROM strategies
                            WHERE user_id=:user_id AND setup_id=:setup_id
                            ORDER BY created_at DESC, id DESC LIMIT 1
                        """), {"user_id": run.user_id, "setup_id": int(owned_setup["id"])})
                        strategy_row = strategy_result.mappings().first()
                    current_facts["current_linked_strategy"] = (
                        {"id": strategy_row["id"], "name": strategy_row["name"],
                         "setup_type": strategy_row.get("setup_type"),
                         "execution_ready_status": (
                             "draft" if strategy_row.get("execution_ready") == "false"
                             else "declared_ready" if strategy_row.get("execution_ready") == "true"
                             else "unverified"
                         )}
                        if strategy_row else {"status": "missing" if owned_setup else "setup_unavailable"}
                    )
                    if event_type == "paper_next_step" and owned_setup:
                        bot_result = await self.session.execute(text("""
                            SELECT b.id, b.name, b.is_live, b.is_active
                            FROM bot_configs b
                            JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id
                            WHERE b.user_id=:user_id AND s.setup_id=:setup_id
                            ORDER BY b.created_at DESC, b.id DESC LIMIT 1
                        """), {"user_id": run.user_id, "setup_id": int(owned_setup["id"])})
                        linked_bot = bot_result.mappings().first()
                        current_facts["current_linked_bot"] = (
                            {"id": linked_bot["id"], "name": linked_bot["name"],
                             "is_live": bool(linked_bot["is_live"]),
                             "is_active": bool(linked_bot["is_active"])}
                            if linked_bot else {"status": "missing"}
                        )
                current_available = assessment.get("source_status") == "available"
                if event_type in {"strategy_next_step", "paper_next_step"}:
                    current_available = bool(owned_setup)
                if event_type in {"improvement_suggestion", "analysis_ready", "strategy_next_step",
                                  "paper_next_step"}:
                    score_row = getattr(matcher, "last_source_row", None) or {}
                    current_as_of = self._parse_feed_moment(score_row.get("calculated_at"))
            elif event_type in {"daily_report_ready", "periodic_report_ready"}:
                pair = str(recorded.get("attention_pair") or "").strip().upper()
                if re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,19}(?:/[A-Z]{2,12})?", pair):
                    asset, separator, quote = pair.partition("/")
                    symbol = asset
                    market_id = None
                    pair_resolved = True
                    if separator:
                        result = await self.session.execute(text("""
                            SELECT w.market_id
                            FROM watchlists w JOIN trading_markets m ON m.id=w.market_id
                            WHERE w.user_id=:user_id AND w.symbol=:symbol
                              AND m.quote_currency=:quote
                            ORDER BY w.id DESC LIMIT 2
                        """), {"user_id": run.user_id, "symbol": asset, "quote": quote})
                        owned_pairs = result.mappings().all()
                        pair_resolved = len(owned_pairs) == 1
                        if pair_resolved:
                            market_id = owned_pairs[0]["market_id"]
                    if pair_resolved:
                        from backend.services.setup_market_match_service import SetupMarketMatchService
                        matcher = SetupMarketMatchService(self.session)
                        assessment = await matcher.for_asset(run.user_id, asset,
                                                             market_id=market_id)
                        status = assessment.get("source_status")
                        current_facts = {
                            "feed_item_id": item_id,
                            "current_trade_signal_confirmed": False,
                            "current_report_pair": pair,
                            "current_source_status": status,
                            "current_benchmark_score": (
                                assessment.get("benchmark_score") if status == "available" else None),
                            "current_score_as_of": str(assessment.get("as_of") or ""),
                            "current_component_source_status": assessment.get(
                                "component_source_status"),
                        }
                        current_available = status == "available"
                        score_row = getattr(matcher, "last_source_row", None) or {}
                        saved_moment = self._parse_feed_moment(score_row.get("calculated_at"))
                        if saved_moment is not None:
                            current_as_of = saved_moment
                    else:
                        current_facts = {
                            "feed_item_id": item_id,
                            "current_trade_signal_confirmed": False,
                            "current_report_pair": pair,
                            "current_source_status": "exact_pair_unavailable",
                            "current_benchmark_score": None,
                        }
                    current_source = "owner_scoped_current_score"
            elif event_type == "position_risk" and subject == "bot" and item.get("subject_id"):
                from backend.services.paper_position_risk_service import PaperPositionRiskService
                try:
                    bot_id = int(item["subject_id"])
                except (TypeError, ValueError):
                    bot_id = None
                current = (await PaperPositionRiskService(self.session).evaluate(run.user_id)).get(bot_id)
                if current:
                    # Feed facts are also persisted in the Responses tool trace.
                    # Keep the owner-scoped valuation moments, but make them
                    # JSON-safe before the runtime contract is written.
                    current = {
                        key: value.isoformat() if isinstance(value, datetime) else value
                        for key, value in current.items()
                    }
                current_facts = {
                    "feed_item_id": item_id, "current_trade_signal_confirmed": False,
                    "current_position_risk": current or {"status": "bot_unavailable"},
                }
                current_available = bool(current and current["status"] in {
                    "within_limit", "above_saved_limit"})
                current_source = "owner_scoped_current_paper_portfolio"
                if current and current.get("valuation_as_of"):
                    current_as_of = self._parse_feed_moment(current["valuation_as_of"])
            elif event_type == "bot_decision" and subject == "bot":
                try:
                    decision_id = int(recorded.get("decision_id"))
                except (TypeError, ValueError):
                    decision_id = None
                saved = None
                if decision_id and decision_id > 0:
                    result = await self.session.execute(text("""
                        SELECT d.id, d.action, d.status, d.decision_ts,
                               d.amount_eur, d.reason_json,
                               o.status AS order_status,
                               o.quote_amount_eur AS filled_amount_eur
                        FROM bot_decisions d JOIN bot_configs b
                          ON b.id=d.bot_id AND b.user_id=d.user_id
                        LEFT JOIN LATERAL (
                          SELECT status, quote_amount_eur FROM bot_orders o
                          WHERE o.user_id=d.user_id AND o.bot_id=d.bot_id
                            AND o.decision_id=d.id AND o.execution_environment='paper'
                          ORDER BY o.id DESC LIMIT 1
                        ) o ON TRUE
                        WHERE d.user_id=:user_id AND d.id=:decision_id
                          AND COALESCE(b.is_live,FALSE)=FALSE
                    """), {"user_id": run.user_id, "decision_id": decision_id})
                    saved = result.mappings().first()
                current_facts = {"feed_item_id": item_id,
                                 "current_trade_signal_confirmed": False,
                                 "current_bot_decision": ({
                                     "action": saved["action"], "status": saved["status"],
                                     "order_status": saved["order_status"],
                                     "decision_amount_eur": saved["amount_eur"],
                                     "filled_amount_eur": (saved["filled_amount_eur"]
                                                           if saved["order_status"] == "filled" else None),
                                 } if saved else {"status": "unavailable"})}
                if saved:
                    reasons = saved["reason_json"]
                    if isinstance(reasons, str):
                        try:
                            reasons = json.loads(reasons)
                        except ValueError:
                            reasons = []
                    if isinstance(reasons, list):
                        current_facts["current_bot_decision"]["recorded_reason_text_untrusted"] = [
                            value.strip()[:240] for value in reasons[:2]
                            if isinstance(value, str) and value.strip()]
                current_available = bool(saved)
                current_source = "owner_scoped_persisted_paper_decision"
                current_as_of = self._parse_feed_moment(saved["decision_ts"]) if saved else None
            elif event_type == "weekly_reflection" and subject == "reflection":
                try:
                    week_start = date.fromisoformat(str(recorded.get("week_start") or ""))
                except ValueError:
                    week_start = None
                saved = None
                if week_start:
                    result = await self.session.execute(text("""
                        SELECT summary, generated_at FROM finn_weekly_trade_reflections
                        WHERE user_id=:user_id AND week_start=:week_start
                    """), {"user_id": run.user_id, "week_start": week_start})
                    saved = result.mappings().first()
                summary = saved["summary"] if saved else None
                if isinstance(summary, str):
                    try:
                        summary = json.loads(summary)
                    except ValueError:
                        summary = None
                current_facts = {"feed_item_id": item_id,
                                 "current_trade_signal_confirmed": False,
                                 "current_weekly_reflection": ({
                                     key: summary.get(key) for key in (
                                         "trades", "plans", "notes", "analyzed",
                                         "pending", "unavailable")
                                 } if isinstance(summary, dict) else {"status": "unavailable"})}
                if isinstance(summary, dict):
                    allowed_themes = {"plan_followed", "risk", "timing", "exit_process",
                                      "evidence_gap", "missing_plan", "plan_not_recorded"}
                    current_facts["current_weekly_reflection"]["observed_patterns"] = [
                        {"theme": row["theme"], "count": row["count"],
                         "basis": row.get("basis")}
                        for row in (summary.get("patterns") or [])[:7]
                        if isinstance(row, dict) and row.get("theme") in allowed_themes
                        and type(row.get("count")) is int and 1 <= row["count"] <= 500]
                    current_facts["current_weekly_reflection"]["confirmed_repeated_lessons"] = [
                        {"count": row["count"],
                         "basis": "user_confirmed_exact_wording",
                         "scope": "repeated_wording_does_not_prove_repeated_behavior"}
                        for row in (summary.get("confirmed_lesson_repetitions") or [])[:5]
                        if isinstance(row, dict) and row.get("basis") == "user_confirmed_exact_wording"
                        and type(row.get("count")) is int and 2 <= row["count"] <= 500]
                current_available = isinstance(summary, dict)
                current_source = "owner_scoped_weekly_trade_reflection"
                if saved:
                    current_as_of = self._parse_feed_moment(saved["generated_at"])
            source_moment = self._parse_feed_moment(item.get("source_observed_at") or item.get("created_at"))
            historical_item = ReasoningEvidenceItem(
                evidence_id="E0", artifact_id=f"feed-item:{item_id}",
                tool_name="read_feed_event", domain="plan_context",
                entity_type=str(subject or "unknown"),
                entity_id=str(item.get("subject_id") or "") or None,
                asset=symbol, source="owner_scoped_historical_feed",
                as_of=source_moment, freshness="historical",
                availability="available", confidence="medium", facts=historical_facts,
            )
            if current_facts is None:
                return [historical_item]
            current_item = ReasoningEvidenceItem(
                evidence_id="E00", artifact_id=f"feed-current:{item_id}",
                tool_name="read_feed_current_state", domain="plan_context",
                entity_type=str(subject or "unknown"),
                entity_id=str(item.get("subject_id") or "") or None,
                asset=symbol, source=current_source,
                as_of=current_as_of,
                freshness="fresh" if current_available else "stale",
                availability="available",
                confidence="high" if current_available else "medium",
                facts=current_facts,
            )
            return [historical_item, current_item]
        from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
        proposal = await FinnV2ProposalRepository(self.session).get_by_id_for_user(
            proposal_id=str(item.get("subject_id") or ""), user_id=run.user_id,
        )
        expires_at = getattr(proposal, "expires_at", None)
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        active = bool(
            proposal is not None
            and proposal.status in {"draft", "pending_confirmation"}
            and expires_at is not None and expires_at > datetime.now(timezone.utc)
            and item.get("status") in {"unread", "read"}
        )
        facts = {"proposal_status": "awaiting_separate_confirmation" if active else "no_longer_active",
                 "feed_item_id": item_id, "confirmation_authorized": False}
        if active:
            change = (proposal.payload_json or {}).get("change") or {}
            fields = (change.get("setup_fields") or change.get("strategy_fields")
                      or change.get("bot_fields") or change.get("changed_fields") or {})
            if not isinstance(fields, dict):
                fields = {}
            proposed_changes = {
                key: value for key, value in fields.items()
                if key in _PUBLIC_PROPOSAL_FIELDS
                and isinstance(value, (str, int, float, bool, list))
                and (not isinstance(value, list) or (
                    len(value) <= 8 and all(isinstance(part, (str, int, float, bool)) for part in value)
                ))
                and len(json.dumps(value, default=str)) <= 256
            }
            from backend.services.finn_coach_feed_service import FinnCoachFeedService
            target_type, target_id, target_name = await FinnCoachFeedService(self.session)._proposal_target(
                proposal, user_id=run.user_id,
            )
            facts.update({
                "proposal_id": proposal.id,
                "proposal_name": str(fields.get("name") or target_name or proposal.asset or proposal.operation_type)[:120],
                "operation_type": proposal.operation_type,
                "asset": proposal.asset,
                "target_type": target_type,
                "target_id": target_id,
                "target_name": target_name,
                "proposed_changes": proposed_changes,
            })
        return [ReasoningEvidenceItem(
            evidence_id="E0", artifact_id=f"feed-proposal:{item_id}",
            tool_name="read_feed_proposal", domain="plan_context",
            entity_type="proposal", entity_id=str(item.get("subject_id") or ""),
            asset=proposal.asset if active else item.get("symbol"),
            source="owner_scoped_database", as_of=datetime.now(timezone.utc),
            freshness="fresh", availability="available", confidence="high",
            facts=facts,
        )]

    @staticmethod
    def _parse_feed_moment(value) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    @classmethod
    def _attach_plan_price_comparisons(cls, evidence: list[ReasoningEvidenceItem]) -> None:
        """Derive direction only from same-unit, dated, owner-scoped tool facts."""
        markets = [item for item in evidence if item.tool_name == "read_market_snapshot"]
        for strategy in (item for item in evidence if item.tool_name == "read_linked_strategy"):
            facts = strategy.facts
            if facts.get("entry") is None:
                continue
            matching = [
                item for item in markets
                if str(item.facts.get("symbol") or "").upper() == str(facts.get("symbol") or "").upper()
            ]
            market = max(
                matching,
                key=lambda item: cls._parse_feed_moment(item.facts.get("as_of"))
                or datetime.min.replace(tzinfo=timezone.utc),
            ) if matching else None
            result = compare_plan_entry_with_market(facts, market.facts if market else None)
            if market and result["status"] == "available":
                result["market_artifact_id"] = market.artifact_id
            facts["market_price_comparison"] = result

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
            return {"trader_profile": payload.get("trader_profile", {}), "trader_context": payload.get("trader_context"), "has_profile": payload.get("has_profile")}
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
                        **({"weight": item["weight"]} if item.get("weight") is not None else {}),
                    }
                )
            return {
                "symbol": source.get("symbol") or summary.get("symbol"),
                "market_id": source.get("market_id"),
                "pair": source.get("pair"),
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
            return {key: payload.get(key) for key in (
                "symbol", "as_of", "source_status", "reported_scores", "component_source_status",
                "benchmark_score", "benchmark_weights",
            )}
        if tool_name == "read_market_snapshot":
            return {key: payload.get(key) for key in [
                "symbol", "price", "quote_currency", "price_provider",
                "change_24h", "volume", "source", "as_of",
            ] if payload.get(key) is not None}
        if tool_name == "read_macro_snapshot":
            return {"symbol": payload.get("symbol"), "items": payload.get("items", [])[:8]}
        if tool_name == "read_technical_snapshot":
            return {"symbol": payload.get("symbol"), "items": payload.get("items", [])[:8]}
        if tool_name == "read_active_setup":
            facts = {
                key: payload.get(key)
                for key in [
                    "setup_id", "name", "symbol", "timeframe", "setup_type", "description",
                    "dca_frequency", "dca_trigger_mode", "dca_day_name", "dca_month_day", "min_investment",
                    "min_benchmark_score", "max_benchmark_score",
                    "saved_market_condition", "score",
                ]
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
                    "price_currency",
                    "price_currency_status",
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
                    "strategy_name",
                    "setup_id",
                    "setup_name",
                    "is_active",
                    "operational_status",
                    "is_live",
                    "mode",
                    "budget_total_eur",
                    "budget_limit_enabled",
                    "paper_initial_cash_eur",
                ]
                if payload.get(key) is not None
            }
        if tool_name == "read_bot_status":
            return {key: payload.get(key) for key in ["bot_id", "is_active", "operational_status", "is_live", "last_run", "mode", "cadence"] if payload.get(key) is not None}
        if tool_name == "read_watchlist":
            return {
                "target_asset": payload.get("target_asset"),
                "contains_target_asset": payload.get("contains_target_asset"),
                "symbols": payload.get("symbols", [])[:20],
            }
        if tool_name == "read_portfolio":
            global_payload = payload.get("global") or payload.get("global_") or {}
            return {
                "global": global_payload,
                "bots": payload.get("bots", [])[:50],
                "valuation_status": payload.get("valuation_status"),
                "valuation_available": payload.get("valuation_available"),
                "valuation_as_of": payload.get("valuation_as_of"),
                "read_at": payload.get("read_at"),
                "environment": payload.get("environment"),
                "available_cash_eur": payload.get("available_cash_eur"),
                "reserved_cash_eur": payload.get("reserved_cash_eur"),
                "unallocated_cash_eur": payload.get("unallocated_cash_eur"),
                "exchange_name": payload.get("exchange_name"),
                "balance_time_basis": payload.get("balance_time_basis"),
            }
        if tool_name == "read_latest_report":
            return {key: payload.get(key) for key in [
                "report_type", "report_date", "symbol", "status", "id", "generated_at",
                "generated_at_amsterdam",
                "market_score", "macro_score", "technical_score", "setup_score",
                "score_source_snapshot", "best_setup", "top_setups",
            ] if payload.get(key) is not None}
        if tool_name == "read_review_history":
            return {
                "items": payload.get("items", [])[:10],
                "latest_bot_decisions": payload.get("latest_bot_decisions", [])[:20],
                "selected_feed_decision": payload.get("selected_feed_decision"),
                "closed_trade_status": payload.get("closed_trade_status", "no_data"),
                "closed_trade_coverage": payload.get("closed_trade_coverage", {}),
                "closed_trade_review_ids": payload.get("closed_trade_review_ids", [])[:5],
                "closed_trades": payload.get("closed_trades", [])[:5],
                "weekly_reflection": payload.get("weekly_reflection"),
            }
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
