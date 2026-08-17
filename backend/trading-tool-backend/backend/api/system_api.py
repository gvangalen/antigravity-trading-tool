import asyncio
import os
import logging
import json
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Request, Cookie, Header

from backend.celery_task.celery_app import celery_app
from backend.celery_task.queue_policy import resolve_task_queue
from backend.utils.rate_limit import InMemoryRateLimiter, client_ip
from backend.utils.auth_utils import decode_token, get_current_user
from backend.services.system_health_service import SystemHealthService
from backend.services.finn_product_analytics_service import finn_product_analytics
from backend.services.finn_v2_cutover_service import FinnV2CutoverService
from backend.services.system_service import SystemService
from backend.utils.openai_client import clear_openai_runtime_breaker, get_openai_runtime_status, probe_openai_runtime
from backend.schemas.system_schema import BootstrapAgentsResponse
from backend.infrastructure.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()
openai_runtime_probe_limiter = InMemoryRateLimiter(requests_limit=3, window_seconds=60)

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=dotenv_path)

logger.info("⚙️ system_api.py geladen – System endpoints (Clean Architecture).")


async def require_operator(
    request: Request,
    access_token: str = Cookie(default=None),
    authorization: str = Header(default=None),
):
    """Deep ops endpoints stay private to authenticated operators."""
    client_host = getattr(request.client, "host", None)
    host_header = (request.headers.get("host") or "").split(":", 1)[0].strip().lower()
    if (
        client_host in {"127.0.0.1", "::1", "localhost"}
        and host_header in {"127.0.0.1", "::1", "localhost"}
    ):
        return {"id": "loopback", "role": "admin"}

    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    token = access_token or bearer_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    current_user = {
        "id": int(payload.get("sub")),
        "role": payload.get("role"),
    }
    if current_user.get("role") != "admin":
        logger.warning(
            "🚫 Unauthorized system health access by user %s",
            current_user.get("id"),
        )
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


async def require_strict_admin(
    access_token: str = Cookie(default=None),
    authorization: str = Header(default=None),
):
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    token = access_token or bearer_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    current_user = {
        "id": int(payload.get("sub")),
        "role": payload.get("role"),
    }
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


def _redact_availability(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return {
        "available": bool(payload.get("available")),
        "configured": bool(payload.get("configured")),
        "mode": payload.get("mode"),
        "reason": payload.get("reason"),
        "source": payload.get("source"),
        "retry_after_seconds": payload.get("retry_after_seconds"),
    }


def _redact_runtime_status(payload: dict) -> dict:
    return {
        "configured": bool(payload.get("configured")),
        "model": payload.get("model"),
        "quota_breaker_active": bool(payload.get("quota_breaker_active")),
        "quota_cooldown_remaining_seconds": payload.get("quota_cooldown_remaining_seconds"),
        "quota_failures": payload.get("quota_failures"),
        "blocked_calls": payload.get("blocked_calls"),
        "text_calls": payload.get("text_calls"),
        "json_calls": payload.get("json_calls"),
        "last_error": payload.get("last_error"),
        "last_error_at_epoch": payload.get("last_error_at_epoch"),
        "api_key_fingerprint": payload.get("api_key_fingerprint"),
        "api_key_scope": payload.get("api_key_scope"),
        "availability": _redact_availability(payload.get("availability")),
    }


def _redact_probe_result(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return {
        "caller": payload.get("caller"),
        "ok": bool(payload.get("ok")),
        "configured": bool(payload.get("configured")),
        "model": payload.get("model"),
        "api_key_fingerprint": payload.get("api_key_fingerprint"),
        "api_key_scope": payload.get("api_key_scope"),
        "availability_before": _redact_availability(payload.get("availability_before")),
        "availability_after": _redact_availability(payload.get("availability_after")),
        "quota_breaker_before": bool(payload.get("quota_breaker_before")),
        "quota_breaker_after": bool(payload.get("quota_breaker_after")),
        "breaker_cleared": bool(payload.get("breaker_cleared")),
        "http_status": payload.get("http_status"),
        "request_id": payload.get("request_id"),
        "duration_ms": payload.get("duration_ms"),
        "error": payload.get("error"),
        "insufficient_quota": payload.get("insufficient_quota"),
        "task_id": payload.get("task_id"),
    }


def _audit_openai_runtime_action(
    *,
    action: str,
    admin_user_id: int,
    request: Request,
    result: dict,
) -> None:
    safe_result = {
        "action": action,
        "admin_user_id": admin_user_id,
        "trace_id": getattr(request.state, "trace_id", None),
        "client_ip": client_ip(request),
        "path": request.url.path,
        "method": request.method,
        "process_pid": os.getpid(),
        "result": result,
    }
    logger.info("[OPENAI-RUNTIME-AUDIT] %s", json.dumps(safe_result, ensure_ascii=False, sort_keys=True))


def _apply_openai_runtime_probe_limit(*, request: Request, admin_user_id: int) -> None:
    ip_addr = client_ip(request)
    openai_runtime_probe_limiter.check_rate_limit(
        f"user_{admin_user_id}:openai_runtime_probe",
        limit=3,
        detail="Te veel OpenAI runtime probes. Wacht kort en probeer opnieuw.",
    )
    if ip_addr not in {"127.0.0.1", "::1", "localhost"}:
        openai_runtime_probe_limiter.check_rate_limit(
            f"ip_{ip_addr}:openai_runtime_probe",
            limit=10,
            detail="Te veel OpenAI runtime probes vanaf dit IP-adres. Wacht kort en probeer opnieuw.",
        )


# =====================================================
# 🩺 SYSTEM HEALTH (deep, non-LB)
# =====================================================
@router.get("/system/health")
async def system_health(current_user: dict = Depends(require_operator)):
    """
    Deep operational health endpoint for deploy gates and operator dashboards.
    Keep /api/health lightweight for load balancers.
    """
    return await SystemHealthService.deep_health()


@router.get("/system/finn-analytics")
async def system_finn_analytics(current_user: dict = Depends(require_operator)):
    """Lean FINN product analytics for early operator review."""
    return finn_product_analytics.snapshot()


@router.get("/system/openai-runtime")
async def system_openai_runtime(current_user: dict = Depends(require_strict_admin)):
    """Operator view on OpenAI runtime cost controls and quota breaker state."""
    return _redact_runtime_status(get_openai_runtime_status())


@router.post("/system/openai-runtime/probe")
async def system_openai_runtime_probe(
    request: Request,
    include_worker: bool = True,
    current_user: dict = Depends(require_strict_admin),
):
    """Run a minimal OpenAI probe from the API process and, optionally, a Celery worker."""
    _apply_openai_runtime_probe_limit(request=request, admin_user_id=int(current_user["id"]))

    backend_probe = _redact_probe_result(probe_openai_runtime(caller="backend"))
    payload = {
        "backend": backend_probe,
        "worker": None,
    }
    if not include_worker:
        return payload

    task_name = "backend.celery_task.system_task.probe_openai_runtime"
    async_result = celery_app.send_task(
        task_name,
        queue=resolve_task_queue(task_name),
    )
    try:
        worker_probe = await asyncio.to_thread(async_result.get, timeout=20)
    except Exception as exc:
        worker_probe = {
            "ok": False,
            "error": str(exc),
            "task_id": async_result.id,
        }
    if isinstance(worker_probe, dict):
        worker_probe.setdefault("task_id", async_result.id)
    payload["worker"] = _redact_probe_result(worker_probe)
    _audit_openai_runtime_action(
        action="probe",
        admin_user_id=int(current_user["id"]),
        request=request,
        result=payload,
    )
    return payload


@router.post("/system/openai-runtime/reset")
async def system_openai_runtime_reset(
    request: Request,
    current_user: dict = Depends(require_strict_admin),
):
    """Clear the shared OpenAI quota breaker when operators have validated recovery."""
    before = _redact_runtime_status(get_openai_runtime_status())
    clear_openai_runtime_breaker()
    after = _redact_runtime_status(get_openai_runtime_status())
    payload = {
        "status": "reset",
        "before": before,
        "after": after,
    }
    _audit_openai_runtime_action(
        action="reset",
        admin_user_id=int(current_user["id"]),
        request=request,
        result=payload,
    )
    return payload


@router.get("/system/finn-v2/runtime")
async def system_finn_v2_runtime(
    current_user: dict = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    return await FinnV2CutoverService(db).runtime_status()


@router.get("/system/finn-v2/status")
async def system_finn_v2_status(
    current_user: dict = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    return await FinnV2CutoverService(db).operator_snapshot()

# =====================================================
# 🚀 BOOTSTRAP AGENTS (na onboarding)
# =====================================================
@router.post("/system/bootstrap-agents", response_model=BootstrapAgentsResponse)
async def bootstrap_agents(current_user=Depends(get_current_user)):
    """
    Triggers the background initialization of AI agents for a newly onboarded user.
    """
    try:
        user_id = current_user["id"]
        logger.info(f"🚀 API Request: Bootstrap agents gestart voor user {user_id}")

        result = await SystemService.bootstrap_agents_for_user(user_id)
        return result

    except Exception as e:
        logger.exception(f"❌ Bootstrap agents mislukt voor user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Bootstrap agents starten mislukt",
        )
