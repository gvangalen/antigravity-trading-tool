from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.services.ai_availability_service import get_ai_availability


TRACE_SCHEMA_VERSION = "1.0"
MEMORY_FLOWS = {"behavioral_memory", "outcome_memory", "personal_coach"}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compact(values: Iterable[Optional[str]]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _find_freshness(value: Any, path: str = "response") -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        freshness = value.get("freshness")
        if isinstance(freshness, dict):
            results.append({
                "path": path,
                "status": freshness.get("status"),
                "source_timestamp": freshness.get("source_timestamp") or freshness.get("as_of"),
                "age_seconds": freshness.get("age_seconds"),
                "age_minutes": freshness.get("age_minutes"),
            })
        for key, child in value.items():
            if key != "freshness":
                results.extend(_find_freshness(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            results.extend(_find_freshness(child, f"{path}[{index}]"))
    return results[:20]


def _find_source_timestamps(value: Any, path: str = "context") -> List[Dict[str, Any]]:
    timestamps: List[Dict[str, Any]] = []
    timestamp_keys = {"as_of", "source_timestamp", "updated_at", "generated_at", "created_at"}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in timestamp_keys and child not in (None, ""):
                timestamps.append({"path": child_path, "as_of": str(child)})
            elif isinstance(child, (dict, list)):
                timestamps.extend(_find_source_timestamps(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            timestamps.extend(_find_source_timestamps(child, f"{path}[{index}]"))
    return timestamps[:20]


def _memory_layers(flow: str, analysis: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    layers: List[Optional[str]] = []
    if flow in MEMORY_FLOWS:
        layers.append(flow)
    searchable = {**state, **analysis}
    keys = {
        "behavioral_memory": "behavioral_memory",
        "outcome_memory": "outcome_memory",
        "memory_v2": "memory_v2",
        "regime_memory": "regime_memory",
        "conversation_memory": "conversation_state",
        "recent_context_entities": "conversation_state",
        "last_context_entity": "conversation_state",
        "trader_profile": "trader_profile",
        "trader_profile_summary": "trader_profile",
    }
    for key, label in keys.items():
        if searchable.get(key) not in (None, "", [], {}):
            layers.append(label)
    return _compact(layers)


def _data_sources(
    *,
    response_source: str,
    flow: str,
    analysis: Dict[str, Any],
    freshness: List[Dict[str, Any]],
    source_timestamps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    if response_source in {"database", "memory"}:
        sources.append({"kind": response_source, "name": flow or "finn_context"})
    for key in ("source", "data_source", "response_source"):
        value = analysis.get(key)
        if isinstance(value, str) and value:
            sources.append({"kind": "declared", "name": value})
    for item in freshness:
        sources.append({
            "kind": "freshness",
            "name": item.get("path"),
            "status": item.get("status"),
            "as_of": item.get("source_timestamp"),
        })
    for item in source_timestamps:
        sources.append({
            "kind": "timestamped_context",
            "name": item.get("path"),
            "as_of": item.get("as_of"),
        })
    unique: Dict[str, Dict[str, Any]] = {}
    for item in sources:
        key = f"{item.get('kind')}:{item.get('name')}:{item.get('as_of')}"
        unique[key] = item
    return list(unique.values())[:20]


def _specialist_contributors(analysis: Dict[str, Any]) -> List[str]:
    contributors: List[Optional[str]] = [analysis.get("specialist"), analysis.get("agent")]
    for key in ("specialists", "agents", "contributors", "agent_sections"):
        value = analysis.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    contributors.append(item)
                elif isinstance(item, dict):
                    contributors.append(item.get("name") or item.get("agent") or item.get("specialist"))
        elif isinstance(value, dict):
            contributors.extend(str(item) for item in value.keys())
    return _compact(contributors)


def _selection_reason(response_source: str, flow: str, ai: Dict[str, Any]) -> str:
    if response_source == "openai":
        return "openai_selected"
    if response_source == "memory":
        return "memory_flow_selected"
    if response_source == "database":
        return "stored_data_flow_selected"
    if response_source == "deterministic":
        return "deterministic_flow_selected"
    if not ai.get("available"):
        return str(ai.get("reason") or "ai_unavailable")
    return f"{flow or 'unknown'}_fallback_selected"


def build_finn_response_trace(
    *,
    trace_id: str,
    response: Dict[str, Any],
    context: Optional[Dict[str, Any]],
    route_source: str,
    response_source: str,
    response_handler: str,
    latency_ms: Optional[float] = None,
    legacy_rescue_reason: Optional[str] = None,
) -> Dict[str, Any]:
    context = _dict(context)
    state = _dict(response.get("state"))
    analysis = _dict(response.get("analysis"))
    reasoning = _dict(response.get("reasoning"))
    flow = str(response.get("flow") or state.get("current_flow") or "unknown")
    selected_asset = (
        state.get("asset")
        or _dict(response.get("draft")).get("asset")
        or context.get("symbol")
        or context.get("asset")
    )
    timeframe = state.get("timeframe") or context.get("timeframe") or context.get("setup_timeframe")
    freshness = _find_freshness({"analysis": analysis, "state": state, "context": context})
    source_timestamps = _find_source_timestamps({"analysis": analysis, "state": state, "context": context})
    memory_layers = _memory_layers(flow, analysis, state)
    ai = get_ai_availability()
    fallback_reason = (
        legacy_rescue_reason
        or analysis.get("fallback_reason")
        or analysis.get("draft_rejected_reason")
        or (ai.get("reason") if response_source == "fallback" and not ai.get("available") else None)
    )
    specialists = _specialist_contributors(analysis)

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "routing": {
            "intent": response.get("intent"),
            "intent_confidence": reasoning.get("confidence_score"),
            "flow": flow,
            "route": route_source,
        },
        "context": {
            "workspace": context.get("page_type") or context.get("page"),
            "asset": selected_asset,
            "timeframe": timeframe,
            "entity": analysis.get("context_entity_resolution") or analysis.get("context_confidence"),
        },
        "data": {
            "sources": _data_sources(
                response_source=response_source,
                flow=flow,
                analysis=analysis,
                freshness=freshness,
                source_timestamps=source_timestamps,
            ),
            "freshness": freshness,
        },
        "memory": {
            "used": bool(memory_layers),
            "layers": memory_layers,
        },
        "specialist": {
            "name": specialists[0] if specialists else None,
            "contributors": specialists,
            "handler": response_handler,
        },
        "decision": {
            "response_source": response_source,
            "ai_available": bool(ai.get("available")),
            "ai_mode": ai.get("mode"),
            "ai_reason": ai.get("reason"),
            "selection_reason": _selection_reason(response_source, flow, ai),
        },
        "fallback": {
            "used": response_source == "fallback" or bool(fallback_reason),
            "reason": fallback_reason,
        },
        "response": {
            "handler": response_handler,
            "type": (
                "actionable" if response.get("actions") else
                "draft" if response.get("draft") else
                "stateful" if response.get("state") else
                "text"
            ),
            "latency_ms": round(float(latency_ms), 2) if latency_ms is not None else None,
        },
    }
