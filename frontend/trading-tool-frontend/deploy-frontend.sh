#!/bin/bash
set -e

echo "📦 Start frontend deploy..."

# =====================================================
# PATH / NODE
# =====================================================
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"

nvm use 20 || { echo "❌ Node 20 niet beschikbaar"; exit 1; }
echo "Node: $(node -v)"

# =====================================================
# DIRECTORIES
# =====================================================
FRONTEND_DIR="$HOME/antigravity-trading-tool/frontend/trading-tool-frontend"
ENV_FILE="$HOME/.secrets/trading.env"

cd "$FRONTEND_DIR" || { echo "❌ Frontend map niet gevonden"; exit 1; }

# =====================================================
# VERIFY ENV
# =====================================================
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ ENV FILE NOT FOUND: $ENV_FILE"
  exit 1
fi

# =====================================================
# LOAD ENV
# =====================================================
echo "🔐 Loading environment variables..."
set -o allexport
source "$ENV_FILE"
set +o allexport

# Zorg dat Next.js env gebruikt
cp "$ENV_FILE" .env.local || true

echo "✅ ENV loaded"

# =====================================================
# STOP OLD
# =====================================================
echo "🧹 Stopping old frontend..."
pm2 delete frontend || true

sleep 2

# =====================================================
# SYNC CODE
# =====================================================
echo "⬇️ Sync met GitHub..."
git fetch origin main
git reset --hard origin/main

# =====================================================
# CLEAN BUILD
# =====================================================
echo "🧨 Removing old build..."
rm -rf .next

# =====================================================
# INSTALL DEPENDENCIES
# =====================================================
echo "📦 Installing dependencies..."
npm ci --legacy-peer-deps

# =====================================================
# BUILD
# =====================================================
echo "🏗️ Building frontend..."
npm run build

# =====================================================
# START WITH PM2
# =====================================================
echo "🚀 Starting frontend via PM2..."

pm2 start npm \
  --name frontend \
  --cwd "$FRONTEND_DIR" \
  -- run start

# =====================================================
# SAVE STATE
# =====================================================
pm2 save

echo ""
echo "✅ FRONTEND DEPLOY SUCCESSFUL"
echo "-----------------------------------"
pm2 status
echo ""
echo "🌐 Frontend: http://localhost:5002"
echo ""
