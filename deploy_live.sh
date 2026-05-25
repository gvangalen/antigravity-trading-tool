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
  expected_pm2_apps='frontend backend celery-worker-default celery-worker-market-portfolio celery-worker-scoring-execution celery-worker-ai-reporting celery-beat'
  check_pm2_apps_online() {
    pm2 jlist >/tmp/tradamind_pm2_jlist.json
    EXPECTED_PM2_APPS=\"\$expected_pm2_apps\" python3 - <<'PY'
import json
import os
import sys

expected = os.environ.get('EXPECTED_PM2_APPS', '').split()
with open('/tmp/tradamind_pm2_jlist.json', 'r', encoding='utf-8') as handle:
    processes = json.load(handle)

by_name = {process.get('name'): process for process in processes}
missing = [name for name in expected if name not in by_name]
not_online = {
    name: ((by_name.get(name) or {}).get('pm2_env') or {}).get('status')
    for name in expected
    if name in by_name and ((by_name.get(name) or {}).get('pm2_env') or {}).get('status') != 'online'
}

if missing or not_online:
    print('❌ PM2 gate failed: missing={} not_online={}'.format(missing, not_online), file=sys.stderr)
    sys.exit(1)

print('✅ PM2 gate passed: all expected apps online.')
PY
  }

  pm2 delete celery-worker || true
  if pm2 startOrReload ecosystem.config.js --update-env && check_pm2_apps_online; then
    echo \"✅ PM2 reload completed with all expected apps online.\"
  else
    echo \"⚠️ PM2 reload did not leave every expected app online; rebuilding process list.\" >&2
    pm2 delete all || true
    pm2 start ecosystem.config.js --update-env
    check_pm2_apps_online
  fi
  pm2 save --force

  health_ready=false
  for i in \$(seq 1 90); do
    if curl --max-time 5 -fsS http://127.0.0.1:8000/api/health >/tmp/tradamind_health.json 2>/dev/null; then
      health_ready=true
      break
    fi
    sleep 2
  done
  if [ \"\$health_ready\" != \"true\" ]; then
    echo \"❌ Lightweight health did not become ready within deploy timeout.\" >&2
    exit 1
  fi
  curl --max-time 10 -fsS http://127.0.0.1:8000/api/health
  echo
  curl --max-time 30 -fsS http://127.0.0.1:8000/api/system/health >/tmp/tradamind_deep_health.json
  cat /tmp/tradamind_deep_health.json
  echo
  python3 - <<'PY'
import json
import os
import sys

with open('/tmp/tradamind_deep_health.json', 'r', encoding='utf-8') as handle:
    payload = json.load(handle)

status = payload.get('status')
components = payload.get('components') or {}
blocking = {
    name: data
    for name, data in components.items()
    if (data or {}).get('status') in {'down', 'error'}
}

if blocking:
    print('❌ Deep health gate failed: blocking components={}'.format(blocking), file=sys.stderr)
    sys.exit(1)

if status == 'degraded':
    message = '⚠️ Deep health is degraded; rollout continues because STRICT_DEEP_HEALTH=false.'
    if os.getenv('STRICT_DEEP_HEALTH', 'false').lower() in {'1', 'true', 'yes'}:
        print('❌ Deep health gate failed: status=degraded and STRICT_DEEP_HEALTH=true', file=sys.stderr)
        sys.exit(1)
    print(message, file=sys.stderr)
elif status != 'ok':
    print('❌ Deep health gate failed: status={}'.format(status), file=sys.stderr)
    sys.exit(1)
else:
    print('✅ Deep health gate passed.')
PY
  curl --max-time 10 -fsSI http://127.0.0.1:5002/report | head -n 1
"

echo "✅ Deployment complete for ${TARGET_COMMIT}."
echo "Rollback if needed:"
echo "  ssh -i \"$SSH_KEY\" ubuntu@$SERVER_IP 'cd $REMOTE_DIR && git reset --hard <previous_commit> && pm2 restart ecosystem.config.js --update-env'"
