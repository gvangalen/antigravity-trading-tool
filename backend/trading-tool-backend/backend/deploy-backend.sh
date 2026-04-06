#!/bin/bash
set -e

echo "🚀 Starting backend deploy..."

# =====================================================
# PATH FIX
# =====================================================
export PATH="$HOME/.local/bin:$PATH"

# =====================================================
# DIRECTORIES (FIXED)
# =====================================================
BACKEND_DIR="$HOME/antigravity-trading-tool/backend/trading-tool-backend"
ENV_FILE="$HOME/.secrets/trading.env"
LOG_DIR="/var/log/pm2"

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
# LOAD ENV
# =====================================================
echo "🔐 Loading environment variables..."
set -o allexport
source "$ENV_FILE"
set +o allexport

# sanity checks
if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ OPENAI_API_KEY ontbreekt"
  exit 1
fi

if [ -z "$FRONTEND_URL" ]; then
  echo "❌ FRONTEND_URL ontbreekt"
  exit 1
fi

echo "✅ Environment loaded"
echo "➡ FRONTEND_URL=$FRONTEND_URL"

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
# RESTART BACKEND ONLY
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
# SAVE PM2 STATE
# =====================================================
pm2 save

echo ""
echo "✅ BACKEND DEPLOY SUCCESSFUL"
echo "-----------------------------------"
pm2 status
echo ""
echo "🌐 Backend: http://localhost:8000"
echo "📄 Logs backend: $LOG_DIR/backend.log"
echo ""
