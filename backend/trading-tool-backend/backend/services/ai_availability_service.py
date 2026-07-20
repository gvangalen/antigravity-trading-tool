from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


AI_UNAVAILABLE_BUDGET = "ai_unavailable_budget"
_STATE_KEY = "tradamind:ai:openai:availability"
_EVENT_KEY_PREFIX = "tradamind:ai:openai:block-event"
_local_state: Dict[str, Any] = {}
_local_events: Dict[str, float] = {}
_local_call_slots: Dict[str, int] = {}


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _manual_budget_block() -> Optional[Dict[str, Any]]:
    if _env_enabled("OPENAI_CALLS_ENABLED", True):
        return None
    return {
        "reason": AI_UNAVAILABLE_BUDGET,
        "source": "environment",
        "blocked_at_epoch": None,
        "blocked_until_epoch": None,
    }


def get_ai_availability() -> Dict[str, Any]:
    manual = _manual_budget_block()
    if manual:
        return {
            "available": False,
            "configured": bool(os.getenv("OPENAI_API_KEY")),
            "mode": "deterministic_only",
            "retry_after_seconds": None,
            **manual,
        }

    state: Optional[Dict[str, Any]] = None
    source = "local"
    client = _redis_client()
    if client is not None:
        try:
            raw = client.get(_STATE_KEY)
            if raw:
                state = json.loads(raw)
                source = "redis"
        except Exception:
            state = None

    if state is None:
        state = dict(_local_state) if _local_state else None

    now = time.time()
    blocked_until = float((state or {}).get("blocked_until_epoch") or 0)
    if state and (not blocked_until or blocked_until > now):
        return {
            "available": False,
            "configured": bool(os.getenv("OPENAI_API_KEY")),
            "mode": "deterministic_only",
            "reason": state.get("reason") or AI_UNAVAILABLE_BUDGET,
            "source": source,
            "blocked_at_epoch": state.get("blocked_at_epoch"),
            "blocked_until_epoch": int(blocked_until) if blocked_until else None,
            "retry_after_seconds": int(max(0, blocked_until - now)) if blocked_until else None,
        }

    return {
        "available": bool(os.getenv("OPENAI_API_KEY")),
        "configured": bool(os.getenv("OPENAI_API_KEY")),
        "mode": "ai_enabled" if os.getenv("OPENAI_API_KEY") else "deterministic_only",
        "reason": None if os.getenv("OPENAI_API_KEY") else "ai_unavailable_configuration",
        "source": source,
        "blocked_at_epoch": None,
        "blocked_until_epoch": None,
        "retry_after_seconds": None,
    }


def mark_ai_unavailable(reason: str = AI_UNAVAILABLE_BUDGET, ttl_seconds: Optional[int] = None) -> None:
    ttl = max(60, int(ttl_seconds or os.getenv("OPENAI_QUOTA_COOLDOWN_SECONDS", "21600")))
    now = int(time.time())
    state = {
        "reason": reason,
        "blocked_at_epoch": now,
        "blocked_until_epoch": now + ttl,
    }
    _local_state.clear()
    _local_state.update(state)
    client = _redis_client()
    if client is not None:
        try:
            client.setex(_STATE_KEY, ttl, json.dumps(state))
        except Exception:
            pass


def should_emit_block_event(scope: str, reason: str) -> bool:
    """Emit at most one observability row per scope and window."""
    window = max(60, int(os.getenv("OPENAI_BLOCK_LOG_WINDOW_SECONDS", "3600")))
    normalized_scope = (scope or "unscoped").replace(" ", "_")[:160]
    key = f"{_EVENT_KEY_PREFIX}:{reason}:{normalized_scope}"
    client = _redis_client()
    if client is not None:
        try:
            return bool(client.set(key, "1", nx=True, ex=window))
        except Exception:
            pass

    now = time.time()
    expires_at = _local_events.get(key, 0)
    if expires_at > now:
        return False
    _local_events[key] = now + window
    return True


def acquire_ai_call_slot(scope: str, *, scheduled: bool = False) -> bool:
    """Bound model calls per user/agent scope before any paid request is sent."""
    window = max(60, int(os.getenv("OPENAI_CALL_WINDOW_SECONDS", "3600")))
    default_limit = "1" if scheduled else "20"
    limit = max(1, int(os.getenv("OPENAI_MAX_CALLS_PER_SCOPE_WINDOW", default_limit)))
    bucket = int(time.time()) // window
    normalized_scope = (scope or "unscoped").replace(" ", "_")[:180]
    key = f"tradamind:ai:openai:call-slot:{bucket}:{normalized_scope}"
    client = _redis_client()
    if client is not None:
        try:
            current = int(client.incr(key))
            if current == 1:
                client.expire(key, window + 60)
            return current <= limit
        except Exception:
            pass

    current = _local_call_slots.get(key, 0) + 1
    _local_call_slots[key] = current
    return current <= limit


def reset_ai_availability_for_tests() -> None:
    _local_state.clear()
    _local_events.clear()
    _local_call_slots.clear()
