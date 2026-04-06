#!/bin/bash
set -e

echo "📦 Start frontend deploy..."

# -------------------------
# PATH / NODE
# -------------------------
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"

nvm use 20

# -------------------------
# DIRECTORIES (FIX)
# -------------------------
FRONTEND_DIR="$HOME/antigravity-trading-tool/frontend/trading-tool-frontend"
ENV_FILE="$HOME/.secrets/trading.env"

cd "$FRONTEND_DIR" || { echo "❌ Frontend map niet gevonden"; exit 1; }

# -------------------------
# LOAD ENV (BELANGRIJK)
# -------------------------
set -o allexport
source "$ENV_FILE"
set +o allexport

echo "✅ ENV loaded"

# -------------------------
# STOP OLD
# -------------------------
pm2 delete frontend || true

# -------------------------
# SYNC CODE
# -------------------------
echo "⬇️ Sync GitHub..."
git fetch origin main
git reset --hard origin/main

# -------------------------
# CLEAN BUILD
# -------------------------
rm -rf .next

# -------------------------
# INSTALL
# -------------------------
npm ci --legacy-peer-deps

# -------------------------
# BUILD
# -------------------------
npm run build

# -------------------------
# START (FIXED)
# -------------------------
pm2 start npm \
  --name frontend \
  --cwd "$FRONTEND_DIR" \
  -- run start

pm2 save

echo "✅ Frontend running"
pm2 status
