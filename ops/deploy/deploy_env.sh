#!/bin/bash
set -euo pipefail

ENVIRONMENT="${1:-}"
BRANCH="${2:-}"
COMMIT_MSG="${3:-Deploy ${ENVIRONMENT}}"

if [ -z "$ENVIRONMENT" ] || [ -z "$BRANCH" ]; then
  echo "Usage: $0 <environment> <branch> [commit message]" >&2
  exit 1
fi

SSH_KEY="${SSH_KEY:-$HOME/Documents/market_dashboard/Oracle_Keys/ssh-key-2025-05-06.pem}"
SERVER_IP="${SERVER_IP:-}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
NODE_BIN="${NODE_BIN:-/home/ubuntu/.nvm/versions/node/v20.19.5/bin}"
STRICT_DEEP_HEALTH="${STRICT_DEEP_HEALTH:-false}"
DEPLOY_COMPONENT_SET="${DEPLOY_COMPONENT_SET:-full}"
AUTO_ROLLBACK_ON_FAILURE="${AUTO_ROLLBACK_ON_FAILURE:-true}"
DEEP_HEALTH_ATTEMPTS="${DEEP_HEALTH_ATTEMPTS:-6}"
DEEP_HEALTH_RETRY_DELAY_SECONDS="${DEEP_HEALTH_RETRY_DELAY_SECONDS:-10}"

lower_bool() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

case "$ENVIRONMENT" in
  production)
    PM2_CONFIG="ecosystem.production.config.js"
    PM2_DEPLOY_MODE="${PM2_DEPLOY_MODE:-phased}"
    BACKEND_APP="${BACKEND_APP:-backend}"
    BACKEND_PORT="${BACKEND_PORT:-8000}"
    FRONTEND_PORT="${FRONTEND_PORT:-5002}"
    CORE_PM2_APPS="${CORE_PM2_APPS:-frontend,backend}"
    AUX_PM2_APPS="${AUX_PM2_APPS:-celery-worker-default,celery-worker-market-portfolio,celery-worker-scoring-execution,celery-worker-ai-reporting,celery-beat}"
    EXPECTED_PM2_APPS="${EXPECTED_PM2_APPS:-frontend backend celery-worker-default celery-worker-market-portfolio celery-worker-scoring-execution celery-worker-ai-reporting celery-beat}"
    DEPLOY_REF="origin/${BRANCH}"
    EXTERNAL_BASE_URL="${EXTERNAL_BASE_URL:-https://tradamind.com}"
    ;;
  staging)
    PM2_CONFIG="ecosystem.staging.config.js"
    PM2_DEPLOY_MODE="${PM2_DEPLOY_MODE:-reload_then_fallback}"
    BACKEND_APP="${BACKEND_APP:-backend-staging}"
    BACKEND_PORT="${BACKEND_PORT:-8100}"
    FRONTEND_PORT="${FRONTEND_PORT:-5102}"
    CORE_PM2_APPS="${CORE_PM2_APPS:-frontend-staging,backend-staging}"
    AUX_PM2_APPS="${AUX_PM2_APPS:-celery-worker-default-staging,celery-worker-market-portfolio-staging,celery-worker-scoring-execution-staging,celery-worker-ai-reporting-staging,celery-beat-staging}"
    EXPECTED_PM2_APPS="${EXPECTED_PM2_APPS:-frontend-staging backend-staging celery-worker-default-staging celery-worker-market-portfolio-staging celery-worker-scoring-execution-staging celery-worker-ai-reporting-staging celery-beat-staging}"
    DEPLOY_REF="origin/${BRANCH}"
    EXTERNAL_BASE_URL="${EXTERNAL_BASE_URL:-https://staging.tradamind.com}"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT" >&2
    exit 1
    ;;
esac

if [ -z "$SERVER_IP" ]; then
  echo "SERVER_IP is required for $ENVIRONMENT deploy." >&2
  exit 1
fi

DEPLOY_STATE_DIR="ops/deploy/${ENVIRONMENT}"

if [ "$DEPLOY_COMPONENT_SET" = "backend_only" ]; then
  CORE_PM2_APPS="${BACKEND_ONLY_PM2_APPS:-backend}"
  AUX_PM2_APPS=""
  EXPECTED_PM2_APPS="${BACKEND_ONLY_EXPECTED_PM2_APPS:-backend}"
fi

echo "📦 1. Committing & pushing to GitHub for ${ENVIRONMENT}..."
if ! git diff --cached --quiet; then
  git commit -m "$COMMIT_MSG"
elif ! git diff --quiet; then
  echo "⚠️ Working tree has unstaged changes; deploy_env.sh will deploy the current HEAD only." >&2
fi
git push origin HEAD

TARGET_COMMIT="$(git rev-parse --short HEAD)"
REMOTE_LAST_GOOD="$(
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" "
    cd $REMOTE_DIR 2>/dev/null || exit 0
    if [ -f ${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT ]; then
      cat ${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT
    else
      git rev-parse --short HEAD 2>/dev/null || true
    fi
  " 2>/dev/null | tail -n 1
)"
ROLLBACK_COMMIT="${REMOTE_LAST_GOOD:-$(git rev-parse --short HEAD~1 2>/dev/null || git rev-parse --short HEAD)}"
ROLLBACK_COMMAND="ssh -i \"$SSH_KEY\" ubuntu@$SERVER_IP 'cd $REMOTE_DIR && ENVIRONMENT=$ENVIRONMENT bash ./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT'"

echo "🌐 2. Deploying ${ENVIRONMENT} commit ${TARGET_COMMIT}..."
echo "🧭 Previous known-good commit: ${ROLLBACK_COMMIT}"

if ! ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" "
  set -euo pipefail
  export PATH=$NODE_BIN:\$PATH
  export APP_ENV=$ENVIRONMENT
  export BACKEND_PORT=$BACKEND_PORT
  export FRONTEND_PORT=$FRONTEND_PORT
  cd $REMOTE_DIR
  mkdir -p $DEPLOY_STATE_DIR
  printf '%s\n' '$ROLLBACK_COMMIT' > ${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT
  sync_git_ref() {
    for attempt in \$(seq 1 5); do
      rm -f .git/index.lock .git/refs/remotes/origin/$BRANCH.lock .git/refs/remotes/origin/$BRANCH
      if git fetch origin $BRANCH; then
        return 0
      fi
      echo \"⏳ Waiting for git lock to clear (attempt \$attempt/5)...\" >&2
      sleep 2
    done
    return 1
  }
  sync_git_ref
  git reset --hard $DEPLOY_REF
  bash ./ops/deploy/bootstrap_runtime_dependencies.sh

  cd backend/trading-tool-backend
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_18_manual_order_idempotency.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_platform_hardening_phase1.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_runtime_ddl_to_migrations.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_26_auth_refresh_sessions.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_06_10_finn_product_events.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_06_24_mobile_push_tokens.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_06_28_auth_password_reset_tokens.py
  python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_07_20_asset_scoped_ai_insights.py

  cd ../../frontend/trading-tool-frontend
  rm -rf .next
  if [ ! -f out/index.html ]; then
    echo \"❌ Prebuilt frontend export missing: frontend/trading-tool-frontend/out/index.html\" >&2
    exit 1
  fi
  echo \"✅ Using prebuilt frontend export from git (server build skipped).\"

  cd ../..
  if [ ! -f \"$PM2_CONFIG\" ]; then
    echo \"❌ PM2 config $PM2_CONFIG not found on remote host.\" >&2
    exit 1
  fi
  check_pm2_apps_online() {
    for attempt in \$(seq 1 20); do
      pm2 jlist >/tmp/tradamind_pm2_jlist.json
      if EXPECTED_PM2_APPS=\"$EXPECTED_PM2_APPS\" python3 - <<'PY'
import json
import os
import sys

expected = os.environ.get('EXPECTED_PM2_APPS', '').split()
with open('/tmp/tradamind_pm2_jlist.json', 'r', encoding='utf-8') as handle:
    raw = handle.read()

json_payload = None
lines = raw.splitlines()
for index, line in enumerate(lines):
    stripped = line.lstrip()
    if stripped == '[' or stripped.startswith('[{'):
        json_payload = '\n'.join(lines[index:])
        break

if not json_payload:
    print('❌ PM2 gate failed: jlist JSON payload not found', file=sys.stderr)
    sys.exit(1)

processes = json.loads(json_payload)
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
      then
        return 0
      fi
      echo \"⏳ Waiting for PM2 apps to settle (attempt \$attempt/20)...\" >&2
      sleep 3
    done
    return 1
  }

  wait_for_backend_health() {
    local attempts=\"\${1:-120}\"
    for i in \$(seq 1 \"\$attempts\"); do
      if curl --max-time 5 -fsS -H 'Host: 127.0.0.1' http://127.0.0.1:$BACKEND_PORT/api/health >/tmp/tradamind_health.json 2>/dev/null; then
        return 0
      fi
      sleep 2
    done
    return 1
  }

  wait_for_backend_listen() {
    local attempts=\"\${1:-60}\"
    for i in \$(seq 1 \"\$attempts\"); do
      if ss -ltn | grep -q \":$BACKEND_PORT \"; then
        return 0
      fi
      sleep 2
    done
    return 1
  }

  restart_backend_app() {
    echo \"⚠️ Restarting backend app ${BACKEND_APP} to recover startup/bind drift.\" >&2
    pm2 delete \"$BACKEND_APP\" || true
    pm2 start $PM2_CONFIG --only \"$BACKEND_APP\" --update-env
  }

  stabilize_backend_app() {
    if wait_for_backend_listen 120 && wait_for_backend_health 60; then
      return 0
    fi
    restart_backend_app
    wait_for_backend_listen 150
    wait_for_backend_health 120
  }

  rebuild_pm2_processes() {
    echo \"⚠️ Rebuilding PM2 process list with phased startup.\" >&2
    if [ \"$DEPLOY_COMPONENT_SET\" = \"backend_only\" ]; then
      pm2 delete backend || true
    else
      pm2 delete all || true
    fi
    pm2 start $PM2_CONFIG --only \"$CORE_PM2_APPS\" --update-env
    if ! stabilize_backend_app; then
      echo \"❌ Backend did not become healthy during phased core startup.\" >&2
      exit 1
    fi
    if [ -n \"$AUX_PM2_APPS\" ]; then
      pm2 start $PM2_CONFIG --only \"$AUX_PM2_APPS\" --update-env
    fi
    check_pm2_apps_online
  }

  if [ \"$PM2_DEPLOY_MODE\" = \"phased\" ]; then
    rebuild_pm2_processes
  else
    if pm2 startOrReload $PM2_CONFIG --update-env && check_pm2_apps_online; then
      echo \"✅ PM2 reload completed with all expected apps online.\"
    else
      rebuild_pm2_processes
    fi

    if ! stabilize_backend_app; then
      echo \"⚠️ Backend did not become healthy after reload; retrying with clean PM2 rebuild.\" >&2
      rebuild_pm2_processes
    fi
  fi

  if ! stabilize_backend_app; then
    echo \"❌ Lightweight health did not become ready after clean PM2 rebuild.\" >&2
    exit 1
  fi

  pm2 save --force

  health_ready=false
  for i in \$(seq 1 240); do
    if curl --max-time 5 -fsS -H 'Host: 127.0.0.1' http://127.0.0.1:$BACKEND_PORT/api/health >/tmp/tradamind_health.json 2>/dev/null; then
      health_ready=true
      break
    fi
    sleep 2
  done
  if [ \"\$health_ready\" != \"true\" ]; then
    echo \"❌ Lightweight health did not become ready within deploy timeout.\" >&2
    exit 1
  fi
  curl --max-time 10 -fsS -H 'Host: 127.0.0.1' http://127.0.0.1:$BACKEND_PORT/api/health
  echo
  deep_health_ready=false
  for attempt in \$(seq 1 \"$DEEP_HEALTH_ATTEMPTS\"); do
    if curl --max-time 45 -fsS -H 'Host: 127.0.0.1' http://127.0.0.1:$BACKEND_PORT/api/system/health >/tmp/tradamind_deep_health.json; then
      cat /tmp/tradamind_deep_health.json
      echo
      if python3 - <<'PY'
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
    if os.getenv('STRICT_DEEP_HEALTH', 'false').lower() in {'1', 'true', 'yes'}:
        print('❌ Deep health gate failed: status=degraded and STRICT_DEEP_HEALTH=true', file=sys.stderr)
        sys.exit(1)
    print('⚠️ Deep health is degraded; rollout continues because STRICT_DEEP_HEALTH=false.', file=sys.stderr)
elif status != 'ok':
    print('❌ Deep health gate failed: status={}'.format(status), file=sys.stderr)
    sys.exit(1)
else:
    print('✅ Deep health gate passed.')
PY
      then
        deep_health_ready=true
        break
      fi
    fi
    echo \"⏳ Deep health not ready yet (attempt \$attempt/$DEEP_HEALTH_ATTEMPTS); waiting ${DEEP_HEALTH_RETRY_DELAY_SECONDS}s...\" >&2
    sleep \"$DEEP_HEALTH_RETRY_DELAY_SECONDS\"
  done
  if [ \"\$deep_health_ready\" != \"true\" ]; then
    echo \"❌ Deep health did not stabilize within deploy retry window.\" >&2
    exit 1
  fi
  if [ \"$DEPLOY_COMPONENT_SET\" != \"backend_only\" ]; then
    curl --max-time 10 -fsSI http://127.0.0.1:$FRONTEND_PORT/report | head -n 1
  fi
"; then
  echo "❌ ${ENVIRONMENT} deployment failed for ${TARGET_COMMIT}." >&2
  if [ "$(lower_bool "${AUTO_ROLLBACK_ON_FAILURE}")" = "true" ]; then
    echo "↩️ Auto rollback naar ${ROLLBACK_COMMIT}..." >&2
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" \
      "cd $REMOTE_DIR && ENVIRONMENT=$ENVIRONMENT bash ./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" || true
  fi
  echo "Rollback command:" >&2
  echo "  ${ROLLBACK_COMMAND}" >&2
  exit 1
fi

echo "🌤️ 3. Verifying external smoke for ${ENVIRONMENT}..."
check_external() {
  local url="$1"
  local expected="$2"
  local label="$3"
  local attempts="${4:-20}"
  for attempt in $(seq 1 "$attempts"); do
    local status
    status="$(curl -sS -o /tmp/tradamind_external_check.txt -w '%{http_code}' "$url" || true)"
    if [ "$status" = "$expected" ]; then
      echo "✅ ${label}: ${status}"
      return 0
    fi
    echo "⏳ Waiting for ${label} (attempt ${attempt}/${attempts}, got ${status})..." >&2
    sleep 3
  done
  echo "❌ ${label} did not reach expected status ${expected}." >&2
  if [ -f /tmp/tradamind_external_check.txt ]; then
    head -c 500 /tmp/tradamind_external_check.txt >&2 || true
    echo >&2
  fi
  return 1
}

if ! check_external "${EXTERNAL_BASE_URL}/api/health" "200" "external api health" \
  || ! check_external "${EXTERNAL_BASE_URL}/api/system/health" "401" "external deep health gate" \
  || ! check_external "${EXTERNAL_BASE_URL}/report" "200" "external report"; then
  echo "❌ External smoke failed for ${TARGET_COMMIT}." >&2
  if [ "$(lower_bool "${AUTO_ROLLBACK_ON_FAILURE}")" = "true" ]; then
    echo "↩️ Auto rollback naar ${ROLLBACK_COMMIT}..." >&2
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" \
      "cd $REMOTE_DIR && ENVIRONMENT=$ENVIRONMENT bash ./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" || true
  fi
  echo "Rollback command:" >&2
  echo "  ${ROLLBACK_COMMAND}" >&2
  exit 1
fi

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$SERVER_IP" "
  set -euo pipefail
  cd $REMOTE_DIR
  printf '%s\n' '$TARGET_COMMIT' > ${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT
  printf '%s\n' '$ROLLBACK_COMMIT' > ${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT
  if [ -d /var/www/tradamind/ops/deploy ]; then
    printf '%s\n' '$TARGET_COMMIT' | sudo tee /var/www/tradamind/ops/deploy/LAST_GOOD_COMMIT >/dev/null
    printf '%s\n' '$ROLLBACK_COMMIT' | sudo tee /var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT >/dev/null
  fi
"

echo "✅ ${ENVIRONMENT} deployment complete for ${TARGET_COMMIT}."
echo "Rollback if needed:"
echo "  ${ROLLBACK_COMMAND}"
