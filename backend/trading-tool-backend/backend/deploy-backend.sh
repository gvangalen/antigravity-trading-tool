#!/bin/bash
set -e

echo "🚀 Starting backend deploy..."

# =====================================================
# PATH FIX
# =====================================================
export PATH="$HOME/.local/bin:$PATH"

# =====================================================
# DIRECTORIES
# =====================================================
BACKEND_DIR="$HOME/antigravity-trading-tool/backend/trading-tool-backend"
ENV_FILE="$HOME/.secrets/trading.env"
LOG_DIR="$HOME/.pm2/logs"

mkdir -p "$LOG_DIR"

# =====================================================
# VERIFY ENV
# =====================================================
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ ENV FILE NOT FOUND: $ENV_FILE"
  exit 1
fi

echo "✅ Using ENV file:"
echo "➡ $ENV_FILE"

# =====================================================
# UPDATE CODE (CRUCIAAL)
# =====================================================
echo "⬇️ Pull latest code..."
cd "$BACKEND_DIR"
git fetch origin main
git reset --hard origin/main

# =====================================================
# LOAD ENV
# =====================================================
echo "🔐 Loading environment variables..."
set -o allexport
source "$ENV_FILE"
set +o allexport

if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ OPENAI_API_KEY ontbreekt"
  exit 1
fi

if [ -z "$FRONTEND_URL" ]; then
  echo "❌ FRONTEND_URL ontbreekt"
  exit 1
fi

echo "✅ Environment loaded"

# =====================================================
# CLEAN CACHE
# =====================================================
echo "🧹 Cleaning __pycache__..."
find "$BACKEND_DIR" -type d -name '__pycache__' -exec rm -rf {} +

# =====================================================
# INSTALL DEPENDENCIES (FIXED)
# =====================================================
echo "📦 Installing Python dependencies..."
cd "$BACKEND_DIR/backend"
pip install -r requirements.txt

# =====================================================
# RESTART BACKEND
# =====================================================
echo "♻️ Restarting backend service..."
pm2 delete backend || true
sleep 2

# =====================================================
# START FASTAPI
# =====================================================
echo "🚀 Starting FastAPI backend..."

pm2 start uvicorn \
  --name backend \
  --cwd "$BACKEND_DIR" \
  --interpreter python3 \
  --output "$LOG_DIR/backend.log" \
  --error "$LOG_DIR/backend.err.log" \
  -- \
  backend.main:app --host 0.0.0.0 --port 8000

# =====================================================
# START CELERY (BACKGROUND TASKS)
# =====================================================
echo "⚙️ Starting Celery background workers..."

# RESTART CELERY WORKER (executes tasks)
pm2 delete celery-worker || true
pm2 start "celery -A backend.celery_task.celery_app worker --loglevel=info --concurrency=1" \
  --name celery-worker \
  --cwd "$BACKEND_DIR" \
  --output "$LOG_DIR/celery-worker.log" \
  --error "$LOG_DIR/celery-worker.err.log"

# RESTART CELERY BEAT (schedules tasks)
pm2 delete celery-beat || true
pm2 start "celery -A backend.celery_task.celery_app beat --loglevel=info" \
  --name celery-beat \
  --cwd "$BACKEND_DIR" \
  --output "$LOG_DIR/celery-beat.log" \
  --error "$LOG_DIR/celery-beat.err.log"

# =====================================================
# SAVE PM2 STATE
# =====================================================
pm2 save

# =====================================================
# 🧠 AI AGENT ACTIVATION (DASHBOARD REFRESH)
# =====================================================
echo ""
echo "🧠 Triggering AI Agents to refresh dashboard content..."

cd "$BACKEND_DIR/backend"
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

python3 -c "
from ai_agents.market_ai_agent import run_market_agent
from ai_agents.macro_ai_agent import run_macro_agent
from ai_agents.technical_ai_agent import run_technical_agent
from ai_agents.setup_ai_agent import run_setup_agent

UID = 30
print('➡️ Market AI Agent...')
try: run_market_agent(user_id=UID); print('✅ Market OK')
except Exception as e: print(f'❌ Market Error: {e}')

print('➡️ Macro AI Agent...')
try: run_macro_agent(user_id=UID); print('✅ Macro OK')
except Exception as e: print(f'❌ Macro Error: {e}')

print('➡️ Technical AI Agent...')
try: run_technical_agent(user_id=UID); print('✅ Technical OK')
except Exception as e: print(f'❌ Technical Error: {e}')

print('➡️ Setup AI Agent...')
try: run_setup_agent(user_id=UID); print('✅ Setup OK')
except Exception as e: print(f'❌ Setup Error: {e}')
"

echo ""
echo "✅ BACKEND DEPLOY SUCCESSFUL"
echo "-----------------------------------"
pm2 status
echo ""
echo "🌐 Backend: http://localhost:8000"
echo ""
