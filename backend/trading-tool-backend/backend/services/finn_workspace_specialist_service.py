from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.services.ai_availability_service import get_ai_availability
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.services.bot_service import BotService
from backend.services.finn_specialist_service import (
    _cache_get_sync,
    _cache_set_sync,
    _canonical_hash,
    _language,
)
from backend.services.report_service import ReportService
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService
from backend.utils.openai_client import ask_gpt_json_async


PROMPT_VERSION = "workspace-context-v1"
_CACHE_PREFIX = "tradamind:finn:specialist:workspace"


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _valid_content(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    summary = str(payload.get("summary") or "").strip()
    next_step = str(payload.get("next_step") or "").strip()
    findings = payload.get("findings")
    risks = payload.get("risks")
    if not summary or not next_step or not isinstance(findings, list):
        return None
    return {
        "summary": summary[:900],
        "findings": [str(item)[:500] for item in findings[:5]],
        "risks": [str(item)[:500] for item in risks[:5]] if isinstance(risks, list) else [],
        "next_step": next_step[:900],
    }


class FinnWorkspaceSpecialistService:
    """Optional specialist interpretation for existing deterministic workspace facts."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _detail(
        self,
        *,
        user_id: int,
        subject_type: str,
        subject_id: int | None,
        symbol: str,
        period: str,
    ) -> dict[str, Any] | None:
        symbol = str(symbol or "BTC").upper()
        if subject_type == "setup":
            result = await SetupService(self.session).get_last_setup(user_id, subject_id)
            setup = result.get("setup") if isinstance(result, dict) else None
            if not setup:
                return None
            setup_symbol = str(setup.get("symbol") or symbol).upper()
            if setup_symbol != symbol:
                return None
            missing = [field for field in ("name", "symbol", "timeframe", "setup_type") if not setup.get(field)]
            if str(setup.get("setup_type") or "").lower() == "trade":
                score_fields = (
                    "min_market_score", "max_market_score", "min_macro_score",
                    "max_macro_score", "min_technical_score", "max_technical_score",
                )
                if not any(setup.get(field) is not None for field in score_fields):
                    missing.append("score_conditions")
            return self._snapshot("setup", setup.get("id"), setup.get("symbol") or symbol, "setups", setup.get("created_at"), setup, missing)

        if subject_type == "strategy":
            service = StrategyService(self.session)
            if subject_id:
                row = await service.repository.get_raw_strategy_with_setup(subject_id, user_id)
                strategy = service._format_strategy_row(row) if row else None
            else:
                strategy = await service.get_last_strategy(user_id)
            if not strategy:
                return None
            strategy_symbol = str(strategy.get("symbol") or symbol).upper()
            if strategy_symbol != symbol:
                return None
            missing = [field for field in ("name", "setup_id", "execution_mode", "base_amount") if not strategy.get(field)]
            if str(strategy.get("setup_type") or "").lower() == "trade":
                missing.extend(field for field in ("entry", "stop_loss", "targets") if not strategy.get(field))
            return self._snapshot("strategy", strategy.get("id"), strategy.get("symbol") or symbol, "strategies", strategy.get("created_at"), strategy, list(dict.fromkeys(missing)))

        if subject_type == "automation":
            service = BotService(self.session)
            configs = await service.get_bot_configs(user_id)
            selected = next((item for item in configs if int(item.get("id") or 0) == int(subject_id or 0)), None)
            if selected is None:
                selected = next((item for item in configs if str(item.get("symbol") or "").upper() == symbol), None)
            if selected and str(selected.get("symbol") or symbol).upper() != symbol:
                return None
            today = await service.get_bot_today(user_id, symbol, lean=True)
            daily_scores = await service.repository.get_daily_scores_row(user_id, date.today())
            decisions = list(today.get("decisions") or [])
            if selected:
                decisions = [item for item in decisions if int(item.get("bot_id") or 0) == int(selected.get("id") or 0)]
            facts = {
                "config": selected,
                "scores": daily_scores,
                "decisions": decisions[:5],
                "decision_count": len(decisions),
            }
            return self._snapshot(
                "automation",
                selected.get("id") if selected else None,
                (selected or {}).get("symbol") or symbol,
                "bot_configs+bot_decisions",
                today.get("date"),
                facts,
                [] if selected else ["bot_config"],
            )

        if subject_type == "reflection":
            table = {
                "day": "daily_reports",
                "week": "weekly_reports",
                "month": "monthly_reports",
                "quarter": "quarterly_reports",
            }[period]
            service = ReportService(ReportRepository(self.session))
            try:
                report = await service.get_latest_report(user_id, table, symbol=symbol)
            except ValueError:
                report = None
            if not report or report.get("_status") == "pending":
                return None
            facts = {
                key: report.get(key)
                for key in (
                    "report_date", "generated_at", "summary", "master_summary", "market_summary",
                    "strategy_summary", "bot_summary", "macro_score", "market_score", "technical_score",
                    "setup_score", "behavioral_analysis", "risk_flags", "strengths", "watchouts",
                    "next_best_action",
                )
                if report.get(key) is not None
            }
            snapshot = self._snapshot("reflection", report.get("id"), symbol, table, report.get("generated_at") or report.get("report_date"), facts, [])
            snapshot["period"] = period
            return snapshot
        return None

    @staticmethod
    def _snapshot(subject_type, subject_id, symbol, source, as_of, facts, missing):
        return {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "symbol": str(symbol or "BTC").upper(),
            "source": source,
            "as_of": as_of,
            "readiness": {"ready": not missing, "missing": missing},
            "facts": _json_safe(facts),
        }

    async def explain(
        self,
        *,
        user_id: int,
        subject_type: str,
        subject_id: int | None,
        symbol: str,
        timeframe: str,
        period: str,
        locale: str,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        trace_id = str(uuid.uuid4())
        detail = await self._detail(
            user_id=user_id,
            subject_type=subject_type,
            subject_id=subject_id,
            symbol=symbol,
            period=period,
        )
        if detail is None:
            return self._not_found(trace_id, subject_type, symbol, period)

        input_payload = {
            "prompt_version": PROMPT_VERSION,
            "user_id": user_id,
            "subject_type": subject_type,
            "symbol": detail["symbol"],
            "timeframe": str(timeframe or "1D").upper(),
            "period": period,
            "locale": str(locale or "nl").lower(),
            "detail": detail,
        }
        input_hash = _canonical_hash(input_payload)
        cache_key = f"{_CACHE_PREFIX}:{user_id}:{input_hash}"

        def response(*, status, source, ai_calls, reason=None, context=None, availability=None):
            availability = availability or get_ai_availability()
            payload = {
                "status": status,
                "source": source,
                "reason": reason,
                "trace_id": trace_id,
                "input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
                "detail": detail,
                "ai_availability": availability,
                "ai_calls": ai_calls,
                "trace": {
                    "schema_version": "1.0",
                    "trace_id": trace_id,
                    "routing": {"intent": f"{subject_type}_context", "flow": "specialist_on_demand"},
                    "context": {
                        "workspace": subject_type,
                        "asset": detail["symbol"],
                        "timeframe": str(timeframe or "1D").upper(),
                        "period": period,
                        "subject_id": detail.get("subject_id"),
                    },
                    "data": {"source": detail["source"], "as_of": detail.get("as_of"), "readiness": detail["readiness"]},
                    "memory": {"used": False, "layers": []},
                    "specialist": {"name": f"{subject_type}_specialist", "handler": "finn_workspace_specialist_service:explain"},
                    "decision": {
                        "response_source": source,
                        "selection_reason": reason or ("cached_input_hash" if source == "cache" else "explicit_user_request"),
                        "ai_available": bool(availability.get("available")),
                        "ai_mode": availability.get("mode"),
                        "ai_reason": availability.get("reason"),
                    },
                    "final": {"status": status, "ai_calls": ai_calls},
                },
            }
            if context is not None:
                payload["context"] = context
            return payload

        cached = await asyncio.to_thread(_cache_get_sync, cache_key)
        if cached:
            return response(status="available", source="cache", context=cached, ai_calls=0)
        availability = get_ai_availability()
        if not availability.get("available"):
            return response(status="unavailable", source="deterministic", reason=availability.get("reason") or "ai_unavailable", availability=availability, ai_calls=0)

        system_role = (
            "You are an internal FINN specialist. Interpret only the supplied platform facts. "
            "Do not invent prices, statuses, rules, orders, performance or missing fields. "
            f"Respond in {_language(locale)}."
        )
        prompt = (
            f"Review this {subject_type} snapshot. Return concise JSON with summary, findings (array), "
            f"risks (array), and next_step. Authoritative input:\n{json.dumps(input_payload, ensure_ascii=False, default=str)}"
        )
        schema = {"summary": "string", "findings": ["string"], "risks": ["string"], "next_step": "string"}
        with ai_usage_context(
            user_id=user_id,
            user_email=user_email,
            symbol=detail["symbol"],
            timeframe=str(timeframe or "1D").upper(),
            trace_id=trace_id,
            purpose=f"{subject_type}_context",
            run_kind="interactive",
            request_source="live_user",
            entry_point="finn_workspace_specialist_service:explain",
            selected_flow=f"{subject_type}_context",
            response_handler=f"{subject_type}_specialist",
        ):
            generated = await ask_gpt_json_async(
                prompt=prompt,
                system_role=system_role,
                schema=schema,
                retries=1,
                client_max_retries=0,
                max_tokens=600,
            )
        content = _valid_content(generated)
        if content is None:
            return response(
                status="unavailable",
                source="deterministic",
                reason=str(generated.get("error") or "invalid_specialist_response") if isinstance(generated, dict) else "invalid_specialist_response",
                ai_calls=1,
            )
        await asyncio.to_thread(_cache_set_sync, cache_key, content)
        return response(status="available", source="openai", context=content, ai_calls=1)

    @staticmethod
    def _not_found(trace_id: str, subject_type: str, symbol: str, period: str):
        return {
            "status": "not_found",
            "reason": f"{subject_type}_not_found",
            "trace_id": trace_id,
            "ai_calls": 0,
            "trace": {
                "schema_version": "1.0",
                "routing": {"intent": f"{subject_type}_context", "flow": "not_found"},
                "context": {"workspace": subject_type, "asset": str(symbol or "BTC").upper(), "period": period},
                "decision": {"response_source": "deterministic", "selection_reason": "subject_not_found"},
            },
        }
