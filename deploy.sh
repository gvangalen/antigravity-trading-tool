#!/bin/bash
set -e

echo "🚀 AUTO DEPLOY START"

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
echo "✅ DEPLOY DONE"
