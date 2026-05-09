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
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
allow_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://tradamind.com",
    "https://www.tradamind.com",
    frontend_url,
]

# Ensure both www and non-www versions are allowed for production
if "://" in frontend_url:
    proto, domain = frontend_url.split("://")
    if domain.startswith("www."):
        allow_origins.append(f"{proto}://{domain[4:]}")
    else:
        allow_origins.append(f"{proto}://www.{domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,     # ⭐ Cookies toestaan
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            await session.commit()
            logger.info("✅ Database schema migration: global_market_insights.avg_score, conversation_state, ai_category_insights.symbol, ai_usage_logs observability columns, and performance indexes checked/added.")
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
