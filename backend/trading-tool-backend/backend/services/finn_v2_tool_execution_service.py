from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER, ToolExecutionResult
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_tool_call_repository import FinnV2ToolCallRepository
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
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
        started = monotonic()
        results: List[ToolExecutionResult] = []
        shared_state: Dict[str, Any] = {}
        for tool_name in FINN_V2_TOOL_ORDER:
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
                selector={},
                shared_state=shared_state,
                timeout_seconds=2.0,
            )
            results.append(result)
        return results

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
            tool_call = await self.calls.create(
                run_id=run.id,
                user_id=user_id,
                trace_id=run.trace_id,
                tool_name=tool_name,
                status="requested",
                selector_json=selector,
                error_codes_json=[],
            )
            await self.calls.update(tool_call, status="executing")

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
            )
        except asyncio.TimeoutError:
            result = ToolExecutionResult(tool_name=tool_name, status="failed", success=False, selector=selector, error_codes=["tool_timeout"])
        except LookupError as exc:
            result = ToolExecutionResult(tool_name=tool_name, status="failed", success=False, selector=selector, error_codes=[str(exc)])
        except Exception:
            logger.exception("FINN V2 tool execution failed", extra={"tool_name": tool_name, "run_id": run_id})
            result = ToolExecutionResult(tool_name=tool_name, status="failed", success=False, selector=selector, error_codes=["tool_internal_error"])

        if tool_call is not None:
            duration_ms = int((monotonic() - started) * 1000)
            await self.calls.update(
                tool_call,
                status=result.status,
                success=result.success,
                resolution_source=result.resolution_source,
                freshness_status=result.freshness_status,
                result_summary_json=result.result_summary,
                error_codes_json=result.error_codes,
                completed_at=datetime.now(timezone.utc),
                duration_ms=max(duration_ms, 0),
            )
        return result

    async def apply_retention(self) -> Dict[str, int]:
        if not hasattr(self.calls, "redact_results_older_than") or not hasattr(self.calls, "delete_metadata_older_than"):
            return {"tool_results_redacted": 0, "tool_metadata_deleted": 0}
        now = datetime.now(timezone.utc)
        result_retention_days = self.flags.tool_result_retention_days()
        metadata_retention_days = self.flags.tool_metadata_retention_days()
        try:
            redacted = await self.calls.redact_results_older_than(now - timedelta(days=result_retention_days))
            deleted = await self.calls.delete_metadata_older_than(now - timedelta(days=metadata_retention_days))
        except AttributeError:
            return {"tool_results_redacted": 0, "tool_metadata_deleted": 0}
        return {"tool_results_redacted": redacted, "tool_metadata_deleted": deleted}

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
