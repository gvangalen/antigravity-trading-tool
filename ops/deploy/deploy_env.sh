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
STRICT_EXTERNAL_SMOKE="${STRICT_EXTERNAL_SMOKE:-false}"
DEPLOY_COMPONENT_SET="${DEPLOY_COMPONENT_SET:-full}"
AUTO_ROLLBACK_ON_FAILURE="${AUTO_ROLLBACK_ON_FAILURE:-true}"
MIGRATION_COMMAND_TIMEOUT_SECONDS="${MIGRATION_COMMAND_TIMEOUT_SECONDS:-180}"
# A Celery worker is reported online by PM2 before its task registry is ready.
# Production cold starts have taken just over a minute, so keep the real
# deep-health gate but give all workers enough time to finish initializing.
# Cold PM2 restarts initialize the four Celery workers sequentially. Keep the
# deploy gate alive until the last worker can register with Redis/health.
DEEP_HEALTH_ATTEMPTS="${DEEP_HEALTH_ATTEMPTS:-30}"
DEEP_HEALTH_RETRY_DELAY_SECONDS="${DEEP_HEALTH_RETRY_DELAY_SECONDS:-10}"
# A production cold start can take more than two minutes while routers and
# worker-facing dependencies initialize. Do not tear down a healthy startup
# before it has had a chance to bind and answer the lightweight health check.
BACKEND_INITIAL_LISTEN_ATTEMPTS="${BACKEND_INITIAL_LISTEN_ATTEMPTS:-180}"
BACKEND_INITIAL_HEALTH_ATTEMPTS="${BACKEND_INITIAL_HEALTH_ATTEMPTS:-90}"
BACKEND_RECOVERY_LISTEN_ATTEMPTS="${BACKEND_RECOVERY_LISTEN_ATTEMPTS:-180}"
BACKEND_RECOVERY_HEALTH_ATTEMPTS="${BACKEND_RECOVERY_HEALTH_ATTEMPTS:-90}"
SSH_ARGS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=no
  -o ConnectTimeout=20
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=20
)

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
if [ "$(lower_bool "${SKIP_GIT_PUSH:-false}")" = "true" ]; then
  echo "ℹ️ Git push skipped by orchestrator; deploying checked-out HEAD."
else
  if ! git diff --cached --quiet; then
    git commit -m "$COMMIT_MSG"
  elif ! git diff --quiet; then
    echo "⚠️ Working tree has unstaged changes; deploy_env.sh will deploy the current HEAD only." >&2
  fi
  git push origin HEAD
fi

TARGET_COMMIT="$(git rev-parse --short HEAD)"
TARGET_COMMIT_FULL="$(git rev-parse HEAD)"
BUILD_TIMESTAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
REMOTE_LAST_GOOD="$(
  ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP" "
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

if ! ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP" "
  set -euo pipefail
  export PATH=$NODE_BIN:\$PATH
  export APP_ENV=$ENVIRONMENT
  export BACKEND_PORT=$BACKEND_PORT
  export FRONTEND_PORT=$FRONTEND_PORT
  export MIGRATION_COMMAND_TIMEOUT_SECONDS=$MIGRATION_COMMAND_TIMEOUT_SECONDS
  export TRADAMIND_BUILD_COMMIT_SHA=$TARGET_COMMIT_FULL
  export TRADAMIND_BUILD_TIME=$BUILD_TIMESTAMP_UTC
  cd $REMOTE_DIR
  ENV_FILE="\$HOME/.secrets/trading.env"
  if [ -f "\$ENV_FILE" ]; then
    set -o allexport
    source "\$ENV_FILE"
    set +o allexport
  fi
  if [ -z "\${TWELVE_DATA_API_KEY:-}" ]; then
    echo \"❌ TWELVE_DATA_API_KEY ontbreekt in runtime env (\$ENV_FILE).\" >&2
    exit 1
  fi
  mkdir -p $DEPLOY_STATE_DIR
  printf '%s\n' '$ROLLBACK_COMMIT' > ${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT
  PREVIOUS_FRONTEND_STATIC=\"\$(mktemp -d /tmp/tradamind-static-backup.XXXXXX)\"
  cleanup_previous_frontend_static() {
    rm -rf \"\$PREVIOUS_FRONTEND_STATIC\"
  }
  trap cleanup_previous_frontend_static EXIT
  if [ -d frontend/trading-tool-frontend/out/_next/static ]; then
    cp -R frontend/trading-tool-frontend/out/_next/static/. \"\$PREVIOUS_FRONTEND_STATIC/\" 2>/dev/null || true
  fi
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
  mkdir -p frontend/trading-tool-frontend/out/_next/static
  if [ -n \"\$(find \"\$PREVIOUS_FRONTEND_STATIC\" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)\" ]; then
    cp -Rn \"\$PREVIOUS_FRONTEND_STATIC/.\" frontend/trading-tool-frontend/out/_next/static/
    echo \"✅ Previous static chunks retained for browsers opened before this deploy.\"
  fi
  bash ./ops/deploy/bootstrap_runtime_dependencies.sh

  cd backend/trading-tool-backend
  run_migration() {
    local migration=\"\$1\"
    echo \"🗃️ Applying migration \$migration (timeout \${MIGRATION_COMMAND_TIMEOUT_SECONDS}s)...\"
    timeout --foreground \"\${MIGRATION_COMMAND_TIMEOUT_SECONDS}s\" \\
      python3 backend/scripts/run_sql_migration.py \"\$migration\"
  }
  run_migration backend/scripts/migrations/2026_05_18_manual_order_idempotency.py
  run_migration backend/scripts/migrations/2026_05_24_platform_hardening_phase1.py
  run_migration backend/scripts/migrations/2026_05_24_runtime_ddl_to_migrations.py
  run_migration backend/scripts/migrations/2026_05_26_auth_refresh_sessions.py
  run_migration backend/scripts/migrations/2026_06_10_finn_product_events.py
  run_migration backend/scripts/migrations/2026_06_24_mobile_push_tokens.py
  run_migration backend/scripts/migrations/2026_06_28_auth_password_reset_tokens.py
  run_migration backend/scripts/migrations/2026_07_20_asset_scoped_ai_insights.py
  run_migration backend/scripts/migrations/2026_07_20_finn_response_trace_index.py
  run_migration backend/scripts/migrations/2026_08_05_asset_catalog.py
  run_migration backend/scripts/migrations/2026_08_05_asset_catalog_provider_routing.py
  run_migration backend/scripts/migrations/2026_08_06_user_indicator_symbol_overrides.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_foundation.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_tool_registry.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_evidence_state.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_orchestrator.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_policy_confirmation.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_reasoning.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_verified_delivery.py
  run_migration backend/scripts/migrations/2026_08_17_finn_v2_evals_cutover_execution.py
  run_migration backend/scripts/migrations/2026_08_18_finn_v2_capability_mode.py
  run_migration backend/scripts/migrations/2026_08_18_finn_v2_typed_operation_modes.py
  run_migration backend/scripts/migrations/2026_08_20_finn_v2_canonical_modes.py
  run_migration backend/scripts/migrations/2026_08_22_finn_v2_run_lifecycle_statuses.py
  run_migration backend/scripts/migrations/2026_08_22_finn_v2_dispatch_outbox.py
  run_migration backend/scripts/migrations/2026_08_22_finn_v2_remove_legacy_fact_mode.py
  run_migration backend/scripts/migrations/2026_08_23_finn_v2_conversation_context.py
  run_migration backend/scripts/migrations/2026_08_23_finn_v2_evidence_information_scope.py
  run_migration backend/scripts/migrations/2026_08_23_finn_v2_artifact_operation_contract.py
  run_migration backend/scripts/migrations/2026_08_25_canonical_user_indicator_configs.py
  run_migration backend/scripts/migrations/2026_08_25_finn_v2_indicator_config_reconciliation.py
  echo \"🩺 Checking FINN V2 schema contract before process startup...\"
  timeout --foreground "\${MIGRATION_COMMAND_TIMEOUT_SECONDS}s" \
    python3 -m backend.scripts.check_finn_v2_schema

  cd ../../frontend/trading-tool-frontend
  rm -rf .next
  git clean -fd out/_next/static
  if [ ! -f out/index.html ]; then
    echo \"❌ Prebuilt frontend export missing: frontend/trading-tool-frontend/out/index.html\" >&2
    exit 1
  fi
  echo \"✅ Using prebuilt frontend export from git (server build skipped). Old static chunks removed to avoid mixed-build clients.\"
  cat > out/build-info.json <<EOF
{\"service\":\"frontend\",\"commit_sha\":\"$TARGET_COMMIT_FULL\",\"build_time\":\"$BUILD_TIMESTAMP_UTC\"}
EOF

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

  for_each_pm2_app() {
    local csv=\"\${1:-}\"
    local callback=\"\${2:-}\"
    local app
    IFS=',' read -ra pm2_apps <<< \"\$csv\"
    for app in \"\${pm2_apps[@]}\"; do
      app=\"\$(printf '%s' \"\$app\" | xargs)\"
      if [ -n \"\$app\" ]; then
        \"\$callback\" \"\$app\"
      fi
    done
  }

  pm2_delete_app() {
    local app=\"\$1\"
    pm2 delete \"\$app\" || true
  }

  pm2_start_app() {
    local app=\"\$1\"
    pm2 start $PM2_CONFIG --only \"\$app\" --update-env
  }

  restart_backend_app() {
    echo \"⚠️ Restarting backend app ${BACKEND_APP} to recover startup/bind drift.\" >&2
    for_each_pm2_app \"$BACKEND_APP\" pm2_delete_app
    for_each_pm2_app \"$BACKEND_APP\" pm2_start_app
  }

  stabilize_backend_app() {
    if wait_for_backend_listen "$BACKEND_INITIAL_LISTEN_ATTEMPTS" && wait_for_backend_health "$BACKEND_INITIAL_HEALTH_ATTEMPTS"; then
      return 0
    fi
    restart_backend_app
    wait_for_backend_listen "$BACKEND_RECOVERY_LISTEN_ATTEMPTS"
    wait_for_backend_health "$BACKEND_RECOVERY_HEALTH_ATTEMPTS"
  }

  rebuild_pm2_processes() {
    echo \"⚠️ Rebuilding PM2 process list with phased startup.\" >&2
    if [ \"$DEPLOY_COMPONENT_SET\" = \"backend_only\" ]; then
      for_each_pm2_app \"$BACKEND_APP\" pm2_delete_app
    else
      for_each_pm2_app \"$CORE_PM2_APPS\" pm2_delete_app
      for_each_pm2_app \"$AUX_PM2_APPS\" pm2_delete_app
    fi
    for_each_pm2_app \"$CORE_PM2_APPS\" pm2_start_app
    if ! stabilize_backend_app; then
      echo \"❌ Backend did not become healthy during phased core startup.\" >&2
      exit 1
    fi
    if [ -n \"$AUX_PM2_APPS\" ]; then
      for_each_pm2_app \"$AUX_PM2_APPS\" pm2_start_app
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
    ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP" \
      "cd $REMOTE_DIR && ENVIRONMENT=$ENVIRONMENT bash ./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" || true
  fi
  echo "Rollback command:" >&2
  echo "  ${ROLLBACK_COMMAND}" >&2
  exit 1
fi

echo "🌤️ 3. Verifying external smoke for ${ENVIRONMENT}..."
check_external() {
  local url="$1"
  local expected_csv="$2"
  local label="$3"
  local attempts="${4:-20}"
  local method="${5:-GET}"
  local header_dump="/tmp/tradamind_external_check_headers.txt"
  local body_dump="/tmp/tradamind_external_check_body.txt"

  for attempt in $(seq 1 "$attempts"); do
    rm -f "$header_dump" "$body_dump"

    local status
    if [ "$method" = "HEAD" ]; then
      status="$(curl -sS -I -D "$header_dump" -o /dev/null -w '%{http_code}' "$url" || true)"
    else
      status="$(curl -sS -D "$header_dump" -o "$body_dump" -w '%{http_code}' "$url" || true)"
    fi

    IFS=',' read -ra expected_statuses <<< "$expected_csv"
    local expected
    for expected in "${expected_statuses[@]}"; do
      expected="$(printf '%s' "$expected" | xargs)"
      if [ -n "$expected" ] && [ "$status" = "$expected" ]; then
        echo "✅ ${label}: ${status}"
        return 0
      fi
    done

    local location
    location="$(awk 'BEGIN{IGNORECASE=1}/^location:/{sub(/\r$/,"",$0); sub(/^location:[[:space:]]*/,"",$0); print; exit}' "$header_dump" 2>/dev/null || true)"
    if [ -n "$location" ]; then
      echo "⏳ Waiting for ${label} (attempt ${attempt}/${attempts}, got ${status}, location=${location})..." >&2
    else
      echo "⏳ Waiting for ${label} (attempt ${attempt}/${attempts}, got ${status})..." >&2
    fi
    sleep 3
  done

  echo "❌ ${label} did not reach expected statuses [${expected_csv}]." >&2
  if [ -f "$header_dump" ]; then
    echo "Response headers:" >&2
    head -n 20 "$header_dump" >&2 || true
  fi
  if [ "$method" != "HEAD" ] && [ -f "$body_dump" ]; then
    echo "Response body preview:" >&2
    head -c 500 "$body_dump" >&2 || true
    echo >&2
  fi
  return 1
}

external_smoke_failed=false
if ! check_external "${EXTERNAL_BASE_URL}/api/health" "200" "external api health" 20 GET \
  || ! check_external "${EXTERNAL_BASE_URL}/api/system/health" "401" "external deep health gate" 20 GET \
  || ! check_external "${EXTERNAL_BASE_URL}/report" "200,302,307,308" "external report" 20 HEAD; then
  external_smoke_failed=true
fi

if [ "$external_smoke_failed" = "true" ]; then
  if [ "$(lower_bool "${STRICT_EXTERNAL_SMOKE}")" = "true" ]; then
    echo "❌ External smoke failed for ${TARGET_COMMIT}." >&2
    if [ "$(lower_bool "${AUTO_ROLLBACK_ON_FAILURE}")" = "true" ]; then
      echo "↩️ Auto rollback naar ${ROLLBACK_COMMIT}..." >&2
      ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP" \
        "cd $REMOTE_DIR && ENVIRONMENT=$ENVIRONMENT bash ./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" || true
    fi
    echo "Rollback command:" >&2
    echo "  ${ROLLBACK_COMMAND}" >&2
    exit 1
  fi
  echo "⚠️ External smoke failed for ${TARGET_COMMIT}, but rollout continues because STRICT_EXTERNAL_SMOKE=false." >&2
fi

ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP" "
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
