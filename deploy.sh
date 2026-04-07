#!/bin/bash
set -e

echo "🚀 AUTO DEPLOY START"

# =====================================================
# LOAD NVM (FIX PM2 in GitHub Actions)
# =====================================================
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
export PATH="$NVM_DIR/versions/node/$(nvm current)/bin:$PATH"

# =====================================================
# EXTRA PATH FIX (python / pip)
# =====================================================
export PATH="$HOME/.local/bin:$PATH"

# =====================================================
# NAVIGATE TO PROJECT
# =====================================================
cd ~/antigravity-trading-tool

echo "⬇️ Pull latest code..."
git fetch origin main
git reset --hard origin/main

echo ""
echo "🔧 Deploy backend..."
bash backend/trading-tool-backend/backend/deploy-backend.sh

echo ""
echo "💻 Deploy frontend..."
bash frontend/trading-tool-frontend/deploy-frontend.sh

echo ""
echo "💾 Saving PM2 state..."
pm2 save

echo ""
echo "📊 PM2 STATUS:"
pm2 status

echo ""
echo "✅ DEPLOY DONE"
