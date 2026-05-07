#!/bin/bash
set -e

echo "📦 Start frontend deploy..."

# =====================================================
# PATH / NODE
# =====================================================
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# =====================================================
# DIRECTORIES
# =====================================================
FRONTEND_DIR="$HOME/antigravity-trading-tool/frontend/trading-tool-frontend"

cd "$FRONTEND_DIR" || { echo "❌ Frontend map niet gevonden"; exit 1; }

# =====================================================
# SYNC CODE
# =====================================================
echo "⬇️ Sync met GitHub..."
git fetch origin main
git reset --hard origin/main

# =====================================================
# START WITH PM2
# =====================================================
echo "⚡ Using prebuilt frontend (no build on server)"

pm2 delete frontend || true

pm2 start server.js --name frontend

pm2 save

echo ""
echo "✅ FRONTEND DEPLOY SUCCESSFUL"
echo "-----------------------------------"
pm2 status
echo ""
echo "🌐 Frontend static: http://localhost:5002"
echo ""
