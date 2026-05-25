#!/bin/bash
set -euo pipefail

# ==========================================
# ↩️ TRADAMIND PRODUCTION ROLLBACK HELPER
# ==========================================
# Usage:
#   ./rollback_live.sh <commit>
# If no commit is provided, the helper uses ops/deploy/LAST_GOOD_COMMIT.

REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/antigravity-trading-tool}"
NODE_BIN="${NODE_BIN:-/home/ubuntu/.nvm/versions/node/v18.20.8/bin}"
ROLLBACK_COMMIT="${1:-}"
EXPECTED_PM2_APPS="${EXPECTED_PM2_APPS:-frontend backend celery-worker-default celery-worker-market-portfolio celery-worker-scoring-execution celery-worker-ai-reporting celery-beat}"

export PATH="$NODE_BIN:$PATH"
cd "$REMOTE_DIR"

if [ -z "$ROLLBACK_COMMIT" ]; then
  if [ ! -f ops/deploy/LAST_GOOD_COMMIT ]; then
    echo "❌ No rollback commit provided and ops/deploy/LAST_GOOD_COMMIT is missing." >&2
    exit 1
  fi
  ROLLBACK_COMMIT="$(cat ops/deploy/LAST_GOOD_COMMIT)"
fi

echo "↩️ Rolling Tradamind back to ${ROLLBACK_COMMIT}..."
git fetch origin main
git reset --hard "$ROLLBACK_COMMIT"

check_pm2_apps_online() {
  for attempt in $(seq 1 12); do
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
    echo "⏳ Waiting for rollback PM2 apps to settle (attempt $attempt/12)..." >&2
    sleep 2
  done
  return 1
}

pm2 startOrReload ecosystem.config.js --update-env
check_pm2_apps_online
pm2 save --force

curl --max-time 10 -fsS http://127.0.0.1:8000/api/health
echo
curl --max-time 30 -fsS http://127.0.0.1:8000/api/system/health >/tmp/tradamind_rollback_deep_health.json
cat /tmp/tradamind_rollback_deep_health.json
echo
curl --max-time 10 -fsSI http://127.0.0.1:5002/report | head -n 1

mkdir -p ops/deploy
printf "%s\n" "$ROLLBACK_COMMIT" > ops/deploy/LAST_GOOD_COMMIT

echo "✅ Rollback complete for ${ROLLBACK_COMMIT}."
