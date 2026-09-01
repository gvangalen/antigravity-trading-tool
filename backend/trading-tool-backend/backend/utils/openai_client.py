import os
import json
import logging
import time
import re
import asyncio
import inspect
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from backend.services.ai_usage_observability_service import (
    elapsed_ms,
    get_ai_usage_context,
    get_app_env,
    infer_entry_point,
    log_ai_usage_sync,
    log_openai_quota_skip_from_context,
    log_openai_usage_from_context,
    start_timer,
)
from backend.services.ai_availability_service import (
    AI_UNAVAILABLE_BUDGET,
    acquire_ai_call_slot,
    clear_ai_unavailable,
    get_ai_availability,
    mark_ai_unavailable,
    should_emit_block_event,
)

# ============================================================
# ⚙️ Setup
# ============================================================
# Probeer .env te vinden in CWD of in /backend map
env_path = Path(".") / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent / ".env"

load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not api_key:
    logger.warning("⚠️ OPENAI_API_KEY ontbreekt in de omgeving. AI functionaliteit is beperkt.")

client = None
if api_key:
    try:
        client = OpenAI(api_key=api_key)
        logger.info(f"🤖 OpenAI Client geïnitialiseerd (Model: {model})")
    except Exception as e:
        logger.error(f"❌ Fout bij initialiseren OpenAI Client: {e}")

# ============================================================
# 🔥 AI DEFAULTS
# ============================================================
TEXT_TEMP = float(os.getenv("OPENAI_TEXT_TEMP", "0.4"))
JSON_TEMP = float(os.getenv("OPENAI_JSON_TEMP", "0.2"))
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "500"))
QUOTA_COOLDOWN_SECONDS = int(os.getenv("OPENAI_QUOTA_COOLDOWN_SECONDS", "3600"))

_openai_runtime_state: Dict[str, Any] = {
    "quota_exhausted_until": 0.0,
    "quota_failures": 0,
    "blocked_calls": 0,
    "text_calls": 0,
    "json_calls": 0,
    "last_error": None,
    "last_error_at": None,
}
_process_started_at_epoch = int(time.time())


class StructuredOutputContractError(ValueError):
    """Raised when an internal caller violates the structured-output boundary."""


@dataclass(frozen=True)
class StructuredOutputSpec:
    """Raw JSON Schema plus the only provider wrapper metadata we allow."""

    name: str
    schema: Dict[str, Any]
    strict: bool = True


def _validate_structured_output_spec(spec: StructuredOutputSpec) -> None:
    if not isinstance(spec, StructuredOutputSpec):
        raise StructuredOutputContractError("structured_output_spec_required")
    if not isinstance(spec.name, str) or not spec.name.strip():
        raise StructuredOutputContractError("structured_output_name_invalid")
    if not isinstance(spec.strict, bool):
        raise StructuredOutputContractError("structured_output_strict_invalid")
    if not isinstance(spec.schema, dict):
        raise StructuredOutputContractError("structured_output_schema_not_object")
    if "schema" in spec.schema and {"name", "strict"}.intersection(spec.schema):
        raise StructuredOutputContractError("structured_output_provider_wrapper_rejected")
    if "schema" in spec.schema and isinstance(spec.schema.get("schema"), dict):
        raise StructuredOutputContractError("structured_output_double_schema_nesting")
    if not isinstance(spec.schema.get("type"), str) or not spec.schema["type"]:
        raise StructuredOutputContractError("structured_output_root_type_required")


def build_structured_response_request(
    *,
    model_name: str,
    prompt: str,
    system_role: str,
    output_spec: StructuredOutputSpec,
    max_output_tokens: int,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Serialize the one canonical Responses API JSON-schema payload."""
    _validate_structured_output_spec(output_spec)
    request: Dict[str, Any] = {
        "model": model_name,
        "input": [{"role": "system", "content": system_role}, {"role": "user", "content": prompt}],
        "text": {"format": {"type": "json_schema", "name": output_spec.name, "schema": output_spec.schema, "strict": output_spec.strict}},
        "max_output_tokens": max_output_tokens,
    }
    if timeout_seconds is not None:
        request["timeout"] = timeout_seconds
    return request


def _quota_breaker_active() -> bool:
    return float(_openai_runtime_state.get("quota_exhausted_until") or 0.0) > time.time()


def _mark_runtime_error(message: str) -> None:
    _openai_runtime_state["last_error"] = str(message)
    _openai_runtime_state["last_error_at"] = int(time.time())


def _mark_quota_exhausted() -> None:
    _openai_runtime_state["quota_failures"] = int(_openai_runtime_state.get("quota_failures") or 0) + 1
    _openai_runtime_state["quota_exhausted_until"] = time.time() + max(60, QUOTA_COOLDOWN_SECONDS)
    _mark_runtime_error("insufficient_quota")
    mark_ai_unavailable(AI_UNAVAILABLE_BUDGET, QUOTA_COOLDOWN_SECONDS)


def clear_openai_runtime_breaker() -> None:
    _openai_runtime_state["quota_exhausted_until"] = 0.0
    _openai_runtime_state["last_error"] = None
    _openai_runtime_state["last_error_at"] = None
    clear_ai_unavailable()


def _api_key_fingerprint() -> Optional[str]:
    if not api_key:
        return None
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


def _api_key_project_hint() -> Optional[str]:
    if not api_key:
        return None
    return "project_scoped" if api_key.startswith("sk-proj-") else "legacy_or_unknown_scope"


def _read_status_code(value: Any) -> Optional[int]:
    candidate = getattr(value, "status_code", None)
    if isinstance(candidate, int):
        return candidate
    response = getattr(value, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _read_request_id(value: Any) -> Optional[str]:
    request_id = getattr(value, "request_id", None) or getattr(value, "_request_id", None)
    if request_id:
        return str(request_id)
    headers = getattr(value, "headers", None)
    if headers:
        header_value = headers.get("x-request-id") or headers.get("X-Request-Id")
        if header_value:
            return str(header_value)
    response = getattr(value, "response", None)
    response_headers = getattr(response, "headers", None)
    if response_headers:
        header_value = response_headers.get("x-request-id") or response_headers.get("X-Request-Id")
        if header_value:
            return str(header_value)
    return None


def _retry_after_seconds(value: Any) -> Optional[float]:
    """Extract Retry-After from a provider exception for caller-controlled backoff."""
    response = getattr(value, "response", None)
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _is_rate_limited_exception(value: Any) -> bool:
    return _read_status_code(value) == 429 or "rate limit" in str(value).casefold()


def probe_openai_runtime(*, clear_breaker_on_success: bool = True, caller: str = "backend") -> Dict[str, Any]:
    availability_before = get_ai_availability()
    started = time.perf_counter()
    result: Dict[str, Any] = {
        "caller": caller,
        "configured": bool(api_key),
        "model": model,
        "api_key_fingerprint": _api_key_fingerprint(),
        "api_key_scope": _api_key_project_hint(),
        "availability_before": availability_before,
        "quota_breaker_before": _quota_breaker_active(),
    }

    if not client or not api_key:
        result.update(
            {
                "ok": False,
                "error": "ai_unavailable_configuration",
                "http_status": None,
                "request_id": None,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "availability_after": get_ai_availability(),
                "quota_breaker_after": _quota_breaker_active(),
            }
        )
        return result

    if str(availability_before.get("source")) == "environment":
        result.update(
            {
                "ok": False,
                "error": str(availability_before.get("reason") or AI_UNAVAILABLE_BUDGET),
                "http_status": None,
                "request_id": None,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "availability_after": availability_before,
                "quota_breaker_after": _quota_breaker_active(),
            }
        )
        return result

    try:
        active_client = client.with_options(max_retries=0)
        raw_response = active_client.chat.completions.with_raw_response.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return the single token ok."},
                {"role": "user", "content": "ok"},
            ],
            temperature=0,
            max_tokens=1,
        )
        parsed = raw_response.parse()
        if clear_breaker_on_success:
            clear_openai_runtime_breaker()
        result.update(
            {
                "ok": True,
                "http_status": _read_status_code(raw_response) or 200,
                "request_id": _read_request_id(raw_response) or _read_request_id(parsed),
                "response_model": str(getattr(parsed, "model", None) or model),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "availability_after": get_ai_availability(),
                "quota_breaker_after": _quota_breaker_active(),
                "breaker_cleared": clear_breaker_on_success,
            }
        )
        return result
    except Exception as exc:
        message = str(exc)
        insufficient_quota = "insufficient_quota" in message
        if insufficient_quota:
            _mark_quota_exhausted()
        else:
            _mark_runtime_error(message)
        result.update(
            {
                "ok": False,
                "error": message,
                "http_status": _read_status_code(exc),
                "request_id": _read_request_id(exc),
                "insufficient_quota": insufficient_quota,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "availability_after": get_ai_availability(),
                "quota_breaker_after": _quota_breaker_active(),
            }
        )
        return result


def get_openai_runtime_status() -> Dict[str, Any]:
    exhausted_until = float(_openai_runtime_state.get("quota_exhausted_until") or 0.0)
    breaker_active = exhausted_until > time.time()
    remaining = int(max(0, exhausted_until - time.time())) if breaker_active else 0
    availability = get_ai_availability()
    return {
        "configured": bool(api_key),
        "model": model,
        "quota_breaker_active": breaker_active,
        "quota_exhausted_until_epoch": int(exhausted_until) if exhausted_until else None,
        "quota_cooldown_remaining_seconds": remaining,
        "quota_failures": int(_openai_runtime_state.get("quota_failures") or 0),
        "blocked_calls": int(_openai_runtime_state.get("blocked_calls") or 0),
        "text_calls": int(_openai_runtime_state.get("text_calls") or 0),
        "json_calls": int(_openai_runtime_state.get("json_calls") or 0),
        "last_error": _openai_runtime_state.get("last_error"),
        "last_error_at_epoch": _openai_runtime_state.get("last_error_at"),
        "api_key_fingerprint": _api_key_fingerprint(),
        "api_key_scope": _api_key_project_hint(),
        "availability": availability,
    }

# ============================================================
# 🧰 JSON parsing helper
# ============================================================
def _strip_fences(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"^\s*```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()

def sanitize_json_output(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}
    text = _strip_fences(raw_text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                candidate = m.group(0).replace("True", "true").replace("False", "false")
                return json.loads(candidate)
            except:
                pass
    return {}


def _infer_unscoped_entry_point() -> str:
    try:
        for frame_info in inspect.stack()[2:]:
            frame_path = Path(frame_info.filename)
            if frame_path == Path(__file__):
                continue
            module_name = frame_path.stem
            function_name = frame_info.function or "unknown"
            return f"{module_name}:{function_name}"
    except Exception:
        pass
    return "openai_client:unknown"


def _compact_stacktrace(limit: int = 8) -> list[str]:
    frames: list[str] = []
    try:
        for frame_info in inspect.stack()[2:]:
            frame_path = Path(frame_info.filename)
            if frame_path == Path(__file__):
                continue
            frames.append(f"{frame_path.stem}:{frame_info.function}")
            if len(frames) >= limit:
                break
    except Exception:
        return []
    return frames


def _quota_block_debug_payload(*, call_kind: str) -> Dict[str, Any]:
    context = dict(get_ai_usage_context() or {})
    caller_tag = (
        context.get("caller_tag")
        or context.get("entry_point")
        or _infer_unscoped_entry_point()
    )
    payload: Dict[str, Any] = {
        "call_kind": call_kind,
        "model": model,
        "caller_tag": caller_tag,
        "trace_id": context.get("trace_id"),
        "user_id": context.get("user_id"),
        "http_route": context.get("http_route"),
        "page_route": context.get("page_route") or context.get("page"),
        "page_type": context.get("page_type"),
        "selected_flow": context.get("selected_flow"),
        "response_source": context.get("response_source"),
        "response_handler": context.get("response_handler"),
        "job_name": context.get("job_name"),
        "job_id": context.get("job_id"),
        "request_source": context.get("request_source"),
        "run_kind": context.get("run_kind"),
        "purpose": context.get("purpose"),
        "process": os.getpid(),
        "stacktrace": _compact_stacktrace(),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _log_openai_usage(
    *,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    response_time_ms: int,
    status: str = "full_ai",
    rejected_reason: Optional[str] = None,
) -> None:
    context = get_ai_usage_context()
    if context:
        try:
            log_openai_usage_from_context(
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                response_time_ms=response_time_ms,
                status=status,
                rejected_reason=rejected_reason,
            )
        except Exception as exc:
            # Usage telemetry is observability, not part of the provider
            # contract. A lagging analytics schema must never turn a valid
            # structured response into an unavailable FINN result.
            logger.warning(
                "OpenAI usage telemetry failed after provider success",
                extra={"telemetry_error_class": type(exc).__name__},
            )
        return

    cost = 0.0
    try:
        from backend.utils.ai_cost_calculator import calculate_cost

        cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
    except Exception:
        cost = 0.0

    entry_point = _infer_unscoped_entry_point()
    try:
        log_ai_usage_sync(
            user_id=None,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            purpose="unscoped_openai_call",
            status=status,
            response_time_ms=response_time_ms,
            estimated_cost_if_full=cost,
            rejected_reason=rejected_reason,
            symbol="GLOBAL",
            trace_id=None,
            completion_status="success",
            request_source="system",
            app_env=get_app_env(),
            run_kind="interactive",
            entry_point=entry_point or infer_entry_point(purpose="unscoped_openai_call", run_kind="interactive"),
            user_email_snapshot=None,
        )
    except Exception as exc:
        logger.warning(
            "OpenAI usage telemetry failed after provider success",
            extra={"telemetry_error_class": type(exc).__name__},
        )


def _log_openai_quota_skip(reason: str = "insufficient_quota") -> None:
    context = get_ai_usage_context()
    scope = str(
        (context or {}).get("entry_point")
        or (context or {}).get("purpose")
        or _infer_unscoped_entry_point()
    )
    if not should_emit_block_event(scope, reason):
        return
    if context:
        log_openai_quota_skip_from_context(status="ai_unavailable", rejected_reason=reason)
        return

    entry_point = _infer_unscoped_entry_point()
    log_ai_usage_sync(
        user_id=None,
        model=model,
        prompt_tokens=0,
        completion_tokens=0,
        cost=0.0,
        purpose="unscoped_openai_call",
        status="ai_unavailable",
        response_time_ms=0,
        estimated_cost_if_full=0.0,
        rejected_reason=reason,
        symbol="GLOBAL",
        trace_id=None,
        completion_status="ai_unavailable",
        request_source="system",
        app_env=get_app_env(),
        run_kind="interactive",
        entry_point=entry_point or infer_entry_point(purpose="unscoped_openai_call", run_kind="interactive"),
        user_email_snapshot=None,
    )


def _log_quota_block_warning(call_kind: str) -> None:
    try:
        payload = _quota_block_debug_payload(call_kind=call_kind)
        logger.warning(
            "⛔ GPT %s Call overgeslagen: quota breaker actief | %s",
            call_kind,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    except Exception:
        logger.warning("⛔ GPT %s Call overgeslagen: quota breaker actief", call_kind)


def _call_scope() -> tuple[str, bool]:
    context = dict(get_ai_usage_context() or {})
    scope = ":".join(
        str(value)
        for value in (
            context.get("entry_point") or context.get("purpose") or _infer_unscoped_entry_point(),
            context.get("user_id") or "system",
            context.get("symbol") or "GLOBAL",
        )
    )
    return scope, context.get("run_kind") == "scheduled"


def _rate_limit_allows_call() -> bool:
    context = dict(get_ai_usage_context() or {})
    scope, scheduled = _call_scope()
    limit_override = None
    if context.get("entry_point") == "finn_v2_selector":
        # Every interactive turn must pass the model-first selector before a
        # contract can choose tools or a deterministic response. Keep that
        # small paid call bounded separately from broader reasoning calls so
        # a busy conversation cannot strand later user turns in UNAVAILABLE.
        generic_limit = max(1, int(os.getenv("OPENAI_MAX_CALLS_PER_SCOPE_WINDOW", "20")))
        limit_override = max(
            generic_limit,
            int(os.getenv("OPENAI_MAX_SELECTOR_CALLS_PER_SCOPE_WINDOW", "60")),
        )
    allowed = acquire_ai_call_slot(scope, scheduled=scheduled, limit_override=limit_override)
    if not allowed:
        _log_openai_quota_skip("ai_rate_limited")
    return allowed

# ============================================================
# ✅ GPT JSON CALL
# ============================================================
def ask_gpt_json(
    *,
    prompt: str,
    system_role: str,
    schema: Optional[Dict[str, Any]] = None,
    retries: int = 2,
    max_tokens: Optional[int] = None,
    client_max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """Genereert een gestructureerde JSON response."""
    
    availability = get_ai_availability()
    if not availability["available"]:
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        reason = str(availability.get("reason") or AI_UNAVAILABLE_BUDGET)
        _log_openai_quota_skip(reason)
        return {"error": reason, "ai_status": availability}
    if not client:
        logger.error("❌ GPT JSON Call gefaald: Geen OpenAI Client (Missing API Key)")
        return {"error": "AI is offline"}
    if not _rate_limit_allows_call():
        return {"error": "ai_rate_limited", "ai_status": get_ai_availability()}
    if _quota_breaker_active():
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        _log_quota_block_warning("JSON")
        _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
        return {"error": AI_UNAVAILABLE_BUDGET, "ai_status": get_ai_availability()}

    _openai_runtime_state["json_calls"] = int(_openai_runtime_state.get("json_calls") or 0) + 1

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt + "\n\nRETURN ONLY VALID JSON."}
    ]

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🧠 GPT JSON Call (Attempt {attempt})")
            started = start_timer()
            
            active_client = client.with_options(max_retries=client_max_retries) if client_max_retries is not None else client
            response = active_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=JSON_TEMP,
                max_tokens=max_tokens or MAX_TOKENS,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            parsed = sanitize_json_output(content)

            if parsed:
                usage = getattr(response, "usage", None)
                _log_openai_usage(
                    model_name=str(getattr(response, "model", None) or model),
                    prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    response_time_ms=elapsed_ms(started),
                )
                return parsed
            
        except Exception as e:
            logger.error(f"❌ OpenAI JSON API Error (Attempt {attempt}): {e}")
            _mark_runtime_error(str(e))

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                _mark_quota_exhausted()
                _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
                return {"error": AI_UNAVAILABLE_BUDGET, "ai_status": get_ai_availability()}

            if attempt == retries:
                return {"error": str(e)}

            time.sleep(1)

    return {"error": "Failed to generate valid JSON"}


def ask_gpt_structured_response(
    *,
    prompt: str,
    system_role: str,
    output_spec: StructuredOutputSpec,
    model_override: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    client_max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        _validate_structured_output_spec(output_spec)
    except StructuredOutputContractError as exc:
        # A developer contract error must not consume a provider slot or be
        # surfaced as a user-facing rate limit.
        return {"error": "structured_schema_contract_error", "error_detail": str(exc)}
    availability = get_ai_availability()
    if not availability["available"]:
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        reason = str(availability.get("reason") or AI_UNAVAILABLE_BUDGET)
        _log_openai_quota_skip(reason)
        return {"error": reason, "ai_status": availability}
    if not client:
        return {"error": "ai_unavailable_configuration", "ai_status": availability}
    if not _rate_limit_allows_call():
        return {"error": "ai_rate_limited", "ai_status": get_ai_availability()}
    if _quota_breaker_active():
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        _log_quota_block_warning("Structured")
        _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
        return {"error": AI_UNAVAILABLE_BUDGET, "ai_status": get_ai_availability()}

    _openai_runtime_state["json_calls"] = int(_openai_runtime_state.get("json_calls") or 0) + 1
    active_model = str(model_override or model)
    started = start_timer()
    try:
        active_client = client.with_options(max_retries=client_max_retries) if client_max_retries is not None else client
        request_kwargs = build_structured_response_request(
            model_name=active_model,
            prompt=prompt,
            system_role=system_role,
            output_spec=output_spec,
            max_output_tokens=max_output_tokens or MAX_TOKENS,
            timeout_seconds=timeout_seconds,
        )
        response = active_client.responses.create(**request_kwargs)
        parsed = None
        parsed_source = None
        if getattr(response, "output_parsed", None) is not None:
            parsed = response.output_parsed
            parsed_source = "sdk_parsed"
        if parsed is None and getattr(response, "output", None):
            for item in response.output:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "parsed", None) is not None:
                        parsed = content.parsed
                        parsed_source = "content_parsed"
                        break
                if parsed is not None:
                    break

        # `responses.create` returns JSON Schema output as output_text in the
        # current SDK. Only parse it as strict JSON; do not apply the lenient
        # legacy JSON sanitizer at this contract boundary.
        if parsed is None:
            output_text = getattr(response, "output_text", None)
            if output_text:
                try:
                    candidate = json.loads(output_text)
                    if isinstance(candidate, dict):
                        parsed = candidate
                        parsed_source = "response_output_text"
                except (TypeError, json.JSONDecodeError):
                    pass

        if parsed is None:
            incomplete_details = getattr(response, "incomplete_details", None)
            output_items = getattr(response, "output", None) or []
            content_types = []
            refusal = None
            output_text = None
            for item in output_items:
                for content in getattr(item, "content", []) or []:
                    content_types.append(str(getattr(content, "type", "unknown")))
                    refusal = refusal or getattr(content, "refusal", None)
                    output_text = output_text or getattr(content, "text", None)
            parse_error = None
            if output_text:
                try:
                    candidate = json.loads(output_text)
                    if isinstance(candidate, dict):
                        parsed = candidate
                        parsed_source = "content_text"
                except (TypeError, json.JSONDecodeError) as exc:
                    parse_error = type(exc).__name__
            if parsed is not None:
                # Content blocks are used by older SDK response objects which
                # do not expose response.output_text.
                pass
            else:
                detail = {
                    "response_status": getattr(response, "status", None),
                    "incomplete_reason": getattr(incomplete_details, "reason", None),
                    "content_types": content_types,
                    "refusal": str(refusal)[:500] if refusal else None,
                    "json_parse_error": parse_error,
                    "request_id": _read_request_id(response),
                }
                logger.warning("OpenAI structured response incomplete", extra={"structured_response_detail": detail})
                return {"error": "incomplete_structured_response", "error_detail": detail}
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        reasoning_tokens = int(getattr(usage, "reasoning_tokens", 0) or 0)
        _log_openai_usage(
            model_name=str(getattr(response, "model", None) or active_model),
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            response_time_ms=elapsed_ms(started),
        )
        return {
            "parsed": parsed if isinstance(parsed, dict) else dict(parsed),
            "model": str(getattr(response, "model", None) or active_model),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "provider_metadata": {
                "response_status": getattr(response, "status", None),
                "response_id": getattr(response, "id", None),
                "request_id": _read_request_id(response),
                "parsed_source": parsed_source,
            },
        }
    except Exception as e:
        logger.exception("❌ OpenAI structured response error")
        if _is_provider_schema_contract_error(str(e)):
            return {"error": "structured_schema_contract_error", "error_detail": "provider_rejected_schema"}
        _mark_runtime_error(str(e))
        if "insufficient_quota" in str(e):
            _mark_quota_exhausted()
            _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
            return {"error": AI_UNAVAILABLE_BUDGET, "ai_status": get_ai_availability()}
        if _is_rate_limited_exception(e):
            return {
                "error": "ai_rate_limited",
                "error_detail": "provider_http_429",
                "provider_metadata": {
                    "http_status": _read_status_code(e),
                    "request_id": _read_request_id(e),
                    "retry_after_seconds": _retry_after_seconds(e),
                },
            }
        if "timeout" in str(e).lower():
            return {"error": "timeout"}
        return {"error": "provider_error"}


def _is_provider_schema_contract_error(message: str) -> bool:
    normalized = message.casefold()
    return "invalid schema" in normalized or ("json schema" in normalized and "type" in normalized)

# ============================================================
# 🧠 GPT TEXT CALL
# ============================================================
def ask_gpt_text(
    *,
    prompt: str,
    system_role: str,
    retries: int = 2,
    max_tokens: Optional[int] = None,
    client_max_retries: Optional[int] = None,
) -> str:
    """Genereert een platte tekst response."""
    
    availability = get_ai_availability()
    if not availability["available"]:
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        reason = str(availability.get("reason") or AI_UNAVAILABLE_BUDGET)
        _log_openai_quota_skip(reason)
        return "AI is tijdelijk niet beschikbaar. FINN gebruikt alleen opgeslagen en mechanisch berekende platformdata."
    if not client:
        logger.error("❌ GPT Text Call gefaald: Geen OpenAI Client (Missing API Key)")
        return "De AI assistent is momenteel offline omdat de OpenAI API sleutel ontbreekt. Controleer je .env bestand."
    if not _rate_limit_allows_call():
        return "AI is tijdelijk begrensd om onverwachte modelkosten te voorkomen. Probeer het later opnieuw."
    if _quota_breaker_active():
        _openai_runtime_state["blocked_calls"] = int(_openai_runtime_state.get("blocked_calls") or 0) + 1
        _log_quota_block_warning("Text")
        _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
        return "AI is tijdelijk niet beschikbaar. FINN gebruikt alleen opgeslagen en mechanisch berekende platformdata."

    _openai_runtime_state["text_calls"] = int(_openai_runtime_state.get("text_calls") or 0) + 1

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt}
    ]

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🧠 GPT Text Call (Attempt {attempt})")
            started = start_timer()
            
            active_client = client.with_options(max_retries=client_max_retries) if client_max_retries is not None else client
            response = active_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=TEXT_TEMP,
                max_tokens=max_tokens or MAX_TOKENS
            )

            content = response.choices[0].message.content
            if content:
                usage = getattr(response, "usage", None)
                _log_openai_usage(
                    model_name=str(getattr(response, "model", None) or model),
                    prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    response_time_ms=elapsed_ms(started),
                )
                return content.strip()

        except Exception as e:
            logger.error(f"❌ OpenAI Text API Error (Attempt {attempt}): {e}")
            _mark_runtime_error(str(e))

            # 🔥 STOP bij quota errors
            if "insufficient_quota" in str(e):
                logger.error("❌ QUOTA bereikt → stop retries")
                _mark_quota_exhausted()
                _log_openai_quota_skip(AI_UNAVAILABLE_BUDGET)
                return "AI is tijdelijk niet beschikbaar. FINN gebruikt alleen opgeslagen en mechanisch berekende platformdata."

            if attempt == retries:
                return f"⚠️ Er is een fout opgetreden bij de AI aanvraag: {str(e)}"

            time.sleep(1)

    return "Fout bij het genereren van de analyse."
# ============================================================
# 🌏 ASYNC WRAPPERS (To prevent blocking the event loop)
# ============================================================
async def ask_gpt_json_async(*args, **kwargs):
    return await asyncio.to_thread(ask_gpt_json, *args, **kwargs)

async def ask_gpt_text_async(*args, **kwargs):
    return await asyncio.to_thread(ask_gpt_text, *args, **kwargs)


def stream_gpt_json(
    *,
    prompt: str,
    system_role: str,
    max_tokens: Optional[int] = None
):
    """
    Initiates a streaming chat completion in JSON mode, yielding the raw OpenAI stream.
    """
    availability = get_ai_availability()
    if not availability["available"]:
        reason = str(availability.get("reason") or AI_UNAVAILABLE_BUDGET)
        _log_openai_quota_skip(reason)
        raise RuntimeError(reason)
    if not client:
        logger.error("❌ GPT Stream Call gefaald: Geen OpenAI Client")
        raise ValueError("AI is offline")
    if not _rate_limit_allows_call():
        raise RuntimeError("ai_rate_limited")

    messages = [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt + "\n\nRETURN ONLY VALID JSON."}
    ]

    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=JSON_TEMP,
        max_tokens=max_tokens or MAX_TOKENS,
        response_format={"type": "json_object"},
        stream=True
    )
