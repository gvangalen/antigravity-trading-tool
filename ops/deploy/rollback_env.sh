#!/bin/bash
set -euo pipefail

ENVIRONMENT="${1:-}"
ROLLBACK_COMMIT="${2:-}"

if [ -z "$ENVIRONMENT" ]; then
  echo "Usage: $0 <environment> [commit]" >&2
  exit 1
fi

REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
NODE_BIN="${NODE_BIN:-/home/ubuntu/.nvm/versions/node/v18.20.8/bin}"

case "$ENVIRONMENT" in
  production)
    PM2_CONFIG="ecosystem.production.config.js"
    BACKEND_PORT="${BACKEND_PORT:-8000}"
    FRONTEND_PORT="${FRONTEND_PORT:-5002}"
    EXPECTED_PM2_APPS="${EXPECTED_PM2_APPS:-frontend backend celery-worker-default celery-worker-market-portfolio celery-worker-scoring-execution celery-worker-ai-reporting celery-beat}"
    ;;
  staging)
    PM2_CONFIG="ecosystem.staging.config.js"
    BACKEND_PORT="${BACKEND_PORT:-8100}"
    FRONTEND_PORT="${FRONTEND_PORT:-5102}"
    EXPECTED_PM2_APPS="${EXPECTED_PM2_APPS:-frontend-staging backend-staging celery-worker-default-staging celery-worker-market-portfolio-staging celery-worker-scoring-execution-staging celery-worker-ai-reporting-staging celery-beat-staging}"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT" >&2
    exit 1
    ;;
esac

DEPLOY_STATE_DIR="ops/deploy/${ENVIRONMENT}"
CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"

export PATH="$NODE_BIN:$PATH"
export APP_ENV="$ENVIRONMENT"
export BACKEND_PORT
export FRONTEND_PORT
cd "$REMOTE_DIR"

if [ -z "$ROLLBACK_COMMIT" ]; then
  if [ ! -f "${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT" ]; then
    echo "❌ No rollback commit provided and ${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT is missing." >&2
    exit 1
  fi
  ROLLBACK_COMMIT="$(cat "${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT")"
fi

echo "↩️ Rolling ${ENVIRONMENT} back to ${ROLLBACK_COMMIT}..."
git fetch origin
git reset --hard "$ROLLBACK_COMMIT"

if [ ! -f "$PM2_CONFIG" ]; then
  if [ -f ecosystem.config.js ]; then
    echo "⚠️ PM2 config $PM2_CONFIG not found; falling back to ecosystem.config.js." >&2
    PM2_CONFIG="ecosystem.config.js"
  else
    echo "❌ PM2 config $PM2_CONFIG not found on remote host." >&2
    exit 1
  fi
fi

check_pm2_apps_online() {
  for attempt in $(seq 1 20); do
    pm2 jlist >/tmp/tradamind_rollback_pm2_jlist.json
    if EXPECTED_PM2_APPS="$EXPECTED_PM2_APPS" python3 - <<'PY'
import json
import os
import sys

expected = os.environ.get("EXPECTED_PM2_APPS", "").split()
with open("/tmp/tradamind_rollback_pm2_jlist.json", "r", encoding="utf-8") as handle:
    raw = handle.read()

json_payload = None
lines = raw.splitlines()
for index, line in enumerate(lines):
    stripped = line.lstrip()
    if stripped == "[" or stripped.startswith("[{"):
        json_payload = "\n".join(lines[index:])
        break

if not json_payload:
    print("❌ Rollback PM2 gate failed: jlist JSON payload not found", file=sys.stderr)
    sys.exit(1)

processes = json.loads(json_payload)
by_name = {process.get("name"): process for process in processes}
missing = [name for name in expected if name not in by_name]
not_online = {
    name: ((by_name.get(name) or {}).get("pm2_env") or {}).get("status")
    for name in expected
    if name in by_name and ((by_name.get(name) or {}).get("pm2_env") or {}).get("status") != "online"
}

if missing or not_online:
    print(
        "❌ Rollback PM2 gate failed: missing={} not_online={}".format(missing, not_online),
        file=sys.stderr,
    )
    sys.exit(1)

print("✅ Rollback PM2 gate passed: all expected apps online.")
PY
    then
      return 0
    fi
    echo "⏳ Waiting for rollback PM2 apps to settle (attempt $attempt/20)..." >&2
    sleep 3
  done
  return 1
}

pm2 startOrReload "$PM2_CONFIG" --update-env
check_pm2_apps_online
pm2 save --force

curl --max-time 10 -fsS -H 'Host: 127.0.0.1' "http://127.0.0.1:${BACKEND_PORT}/api/health"
echo
curl --max-time 45 -fsS -H 'Host: 127.0.0.1' "http://127.0.0.1:${BACKEND_PORT}/api/system/health" >/tmp/tradamind_rollback_deep_health.json
cat /tmp/tradamind_rollback_deep_health.json
echo
curl --max-time 10 -fsSI "http://127.0.0.1:${FRONTEND_PORT}/report" | head -n 1

mkdir -p "$DEPLOY_STATE_DIR"
printf "%s\n" "$ROLLBACK_COMMIT" > "${DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT"
if [ -n "$CURRENT_COMMIT" ]; then
  printf "%s\n" "$CURRENT_COMMIT" > "${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT"
fi
if [ -d /var/www/tradamind/ops/deploy ]; then
  printf "%s\n" "$ROLLBACK_COMMIT" | sudo tee /var/www/tradamind/ops/deploy/LAST_GOOD_COMMIT >/dev/null
  if [ -n "$CURRENT_COMMIT" ]; then
    printf "%s\n" "$CURRENT_COMMIT" | sudo tee /var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT >/dev/null
  fi
fi

echo "✅ ${ENVIRONMENT} rollback complete for ${ROLLBACK_COMMIT}."
