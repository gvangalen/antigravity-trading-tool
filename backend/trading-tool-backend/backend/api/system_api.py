import asyncio
import os
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Request, Cookie, Header

from backend.celery_task.celery_app import celery_app
from backend.celery_task.queue_policy import resolve_task_queue
from backend.utils.auth_utils import decode_token, get_current_user
from backend.services.system_health_service import SystemHealthService
from backend.services.finn_product_analytics_service import finn_product_analytics
from backend.services.system_service import SystemService
from backend.utils.openai_client import clear_openai_runtime_breaker, get_openai_runtime_status, probe_openai_runtime
from backend.schemas.system_schema import BootstrapAgentsResponse

logger = logging.getLogger(__name__)
router = APIRouter()

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
async def system_openai_runtime(current_user: dict = Depends(require_operator)):
    """Operator view on OpenAI runtime cost controls and quota breaker state."""
    return get_openai_runtime_status()


@router.post("/system/openai-runtime/probe")
async def system_openai_runtime_probe(
    include_worker: bool = True,
    current_user: dict = Depends(require_operator),
):
    """Run a minimal OpenAI probe from the API process and, optionally, a Celery worker."""
    backend_probe = probe_openai_runtime(caller="backend")
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
    payload["worker"] = worker_probe
    return payload


@router.post("/system/openai-runtime/reset")
async def system_openai_runtime_reset(current_user: dict = Depends(require_operator)):
    """Clear the shared OpenAI quota breaker when operators have validated recovery."""
    before = get_openai_runtime_status()
    clear_openai_runtime_breaker()
    after = get_openai_runtime_status()
    return {
        "status": "reset",
        "before": before,
        "after": after,
    }

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
