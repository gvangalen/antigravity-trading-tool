#!/bin/bash
set -e

echo "🚀 AUTO DEPLOY START"

# =====================================================
# LOAD NVM (FIX PM2 / NODE in SSH)
# =====================================================
export NVM_DIR="$HOME/.nvm"

if [ -s "$NVM_DIR/nvm.sh" ]; then
  source "$NVM_DIR/nvm.sh"
else
  echo "❌ NVM not found!"
fi

# Force juiste Node versie (belangrijk)
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
cd ~/antigravity-trading-tool

echo "⬇️ Pull latest code..."
git fetch origin main
git reset --hard origin/main

# =====================================================
# BACKEND DEPLOY
# =====================================================
echo ""
echo "🔧 Deploy backend..."
bash backend/trading-tool-backend/backend/deploy-backend.sh

# =====================================================
# FRONTEND DEPLOY
# =====================================================
echo ""
echo "💻 Deploy frontend..."
bash frontend/trading-tool-frontend/deploy-frontend.sh

# =====================================================
# PM2 SAVE + STATUS
# =====================================================
echo ""
echo "💾 Saving PM2 state..."
pm2 save

echo ""
echo "📊 PM2 STATUS:"
pm2 status

echo ""
echo "✅ DEPLOY DONE"
