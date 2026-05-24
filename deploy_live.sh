#!/bin/bash
set -euo pipefail

# ==========================================
# 🚀 TRADAMIND PRODUCTION DEPLOYMENT SCRIPT
# ==========================================
# Deploys the current main branch to Oracle, runs explicit migrations, restarts
# PM2 services, and gates rollout on lightweight + deep health checks.

COMMIT_MSG=${1:-"Update: system synchronization"}
SSH_KEY="${SSH_KEY:-$HOME/Documents/market_dashboard/Oracle_Keys/ssh-key-2025-05-06.pem}"
SERVER_IP="${SERVER_IP:-143.47.186.148}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
NODE_BIN="${NODE_BIN:-/home/ubuntu/.nvm/versions/node/v18.20.8/bin}"
STRICT_DEEP_HEALTH="${STRICT_DEEP_HEALTH:-false}"

echo "📦 1. Committing & pushing to GitHub..."
git add .
if ! git diff --cached --quiet; then
  git commit -m "$COMMIT_MSG"
  git push origin main
else
  echo "No staged changes to commit."
fi

TARGET_COMMIT="$(git rev-parse --short HEAD)"
echo "🌐 2. Deploying commit ${TARGET_COMMIT} to Oracle..."

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" "
  set -euo pipefail
  export PATH=$NODE_BIN:\$PATH
  cd $REMOTE_DIR
  rm -f .git/index.lock .git/refs/remotes/origin/main
  git fetch origin main
  git reset --hard $TARGET_COMMIT

  cd backend/trading-tool-backend
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_18_manual_order_idempotency.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_platform_hardening_phase1.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_runtime_ddl_to_migrations.py

  cd ../..
  pm2 delete celery-worker || true
  pm2 startOrReload ecosystem.config.js --update-env || (pm2 delete all || true; pm2 start ecosystem.config.js --update-env)
  pm2 save

  for i in \$(seq 1 60); do
    if curl -fsS http://127.0.0.1:8000/api/health >/tmp/tradamind_health.json 2>/dev/null; then
      break
    fi
    sleep 2
  done
  curl -fsS http://127.0.0.1:8000/api/health
  echo
  curl -fsS http://127.0.0.1:8000/api/system/health >/tmp/tradamind_deep_health.json
  cat /tmp/tradamind_deep_health.json
  echo
  python3 - <<'PY'
import json
import os
import sys

with open("/tmp/tradamind_deep_health.json", "r", encoding="utf-8") as handle:
    payload = json.load(handle)

status = payload.get("status")
components = payload.get("components") or {}
blocking = {
    name: data
    for name, data in components.items()
    if (data or {}).get("status") in {"down", "error"}
}

if blocking:
    print(f"❌ Deep health gate failed: blocking components={blocking}", file=sys.stderr)
    sys.exit(1)

if status == "degraded":
    message = "⚠️ Deep health is degraded; rollout continues because STRICT_DEEP_HEALTH=false."
    if os.getenv("STRICT_DEEP_HEALTH", "false").lower() in {"1", "true", "yes"}:
        print("❌ Deep health gate failed: status=degraded and STRICT_DEEP_HEALTH=true", file=sys.stderr)
        sys.exit(1)
    print(message, file=sys.stderr)
elif status != "ok":
    print(f"❌ Deep health gate failed: status={status}", file=sys.stderr)
    sys.exit(1)
else:
    print("✅ Deep health gate passed.")
PY
  curl -fsSI http://127.0.0.1:5002/report | head -n 1
"

echo "✅ Deployment complete for ${TARGET_COMMIT}."
echo "Rollback if needed:"
echo "  ssh -i \"$SSH_KEY\" ubuntu@$SERVER_IP 'cd $REMOTE_DIR && git reset --hard <previous_commit> && pm2 restart ecosystem.config.js --update-env'"
