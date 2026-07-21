from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.ai_availability_service import get_ai_availability
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.services.workspace_data_service import WorkspaceDataService
from backend.utils.openai_client import ask_gpt_json_async


PROMPT_VERSION = "indicator-context-v1"
CACHE_TTL_SECONDS = max(300, int(os.getenv("FINN_SPECIALIST_CACHE_TTL_SECONDS", "21600")))
_CACHE_PREFIX = "tradamind:finn:specialist:indicator"
_local_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _redis_client():
    try:
        import redis

        return redis.from_url(
            os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
    except Exception:
        return None


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cache_get_sync(key: str) -> dict[str, Any] | None:
    client = _redis_client()
    if client is not None:
        try:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    cached = _local_cache.get(key)
    if cached and cached[0] > time.time():
        return dict(cached[1])
    _local_cache.pop(key, None)
    return None


def _cache_set_sync(key: str, value: dict[str, Any]) -> None:
    client = _redis_client()
    if client is not None:
        try:
            client.setex(key, CACHE_TTL_SECONDS, json.dumps(value, default=str))
            return
        except Exception:
            pass
    _local_cache[key] = (time.time() + CACHE_TTL_SECONDS, dict(value))


def _language(locale: str) -> str:
    normalized = str(locale or "nl").lower()
    if normalized.startswith("de"):
        return "German"
    if normalized.startswith("en"):
        return "English"
    return "Dutch"


def _stable_freshness(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "source": payload.get("source"),
        "as_of": payload.get("as_of"),
        "stale": payload.get("stale"),
        "status": payload.get("status"),
    }


def _stable_indicator(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    payload["freshness"] = _stable_freshness(payload.get("freshness"))
    return payload


def _valid_content(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    summary = str(payload.get("summary") or "").strip()
    why_it_counts = str(payload.get("why_it_counts") or "").strip()
    confirmation = str(payload.get("confirmation") or "").strip()
    conflicts = payload.get("conflicts")
    if not summary or not why_it_counts or not confirmation:
        return None
    return {
        "summary": summary[:900],
        "why_it_counts": why_it_counts[:900],
        "confirmation": confirmation[:900],
        "conflicts": [str(item)[:500] for item in conflicts[:5]] if isinstance(conflicts, list) else [],
    }


class FinnSpecialistService:
    """Runs optional, user-requested specialist synthesis on authoritative workspace data."""

    def __init__(self, session: AsyncSession):
        self.workspace = WorkspaceDataService(session)

    async def explain_indicator(
        self,
        *,
        user_id: int,
        symbol: str,
        category: str,
        indicator: str,
        period: str,
        timeframe: str,
        locale: str,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        trace_id = str(uuid.uuid4())
        detail = await self.workspace.get_indicator_detail(
            user_id,
            symbol,
            category,
            period,
            indicator,
        )
        if detail is None:
            return {
                "status": "not_found",
                "reason": "indicator_not_found_for_asset_period",
                "trace_id": trace_id,
                "ai_calls": 0,
                "trace": {
                    "schema_version": "1.0",
                    "routing": {"intent": "indicator_context", "flow": "not_found"},
                    "context": {"asset": str(symbol or "BTC").upper(), "timeframe": timeframe},
                    "decision": {"response_source": "deterministic", "selection_reason": "indicator_not_found"},
                },
            }

        input_payload = {
            "prompt_version": PROMPT_VERSION,
            "user_id": user_id,
            "symbol": detail["symbol"],
            "category": detail["category"],
            "period": detail["period"],
            "timeframe": str(timeframe or "1D").upper(),
            "locale": str(locale or "nl").lower(),
            "indicator": _stable_indicator(detail["indicator"]),
            "category_score": detail["category_score"],
            "category_freshness": _stable_freshness(detail["category_freshness"]),
        }
        input_hash = _canonical_hash(input_payload)
        cache_key = f"{_CACHE_PREFIX}:{user_id}:{input_hash}"

        def response(
            *,
            status: str,
            source: str,
            ai_calls: int,
            reason: str | None = None,
            context: dict[str, Any] | None = None,
            availability: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
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
                    "routing": {"intent": "indicator_context", "flow": "specialist_on_demand"},
                    "context": {
                        "workspace": "analysis",
                        "asset": detail["symbol"],
                        "timeframe": str(timeframe or "1D").upper(),
                        "period": detail["period"],
                        "category": detail["category"],
                        "indicator": detail["indicator"].get("indicator_key"),
                    },
                    "data": {
                        "source": detail["indicator"].get("source"),
                        "as_of": detail["indicator"].get("freshness", {}).get("as_of"),
                        "freshness": detail["indicator"].get("freshness"),
                        "score_contribution": detail["indicator"].get("score_contribution"),
                    },
                    "memory": {"used": False, "layers": []},
                    "specialist": {
                        "name": f"{detail['category']}_specialist",
                        "handler": "finn_specialist_service:indicator_context",
                    },
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
            return response(
                status="unavailable",
                source="deterministic",
                reason=availability.get("reason") or "ai_unavailable",
                availability=availability,
                ai_calls=0,
            )

        category_focus = {
            "market": "Focus on price participation, volume, liquidity, volatility and market structure.",
            "macro": "Focus on rates, dollar conditions, flows, sentiment and cross-asset pressure.",
            "technical": "Focus on trend, momentum, volatility, confirmation and invalidation evidence.",
        }[category]
        system_role = (
            "You are an internal FINN market-data specialist. Explain only the supplied evidence. "
            "Never invent prices, history, causality, confidence, or advice. Explicitly mention stale or "
            "insufficient data. Keep the explanation educational and concise, not a trade recommendation. "
            + category_focus
        )
        prompt = (
            f"Respond in {_language(locale)}. Analyse this indicator in its current asset context.\n"
            f"Authoritative input:\n{json.dumps(input_payload, ensure_ascii=False, default=str)}\n"
            "Return JSON with: summary (current meaning), why_it_counts (score contribution), "
            "confirmation (what measurable evidence to monitor next), conflicts (array of conflicts or caveats)."
        )
        schema = {
            "summary": "string",
            "why_it_counts": "string",
            "confirmation": "string",
            "conflicts": ["string"],
        }
        with ai_usage_context(
            user_id=user_id,
            user_email=user_email,
            symbol=detail["symbol"],
            timeframe=str(timeframe or "1D").upper(),
            trace_id=trace_id,
            purpose="indicator_context",
            run_kind="interactive",
            request_source="live_user",
            entry_point="finn_specialist_service:indicator_context",
            selected_flow="indicator_context",
            response_handler=f"{category}_specialist",
        ):
            generated = await ask_gpt_json_async(
                prompt=prompt,
                system_role=system_role,
                schema=schema,
                retries=1,
                client_max_retries=0,
                max_tokens=500,
            )
        content = _valid_content(generated)
        if content is None:
            return response(
                status="unavailable",
                source="deterministic",
                reason=str(generated.get("error") or "invalid_specialist_response") if isinstance(generated, dict) else "invalid_specialist_response",
                ai_calls=1,
            )

        content["generated_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(_cache_set_sync, cache_key, content)
        return response(status="available", source="openai", context=content, ai_calls=1)
