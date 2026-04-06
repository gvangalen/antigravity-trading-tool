#!/bin/bash
set -e

echo "📦 Start frontend deploy op $(date)"

# -------------------------
# 1. Load NVM
# -------------------------
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"

nvm use 20 || { echo "❌ Node 20 niet beschikbaar"; exit 1; }
echo "Node: $(node -v)"

# -------------------------
# 2. Ga naar project
# -------------------------
cd ~/trading-tool-frontend || { echo "❌ Map niet gevonden"; exit 1; }

# -------------------------
# 3. Stop frontend (safe)
# -------------------------
if pm2 list | grep -q frontend; then
  echo "🧹 Stop frontend..."
  pm2 stop frontend
  pm2 delete frontend
fi

# -------------------------
# 4. Pull exact GitHub state
# -------------------------
echo "⬇️ Sync met GitHub..."
git fetch origin main
git reset --hard origin/main

# -------------------------
# 5. Opschonen build artifacts
# -------------------------
echo "🧨 Verwijder .next build"
rm -rf .next

# -------------------------
# 6. Install EXACT dependencies
# -------------------------
echo "📦 Install dependencies (lockfile leidend)"
npm ci --legacy-peer-deps

# -------------------------
# 7. Build
# -------------------------
echo "🏗️ Build frontend..."
npm run build

# -------------------------
# 8. Start via PM2
# -------------------------
echo "🚀 Start frontend via PM2..."
pm2 start npm --name frontend -- run start
pm2 save

echo "✅ Frontend deploy klaar op $(date)"
