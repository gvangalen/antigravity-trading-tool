import sys
import os
import logging
import importlib
import traceback
import uuid
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from dotenv import load_dotenv

# ------------------------------------------------------------
# 📌 .env laden
# ------------------------------------------------------------
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

# ------------------------------------------------------------
# 📌 Root path toevoegen
# ------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ------------------------------------------------------------
# 📌 Logging
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 🚀 FastAPI app
# ------------------------------------------------------------
app = FastAPI(title="Market Dashboard API", version="1.0")
UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
}


def _is_trusted_same_origin_request(request) -> bool:
    request_origin = request.headers.get("origin") or ""
    request_referer = request.headers.get("referer") or ""
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    expected_scheme = forwarded_proto or request.url.scheme
    expected_host = forwarded_host or request.url.netloc
    expected_origin = f"{expected_scheme}://{expected_host}"
    sec_fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()

    if request_origin and request_origin == expected_origin:
        return True

    if request_referer:
        parsed = urlparse(request_referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        if referer_origin == expected_origin:
            return True

    if sec_fetch_site in {"same-origin", "same-site"}:
        return True

    return False


@app.middleware("http")
async def request_trace_id_middleware(request, call_next):
    trace_id = request.headers.get("x-trace-id") or f"trdm-req-{uuid.uuid4().hex[:12]}"
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.middleware("http")
async def csrf_protect_cookie_auth_middleware(request, call_next):
    if (
        request.url.path.startswith("/api/")
        and request.method.upper() in UNSAFE_HTTP_METHODS
        and request.url.path not in CSRF_EXEMPT_PATHS
    ):
        authorization = request.headers.get("authorization", "")
        using_bearer_auth = authorization.lower().startswith("bearer ")
        session_cookie = request.cookies.get("access_token") or request.cookies.get("refresh_token")

        if session_cookie and not using_bearer_auth:
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            csrf_header = request.headers.get(CSRF_HEADER_NAME)
            trusted_same_origin = _is_trusted_same_origin_request(request)
            if (
                not trusted_same_origin
                and (
                    not csrf_cookie
                    or not csrf_header
                    or csrf_cookie != csrf_header
                )
            ):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})

    return await call_next(request)


@app.middleware("http")
async def api_no_store_middleware(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "connect-src 'self' https: wss: ws:; "
        "form-action 'self'"
    )
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if request.url.scheme == "https" or forwarded_proto.lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# 🌍 CORS — Dynamic Configuration
frontend_urls = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
    if origin.strip()
]
extra_cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
allow_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5002",
    "http://143.47.186.148:5002",
    "https://143.47.186.148",
    "https://tradamind.com",
    "https://www.tradamind.com",
    "capacitor://localhost",
    "ionic://localhost",
]
allow_origins.extend(frontend_urls)
allow_origins.extend(extra_cors_origins)
allow_origins = list(dict.fromkeys(origin for origin in allow_origins if origin))

default_allow_origin_regex = (
    r"^https://(www\.)?tradamind\.com$|"
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|"
    r"^https?://143\.47\.186\.148(:\d+)?$|"
    r"^(capacitor|ionic)://localhost$"
)
allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX", default_allow_origin_regex)

# Ensure both www and non-www versions are allowed for production
for frontend_url in frontend_urls:
    if "://" in frontend_url:
        proto, domain = frontend_url.split("://", 1)
        if domain.startswith("www."):
            allow_origins.append(f"{proto}://{domain[4:]}")
        else:
            allow_origins.append(f"{proto}://www.{domain}")
allow_origins = list(dict.fromkeys(origin for origin in allow_origins if origin))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,     # ⭐ Cookies toestaan
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def fail_fast_database_config():
    from backend.infrastructure.database import validate_database_connection
    await validate_database_connection()
    logger.info("✅ Database connection validated before serving auth/Finn routes.")

# ------------------------------------------------------------
# 📂 Static files
# ------------------------------------------------------------
app.mount("/static", StaticFiles(directory="backend/static"), name="static")


# ==================================================================
# 🔧 Veilig routers includen
# ==================================================================
def safe_include(import_path: str, name: str = ""):
    try:
        module = importlib.import_module(import_path)
        app.include_router(module.router, prefix="/api")
        logger.info(f"✅ Router geladen: {name or import_path}")
    except Exception as e:
        logger.error(f"❌ Router FOUT bij {name or import_path}: {e}")
        traceback.print_exc()


# ==================================================================
# 🔐 AUTH — ALTIJD EERST LADEN
# ==================================================================
safe_include("backend.api.auth_api", "auth_api")

# ==================================================================
# 🎯 ONBOARDING
# ==================================================================
safe_include("backend.api.onboarding_api", "onboarding_api")

# ==================================================================
# 📦 Overige API's
# ==================================================================
safe_include("backend.api.market_data_api", "market_data_api")
safe_include("backend.api.macro_data_api", "macro_data_api")
safe_include("backend.api.technical_data_api", "technical_data_api")
safe_include("backend.api.setups_api", "setups_api")
safe_include("backend.api.strategy_api", "strategy_api")
safe_include("backend.api.indicator_config_api", "indicator_config_api")
safe_include("backend.api.score_api", "score_api")
safe_include("backend.api.workspace_api", "workspace_api")
safe_include("backend.api.finn_specialist_api", "finn_specialist_api")
safe_include("backend.api.dashboard_api", "dashboard_api")
safe_include("backend.api.sidebar_api", "sidebar_api")
safe_include("backend.api.asset_catalog_api", "asset_catalog_api")
safe_include("backend.api.agents_api", "agents_api")
safe_include("backend.api.bot_api", "bot_api")
safe_include("backend.api.backtest_api", "backtest_api")
safe_include("backend.api.market_intelligence_api", "market_intelligence_api")
safe_include("backend.api.system_api", "system_api")
safe_include("backend.api.report_api", "report_api")

safe_include("backend.api.report_public_api", "report_public_api")
safe_include("backend.api.ai_assistant_api", "ai_assistant_api")
safe_include("backend.api.finn_v2_api", "finn_v2_api")
safe_include("backend.api.admin_api", "admin_api")
safe_include("backend.api.notifications_api", "notifications_api")
safe_include("backend.api.exchange_api", "exchange_api")
safe_include("backend.api.watchlist_api", "watchlist_api")
safe_include("backend.api.intelligence_event_api", "intelligence_event_api")

# ==================================================================
# 🔧 Database Schema
# ==================================================================
# Runtime DDL is intentionally not executed from app startup. Apply versioned
# migrations from backend/scripts/migrations before restarting production.

# ==================================================================
# 🧠 Phase 3: Semantic Cache Initialization
# ==================================================================
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 System Startup: Initializing Vector Intelligence...")
    from backend.infrastructure.vector_store import get_vector_store
    from backend.infrastructure.database import async_session_factory

    os.makedirs("backend/static/ai", exist_ok=True)

    async def _warm_vector_store():
        try:
            vs = get_vector_store()
            if vs.index and vs.index.ntotal == 0:
                logger.info("🔍 Vector index is leeg of ontbreekt. Rebuilding vanuit DB in background...")
                async with async_session_factory() as session:
                    await vs.rebuild_from_db(session)
                logger.info("✅ Vector index background rebuild voltooid.")
            elif vs.index:
                logger.info(f"✅ Vector index geladen met {vs.index.ntotal} items.")
            else:
                logger.warning("⚠️ Vector store index is None (FAISS missing).")
        except Exception as e:
            logger.error(f"❌ Fout bij initialiseren Vector Store: {e}")

    asyncio.create_task(_warm_vector_store())
    logger.info("✅ Vector Intelligence warmup scheduled in background.")

# ==================================================================
# 👨‍⚕️ Health check
# ==================================================================
@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "API is running",
        "app_env": os.getenv("APP_ENV", "production"),
    }


# ==================================================================
# 🧪 AnyIO Thread Pool Limit (Fix for 'can't start new thread')
# ==================================================================
@app.on_event("startup")
async def set_thread_limit():
    from anyio.lowlevel import checkpoint
    from anyio import to_thread
    # Set max threads to 25. Default is often 40+, which is too much for small VPS
    limiter = to_thread.current_default_thread_limiter()
    limiter.total_tokens = 25
    logger.info(f"🛡️ Thread pool limiter set to {limiter.total_tokens} tokens.")

# ==================================================================
# 🧭 Debug: toon alle routes bij boot
# ==================================================================
print("\n--------------------------------------------------")
print("🚦 Geregistreerde API-routes:")
for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"{route.path} - methods: {route.methods}")
print("--------------------------------------------------\n")
