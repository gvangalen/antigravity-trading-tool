#!/bin/bash
set -e

echo "🚀 AUTO DEPLOY START (UNIFIED ECOSYSTEM-BASED)"

# =====================================================
# LOAD NVM (FIX PM2 / NODE in SSH)
# =====================================================
export NVM_DIR="$HOME/.nvm"

if [ -s "$NVM_DIR/nvm.sh" ]; then
  source "$NVM_DIR/nvm.sh"
else
  echo "❌ NVM not found!"
fi

# Force correct Node version
nvm use 20 || nvm use --lts

# =====================================================
# FIX PATH (node + python)
# =====================================================
export PATH="$NVM_DIR/versions/node/$(nvm current)/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"

echo "📦 Node version: $(node -v)"
echo "📦 PM2 path: $(which pm2 || echo 'pm2 NOT FOUND')"

# =====================================================
# NAVIGATE TO PROJECT
# =====================================================
PROJECT_DIR="/home/ubuntu/antigravity-trading-tool"
BACKEND_DIR="$PROJECT_DIR/backend/trading-tool-backend"
ENV_FILE="$HOME/.secrets/trading.env"

cd "$PROJECT_DIR"

echo "⬇️ Pull latest code..."
git fetch origin main
git reset --hard origin/main

# =====================================================
# LOAD ENV
# =====================================================
echo "🔐 Loading environment variables..."
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ ENV FILE NOT FOUND: $ENV_FILE"
  exit 1
fi
set -o allexport
source "$ENV_FILE"
set +o allexport
echo "✅ Environment loaded"

# =====================================================
# INSTALL PYTHON DEPENDENCIES
# =====================================================
echo "📦 Installing Python dependencies..."
cd "$BACKEND_DIR/backend"
pip install -r requirements.txt

# =====================================================
# CLEAN CACHE
# =====================================================
echo "🧹 Cleaning __pycache__..."
find "$BACKEND_DIR" -type d -name '__pycache__' -exec rm -rf {} +

# =====================================================
# UNIFIED PM2 LAUNCH
# =====================================================
echo "♻️ Purging and launching unified PM2 process pool..."
cd "$PROJECT_DIR"
pm2 delete all || true
sleep 2

pm2 start ecosystem.config.js
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
echo "📊 PM2 STATUS:"
pm2 status

echo ""
echo "✅ UNIFIED DEPLOY SUCCESSFUL"
