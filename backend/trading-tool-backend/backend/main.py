import sys
import os
import logging
import importlib
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from dotenv import load_dotenv

# ------------------------------------------------------------
# 📌 .env laden
# ------------------------------------------------------------
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)
print("ENV FRONTEND_URL =", os.getenv("FRONTEND_URL"))
print("ENV DB_HOST =", os.getenv("DB_HOST"))

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
safe_include("backend.api.dashboard_api", "dashboard_api")
safe_include("backend.api.sidebar_api", "sidebar_api")
safe_include("backend.api.agents_api", "agents_api")
safe_include("backend.api.bot_api", "bot_api")
safe_include("backend.api.backtest_api", "backtest_api")
safe_include("backend.api.market_intelligence_api", "market_intelligence_api")
safe_include("backend.api.system_api", "system_api")
safe_include("backend.api.report_api", "report_api")

safe_include("backend.api.report_public_api", "report_public_api")
safe_include("backend.api.ai_assistant_api", "ai_assistant_api")
safe_include("backend.api.admin_api", "admin_api")
safe_include("backend.api.notifications_api", "notifications_api")
safe_include("backend.api.exchange_api", "exchange_api")
safe_include("backend.api.watchlist_api", "watchlist_api")
safe_include("backend.api.intelligence_event_api", "intelligence_event_api")

# ==================================================================
# 🔧 Database Schema Migration / Hotfixes
# ==================================================================
@app.on_event("startup")
async def database_migrations():
    logger.info("🔧 Running database schema hotfixes/migrations...")
    from backend.infrastructure.database import async_session_factory
    from sqlalchemy import text
    async with async_session_factory() as session:
        try:
            # Safely add avg_score column to global_market_insights if it doesn't exist
            await session.execute(text("""
                ALTER TABLE global_market_insights 
                ADD COLUMN IF NOT EXISTS avg_score numeric(5,2);
            """))
            # Safely create conversation_state table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS conversation_state (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    current_flow VARCHAR,
                    asset VARCHAR,
                    slots JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # Safely add symbol column to ai_category_insights if it doesn't exist
            await session.execute(text("""
                ALTER TABLE ai_category_insights 
                ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';
            """))
            # Safely add Phase 3 & 4 Observability columns to ai_usage_logs if they don't exist in live database
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS trace_id VARCHAR;
            """))
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS completion_status VARCHAR DEFAULT 'success';
            """))
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS parser_recovery_triggered BOOLEAN DEFAULT false;
            """))
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5, 2);
            """))
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS safety_guardrail_triggered BOOLEAN DEFAULT false;
            """))
            await session.execute(text("""
                ALTER TABLE ai_usage_logs 
                ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';
            """))
            # Safely create indexes on ai_usage_logs for performance under load
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_trace_id ON ai_usage_logs(trace_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_timestamp ON ai_usage_logs(timestamp);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_completion_status ON ai_usage_logs(completion_status);
            """))

            # Safely create chat_sessions table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id VARCHAR PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # Safely create chat_messages table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    intent VARCHAR,
                    actions JSONB DEFAULT '{}'::jsonb
                );
            """))
            # Safely create indexes on chat tables for query speed
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at DESC);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
            """))

            # Safely create ai_pending_actions table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_pending_actions (
                    id VARCHAR PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    type VARCHAR NOT NULL,
                    payload JSONB NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    trace_id VARCHAR
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_pending_actions_user_id ON ai_pending_actions(user_id);
            """))

            # Safely create ai_intelligence_events table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_intelligence_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    type VARCHAR NOT NULL,
                    symbol VARCHAR,
                    title VARCHAR NOT NULL,
                    description TEXT NOT NULL,
                    severity VARCHAR NOT NULL DEFAULT 'info',
                    payload JSONB DEFAULT '{}'::jsonb,
                    status VARCHAR NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_intelligence_events_user_id ON ai_intelligence_events(user_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_intelligence_events_status ON ai_intelligence_events(status);
            """))
            await session.execute(text("""
                ALTER TABLE bot_configs
                ADD COLUMN IF NOT EXISTS symbol VARCHAR;
            """))
            await session.execute(text("""
                ALTER TABLE bot_configs
                DROP CONSTRAINT IF EXISTS bot_configs_cadence_check;
            """))
            await session.execute(text("""
                ALTER TABLE bot_configs
                ADD CONSTRAINT bot_configs_cadence_check
                CHECK (cadence IN ('hourly', 'daily', 'weekly', 'monthly', 'custom'));
            """))
            await session.execute(text("""
                ALTER TABLE bot_orders
                ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
            """))
            await session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_orders_user_idempotency_key
                ON bot_orders (user_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
            """))

            await session.commit()
            logger.info("✅ Database schema migration: global_market_insights.avg_score, conversation_state, ai_category_insights.symbol, ai_usage_logs, chat_sessions, chat_messages, ai_pending_actions, and ai_intelligence_events tables/indexes checked/added.")
        except Exception as e:
            logger.error(f"❌ Database schema migration failed: {e}")

# ==================================================================
# 🧠 Phase 3: Semantic Cache Initialization
# ==================================================================
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 System Startup: Initializing Vector Intelligence...")
    from backend.infrastructure.vector_store import get_vector_store
    from backend.infrastructure.database import async_session_factory
    
    # Zorg dat de static folder bestaat
    os.makedirs("backend/static/ai", exist_ok=True)
    
    # Initialiseer Vector Store
    try:
        vs = get_vector_store()
        
        # Als de index leeg is, probeer te rebuilden vanuit DB
        if vs.index and vs.index.ntotal == 0:
            logger.info("🔍 Vector index is leeg of ontbreekt. Rebuilding vanuit DB...")
            async with async_session_factory() as session:
                await vs.rebuild_from_db(session)
        elif vs.index:
            logger.info(f"✅ Vector index geladen met {vs.index.ntotal} items.")
        else:
            logger.warning("⚠️ Vector store index is None (FAISS missing).")
    except Exception as e:
        logger.error(f"❌ Fout bij initialiseren Vector Store: {e}")

# ==================================================================
# 👨‍⚕️ Health check
# ==================================================================
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "API is running"}


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
