#!/bin/bash

# ==========================================
# 🚀 TRADAMIND AUTOMATIC DEPLOYMENT SCRIPT
# ==========================================

COMMIT_MSG=${1:-"Update: System synchronization and optimization"}
SSH_KEY="~/Documents/market_dashboard/Oracle_Keys/ssh-key-2025-05-06.pem"
SERVER_IP="143.47.186.148"
PM2_PATH="/home/ubuntu/.nvm/versions/node/v20.19.5/bin/pm2"

echo "📦 1. Committing & Pushing to GitHub..."
git add .
git commit -m "$COMMIT_MSG"
git push origin main

echo "🌐 2. Updating Live Server via SSH..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$SERVER_IP "
    cd ~/antigravity-trading-tool && \
    git fetch origin main && \
    git reset --hard origin/main && \
    git clean -fd && \
    cd frontend/trading-tool-frontend && \
    $PM2_PATH restart frontend || $PM2_PATH start 'npx serve out -p 5006 -s' --name 'frontend'
"

echo "🧠 3. Triggering AI Agents on Live Database..."
ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$SERVER_IP "
    cd ~/antigravity-trading-tool/backend/trading-tool-backend/backend && \
    export PYTHONPATH=\$PYTHONPATH:\$(pwd)/.. && \
    python3 -c 'from ai_agents.market_ai_agent import run_market_agent; \
               from ai_agents.macro_ai_agent import run_macro_agent; \
               from ai_agents.technical_ai_agent import run_technical_agent; \
               from ai_agents.setup_ai_agent import run_setup_agent; \
               UID=30; \
               run_market_agent(user_id=UID); \
               run_macro_agent(user_id=UID); \
               run_technical_agent(user_id=UID); \
               run_setup_agent(user_id=UID);'
"

echo "✅ DEPLOYMENT COMPLETE! Tradamind.com is up-to-date."
