from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER, ToolExecutionResult
from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_tool_call_repository import FinnV2ToolCallRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.schemas.finn_v2_orchestrator_schema import ToolPlan
from backend.services.finn_v2_evidence_ingestion_service import FinnV2EvidenceIngestionService
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService
from backend.services.finn_v2_tool_adapters.asset_tool_adapter import AssetToolAdapter
from backend.services.finn_v2_tool_adapters.bot_tool_adapter import BotToolAdapter
from backend.services.finn_v2_tool_adapters.indicator_tool_adapter import IndicatorToolAdapter
from backend.services.finn_v2_tool_adapters.macro_tool_adapter import MacroToolAdapter
from backend.services.finn_v2_tool_adapters.market_tool_adapter import MarketToolAdapter
from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
from backend.services.finn_v2_tool_adapters.preferences_tool_adapter import PreferencesToolAdapter
from backend.services.finn_v2_tool_adapters.profile_tool_adapter import ProfileToolAdapter
from backend.services.finn_v2_tool_adapters.report_tool_adapter import ReportToolAdapter
from backend.services.finn_v2_tool_adapters.review_tool_adapter import ReviewToolAdapter
from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import SetupToolAdapter
from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter
from backend.services.finn_v2_tool_adapters.technical_tool_adapter import TechnicalToolAdapter
from backend.services.finn_v2_tool_redaction_service import FinnV2ToolRedactionService
from backend.services.finn_v2_tool_registry_service import FinnV2ToolRegistryService
from backend.services.platform_metrics import increment_execution_safety_counter, record_latency_sample


logger = logging.getLogger(__name__)


class FinnV2ToolExecutionService:
    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.registry = FinnV2ToolRegistryService()
        self.redaction = FinnV2ToolRedactionService()
        self.freshness = FinnV2FreshnessService()
        self.resolver = FinnV2EntityResolutionService(session)
        self.runs = FinnV2RunRepository(session)
        self.calls = FinnV2ToolCallRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.evidence = FinnV2EvidenceIngestionService(session, self.flags)
        self.snapshots = FinnV2StateAssemblyService(session, self.flags)
        self.validator = FinnV2EvidenceValidatorService(session)
        self.evidence_repo = FinnV2EvidenceRepository(session)
        self.state_repo = FinnV2StateRepository(session)
        self.validation_repo = FinnV2ValidationRepository(session)
        self.profile_adapter = ProfileToolAdapter(session)
        self.preferences_adapter = PreferencesToolAdapter(session)
        self.asset_adapter = AssetToolAdapter(session)
        self.indicator_adapter = IndicatorToolAdapter(session)
        self.score_adapter = ScoreToolAdapter(session)
        self.market_adapter = MarketToolAdapter(session)
        self.macro_adapter = MacroToolAdapter(session)
        self.technical_adapter = TechnicalToolAdapter(session)
        self.setup_adapter = SetupToolAdapter()
        self.strategy_adapter = StrategyToolAdapter()
        self.bot_adapter = BotToolAdapter()
        self.portfolio_adapter = PortfolioToolAdapter(session)
        self.report_adapter = ReportToolAdapter(session)
        self.review_adapter = ReviewToolAdapter()

    async def execute_shadow_tool_chain(self, *, run_id: str, user_id: int) -> List[ToolExecutionResult]:
        if not self.flags.is_tool_shadow_execution_enabled():
            return []
        if not self.flags.is_tool_shadow_canary_user(user_id):
            return []
        plan = ToolPlan(
            run_id=run_id,
            interaction_mode="UNAVAILABLE",
            required_domains=[],
            optional_domains=[],
            tool_names=list(FINN_V2_TOOL_ORDER),
            tool_inputs={tool_name: {} for tool_name in FINN_V2_TOOL_ORDER},
            max_tool_calls=15,
            read_only=True,
            planning_reasons=["legacy_shadow_chain"],
        )
        results = await self.execute_tool_plan(run_id=run_id, user_id=user_id, tool_plan=plan)
        if self.flags.should_run_block3_shadow(user_id):
            await self._run_state_pipeline(run_id=run_id, user_id=user_id)
        return results

    async def execute_tool_plan(self, *, run_id: str, user_id: int, tool_plan: ToolPlan) -> List[ToolExecutionResult]:
        started = monotonic()
        results: List[ToolExecutionResult] = []
        shared_state: Dict[str, Any] = {}
        for tool_name in tool_plan.tool_names:
            if monotonic() - started > 20.0:
                results.append(
                    ToolExecutionResult(
                        tool_name=tool_name,
                        status="failed",
                        success=False,
                        error_codes=["tool_timeout"],
                    )
                )
                continue
            result = await self.execute_tool(
                run_id=run_id,
                user_id=user_id,
                tool_name=tool_name,
                selector=tool_plan.tool_inputs.get(tool_name, {}),
                shared_state=shared_state,
                timeout_seconds=2.0,
            )
            results.append(result)
        return results

    async def run_state_pipeline(self, *, run_id: str, user_id: int) -> Tuple[Optional[object], Optional[object]]:
        return await self._run_state_pipeline(run_id=run_id, user_id=user_id)

    async def execute_tool(
        self,
        *,
        run_id: str,
        user_id: int,
        tool_name: str,
        selector: Dict[str, Any],
        shared_state: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 2.0,
    ) -> ToolExecutionResult:
        if not self.flags.is_tool_registry_enabled():
            return ToolExecutionResult(tool_name=tool_name, status="failed", success=False, error_codes=["tool_feature_disabled"])
        if not self.flags.is_tool_registry_readonly():
            return ToolExecutionResult(tool_name=tool_name, status="failed", success=False, error_codes=["tool_readonly_violation"])
        try:
            self.registry.get_tool(tool_name)
        except KeyError:
            return ToolExecutionResult(tool_name=tool_name, status="failed", success=False, error_codes=["tool_unknown"])

        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            return ToolExecutionResult(tool_name=tool_name, status="failed", success=False, error_codes=["tool_run_not_owned"])
        if run.status not in {"collecting", "planned"}:
            return ToolExecutionResult(tool_name=tool_name, status="failed", success=False, error_codes=["tool_run_invalid_state"])

        selector = self.redaction.redact_selector(selector or {})
        tool_call = None
        if self.flags.is_tool_call_logging_enabled():
            tool_call = await self._create_tool_call(
                run_id=run.id,
                user_id=user_id,
                trace_id=run.trace_id,
                tool_name=tool_name,
                selector=selector,
            )

        started = monotonic()
        try:
            payload = await asyncio.wait_for(
                self._dispatch_tool(
                    tool_name=tool_name,
                    user_id=user_id,
                    selector=selector,
                    run=run,
                    shared_state=shared_state or {},
                ),
                timeout=timeout_seconds,
            )
            as_of = payload.get("as_of")
            freshness_status = self.freshness.freshness_for(tool_name, as_of)
            result_summary = self.redaction.redact_result_summary(payload.get("summary") or {})
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="completed",
                success=True,
                result=payload.get("data"),
                result_summary=result_summary,
                selector=selector,
                resolution_source=payload.get("resolution_source"),
                freshness_status=freshness_status,
                source=payload.get("source", "internal"),
                schema_name=payload.get("schema_name"),
                availability="stale" if freshness_status == "stale" else "available",
                entity_type=payload.get("entity_type"),
                entity_id=payload.get("entity_id"),
                asset=payload.get("asset"),
            )
        except asyncio.TimeoutError:
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="failed",
                success=False,
                selector=selector,
                error_codes=["tool_timeout"],
                schema_name=tool_name,
                availability="unavailable",
            )
        except LookupError as exc:
            code = str(exc)
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="failed",
                success=False,
                selector=selector,
                error_codes=[code],
                schema_name=tool_name,
                availability="ambiguous" if code.endswith("_ambiguous") else "unavailable",
            )
        except Exception:
            logger.exception("FINN V2 tool execution failed", extra={"tool_name": tool_name, "run_id": run_id})
            result = ToolExecutionResult(
                tool_name=tool_name,
                status="failed",
                success=False,
                selector=selector,
                error_codes=["tool_internal_error"],
                schema_name=tool_name,
                availability="unavailable",
            )

        if tool_call is not None:
            duration_ms = int((monotonic() - started) * 1000)
            persisted_tool_call = await self._complete_tool_call(
                tool_call=tool_call,
                result=result,
                duration_ms=max(duration_ms, 0),
                run_id=run_id,
                user_id=user_id,
                trace_id=run.trace_id,
            )
            if persisted_tool_call is not None:
                result.tool_call_id = getattr(persisted_tool_call, "id", result.tool_call_id)
        record_latency_sample("finn_v2_tool_execution_duration_ms", int((monotonic() - started) * 1000))
        if self.flags.should_run_block3_shadow(user_id) and tool_call is not None:
            await self._ingest_evidence(run_id=run_id, user_id=user_id, trace_id=run.trace_id, result=result)
        return result

    async def _create_tool_call(
        self,
        *,
        run_id: str,
        user_id: int,
        trace_id: str,
        tool_name: str,
        selector: Dict[str, Any],
    ):
        tool_call = None
        try:
            async with self.session.begin_nested():
                tool_call = await self.calls.create(
                    run_id=run_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    tool_name=tool_name,
                    status="requested",
                    selector_json=selector,
                    error_codes_json=[],
                )
                await self.calls.update(tool_call, status="executing")
            return tool_call
        except Exception as primary_exc:
            self._log_tool_transaction_exception(
                message="FINN V2 tool-call persistence failed before execution",
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                tool_name=tool_name,
                tool_call_id=getattr(tool_call, "id", None),
                failure_stage="tool_call_create",
                primary_exception=primary_exc,
            )
            return None

    async def _complete_tool_call(
        self,
        *,
        tool_call,
        result: ToolExecutionResult,
        duration_ms: int,
        run_id: str,
        user_id: int,
        trace_id: str,
    ):
        try:
            async with self.session.begin_nested():
                await self.calls.update(
                    tool_call,
                    status=result.status,
                    success=result.success,
                    resolution_source=result.resolution_source,
                    freshness_status=result.freshness_status,
                    result_summary_json=result.result_summary,
                    error_codes_json=result.error_codes,
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                )
            return tool_call
        except Exception as cleanup_exc:
            self._log_tool_transaction_exception(
                message="FINN V2 tool-call persistence failed after execution",
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                tool_name=result.tool_name,
                tool_call_id=getattr(tool_call, "id", None),
                failure_stage="tool_call_complete",
                cleanup_exception=cleanup_exc,
            )
            return None

    async def apply_retention(self) -> Dict[str, int]:
        if not hasattr(self.calls, "redact_results_older_than") or not hasattr(self.calls, "delete_metadata_older_than"):
            return {
                "tool_results_redacted": 0,
                "tool_metadata_deleted": 0,
                "evidence_payloads_redacted": 0,
                "state_payloads_redacted": 0,
                "validation_payloads_redacted": 0,
            }
        now = datetime.now(timezone.utc)
        result_retention_days = self.flags.tool_result_retention_days()
        metadata_retention_days = self.flags.tool_metadata_retention_days()
        try:
            redacted = await self.calls.redact_results_older_than(now - timedelta(days=result_retention_days))
            deleted = await self.calls.delete_metadata_older_than(now - timedelta(days=metadata_retention_days))
            evidence_redacted = await self.evidence_repo.redact_payloads_older_than(now - timedelta(days=self.flags.evidence_payload_retention_days()))
            state_redacted = await self.state_repo.redact_payloads_older_than(now - timedelta(days=self.flags.state_payload_retention_days()))
            validation_redacted = await self.validation_repo.redact_payloads_older_than(now - timedelta(days=self.flags.validation_payload_retention_days()))
        except AttributeError:
            return {
                "tool_results_redacted": 0,
                "tool_metadata_deleted": 0,
                "evidence_payloads_redacted": 0,
                "state_payloads_redacted": 0,
                "validation_payloads_redacted": 0,
            }
        return {
            "tool_results_redacted": redacted,
            "tool_metadata_deleted": deleted,
            "evidence_payloads_redacted": evidence_redacted,
            "state_payloads_redacted": state_redacted,
            "validation_payloads_redacted": validation_redacted,
        }

    async def _dispatch_tool(self, *, tool_name: str, user_id: int, selector: Dict[str, Any], run, shared_state: Dict[str, Any]) -> Dict[str, Any]:
        workspace_hints = getattr(run, "workspace_hints_json", {}) or {}
        client_context = getattr(run, "client_context_json", {}) or {}

        if tool_name == "read_profile":
            return await self.profile_adapter.execute(user_id=user_id)
        if tool_name == "read_user_preferences":
            return await self.preferences_adapter.execute(user_id=user_id)
        if tool_name == "read_active_asset":
            resolved = await self.resolver.resolve_asset(user_id=user_id, selector=selector, workspace_hints=workspace_hints, client_context=client_context)
            shared_state.update(resolved)
            return await self.asset_adapter.execute(**resolved)
        if tool_name == "read_indicator_configuration":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.indicator_adapter.execute(user_id=user_id, asset=asset_state["asset"])
        if tool_name == "read_asset_scores":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.score_adapter.execute(user_id=user_id, asset=asset_state["asset"])
        if tool_name == "read_market_snapshot":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.market_adapter.execute(asset=asset_state["asset"])
        if tool_name == "read_macro_snapshot":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.macro_adapter.execute(user_id=user_id, asset=asset_state["asset"])
        if tool_name == "read_technical_snapshot":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.technical_adapter.execute(user_id=user_id, asset=asset_state["asset"])
        if tool_name == "read_active_setup":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            resolved = await self.resolver.resolve_setup(user_id=user_id, selector=selector, asset=asset_state["asset"])
            shared_state.update(resolved)
            return await self.setup_adapter.execute(**resolved)
        if tool_name == "read_linked_strategy":
            setup_state = await self._ensure_setup(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            resolved = await self.resolver.resolve_strategy(user_id=user_id, selector=selector, setup=setup_state["setup"])
            shared_state.update(resolved)
            return await self.strategy_adapter.execute(**resolved)
        if tool_name == "read_linked_bot":
            strategy_state = await self._ensure_strategy(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            resolved = await self.resolver.resolve_bot(user_id=user_id, selector=selector, strategy=strategy_state["strategy"])
            shared_state.update(resolved)
            return await self.bot_adapter.execute_linked_bot(**resolved)
        if tool_name == "read_bot_status":
            bot_state = await self._ensure_bot(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.bot_adapter.execute_status(bot=bot_state["bot"])
        if tool_name == "read_portfolio":
            return await self.portfolio_adapter.execute(user_id=user_id)
        if tool_name == "read_latest_report":
            asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
            return await self.report_adapter.execute(user_id=user_id, asset=asset_state["asset"], selector=selector)
        if tool_name == "read_review_history":
            return await self.review_adapter.execute()
        raise LookupError("tool_unknown")

    async def _ensure_asset(self, *, user_id: int, selector: Dict[str, Any], run, shared_state: Dict[str, Any]) -> Dict[str, Any]:
        if "asset" in shared_state:
            return {"asset": shared_state["asset"], "resolution_source": shared_state.get("resolution_source")}
        resolved = await self.resolver.resolve_asset(
            user_id=user_id,
            selector=selector,
            workspace_hints=getattr(run, "workspace_hints_json", {}) or {},
            client_context=getattr(run, "client_context_json", {}) or {},
        )
        shared_state.update(resolved)
        return resolved

    async def _ensure_setup(self, *, user_id: int, selector: Dict[str, Any], run, shared_state: Dict[str, Any]) -> Dict[str, Any]:
        if "setup" in shared_state:
            return {"setup": shared_state["setup"], "resolution_source": shared_state.get("resolution_source")}
        asset_state = await self._ensure_asset(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
        resolved = await self.resolver.resolve_setup(user_id=user_id, selector=selector, asset=asset_state["asset"])
        shared_state.update(resolved)
        return resolved

    async def _ensure_strategy(self, *, user_id: int, selector: Dict[str, Any], run, shared_state: Dict[str, Any]) -> Dict[str, Any]:
        if "strategy" in shared_state:
            return {"strategy": shared_state["strategy"], "resolution_source": shared_state.get("resolution_source")}
        setup_state = await self._ensure_setup(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
        resolved = await self.resolver.resolve_strategy(user_id=user_id, selector=selector, setup=setup_state["setup"])
        shared_state.update(resolved)
        return resolved

    async def _ensure_bot(self, *, user_id: int, selector: Dict[str, Any], run, shared_state: Dict[str, Any]) -> Dict[str, Any]:
        if "bot" in shared_state:
            return {"bot": shared_state["bot"], "resolution_source": shared_state.get("resolution_source")}
        strategy_state = await self._ensure_strategy(user_id=user_id, selector=selector, run=run, shared_state=shared_state)
        resolved = await self.resolver.resolve_bot(user_id=user_id, selector=selector, strategy=strategy_state["strategy"])
        shared_state.update(resolved)
        return resolved

    async def _ingest_evidence(self, *, run_id: str, user_id: int, trace_id: str, result: ToolExecutionResult) -> None:
        started = monotonic()
        await self._append_trace(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type="evidence_ingestion_started",
            payload_json={"run_id": run_id, "user_id": user_id, "tool_call_id": result.tool_call_id, "tool_name": result.tool_name},
        )
        try:
            envelope = ToolExecutionEnvelope(
                tool_name=result.tool_name,
                status=result.status,
                success=result.success,
                selector=result.selector,
                result=result.result,
                result_summary=result.result_summary,
                resolution_source=result.resolution_source,
                freshness_status=result.freshness_status,
                error_codes=result.error_codes,
                source=result.source,
                schema_name=result.schema_name,
                schema_version=result.schema_version,
                availability=result.availability,
                entity_type=result.entity_type,
                entity_id=result.entity_id,
                asset=result.asset,
                tool_call_id=result.tool_call_id,
            )
            artifact = await self.evidence.ingest_tool_result(
                user_id=user_id,
                run_id=run_id,
                trace_id=trace_id,
                tool_call_id=int(result.tool_call_id or 0),
                result=envelope,
            )
            result.artifact_id = artifact.artifact_id
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                event_type="evidence_ingestion_completed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "tool_call_id": result.tool_call_id,
                    "tool_name": result.tool_name,
                    "artifact_id": artifact.artifact_id,
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )
            increment_execution_safety_counter(f"finn_v2_evidence_artifacts_total:{result.tool_name}:{artifact.availability}")
        except Exception as exc:
            increment_execution_safety_counter(f"finn_v2_evidence_ingestion_failures_total:{result.tool_name}:{type(exc).__name__}")
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                event_type="evidence_ingestion_failed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "tool_call_id": result.tool_call_id,
                    "tool_name": result.tool_name,
                    "issue_codes": [str(exc)],
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )

    async def _run_state_pipeline(self, *, run_id: str, user_id: int) -> Tuple[Optional[object], Optional[object]]:
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            return None, None
        started = monotonic()
        await self._append_trace(
            run_id=run_id,
            user_id=user_id,
            trace_id=run.trace_id,
            event_type="state_assembly_started",
            payload_json={"run_id": run_id, "user_id": user_id},
        )
        try:
            snapshot = await self.snapshots.assemble_for_run(run_id=run_id, user_id=user_id)
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=run.trace_id,
                event_type="state_assembly_completed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )
        except Exception as exc:
            await self.session.rollback()
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=run.trace_id,
                event_type="state_assembly_failed",
                payload_json={"run_id": run_id, "user_id": user_id, "issue_codes": [str(exc)], "duration_ms": int((monotonic() - started) * 1000)},
            )
            return None, None

        validation_started = monotonic()
        await self._append_trace(
            run_id=run_id,
            user_id=user_id,
            trace_id=run.trace_id,
            event_type="evidence_validation_started",
            payload_json={"run_id": run_id, "user_id": user_id, "snapshot_id": snapshot.snapshot_id},
        )
        try:
            validation = await self.validator.validate_snapshot(snapshot)
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=run.trace_id,
                event_type="evidence_validation_completed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "validation_id": validation.validation_id,
                    "integrity_status": validation.integrity_status,
                    "domain_statuses": {domain.domain: domain.status for domain in validation.domains},
                    "duration_ms": int((monotonic() - validation_started) * 1000),
                },
            )
            if validation.integrity_status == "invalid":
                await self._append_trace(
                    run_id=run_id,
                    user_id=user_id,
                    trace_id=run.trace_id,
                    event_type="evidence_integrity_invalid",
                    payload_json={
                        "run_id": run_id,
                        "user_id": user_id,
                        "snapshot_id": snapshot.snapshot_id,
                        "validation_id": validation.validation_id,
                        "integrity_status": validation.integrity_status,
                        "issue_codes": [issue.code for issue in validation.issues],
                    },
                )
        except Exception as exc:
            logger.exception(
                "FINN V2 evidence validation failed",
                extra={
                    "trace_id": run.trace_id,
                    "user_id": user_id,
                    "conversation_id": getattr(run, "conversation_id", None),
                    "run_id": run_id,
                    "failure_stage": "evidence_validation",
                    "service": "FinnV2ToolExecutionService",
                    "method": "_run_state_pipeline",
                    "exception_class": exc.__class__.__name__,
                    "exception_message": str(exc),
                    "transaction_status": self._transaction_status(),
                    "snapshot_id": snapshot.snapshot_id,
                },
            )
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=run.trace_id,
                event_type="evidence_validation_failed",
                payload_json={"run_id": run_id, "user_id": user_id, "snapshot_id": snapshot.snapshot_id, "issue_codes": [str(exc)], "duration_ms": int((monotonic() - validation_started) * 1000)},
            )
            return snapshot, None
        return snapshot, validation

    async def _append_trace(self, *, run_id: str, user_id: int, trace_id: str, event_type: str, payload_json: Dict[str, Any]) -> None:
        await self.traces.append_event(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type=event_type,
            payload_json=payload_json,
        )

    def _transaction_status(self) -> Dict[str, Any]:
        transaction = self.session.get_transaction()
        return {
            "in_transaction": self.session.in_transaction(),
            "transaction_present": transaction is not None,
            "transaction_is_active": getattr(transaction, "is_active", None),
        }

    def _log_tool_transaction_exception(
        self,
        *,
        message: str,
        run_id: str,
        user_id: int,
        trace_id: Optional[str],
        tool_name: str,
        tool_call_id: Optional[int] = None,
        failure_stage: str,
        primary_exception: Optional[Exception] = None,
        cleanup_exception: Optional[Exception] = None,
    ) -> None:
        exc = cleanup_exception or primary_exception
        if exc is None:
            return
        logger.exception(
            message,
            extra={
                "trace_id": trace_id,
                "run_id": run_id,
                "user_id": user_id,
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "failure_stage": failure_stage,
                "service": "FinnV2ToolExecutionService",
                "method": "execute_tool",
                "primary_exception_class": primary_exception.__class__.__name__ if primary_exception else None,
                "primary_exception_message": str(primary_exception) if primary_exception else None,
                "cleanup_exception_class": cleanup_exception.__class__.__name__ if cleanup_exception else None,
                "cleanup_exception_message": str(cleanup_exception) if cleanup_exception else None,
                "transaction_status": self._transaction_status(),
            },
        )
